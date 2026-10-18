"""Require executed, repeatable evidence before a public case is qualified."""

import hashlib
import json
import shutil
from pathlib import Path

import pytest

from seam.evals import qualification
from seam.evals.catalogue import load_case
from seam.models import ExecutionResult, PhaseResult, RunReport
from seam.models import TestCaseResult as CaseResult
from seam.verification.config import load_config

SOURCE_CASE = Path(__file__).resolve().parents[2] / "evals/python/cases/h11"
IMAGE_ID = "sha256:" + "d" * 64


def report_for(dataset: Path, *, negative: bool, repeat: bool = False) -> RunReport:
    case, directory = load_case(dataset, "h11")
    config = load_config(directory / "harness.toml")
    if repeat or negative:
        config.runner.image = IMAGE_ID
    phases = []
    for name, revision in (
        ("upstream_parent", case.upstream_parent_commit),
        ("upstream_fix", case.upstream_fix_commit),
        ("target_baseline", case.base_commit),
        ("backport", case.base_commit),
    ):
        vulnerable = name in {"upstream_parent", "target_baseline"} or (
            negative and name == "backport"
        )
        phases.append(
            PhaseResult(
                name=name,
                revision=revision,
                security=ExecutionResult(
                    returncode=1 if vulnerable else 0,
                    tests=[
                        CaseResult(
                            name=config.oracle.security_test,
                            outcome="failed" if vulnerable else "passed",
                            message=f"AssertionError: {config.oracle.failure_marker}"
                            if vulnerable
                            else "",
                        ),
                        *[
                            CaseResult(name=name, outcome="passed")
                            for name in config.oracle.controls
                        ],
                    ],
                ),
                suite=ExecutionResult(
                    returncode=0,
                    tests=[
                        CaseResult(classname="tests.io", name=name, outcome="passed")
                        for name in ("test_existing_a", "test_existing_b")
                    ],
                ),
            )
        )
    return RunReport(
        status="failed" if negative else "verified",
        reason="intended regression reproduced" if negative else "checks passed",
        fix_commit=case.upstream_fix_commit,
        parent_commit=case.upstream_parent_commit,
        target_commit=case.base_commit,
        image_id=IMAGE_ID,
        oracle_sha256=case.asset_sha256["oracle.py"],
        config_sha256=hashlib.sha256(
            (config.model_dump_json(indent=2) + "\n").encode()
        ).hexdigest(),
        patch_sha256=None
        if negative
        else hashlib.sha256((directory / "reference.patch").read_bytes()).hexdigest(),
        phases=phases,
        attempts=1,
        adaptation="provided_patch",
    )


