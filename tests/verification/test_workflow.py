"""Cover failures that otherwise look like completed execution or verification."""

import difflib
import hashlib
import json
from pathlib import Path

import pytest

from seam.demo import create_demo
from seam.exceptions import RunnerError
from seam.models import ExecutionResult, RunReport
from seam.models import TestCaseResult as Case
from seam.verification import workflow


def test_missing_repository_writes_inconclusive_report(tmp_path: Path) -> None:
    output = tmp_path / "evidence"
    report = workflow.run_backport(
        tmp_path / "missing",
        "fix",
        "target",
        tmp_path / "missing.toml",
        output,
        direct=True,
    )
    saved = RunReport.model_validate_json((output / "report.json").read_bytes())
    assert saved == report
    assert saved.schema_version == 2
    assert saved.status == "inconclusive"
    assert saved.fix_commit is None
    assert saved.image_id is None
    assert saved.phases == []
    assert "missing" in saved.reason
    assert not (output / "backport.patch").exists()


def test_invalid_config_reports_validation_without_echoing_values(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source"
    source.mkdir()
    config = tmp_path / "invalid.toml"
    config.write_text('secret = "private-config-value"\n')
    output = tmp_path / "evidence"
    report = workflow.run_backport(source, "fix", "target", config, output, direct=True)
    assert report.status == "inconclusive"
    assert "oracle" in report.reason and "runner" in report.reason
    assert "private-config-value" not in (output / "report.json").read_text()
    assert "private-config-value" not in (output / "report.md").read_text()
    assert not (output / "verification.py").exists()


def test_real_git_rejection_retains_report_and_frozen_input(tmp_path: Path) -> None:
    project = create_demo(tmp_path / "project")
    initial = workflow.repository.git(
        project.repo, "rev-list", "--max-parents=0", "HEAD"
    ).strip()
    output = tmp_path / "evidence"
    report = workflow.run_backport(
        project.repo, initial, project.target, project.config_path, output, direct=True
    )
    assert report.status == "inconclusive"
    assert "one ordinary commit" in report.reason
    assert report.fix_commit == initial
    assert report.parent_commit is None
    assert report.phases == []
    assert (output / "verification.py").read_bytes() == (
        project.config_path.parent / "oracle.py"
    ).read_bytes()


def test_image_setup_failure_retains_preflighted_provenance(
    tmp_path: Path, monkeypatch
) -> None:
    project = create_demo(tmp_path / "project")

    class BrokenRunner:
        def __init__(self, _config) -> None:
            pass

        def resolve_image(self) -> str:
            raise RunnerError("Could not prepare Docker image: fixture unavailable")

    monkeypatch.setattr(workflow, "DockerRunner", BrokenRunner)
    output = tmp_path / "evidence"
    report = workflow.run_backport(
        project.repo,
        project.fix,
        project.target,
        project.config_path,
        output,
        direct=True,
    )
    assert report.status == "inconclusive"
    assert "fixture unavailable" in report.reason
    assert report.fix_commit and report.parent_commit and report.target_commit
    assert report.image_id is None
    assert report.phases == []


def test_all_revisions_preflight_before_image_preparation(
    tmp_path: Path, monkeypatch
) -> None:
    project = create_demo(tmp_path / "project")
    checked = []

    def preflight(path: Path, *, reviewed_fixtures) -> None:
        assert reviewed_fixtures == {}
        checked.append(path.name)
        if path.name == "target_baseline":
            raise ValueError("unsupported symlink: docs/broken-link")

    def forbidden_image(_runner):
        pytest.fail("Image preparation must wait for every revision's preflight")

    monkeypatch.setattr(workflow, "preflight_snapshot", preflight)
    monkeypatch.setattr(workflow.DockerRunner, "resolve_image", forbidden_image)
    report = workflow.run_backport(
        project.repo,
        project.fix,
        project.target,
        project.config_path,
        tmp_path / "evidence",
        direct=True,
    )
    assert checked == ["upstream_parent", "upstream_fix", "target_baseline"]
    assert report.status == "inconclusive"
    assert "target_baseline snapshot" in report.reason
    assert "docs/broken-link" in report.reason
    assert report.phases == []


def test_output_safety_rejection_writes_nothing(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    with pytest.raises(ValueError, match="outside"):
        workflow.run_backport(
            source, "fix", "target", tmp_path / "none", source, direct=True
        )
    assert list(source.iterdir()) == []
    output = tmp_path / "evidence"
    output.mkdir()
    (output / "keep.txt").write_text("existing evidence")
    with pytest.raises(ValueError, match="new or empty"):
        workflow.run_backport(
            source, "fix", "target", tmp_path / "none", output, direct=True
        )
    assert sorted(path.name for path in output.iterdir()) == ["keep.txt"]
    assert (output / "keep.txt").read_text() == "existing evidence"


@pytest.mark.parametrize("reviewed_submodules", [False, True])
def test_backport_cannot_drop_previously_collected_suite_tests(
    tmp_path: Path,
    monkeypatch,
    reviewed_submodules: bool,
) -> None:
    repo = tmp_path / "source"
    repo.mkdir()
    oracle = tmp_path / "oracle.py"
    oracle.write_text("# trusted regression fixture\n")
    config = tmp_path / "run.toml"
    config.write_text(
        """[oracle]
path = "oracle.py"
security_test = "test_security"
controls = ["test_control"]
failure_marker = "SECURITY_REGRESSION"
[runner]
image = "test-image"
"""
    )
    modules = {"test/cache-fixtures": ("c" * 40,)} if reviewed_submodules else {}
    if modules:
        config.write_text(
            config.read_text()
            + "\n[runner.reviewed_submodules]\n"
            + f'"test/cache-fixtures" = ["{"c" * 40}"]\n'
        )
    revisions = {"fix": "f" * 40, "target": "b" * 40}
    monkeypatch.setattr(
        workflow.repository, "resolve", lambda _repo, ref: revisions[ref]
    )
    monkeypatch.setattr(workflow.repository, "parent", lambda *_: "a" * 40)
    monkeypatch.setattr(
        workflow.repository, "upstream_patch", lambda *_: "source patch"
    )
    cloned = []

    def clone(_repo, _revision, destination, *, reviewed_submodules=None):
        assert reviewed_submodules == (modules or None)
        cloned.append(destination.name)
        destination.mkdir()

    monkeypatch.setattr(workflow.repository, "clone_at", clone)
    monkeypatch.setattr(
        workflow.repository, "apply_patch", lambda _workspace, patch, _language: patch
    )

    class Runner:
        def __init__(self, _config) -> None:
            pass

        def resolve_image(self) -> str:
            return "sha256:" + "a" * 64

        def run(self, workspace, _oracle, _image, kind) -> ExecutionResult:
            if kind == "suite":
                names = ["test_existing"]
                if not workspace.name.startswith("candidate-"):
                    names.append("test_previously_collected")
                return ExecutionResult(
                    returncode=0,
                    tests=[Case(name=name, outcome="passed") for name in names],
                )
            vulnerable = workspace.name in {"upstream_parent", "target_baseline"}
            return ExecutionResult(
                returncode=1 if vulnerable else 0,
                tests=[
                    Case(
                        name="test_security",
                        outcome="failed" if vulnerable else "passed",
                        message="AssertionError: SECURITY_REGRESSION"
                        if vulnerable
                        else "",
                    ),
                    Case(name="test_control", outcome="passed"),
                ],
            )

    monkeypatch.setattr(workflow, "DockerRunner", Runner)
    report = workflow.run_backport(
        repo, "fix", "target", config, tmp_path / "output", direct=True
    )
    assert report.status == "inconclusive"
    assert "collect" in report.reason.lower() or "missing" in report.reason.lower()
    assert cloned == [
        "upstream_parent",
        "upstream_fix",
        "target_baseline",
        "candidate-1",
    ]
    assert report.reviewed_submodules == modules


@pytest.mark.parametrize("invalid_review", [None, "hash", "body"])
def test_reviewed_assertions_are_frozen_and_exported_without_changing_baselines(
    tmp_path: Path, monkeypatch, invalid_review: str | None
) -> None:
    project = create_demo(tmp_path / "project")
    test_name = "tests/test_paths.py"
    before = (project.repo / test_name).read_text()
    after = before.replace(
        '== tmp_path / "docs/readme.txt"',
        '== Path(tmp_path, "docs/readme.txt")',
    )
    if invalid_review == "body":
        after = after.replace("def test_nested_member", "def test_removed_member")
    review = "".join(
        difflib.unified_diff(
            before.splitlines(keepends=True),
            after.splitlines(keepends=True),
            fromfile=f"a/{test_name}",
            tofile=f"b/{test_name}",
        )
    )
    review_path = project.config_path.parent / "reviewed.patch"
    review_path.write_text(review)
    digest = hashlib.sha256(review.encode()).hexdigest()
    project.config_path.write_text(
        project.config_path.read_text()
        + '\n[reviewed_tests]\npath = "reviewed.patch"\n'
        + f'sha256 = "{"0" * 64 if invalid_review == "hash" else digest}"\n'
        + 'reason = "Reviewed assertion compatibility change"\n'
    )
    checked = []

    class Runner:
        def __init__(self, _config) -> None:
            pass

        def resolve_image(self) -> str:
            assert invalid_review is None, "Invalid review must stop before Docker"
            # The selected input can change after freezing without changing the run.
            review_path.write_text("changed operator input after freezing\n")
            return "sha256:" + "a" * 64

        def run(self, workspace, _oracle, _image, kind) -> ExecutionResult:
            candidate = workspace.name.startswith("candidate-")
            assert (workspace / test_name).read_text() == (
                after if candidate else before
            )
            checked.append((workspace.name, kind))
            if kind == "suite":
                return ExecutionResult(
                    returncode=0,
                    tests=[Case(name="test_existing", outcome="passed")],
                )
            vulnerable = workspace.name in {"upstream_parent", "target_baseline"}
            return ExecutionResult(
                returncode=1 if vulnerable else 0,
                tests=[
                    Case(
                        name="test_security_traversal",
                        outcome="failed" if vulnerable else "passed",
                        message="AssertionError: TRAVERSAL_SECURITY_ORACLE"
                        if vulnerable
                        else "",
                    ),
                    *[
                        Case(name=name, outcome="passed")
                        for name in (
                            "test_control_nested_path",
                            "test_control_repeated_dots",
                            "test_control_unicode_filename",
                        )
                    ],
                ],
            )

    monkeypatch.setattr(workflow, "DockerRunner", Runner)
    output = tmp_path / "evidence"
    report = workflow.run_backport(
        project.repo,
        project.fix,
        project.target,
        project.config_path,
        output,
        candidate_patch=project.candidate_patch,
    )
    assert not workflow.repository.git(project.repo, "status", "--porcelain")
    if invalid_review:
        assert report.status == "inconclusive"
        assert report.image_id is None
        assert checked == []
        assert not (output / "backport.patch").exists()
        expected_reason = "SHA-256" if invalid_review == "hash" else "assertion"
        assert expected_reason in report.reason
        return
    assert report.status == "verified"
    assert len(checked) == 8
    assert (output / "reviewed-tests.patch").read_text() == review
    assert report.reviewed_tests is not None
    assert report.reviewed_tests.path == Path("reviewed-tests.patch")
    assert report.reviewed_tests.sha256 == digest
    frozen_config = json.loads((output / "config.json").read_text())
    assert frozen_config["reviewed_tests"]["sha256"] == digest
    canonical = (output / "backport.patch").read_text()
    assert report.patch_sha256 == hashlib.sha256(canonical.encode()).hexdigest()
    assert test_name in canonical and "src/parcel_paths/legacy.py" in canonical
    assert test_name not in (output / "implementation.patch").read_text()
    exported = tmp_path / "exported"
    workflow.repository.clone_at(project.repo, report.target_commit, exported)
    workflow.repository.git(exported, "apply", "-", input_text=canonical)
    assert (exported / test_name).read_text() == after
    assert (
        "Reviewed assertion compatibility change" in (output / "report.md").read_text()
    )
