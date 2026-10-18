"""Keep replay inputs, image overrides and publication provenance consistent."""

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from seam.demo import create_demo
from seam.evals import runner
from seam.evals.catalogue import load_case
from seam.evals.models import EvalCase
from seam.exceptions import RepositoryError
from seam.models import (
    ExecutionResult,
    PhaseResult,
    ProcessResult,
    RunnerConfig,
    RunReport,
)
from seam.models import (
    TestCaseResult as CaseResult,
)
from seam.verification import workflow

DATASET = Path(__file__).resolve().parents[2] / "evals/python"
IMAGE_ID = "sha256:" + "a" * 64


def passing_report(case: EvalCase) -> RunReport:
    phases = []
    for name, revision in (
        ("upstream_parent", case.upstream_parent_commit),
        ("upstream_fix", case.upstream_fix_commit),
        ("target_baseline", case.base_commit),
        ("backport", case.base_commit),
    ):
        vulnerable = name in {"upstream_parent", "target_baseline"}
        security = ExecutionResult(
            returncode=1 if vulnerable else 0,
            tests=[
                CaseResult(
                    name="test_security",
                    outcome="failed" if vulnerable else "passed",
                    message="AssertionError: expected regression" if vulnerable else "",
                ),
                CaseResult(name="test_control", outcome="passed"),
            ],
        )
        phases.append(
            PhaseResult(
                name=name,
                revision=revision,
                security=security,
                suite=ExecutionResult(
                    returncode=0,
                    tests=[
                        CaseResult(name=f"test_{index}", outcome="passed")
                        for index in range(case.expected_suite_cases)
                    ],
                ),
            )
        )
    return RunReport(
        status="verified",
        reason="all recorded checks passed",
        fix_commit=case.upstream_fix_commit,
        parent_commit=case.upstream_parent_commit,
        target_commit=case.base_commit,
        image_id=IMAGE_ID,
        oracle_sha256="b" * 64,
        config_sha256="c" * 64,
        patch_sha256="d" * 64,
        phases=phases,
    )


@pytest.fixture
def executor(monkeypatch: pytest.MonkeyPatch) -> dict[str, object]:
    case, _ = load_case(DATASET, "h11")
    state: dict[str, object] = {"builds": [], "git": [], "workflow": []}

    def build(command, **kwargs):
        state["builds"].append((command, kwargs))
        return ProcessResult(returncode=0, stdout="image built")

    def git(path, *arguments, **kwargs):
        state["git"].append((path, arguments))
        Path(arguments[-1]).mkdir()
        return ""

    def verify(repo, fix, target, config_path, output, **kwargs):
        state["workflow"].append((repo, fix, target, config_path, kwargs))
        report = passing_report(case)
        output.mkdir()
        (output / "report.json").write_text(report.model_dump_json())
        return report

    monkeypatch.setattr(runner, "run_process", build)
    monkeypatch.setattr(runner.repository, "git", git)
    monkeypatch.setattr(runner.repository, "resolve", lambda _repo, ref: ref)
    monkeypatch.setattr(
        runner.repository, "parent", lambda _repo, _ref: case.upstream_parent_commit
    )
    monkeypatch.setattr(runner, "run_backport", verify)
    return state