@pytest.fixture
def replay(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict:
    dataset = tmp_path / "dataset"
    directory = dataset / "cases/h11"
    shutil.copytree(SOURCE_CASE, directory)
    metadata = json.loads((directory / "case.json").read_text())
    metadata["expected_suite_cases"] = 2
    (directory / "case.json").write_text(json.dumps(metadata))
    reports = [
        report_for(dataset, negative=False),
        report_for(dataset, negative=False, repeat=True),
        report_for(dataset, negative=True),
    ]
    calls = []
    applications = []
    manifest_changes = {}
    artifact_changes = {}

    def run_case(dataset: Path, instance_id: str, output: Path, **kwargs) -> RunReport:
        index = len(calls)
        calls.append(kwargs)
        evidence = output / "evidence"
        evidence.mkdir(parents=True)
        config = load_config(directory / "harness.toml")
        if kwargs.get("image") is not None:
            config.runner.image = kwargs["image"]
        (evidence / "config.json").write_text(config.model_dump_json(indent=2) + "\n")
        if kwargs.get("mode") == "candidate":
            supplied = kwargs["candidate_patch"].read_text()
            assert (
                "Negative control: implementation intentionally unchanged" in supplied
            )
            (evidence / "attempt-1.patch").write_text(supplied)
        else:
            (evidence / "backport.patch").write_bytes(
                (directory / "reference.patch").read_bytes()
            )
            if index == 0 and "exported_patch" in artifact_changes:
                (evidence / "backport.patch").write_text(
                    artifact_changes["exported_patch"]
                )
        report_path = evidence / "report.json"
        report_path.write_text(reports[index].model_dump_json())
        manifest = {
            "case_sha256": hashlib.sha256(
                (directory / "case.json").read_bytes()
            ).hexdigest(),
            "asset_sha256": metadata["asset_sha256"],
            "harness_source_sha256": "e" * 64,
            "harness_version": "0.3.0",
            "harness_distribution": {"archive_sha256": "f" * 64},
            "image_id": reports[index].image_id,
            "base_image_manifest_digests": ["sha256:" + "a" * 64],
            "repo": metadata["repo"],
            "base_commit": metadata["base_commit"],
            "upstream_parent_commit": metadata["upstream_parent_commit"],
            "upstream_fix_commit": metadata["upstream_fix_commit"],
            "report_sha256": hashlib.sha256(report_path.read_bytes()).hexdigest(),
        }
        manifest.update(manifest_changes.get(index, {}))
        (output / "run-manifest.json").write_text(json.dumps(manifest))
        return reports[index]

    def git(source: Path, *arguments: str, **kwargs) -> str:
        if arguments[0] == "ls-tree":
            return "100644 blob " + "a" * 40 + "\th11/_readers.py\n"
        if arguments[0] == "show":
            return "def parse_chunk():\n    pass\n"
        assert arguments[0] == "apply"
        applications.append((arguments, kwargs["input_text"]))
        return ""

    def clone_at(source: Path, revision: str, output: Path) -> None:
        assert revision == metadata["base_commit"]
        output.mkdir(parents=True)

    monkeypatch.setattr(qualification, "run_case", run_case)
    monkeypatch.setattr(qualification.repository, "git", git)
    monkeypatch.setattr(qualification.repository, "clone_at", clone_at)
    monkeypatch.setattr(
        qualification.repository, "validate_patch", lambda *args: ["h11/_readers.py"]
    )
    return {
        "dataset": dataset,
        "output": tmp_path / "qualification",
        "reports": reports,
        "calls": calls,
        "applications": applications,
        "manifest_changes": manifest_changes,
        "artifact_changes": artifact_changes,
    }


def test_qualification_requires_repeat_and_executed_unchanged_negative(
    replay: dict,
) -> None:
    summary = qualification.qualify_case(
        replay["dataset"], "h11", replay["output"], build_image=True
    )
    assert summary["qualified"] is True, summary
    assert summary["negative_intended_failure"] is True
    assert summary["ordinary_git_apply"] is True
    assert summary["target_suite_cases"] == 2
    assert len(replay["calls"]) == 3
    assert replay["calls"][0]["mode"] == "reference"
    assert replay["calls"][1]["mode"] == "reference"
    assert replay["calls"][0]["build_image"] is True
    assert replay["calls"][1]["image"] == IMAGE_ID
    assert replay["calls"][2]["image"] == IMAGE_ID
    assert replay["calls"][2]["mode"] == "candidate"
    assert [args for args, _ in replay["applications"]] == [
        ("apply", "--check", "-"),
        ("apply", "-"),
    ]
    saved = json.loads((replay["output"] / "qualification.json").read_text())
    assert saved == summary


@pytest.mark.parametrize("index", [0, 1])
@pytest.mark.parametrize(
    "change", ["failed_control", "missing_control", "missing_phase"]
)
def test_reference_headline_cannot_hide_bad_or_missing_checks(
    replay: dict, index: int, change: str
) -> None:
    report = replay["reports"][index]
    if change == "failed_control":
        report.phases[-1].security.tests[-1].outcome = "failed"
    elif change == "missing_control":
        for phase in report.phases:
            phase.security.tests.pop()
    else:
        report.phases.pop()
    result = qualification.qualify_case(replay["dataset"], "h11", replay["output"])
    assert result["qualified"] is False, result


@pytest.mark.parametrize(
    "field,value",
    [
        ("image_id", "sha256:" + "e" * 64),
        ("oracle_sha256", "a" * 64),
        ("config_sha256", "b" * 64),
        ("patch_sha256", "c" * 64),
        ("fix_commit", "a" * 40),
        ("parent_commit", "b" * 40),
        ("target_commit", "c" * 40),
    ],
)
def test_reference_repeat_rejects_provenance_or_hash_drift(
    replay: dict, field: str, value: str
) -> None:
    setattr(replay["reports"][1], field, value)
    result = qualification.qualify_case(replay["dataset"], "h11", replay["output"])
    assert result["qualified"] is False, result


def test_reference_repeat_rejects_changed_suite_identity(replay: dict) -> None:
    for phase in replay["reports"][1].phases:
        phase.suite.tests[0].name = "test_replacement"
    result = qualification.qualify_case(replay["dataset"], "h11", replay["output"])
    assert result["qualified"] is False, result


def test_matching_reference_replays_still_require_the_published_suite_count(
    replay: dict,
) -> None:
    for report in replay["reports"][:2]:
        for phase in report.phases:
            phase.suite.tests.pop()
    result = qualification.qualify_case(replay["dataset"], "h11", replay["output"])
    assert result["qualified"] is False, result


def test_exported_patch_must_be_the_patch_that_verified(replay: dict) -> None:
    patch = SOURCE_CASE.joinpath("reference.patch").read_text()
    replay["artifact_changes"]["exported_patch"] = patch.replace(
        'self._bytes_to_discard = b"\\r\\n"', 'self._bytes_to_discard = b"__"'
    )
    assert replay["artifact_changes"]["exported_patch"] != patch
    result = qualification.qualify_case(replay["dataset"], "h11", replay["output"])
    assert result["qualified"] is False, result


@pytest.mark.parametrize(
    "field,value",
    [
        ("case_sha256", "b" * 64),
        ("harness_source_sha256", "c" * 64),
        ("harness_version", "another-version"),
        ("harness_distribution", {"archive_sha256": "a" * 64}),
        ("asset_sha256", {}),
        ("base_image_manifest_digests", ["sha256:" + "b" * 64]),
    ],
)
def test_qualification_rejects_manifest_input_drift(
    replay: dict, field: str, value: object
) -> None:
    replay["manifest_changes"][1] = {field: value}
    result = qualification.qualify_case(replay["dataset"], "h11", replay["output"])
    assert result["qualified"] is False, result


@pytest.mark.parametrize("change", ["oracle_and_metadata", "metadata_bytes"])
def test_qualification_rejects_case_drift_after_all_replays(
    replay: dict, monkeypatch: pytest.MonkeyPatch, change: str
) -> None:
    clone_at = qualification.repository.clone_at

    def change_case_during_export_check(
        source: Path, revision: str, output: Path
    ) -> None:
        clone_at(source, revision, output)
        directory = replay["dataset"] / "cases/h11"
        metadata_path = directory / "case.json"
        if change == "metadata_bytes":
            metadata_path.write_bytes(metadata_path.read_bytes() + b"\n")
        else:
            oracle = directory / "oracle.py"
            oracle.write_bytes(
                oracle.read_bytes() + b"\nraise RuntimeError('changed after replays')\n"
            )
            metadata = json.loads(metadata_path.read_text())
            metadata["asset_sha256"]["oracle.py"] = hashlib.sha256(
                oracle.read_bytes()
            ).hexdigest()
            metadata_path.write_text(json.dumps(metadata))

    monkeypatch.setattr(
        qualification.repository, "clone_at", change_case_during_export_check
    )
    result = qualification.qualify_case(replay["dataset"], "h11", replay["output"])
    assert len(replay["calls"]) == 3
    assert result["qualified"] is False, result


@pytest.mark.parametrize(
    "change",
    [
        "not_applied",
        "missing_phase",
        "missing_control",
        "failed_control",
        "wrong_assertion",
        "green_exit",
        "timed_out",
        "missing_suite",
        "baseline_missing_checks",
    ],
)
def test_negative_requires_applied_candidate_and_complete_intended_failure(
    replay: dict, change: str
) -> None:
    negative = replay["reports"][2]
    if change == "not_applied":
        negative.adaptation = "none"
        negative.attempts = 0
    elif change == "missing_phase":
        negative.phases.pop(0)
    elif change == "missing_control":
        negative.phases[-1].security.tests.pop()
    elif change == "failed_control":
        negative.phases[-1].security.tests[-1].outcome = "failed"
    elif change == "wrong_assertion":
        negative.phases[-1].security.tests[0].message = "AssertionError: unrelated"
    elif change == "green_exit":
        negative.phases[-1].security.returncode = 0
    elif change == "timed_out":
        negative.phases[-1].security.timed_out = True
    elif change == "missing_suite":
        negative.phases[-1].suite.tests.clear()
    else:
        negative.phases[0].security.tests.clear()
    result = qualification.qualify_case(replay["dataset"], "h11", replay["output"])
    assert result["qualified"] is False, result


def test_negative_may_fail_reviewed_policy_assertions_with_complete_suite_evidence(
    replay: dict,
) -> None:
    suite = replay["reports"][2].phases[-1].suite
    suite.returncode = 1
    suite.tests[0].outcome = "failed"
    result = qualification.qualify_case(replay["dataset"], "h11", replay["output"])
    assert result["qualified"] is True, result


def test_setup_failure_is_recorded_without_attempting_a_negative(replay: dict) -> None:
    replay["reports"][0] = RunReport(
        status="inconclusive", reason="source acquisition failed"
    )
    result = qualification.qualify_case(replay["dataset"], "h11", replay["output"])
    assert result["qualified"] is False
    assert len(replay["calls"]) == 1
    assert (replay["output"] / "qualification.json").is_file()


def test_qualification_preserves_existing_output(replay: dict) -> None:
    output = replay["output"]
    output.mkdir()
    marker = output / "keep.txt"
    marker.write_text("existing evidence")
    with pytest.raises(ValueError, match="new or empty"):
        qualification.qualify_case(replay["dataset"], "h11", output)
    assert marker.read_text() == "existing evidence"
    assert replay["calls"] == []
