"""Reject plausible but insufficient security verification evidence."""

from pathlib import Path

import pytest

from backport_harness.core import assess_phase, load_config
from backport_harness.models import (
    ExecutionResult,
    HarnessConfig,
    OracleConfig,
    PhaseResult,
    RunnerConfig,
)
from backport_harness.models import (
    TestCaseResult as Case,
)


def configuration() -> HarnessConfig:
    return HarnessConfig(
        oracle=OracleConfig(
            path=Path("test_regression.py"),
            security_test="test_security",
            controls=("test_legitimate",),
            failure_marker="SECURITY_REGRESSION",
        ),
        runner=RunnerConfig(image="test-image"),
    )


def phase(*, vulnerable: bool) -> PhaseResult:
    return PhaseResult(
        name="target_baseline" if vulnerable else "backport",
        revision="a" * 40,
        security=ExecutionResult(
            returncode=1 if vulnerable else 0,
            tests=[
                Case(
                    name="test_security",
                    outcome="failed" if vulnerable else "passed",
                    message="AssertionError: SECURITY_REGRESSION" if vulnerable else "",
                ),
                Case(name="test_legitimate", outcome="passed"),
            ],
        ),
        suite=ExecutionResult(
            returncode=0, tests=[Case(name="test_existing", outcome="passed")]
        ),
    )


def test_expected_assertion_with_working_controls_is_evidence() -> None:
    assert (
        assess_phase(phase(vulnerable=True), configuration(), vulnerable=True)[0]
        == "passed"
    )
    assert (
        assess_phase(phase(vulnerable=False), configuration(), vulnerable=False)[0]
        == "passed"
    )


@pytest.mark.parametrize(
    "message", ["ModuleNotFoundError: missing", "AssertionError: unrelated"]
)
def test_arbitrary_failures_do_not_establish_vulnerability(message: str) -> None:
    result = phase(vulnerable=True)
    result.security.tests[0].message = message
    assert assess_phase(result, configuration(), vulnerable=True)[0] == "inconclusive"


def test_deny_all_fix_fails_normal_behavior_control() -> None:
    result = phase(vulnerable=False)
    result.security.tests[1].outcome = "failed"
    assert assess_phase(result, configuration(), vulnerable=False)[0] == "failed"


@pytest.mark.parametrize("outcome", ["error", "skipped"])
def test_incomplete_tests_are_inconclusive(outcome: str) -> None:
    result = phase(vulnerable=False)
    result.security.tests[0] = Case(name="test_security", outcome=outcome)
    assert assess_phase(result, configuration(), vulnerable=False)[0] == "inconclusive"


@pytest.mark.parametrize("flag", ["timed_out", "truncated"])
def test_execution_limits_prevent_success(flag: str) -> None:
    result = phase(vulnerable=False)
    setattr(result.suite, flag, True)
    assert assess_phase(result, configuration(), vulnerable=False)[0] == "inconclusive"


def test_missing_or_duplicate_required_case_is_inconclusive() -> None:
    result = phase(vulnerable=False)
    result.security.tests.pop()
    assert assess_phase(result, configuration(), vulnerable=False)[0] == "inconclusive"
    result = phase(vulnerable=False)
    result.security.tests.append(result.security.tests[0])
    assert assess_phase(result, configuration(), vulnerable=False)[0] == "inconclusive"


def test_green_exit_with_no_tests_is_inconclusive() -> None:
    result = phase(vulnerable=False)
    result.suite.tests = []
    assert assess_phase(result, configuration(), vulnerable=False)[0] == "inconclusive"


def test_config_unknown_fields_and_unsafe_suite_are_rejected(tmp_path: Path) -> None:
    oracle = tmp_path / "checks.py"
    oracle.write_text("# fixture\n")
    config = tmp_path / "harness.toml"
    text = """[oracle]
path = "checks.py"
security_test = "test_security"
controls = ["test_legitimate"]
failure_marker = "SECURITY_REGRESSION"
[runner]
image = "test-image"
suite = ["--override-ini=addopts=--ignore=tests"]
"""
    config.write_text(text)
    with pytest.raises(ValueError, match="relative pytest paths"):
        load_config(config)
    config.write_text(
        text.replace(
            'suite = ["--override-ini=addopts=--ignore=tests"]', "surprise = true"
        )
    )
    with pytest.raises(ValueError, match="surprise"):
        load_config(config)