@pytest.mark.parametrize("mode", ["reference", "direct", "candidate", "agent"])
def test_replay_propagates_native_config_and_records_provenance(
    tmp_path: Path, executor: dict[str, object], mode: str
) -> None:
    case, directory = load_case(DATASET, "h11")
    original = (directory / "harness.toml").read_bytes()
    candidate = tmp_path / "candidate.patch"
    candidate.write_text("explicit operator candidate\n")
    proposer = SimpleNamespace(usage={"api_calls": 3}) if mode == "agent" else None
    output = tmp_path / "run"
    report = runner.run_case(
        DATASET,
        "h11",
        output,
        docker=("sudo", "-n", "docker"),
        image=IMAGE_ID,
        mode=mode,
        candidate_patch=candidate if mode == "candidate" else None,
        proposer=proposer,
    )
    assert report.status == "verified"
    assert not executor["builds"]
    call = executor["workflow"][0]
    assert call[3] == directory / "harness.toml"
    assert call[4]["runner_config"].docker == ("sudo", "-n", "docker")
    assert call[4]["runner_config"].image == IMAGE_ID
    assert call[4]["candidate_patch"] == (
        directory / "reference.patch"
        if mode == "reference"
        else candidate
        if mode == "candidate"
        else None
    )
    assert call[4]["proposer"] is proposer
    assert call[4]["direct"] is (mode == "direct")
    assert original == (directory / "harness.toml").read_bytes()
    assert not (output / "harness.toml").exists()
    manifest = json.loads((output / "run-manifest.json").read_text())
    assert manifest["mode"] == mode
    assert manifest["image_reference"] == IMAGE_ID
    assert manifest["image_id"] == IMAGE_ID
    assert manifest["case_image_reference"] == "seam-eval-h11:python-v1"
    assert manifest["base_image_manifest_digests"][0].startswith("sha256:")
    assert (
        manifest["case_sha256"]
        == hashlib.sha256((directory / "case.json").read_bytes()).hexdigest()
    )
    assert manifest["asset_sha256"] == case.asset_sha256
    assert manifest["base_commit"] == case.base_commit
    assert (
        manifest["report_sha256"]
        == hashlib.sha256((output / "evidence/report.json").read_bytes()).hexdigest()
    )
    assert manifest["patch_sha256"] == report.patch_sha256
    assert len(manifest["harness_source_sha256"]) == 64
    assert manifest["model_usage"] == ({"api_calls": 3} if proposer else {})
    assert len(manifest["phases"]) == 4
    assert manifest["phases"][-1]["suite_cases"] == case.expected_suite_cases


def test_build_uses_public_recipe_and_preserves_case_config(
    tmp_path: Path, executor: dict[str, object]
) -> None:
    runner.run_case(
        DATASET, "h11", tmp_path / "run", mode="reference", build_image=True
    )
    command, options = executor["builds"][0]
    assert command[:4] == ["docker", "build", "--pull", "--no-cache"]
    assert command[command.index("--platform") + 1] == "linux/amd64"
    assert command[command.index("--tag") + 1] == "seam-eval-h11:python-v1"
    assert options["timeout"] > 0


@pytest.mark.parametrize(
    "options",
    [
        {},
        {"mode": "unknown"},
        {"mode": "candidate"},
        {"mode": "agent"},
        {"mode": "direct", "proposer": SimpleNamespace(usage={})},
        {"mode": "reference", "docker": ()},
        {"mode": "reference", "image": ""},
        {"mode": "reference", "image": IMAGE_ID, "build_image": True},
    ],
)
def test_invalid_inputs_fail_before_output_or_executor(
    tmp_path: Path, executor: dict[str, object], options: dict[str, object]
) -> None:
    output = tmp_path / "run"
    with pytest.raises(ValueError):
        runner.run_case(DATASET, "h11", output, **options)
    assert not output.exists()
    assert not any(executor.values())


def test_default_agent_mode_uses_explicit_proposer_without_a_reference_patch(
    tmp_path: Path, executor: dict[str, object]
) -> None:
    proposer = SimpleNamespace(usage={"api_calls": 1})
    output = tmp_path / "run"
    runner.run_case(DATASET, "h11", output, proposer=proposer)
    options = executor["workflow"][0][4]
    assert options["proposer"] is proposer
    assert options["candidate_patch"] is None
    assert options["direct"] is False
    assert json.loads((output / "run-manifest.json").read_text())["mode"] == "agent"


@pytest.mark.parametrize("content", [b"", b"\xff"])
def test_invalid_candidate_is_rejected_before_build(
    tmp_path: Path, executor: dict[str, object], content: bytes
) -> None:
    candidate = tmp_path / "candidate.patch"
    candidate.write_bytes(content)
    with pytest.raises(ValueError):
        runner.run_case(
            DATASET,
            "h11",
            tmp_path / "run",
            mode="candidate",
            candidate_patch=candidate,
            build_image=True,
        )
    assert not (tmp_path / "run").exists()
    assert not any(executor.values())


