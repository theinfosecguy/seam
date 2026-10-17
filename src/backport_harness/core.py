"""Coordinate independent evidence collection and bounded patch attempts."""

import hashlib
import json
import tempfile
import tomllib
from collections.abc import Callable
from pathlib import Path
from typing import Protocol

from backport_harness import repository
from backport_harness.models import (
    AgentContext,
    AgentProposal,
    ExecutionResult,
    HarnessConfig,
    PhaseName,
    PhaseResult,
    RunReport,
)
from backport_harness.runner import DockerRunner


class PatchProposer(Protocol):
    """Propose source diffs without determining their verification status."""

    def propose(self, context: AgentContext) -> AgentProposal:
        """Return a candidate for an independent attempt."""
        ...

    @property
    def usage(self) -> dict[str, int | float | str]:
        """Return bounded model usage without credentials or raw transcripts."""
        ...


def load_config(path: Path) -> HarnessConfig:
    """Read one explicitly selected TOML file, resolving its oracle relative to it."""

    if path.stat().st_size > 65536:
        raise ValueError("configuration exceeds 64 KiB")
    config = HarnessConfig.model_validate(tomllib.loads(path.read_text("utf-8")))
    original = config.oracle.path
    if not original.is_absolute():
        original = path.resolve().parent / original
    if original.is_symlink() or not original.is_file() or original.suffix != ".py":
        raise ValueError("oracle must be a regular Python file")
    if original.stat().st_size > 131072:
        raise ValueError("oracle exceeds 128 KiB")
    config.oracle.path = original.resolve()
    if config.oracle.security_test in config.oracle.controls:
        raise ValueError("security test cannot also be a normal-behavior control")
    for selector in config.runner.suite:
        file = selector.split("::", 1)[0]
        candidate = Path(file)
        if (
            selector.startswith("-")
            or candidate.is_absolute()
            or ".." in candidate.parts
            or "\\" in selector
        ):
            raise ValueError(
                "suite selectors must be relative pytest paths, not options"
            )
    return config


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


def _write_report(output: Path, report: RunReport) -> RunReport:
    (output / "report.json").write_text(
        report.model_dump_json(indent=2) + "\n", "utf-8"
    )
    rows = [
        "# Security backport evidence",
        "",
        f"Status: **{report.status}**",
        "",
        report.reason,
        "",
        "Verification is limited to the recorded tests, revisions, and execution image.",
        "",
        f"- Fix: `{report.fix_commit}`",
        f"- Target: `{report.target_commit}`",
        f"- Image: `{report.image_id}`",
        f"- Oracle SHA-256: `{report.oracle_sha256}`",
        f"- Patch SHA-256: `{report.patch_sha256 or 'none'}`",
        "",
        "| Revision | Security exit | Suite exit | Test cases |",
        "| --- | ---: | ---: | ---: |",
    ]
    for phase in report.phases:
        rows.append(
            f"| {phase.name} | {phase.security.returncode} | {phase.suite.returncode} "
            f"| {len(phase.security.tests) + len(phase.suite.tests)} |"
        )
    rows.extend(
        ["", "See report.json for individual outcomes and bounded execution logs.", ""]
    )
    (output / "report.md").write_text("\n".join(rows), "utf-8")
    return report


