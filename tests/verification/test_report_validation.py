"""Reject verified reports whose recorded executions contradict their verdict."""

import copy
import json
from pathlib import Path

import pytest
from pydantic import ValidationError
from typer.testing import CliRunner

from seam.cli import app
from seam.models import RunReport
from seam.verification.reporting import write_report


@pytest.fixture
def complete_report_data() -> dict:
    phases = []
    for name, revision in (
        ("upstream_parent", "b" * 40),
        ("upstream_fix", "a" * 40),
        ("target_baseline", "c" * 40),
        ("backport", "c" * 40),
    ):
        vulnerable = name in {"upstream_parent", "target_baseline"}
        phases.append(
            {
                "name": name,
                "revision": revision,
                "security": {
                    "returncode": 1 if vulnerable else 0,
                    "tests": [
                        {
                            "name": "test_security",
                            "outcome": "failed" if vulnerable else "passed",
                            "message": "AssertionError: SECURITY_REGRESSION"
                            if vulnerable
                            else "",
                        },
                        {"name": "test_control", "outcome": "passed"},
                    ],
                },
                "suite": {
                    "returncode": 0,
                    "tests": [
                        {
                            "classname": "first",
                            "name": "test_existing",
                            "outcome": "passed",
                        },
                        {
                            "classname": "second",
                            "name": "test_existing",
                            "outcome": "passed",
                        },
                    ],
                },
            }
        )
    return {
        "status": "verified",
        "reason": "recorded checks passed",
        "fix_commit": "a" * 40,
        "parent_commit": "b" * 40,
        "target_commit": "c" * 40,
        "image_id": "sha256:" + "d" * 64,
        "oracle_sha256": "e" * 64,
        "config_sha256": "f" * 64,
        "patch_sha256": "1" * 64,
        "phases": phases,
    }


@pytest.mark.parametrize("schema_version", [1, 2])
def test_complete_reports_preserve_failed_attempts_and_suite_order(
    tmp_path: Path, complete_report_data: dict, schema_version: int
) -> None:
    complete_report_data["schema_version"] = schema_version
    prior = copy.deepcopy(complete_report_data["phases"][-1])
    prior["suite"]["returncode"] = 1
    prior["suite"]["tests"][0]["outcome"] = "failed"
    complete_report_data["phases"].insert(-1, prior)
    complete_report_data["phases"][-1]["suite"]["tests"].reverse()
    report = RunReport.model_validate(complete_report_data)
    write_report(tmp_path, report)
    for flags in ([], ["--json"]):
        result = CliRunner().invoke(
            app, ["inspect", "--report", str(tmp_path / "report.json"), *flags]
        )
        assert result.exit_code == 0, result.output
        if flags:
            assert json.loads(result.output)["status"] == "verified"
        else:
            assert result.output.startswith("VERIFIED:")


@pytest.mark.parametrize("schema_version", [1, 2])
@pytest.mark.parametrize("phase_index", range(4))
@pytest.mark.parametrize("kind", ["security", "suite"])
@pytest.mark.parametrize(
    "change",
    [
        {"timed_out": True},
        {"truncated": True},
        {"evidence_error": "unreadable evidence"},
        {"tests": []},
        {"returncode": 2},
    ],
)
def test_inspect_rejects_verified_with_incomplete_execution(
    tmp_path: Path,
    complete_report_data: dict,
    schema_version: int,
    phase_index: int,
    kind: str,
    change: dict,
) -> None:
    complete_report_data["schema_version"] = schema_version
    complete_report_data["phases"][phase_index][kind].update(change)
    path = tmp_path / "edited.json"
    path.write_text(json.dumps(complete_report_data))
    for flags in ([], ["--json"]):
        result = CliRunner().invoke(app, ["inspect", "--report", str(path), *flags])
        assert result.exit_code == 2, result.output
        assert result.output.startswith("Invalid report:")
        assert "recorded checks passed" not in result.output


@pytest.mark.parametrize("phase_index", range(4))
@pytest.mark.parametrize("kind", ["security", "suite"])
@pytest.mark.parametrize("outcome", ["failed", "error", "skipped"])
def test_inspect_rejects_verified_with_unsuccessful_cases(
    tmp_path: Path,
    complete_report_data: dict,
    phase_index: int,
    kind: str,
    outcome: str,
) -> None:
    execution = complete_report_data["phases"][phase_index][kind]
    execution["tests"][-1]["outcome"] = outcome
    path = tmp_path / "edited.json"
    path.write_text(json.dumps(complete_report_data))
    result = CliRunner().invoke(app, ["inspect", "--report", str(path)])
    assert result.exit_code == 2, result.output
    assert result.output.startswith("Invalid report:")


@pytest.mark.parametrize(
    "change", ["remove", "rename", "classname", "duplicate", "empty_name"]
)
def test_verified_report_rejects_changed_or_ambiguous_suite_evidence(
    complete_report_data: dict,
    change: str,
) -> None:
    tests = complete_report_data["phases"][-1]["suite"]["tests"]
    if change == "remove":
        tests.pop()
    elif change == "rename":
        tests[0]["name"] = "test_replacement"
    elif change == "classname":
        tests[0]["classname"] = "another_class"
    elif change == "duplicate":
        tests.append(copy.deepcopy(tests[0]))
    else:
        tests[0]["name"] = ""
    with pytest.raises(ValidationError):
        RunReport.model_validate(complete_report_data)


