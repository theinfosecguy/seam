"""Classify security and compatibility evidence without model judgments."""

from seam.models import ExecutionResult, HarnessConfig, PhaseResult


def _unresolved(execution: ExecutionResult) -> str | None:
    if execution.timed_out:
        return "test execution timed out"
    if execution.truncated:
        return "test output exceeded the configured limit"
    if execution.evidence_error:
        return execution.evidence_error
    if execution.returncode not in {0, 1}:
        return "pytest did not complete a normal test run"
    if not execution.tests:
        return "test execution produced no test cases"
    if any(test.outcome in {"error", "skipped"} for test in execution.tests):
        return "test execution contained errors or skipped tests"
    return None


def assess_phase(
    phase: PhaseResult, config: HarnessConfig, *, vulnerable: bool
) -> tuple[str, str]:
    """Require the expected assertion and working controls, never just a red exit."""

    for label, execution in (("security", phase.security), ("suite", phase.suite)):
        reason = _unresolved(execution)
        if reason:
            return "inconclusive", f"{phase.name} {label}: {reason}"
    cases = {test.name: test for test in phase.security.tests}
    if len(cases) != len(phase.security.tests):
        return "inconclusive", f"{phase.name}: duplicate security test names"
    required = {config.oracle.security_test, *config.oracle.controls}
    if not required.issubset(cases):
        return "inconclusive", f"{phase.name}: required security tests are missing"
    controls = [
        case for name, case in cases.items() if name != config.oracle.security_test
    ]
    if any(case.outcome != "passed" for case in controls):
        return "failed", f"{phase.name}: normal-behavior controls failed"
    if phase.suite.returncode != 0 or any(
        test.outcome != "passed" for test in phase.suite.tests
    ):
        return "failed", f"{phase.name}: existing project suite failed"
    security = cases[config.oracle.security_test]
    if vulnerable:
        if (
            phase.security.returncode == 1
            and security.outcome == "failed"
            and config.oracle.failure_marker in security.message
            and "AssertionError" in security.message
        ):
            return "passed", "expected security assertion reproduced; controls passed"
        return (
            "inconclusive",
            f"{phase.name}: expected security assertion was not reproduced",
        )
    if phase.security.returncode == 0 and security.outcome == "passed":
        return "passed", "security regression and compatibility checks passed"
    return "failed", f"{phase.name}: security regression still fails"
