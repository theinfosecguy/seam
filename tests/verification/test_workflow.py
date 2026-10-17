"""Cover failures that otherwise look like completed execution or verification."""

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
        tmp_path / "missing", "fix", "target", tmp_path / "missing.toml", output
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
    report = workflow.run_backport(source, "fix", "target", config, output)
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
        project.repo, initial, project.target, project.config_path, output
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
        project.repo, project.fix, project.target, project.config_path, output
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

    def preflight(path: Path) -> None:
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
        workflow.run_backport(source, "fix", "target", tmp_path / "none", source)
    assert list(source.iterdir()) == []
    output = tmp_path / "evidence"
    output.mkdir()
    (output / "keep.txt").write_text("existing evidence")
    with pytest.raises(ValueError, match="new or empty"):
        workflow.run_backport(source, "fix", "target", tmp_path / "none", output)
    assert sorted(path.name for path in output.iterdir()) == ["keep.txt"]
    assert (output / "keep.txt").read_text() == "existing evidence"


def test_backport_cannot_drop_previously_collected_suite_tests(
    tmp_path: Path, monkeypatch
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
    revisions = {"fix": "f" * 40, "target": "b" * 40}
    monkeypatch.setattr(
        workflow.repository, "resolve", lambda _repo, ref: revisions[ref]
    )
    monkeypatch.setattr(workflow.repository, "parent", lambda *_: "a" * 40)
    monkeypatch.setattr(
        workflow.repository, "upstream_patch", lambda *_: "source patch"
    )
    monkeypatch.setattr(
        workflow.repository, "clone_at", lambda _r, _c, dst: dst.mkdir()
    )
    monkeypatch.setattr(
        workflow.repository, "apply_patch", lambda _workspace, patch: patch
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
    report = workflow.run_backport(repo, "fix", "target", config, tmp_path / "output")
    assert report.status == "inconclusive"
    assert "collect" in report.reason.lower() or "missing" in report.reason.lower()