@pytest.mark.parametrize("phase_index", [0, 2])
@pytest.mark.parametrize(
    "change", ["green_exit", "no_failure", "not_assertion", "no_control", "duplicate"]
)
def test_verified_report_requires_reproduced_security_assertions_and_controls(
    complete_report_data: dict,
    phase_index: int,
    change: str,
) -> None:
    security = complete_report_data["phases"][phase_index]["security"]
    if change == "green_exit":
        security["returncode"] = 0
    elif change == "no_failure":
        security["tests"][0]["outcome"] = "passed"
    elif change == "not_assertion":
        security["tests"][0]["message"] = "ModuleNotFoundError: missing dependency"
    elif change == "no_control":
        security["tests"].pop()
    else:
        security["tests"].append(copy.deepcopy(security["tests"][0]))
    with pytest.raises(ValidationError):
        RunReport.model_validate(complete_report_data)


@pytest.mark.parametrize(
    "change", ["missing_tests", "duplicate_baseline", "reorder", "wrong_revision"]
)
def test_verified_report_rejects_missing_or_inconsistent_matrix(
    complete_report_data: dict,
    change: str,
) -> None:
    phases = complete_report_data["phases"]
    if change == "missing_tests":
        del phases[-1]["security"]["tests"]
    elif change == "duplicate_baseline":
        phases.insert(0, copy.deepcopy(phases[0]))
    elif change == "reorder":
        phases[0], phases[1] = phases[1], phases[0]
    else:
        phases[-1]["revision"] = "f" * 40
    with pytest.raises(ValidationError):
        RunReport.model_validate(complete_report_data)


@pytest.mark.parametrize("kind", ["security", "suite"])
def test_mutated_nested_execution_cannot_be_written_as_verified(
    tmp_path: Path,
    complete_report_data: dict,
    kind: str,
) -> None:
    report = RunReport.model_validate(complete_report_data)
    getattr(report.phases[-1], kind).timed_out = True
    with pytest.raises(ValidationError):
        write_report(tmp_path, report)
    assert not (tmp_path / "report.json").exists()


@pytest.mark.parametrize("status", ["failed", "inconclusive"])
def test_unfinished_reports_remain_inspectable(tmp_path: Path, status: str) -> None:
    path = tmp_path / "partial.json"
    path.write_text(
        json.dumps({"status": status, "reason": "execution did not finish"})
    )
    result = CliRunner().invoke(app, ["inspect", "--report", str(path)])
    assert result.exit_code == 0, result.output
    assert result.output.startswith(status.upper() + ":")


@pytest.mark.parametrize(
    "phase_index,kind",
    [
        (0, "suite"),
        (1, "suite"),
        (2, "suite"),
        (3, "suite"),
        (1, "security"),
        (3, "security"),
    ],
)
def test_verified_report_rejects_nonzero_exit_with_passing_cases(
    complete_report_data: dict,
    phase_index: int,
    kind: str,
) -> None:
    complete_report_data["phases"][phase_index][kind]["returncode"] = 1
    with pytest.raises(ValidationError):
        RunReport.model_validate(complete_report_data)


@pytest.mark.parametrize("phase_index", range(4))
@pytest.mark.parametrize("case_index", [0, 1])
def test_verified_report_requires_the_same_regression_and_a_shared_control(
    complete_report_data: dict, phase_index: int, case_index: int
) -> None:
    complete_report_data["phases"][phase_index]["security"]["tests"][case_index][
        "name"
    ] = "test_unrelated"
    with pytest.raises(ValidationError):
        RunReport.model_validate(complete_report_data)


def test_additional_oracle_cases_can_differ_between_revisions(
    complete_report_data: dict,
) -> None:
    for index, phase in enumerate(complete_report_data["phases"]):
        phase["security"]["tests"].append(
            {"name": f"test_extra_{index}", "outcome": "passed"}
        )
    assert RunReport.model_validate(complete_report_data).status == "verified"


@pytest.mark.parametrize("calls", [None, 0, -1, 1.0, "1", True])
def test_verified_ai_report_requires_positive_integer_model_calls(
    complete_report_data: dict, calls: object
) -> None:
    complete_report_data["adaptation"] = "agent"
    complete_report_data["model_usage"] = {} if calls is None else {"calls": calls}
    with pytest.raises(ValidationError):
        RunReport.model_validate(complete_report_data)


def test_ai_usage_is_visible_when_inspecting_completed_report(
    tmp_path: Path, complete_report_data: dict
) -> None:
    complete_report_data["adaptation"] = "agent"
    complete_report_data["model_usage"] = {
        "provider": "deepseek",
        "model": "test-model",
        "calls": 2,
    }
    report = RunReport.model_validate(complete_report_data)
    write_report(tmp_path, report)
    inspected = CliRunner().invoke(
        app, ["inspect", "--report", str(tmp_path / "report.json")]
    )
    assert inspected.exit_code == 0
    assert "AI adaptation: deepseek / test-model; model requests: 2" in inspected.output
