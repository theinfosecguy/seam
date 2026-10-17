"""Keep useful diagnostics visible without weakening verification evidence."""

from pathlib import Path

import pytest
from pydantic import ValidationError
from typer.testing import CliRunner

from seam.cli import app
from seam.constants import MAX_DIAGNOSTIC_CHARACTERS, MAX_DIAGNOSTIC_LINES
from seam.models import ExecutionResult, PhaseResult, RunReport
from seam.models import TestCaseResult as Case
from seam.verification.reporting import diagnostic_excerpt, display_text, write_report


def test_root_import_error_visible_in_markdown_and_terminal(tmp_path: Path) -> None:
    failed = ExecutionResult(
        returncode=4,
        evidence_error="JUnit test case has conflicting outcomes",
        stdout=(
            "ERROR collecting tests/test_utils.py\n"
            "Traceback:\n"
            "tests/test_utils.py:45: in <module>\n"
            "    from .compat import StringIO\n"
            "E   ImportError: attempted relative import with no known parent package\n"
        ),
        stderr="ERROR: not found: tests/test_utils.py::test_proxy\n" * 20,
    )
    report = RunReport(
        status="inconclusive",
        reason="upstream_parent suite: JUnit test case has conflicting outcomes",
        phases=[
            PhaseResult(
                name="upstream_parent",
                revision="a" * 40,
                security=ExecutionResult(
                    returncode=1,
                    tests=[
                        Case(name="test_security", outcome="failed"),
                        Case(name="test_control", outcome="passed"),
                    ],
                ),
                suite=failed,
            )
        ],
    )
    write_report(tmp_path, report)
    markdown = (tmp_path / "report.md").read_text()
    assert "ImportError: attempted relative import" in markdown
    assert "Oracle cases | Suite exit | Suite cases" in markdown
    assert "| upstream_parent | 1 | 2 | 4 | 0 |" in markdown
    result = CliRunner().invoke(
        app, ["inspect", "--report", str(tmp_path / "report.json")]
    )
    assert result.exit_code == 0
    assert "ImportError: attempted relative import" in result.output
    assert "suite diagnostics" in result.output


def test_fixture_error_and_expected_failures_are_identified(tmp_path: Path) -> None:
    execution = ExecutionResult(
        returncode=1,
        tests=[
            Case(
                name="test_async",
                outcome="error",
                message="fixture 'anyio_backend' not found",
            ),
            Case(name="test_future", outcome="skipped", expected_failure=True),
            Case(name="test_optional", outcome="skipped"),
        ],
    )
    report = RunReport(
        status="inconclusive",
        reason="suite contained errors or skipped tests",
        phases=[
            PhaseResult(
                name="target_baseline",
                revision="a" * 40,
                security=ExecutionResult(returncode=0),
                suite=execution,
            )
        ],
    )
    write_report(tmp_path, report)
    assert "fixture 'anyio_backend' not found" in (tmp_path / "report.md").read_text()
    assert "3 (1 xfailed, 1 skipped)" in (tmp_path / "report.md").read_text()
    result = CliRunner().invoke(
        app, ["inspect", "--report", str(tmp_path / "report.json")]
    )
    assert "1 skipped" in result.output and "1 xfailed" in result.output


def test_diagnostics_are_bounded_and_controls_are_not_executed() -> None:
    execution = ExecutionResult(
        returncode=2,
        stdout="\n".join(f"ImportError: detail-{index}" for index in range(100)),
        stderr="\x1b[31m" + "x" * 5000,
    )
    excerpt = diagnostic_excerpt(execution)
    assert len(excerpt) <= MAX_DIAGNOSTIC_CHARACTERS
    assert len(excerpt.splitlines()) <= MAX_DIAGNOSTIC_LINES
    assert "ImportError: detail-0" in excerpt
    assert "\x1b" not in excerpt
    huge = ExecutionResult(returncode=2, stderr="ImportError: " + "x" * 5000)
    assert len(diagnostic_excerpt(huge)) <= MAX_DIAGNOSTIC_CHARACTERS
    assert len(display_text("x" * 5000)) == MAX_DIAGNOSTIC_CHARACTERS


def test_reason_display_is_literal_and_json_preserves_evidence(tmp_path: Path) -> None:
    reason = "bad path\x1b[31m\n![image](https://example.invalid)"
    report = RunReport(status="inconclusive", reason=reason)
    write_report(tmp_path, report)
    markdown = (tmp_path / "report.md").read_text()
    assert "\x1b" not in markdown
    assert "    bad path [31m ![image]" in markdown
    saved = RunReport.model_validate_json((tmp_path / "report.json").read_bytes())
    assert saved.reason == reason
    result = CliRunner().invoke(
        app, ["inspect", "--report", str(tmp_path / "report.json")]
    )
    assert "\x1b" not in result.output
    assert "\n![image]" not in result.output


def test_mutated_incomplete_report_cannot_be_serialized_as_verified(
    tmp_path: Path,
) -> None:
    report = RunReport(status="inconclusive", reason="not run")
    report.status = "verified"
    with pytest.raises(ValidationError, match="verified reports require"):
        write_report(tmp_path, report)
    assert not (tmp_path / "report.json").exists()


def test_legacy_complete_reports_remain_readable() -> None:
    phases = [
        {
            "name": name,
            "revision": "a" * 40,
            "security": {"returncode": 0},
            "suite": {"returncode": 0},
        }
        for name in ("upstream_parent", "upstream_fix", "target_baseline", "backport")
    ]
    legacy = RunReport.model_validate(
        {
            "schema_version": 1,
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
    )
    assert legacy.schema_version == 1
    # An earlier candidate remains part of the evidence after a later success.
    legacy.phases.insert(-1, legacy.phases[-1].model_copy())
    assert len(RunReport.model_validate(legacy.model_dump()).phases) == 5


def test_failed_baseline_control_has_diagnostics(tmp_path: Path) -> None:
    report = RunReport(
        status="inconclusive",
        reason="upstream_parent: normal-behavior controls failed",
        phases=[
            PhaseResult(
                name="upstream_parent",
                revision="a" * 40,
                security=ExecutionResult(
                    returncode=1,
                    tests=[
                        Case(name="test_security", outcome="passed"),
                        Case(
                            name="test_control",
                            outcome="failed",
                            message="AssertionError: ordinary header changed",
                        ),
                    ],
                ),
                suite=ExecutionResult(returncode=0),
            )
        ],
    )
    write_report(tmp_path, report)
    assert "ordinary header changed" in (tmp_path / "report.md").read_text()
    result = CliRunner().invoke(
        app, ["inspect", "--report", str(tmp_path / "report.json")]
    )
    assert "ordinary header changed" in result.output