def run_backport(
    repo: Path,
    fix: str,
    target: str,
    config_path: Path,
    output: Path,
    *,
    proposer: PatchProposer | None = None,
    candidate_patch: Path | None = None,
    progress: Callable[[str], None] | None = None,
) -> RunReport:
    """Adapt one fix in independent clones and export evidence, preserving the source.

    A caller-supplied candidate exercises the same verifier without an API call.
    Clean application is attempted first otherwise; the model is a fallback.
    """

    repo = repo.resolve(strict=True)
    if proposer is not None and candidate_patch is not None:
        raise ValueError("select either a proposer or a supplied candidate")
    output = output.resolve()
    if output == repo or repo in output.parents:
        raise ValueError("output must be outside the source repository")
    if output.exists() and any(output.iterdir()):
        raise ValueError("output directory must be new or empty")
    config = load_config(config_path)
    oracle_bytes = config.oracle.path.read_bytes()
    config_bytes = (config.model_dump_json(indent=2) + "\n").encode()
    fix_commit = repository.resolve(repo, fix)
    parent_commit = repository.parent(repo, fix_commit)
    target_commit = repository.resolve(repo, target)
    fix_patch = repository.upstream_patch(repo, parent_commit, fix_commit)
    if candidate_patch is not None and candidate_patch.stat().st_size > 262144:
        raise ValueError("candidate patch exceeds 256 KiB")
    explicit_patch = candidate_patch.read_text("utf-8") if candidate_patch else None
    output.mkdir(parents=True, exist_ok=True, mode=0o700)
    output.chmod(0o700)
    (output / "verification.py").write_bytes(oracle_bytes)
    (output / "config.json").write_bytes(config_bytes)
    report = RunReport(
        status="inconclusive",
        reason="run has not completed",
        fix_commit=fix_commit,
        parent_commit=parent_commit,
        target_commit=target_commit,
        image_id="",
        oracle_sha256=hashlib.sha256(oracle_bytes).hexdigest(),
        config_sha256=hashlib.sha256(config_bytes).hexdigest(),
    )
    _write_report(output, report)
    runner = DockerRunner(config.runner)
    try:
        report.image_id = runner.resolve_image()
        with tempfile.TemporaryDirectory(prefix="security-backport-") as directory:
            root = Path(directory)
            oracle_path = root / "test_regression.py"
            oracle_path.write_bytes(oracle_bytes)
            frozen_oracle = config.oracle.model_copy(update={"path": oracle_path})

            def check(name: PhaseName, revision: str, workspace: Path) -> PhaseResult:
                if oracle_path.read_bytes() != oracle_bytes:
                    raise RuntimeError("frozen verification file changed")
                if progress is not None:
                    progress(f"Checking {name}: security regression and existing suite")
                phase = PhaseResult(
                    name=name,
                    revision=revision,
                    security=runner.run(
                        workspace, frozen_oracle, report.image_id, "security"
                    ),
                    suite=runner.run(
                        workspace, frozen_oracle, report.image_id, "suite"
                    ),
                )
                report.phases.append(phase)
                _write_report(output, report)
                return phase

            baselines: tuple[tuple[PhaseName, str, bool], ...] = (
                ("upstream_parent", parent_commit, True),
                ("upstream_fix", fix_commit, False),
                ("target_baseline", target_commit, True),
            )
            for name, revision, vulnerable in baselines:
                workspace = root / name
                repository.clone_at(repo, revision, workspace)
                phase = check(name, revision, workspace)
                status, reason = assess_phase(phase, config, vulnerable=vulnerable)
                if status != "passed":
                    report.status = "inconclusive"
                    report.reason = (
                        f"Verification prerequisites were not established: {reason}"
                    )
                    return _write_report(output, report)

            feedback = ""
            baseline_suite = {
                (test.classname, test.name) for test in report.phases[-1].suite.tests
            }
            for attempt in range(1, config.max_attempts + 1):
                if attempt > 1 and proposer is None:
                    break
                report.attempts = attempt
                if progress is not None:
                    progress(f"Preparing candidate {attempt} of {config.max_attempts}")
                workspace = root / f"candidate-{attempt}"
                repository.clone_at(repo, target_commit, workspace)
                if attempt == 1:
                    patch = explicit_patch if explicit_patch is not None else fix_patch
                    report.adaptation = (
                        "provided_patch" if explicit_patch else "direct_application"
                    )
                elif proposer is not None:
                    proposal = proposer.propose(
                        AgentContext(
                            workspace=workspace,
                            upstream_diff=fix_patch,
                            feedback=feedback,
                        )
                    )
                    patch = proposal.patch
                    report.adaptation = "agent"
                    report.model_usage = proposer.usage
                else:
                    break
                try:
                    repository.apply_patch(workspace, patch)
                except repository.RepositoryError as error:
                    feedback = str(error)
                    (output / f"attempt-{attempt}.txt").write_text(
                        feedback + "\n", "utf-8"
                    )
                    report.reason = "Candidate could not be applied: " + feedback
                    _write_report(output, report)
                    if explicit_patch is not None:
                        break
                    continue
                (output / f"attempt-{attempt}.patch").write_text(patch, "utf-8")
                phase = check("backport", target_commit, workspace)
                status, reason = assess_phase(phase, config, vulnerable=False)
                candidate_suite = {
                    (test.classname, test.name) for test in phase.suite.tests
                }
                if status == "passed" and candidate_suite != baseline_suite:
                    status = "inconclusive"
                    reason = "backport: existing suite collection changed from the target baseline"
                if status == "passed":
                    report.status = "verified"
                    report.reason = "All four revisions met the frozen security and compatibility checks."
                    report.patch_sha256 = hashlib.sha256(patch.encode()).hexdigest()
                    (output / "backport.patch").write_text(patch, "utf-8")
                    return _write_report(output, report)
                report.status = "failed" if status == "failed" else "inconclusive"
                report.reason = reason
                feedback = json.dumps(
                    {
                        "reason": reason,
                        "security": phase.security.model_dump(),
                        "suite": phase.suite.model_dump(),
                    }
                )[:16000]
                if explicit_patch is not None or status == "inconclusive":
                    break
            if report.adaptation == "direct_application" and proposer is None:
                report.reason += (
                    "; supply --model or --candidate-patch for compatibility adaptation"
                )
    except KeyboardInterrupt:
        report.status = "inconclusive"
        report.reason = "Run cancelled; verification did not complete."
        _write_report(output, report)
        raise
    except (OSError, RuntimeError, repository.RepositoryError) as error:
        report.status = "inconclusive"
        # Provider errors are sanitized at their boundary; avoid serializing arbitrary objects.
        report.reason = f"Run could not complete: {str(error)[:2000]}"
    finally:
        if proposer is not None:
            report.model_usage = proposer.usage
        _write_report(output, report)
    return report