@pytest.mark.parametrize("failure", ["build", "clone"])
def test_setup_failure_keeps_inconclusive_manifest_without_report(
    tmp_path: Path,
    executor: dict[str, object],
    monkeypatch: pytest.MonkeyPatch,
    failure: str,
) -> None:
    if failure == "build":
        monkeypatch.setattr(
            runner,
            "run_process",
            lambda *args, **kwargs: ProcessResult(returncode=1, stderr="build failed"),
        )
    else:

        def failed_clone(*args, **kwargs):
            raise RepositoryError("clone failed")

        monkeypatch.setattr(runner.repository, "git", failed_clone)
    output = tmp_path / "run"
    report = runner.run_case(
        DATASET, "h11", output, mode="reference", build_image=failure == "build"
    )
    assert report.status == "inconclusive"
    manifest = json.loads((output / "run-manifest.json").read_text())
    assert manifest["status"] == "inconclusive"
    assert manifest["report_sha256"] is None
    assert manifest["phases"] == []
    assert not executor["workflow"]


def test_published_count_mismatch_updates_both_manifest_and_stored_report(
    tmp_path: Path, executor: dict[str, object], monkeypatch: pytest.MonkeyPatch
) -> None:
    verify = runner.run_backport

    def different_count(*args, **kwargs):
        report = verify(*args, **kwargs)
        report.phases[-1].suite.tests.pop()
        return report

    monkeypatch.setattr(runner, "run_backport", different_count)
    output = tmp_path / "run"
    report = runner.run_case(DATASET, "h11", output, mode="reference")
    assert report.status == "inconclusive"
    assert json.loads((output / "evidence/report.json").read_text())["status"] == (
        "inconclusive"
    )
    assert json.loads((output / "run-manifest.json").read_text())["status"] == (
        "inconclusive"
    )


def test_missing_case_fails_before_output_and_executor(
    tmp_path: Path, executor: dict[str, object]
) -> None:
    output = tmp_path / "run"
    with pytest.raises(OSError):
        runner.run_case(
            DATASET, "missing-case", output, mode="reference", build_image=True
        )
    assert not output.exists()
    assert not any(executor.values())


def test_package_hash_covers_resources_but_excludes_caches_and_dataset(
    tmp_path: Path,
) -> None:
    (tmp_path / "module.py").write_text("code")
    (tmp_path / "resource.txt").write_text("resource")
    original = runner._package_source_hash(tmp_path)
    for relative in ("__pycache__/module.pyc", "evals/data/python/case.json"):
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("changes independently")
    assert runner._package_source_hash(tmp_path) == original
    (tmp_path / "resource.txt").write_text("changed resource")
    assert runner._package_source_hash(tmp_path) != original


@pytest.mark.parametrize(
    ("record", "expected"),
    [
        (None, {}),
        ("malformed", {}),
        ("[]", {}),
        (json.dumps({"url": "file:///private/path"}), {}),
        (
            json.dumps(
                {
                    "url": "https://user:secret@example.test/private.whl",
                    "archive_info": {"hashes": {"sha256": "a" * 64}},
                }
            ),
            {"archive_sha256": "a" * 64},
        ),
        (
            json.dumps(
                {"url": "file:///private/source", "vcs_info": {"commit_id": "b" * 40}}
            ),
            {"vcs_commit": "b" * 40},
        ),
    ],
)
def test_distribution_provenance_keeps_only_immutable_ids(
    monkeypatch: pytest.MonkeyPatch, record: str | None, expected: dict[str, str]
) -> None:
    monkeypatch.setattr(
        runner,
        "distribution",
        lambda _name: SimpleNamespace(read_text=lambda _: record),
    )
    assert runner._distribution_provenance() == expected


def test_workflow_freezes_validated_runner_override(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = create_demo(tmp_path / "project")
    override = RunnerConfig(image=IMAGE_ID, docker=("explicit", "docker"))

    def stop_before_docker(_runner):
        raise ValueError("stop after configuration freeze")

    monkeypatch.setattr(workflow.DockerRunner, "resolve_image", stop_before_docker)
    output = tmp_path / "evidence"
    report = workflow.run_backport(
        project.repo,
        project.fix,
        project.target,
        project.config_path,
        output,
        direct=True,
        runner_config=override,
    )
    assert report.status == "inconclusive"
    frozen = json.loads((output / "config.json").read_text())
    assert frozen["runner"]["image"] == IMAGE_ID
    assert frozen["runner"]["docker"] == ["explicit", "docker"]
