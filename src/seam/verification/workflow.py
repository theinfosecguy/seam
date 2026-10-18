"""Coordinate frozen evidence collection and bounded backport attempts."""

import hashlib
import json
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import Protocol

from pydantic import ValidationError

from seam import repository
from seam.constants.repository import MAX_PATCH_BYTES
from seam.exceptions import RepositoryError
from seam.execution.docker import DockerRunner
from seam.execution.snapshot import preflight_snapshot
from seam.models import (
    AgentContext,
    AgentProposal,
    PhaseName,
    PhaseResult,
    RunReport,
)
from seam.verification.assessment import assess_phase
from seam.verification.config import load_config
from seam.verification.reporting import write_report
from seam.verification.reviewed_tests import (
    apply_reviewed_test_patch,
    load_reviewed_test_patch,
)


class PatchProposer(Protocol):
    """Propose source diffs without determining their verification status."""

    def propose(self, context: AgentContext) -> AgentProposal:
        """Return a candidate for an independent attempt."""
        ...

    @property
    def usage(self) -> dict[str, int | float | str]:
        """Return bounded model usage without credentials or raw transcripts."""
        ...


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

    repo = repo.resolve()
    output = output.resolve()
    if output == repo or repo in output.parents:
        raise ValueError("output must be outside the source repository")
    if output.exists() and any(output.iterdir()):
        raise ValueError("output directory must be new or empty")
    output.mkdir(parents=True, exist_ok=True, mode=0o700)
    output.chmod(0o700)
    report = RunReport(
        status="inconclusive",
        reason="run has not completed",
    )
    write_report(output, report)
    try:
        repo = repo.resolve(strict=True)
        if proposer is not None and candidate_patch is not None:
            raise ValueError("select either a proposer or a supplied candidate")
        config = load_config(config_path)
        reviewed_patch = None
        if config.reviewed_tests is not None:
            reviewed_patch = load_reviewed_test_patch(
                config.reviewed_tests.path, config.reviewed_tests.sha256
            )
            (output / "reviewed-tests.patch").write_bytes(
                reviewed_patch.encode("utf-8")
            )
            report.reviewed_tests = config.reviewed_tests.model_copy(
                update={"path": Path("reviewed-tests.patch")}
            )
        report.reviewed_fixtures = config.runner.reviewed_fixtures.copy()
        oracle_bytes = config.oracle.path.read_bytes()
        config_bytes = (config.model_dump_json(indent=2) + "\n").encode()
        report.oracle_sha256 = hashlib.sha256(oracle_bytes).hexdigest()
        report.config_sha256 = hashlib.sha256(config_bytes).hexdigest()
        (output / "verification.py").write_bytes(oracle_bytes)
        (output / "config.json").write_bytes(config_bytes)
        fix_commit = repository.resolve(repo, fix)
        report.fix_commit = fix_commit
        parent_commit = repository.parent(repo, fix_commit)
        report.parent_commit = parent_commit
        target_commit = repository.resolve(repo, target)
        report.target_commit = target_commit
        fix_patch = repository.upstream_patch(repo, parent_commit, fix_commit)
        if (
            candidate_patch is not None
            and candidate_patch.stat().st_size > MAX_PATCH_BYTES
        ):
            raise ValueError("candidate patch exceeds 256 KiB")
        explicit_patch = candidate_patch.read_text("utf-8") if candidate_patch else None
        runner = DockerRunner(config.runner)
        with tempfile.TemporaryDirectory(prefix="security-backport-") as directory:
            root = Path(directory)
            oracle_path = root / "test_regression.py"
            oracle_path.write_bytes(oracle_bytes)
            frozen_oracle = config.oracle.model_copy(update={"path": oracle_path})
            baselines: tuple[tuple[PhaseName, str, bool], ...] = (
                ("upstream_parent", parent_commit, True),
                ("upstream_fix", fix_commit, False),
                ("target_baseline", target_commit, True),
            )
            for name, revision, _ in baselines:
                workspace = root / name
                repository.clone_at(repo, revision, workspace)
                try:
                    preflight_snapshot(
                        workspace, reviewed_fixtures=config.runner.reviewed_fixtures
                    )
                except (OSError, ValueError) as error:
                    raise RepositoryError(f"{name} snapshot: {error}") from error
            if reviewed_patch is not None:
                target_workspace = root / "target_baseline"
                reviewed_paths = apply_reviewed_test_patch(
                    target_workspace, reviewed_patch
                )
                repository.git(
                    target_workspace, "restore", "--worktree", "--", *reviewed_paths
                )
            image_id = runner.resolve_image()
            report.image_id = image_id
            write_report(output, report)

            def check(name: PhaseName, revision: str, workspace: Path) -> PhaseResult:
                if oracle_path.read_bytes() != oracle_bytes:
                    raise RuntimeError("frozen verification file changed")
                if progress is not None:
                    progress(f"Checking {name}: security regression and existing suite")
                phase = PhaseResult(
                    name=name,
                    revision=revision,
                    security=runner.run(workspace, frozen_oracle, image_id, "security"),
                    suite=runner.run(workspace, frozen_oracle, image_id, "suite"),
                )
                report.phases.append(phase)
                write_report(output, report)
                return phase

            for name, revision, vulnerable in baselines:
                workspace = root / name
                phase = check(name, revision, workspace)
                status, reason = assess_phase(phase, config, vulnerable=vulnerable)
                if status != "passed":
                    report.status = "inconclusive"
                    report.reason = (
                        f"Verification prerequisites were not established: {reason}"
                    )
                    return write_report(output, report)

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
                    report.adaptation = "agent"
                    proposal = proposer.propose(
                        AgentContext(
                            workspace=workspace,
                            upstream_diff=fix_patch,
                            feedback=feedback,
                        )
                    )
                    patch = proposal.patch
                    report.model_usage = proposer.usage
                else:
                    break
                # Preserve rejected proposals too, so an unsuccessful adaptation
                # remains reviewable without recording provider conversations.
                (output / f"attempt-{attempt}.patch").write_text(patch, "utf-8")
                try:
                    patch = repository.apply_patch(workspace, patch)
                except RepositoryError as error:
                    feedback = str(error)
                    (output / f"attempt-{attempt}.txt").write_text(
                        feedback + "\n", "utf-8"
                    )
                    report.reason = "Candidate could not be applied: " + feedback
                    write_report(output, report)
                    if explicit_patch is not None:
                        break
                    continue
                if reviewed_patch is not None:
                    apply_reviewed_test_patch(workspace, reviewed_patch)
                phase = check("backport", target_commit, workspace)
                status, reason = assess_phase(phase, config, vulnerable=False)
                candidate_suite = {
                    (test.classname, test.name) for test in phase.suite.tests
                }
                if status == "passed" and candidate_suite != baseline_suite:
                    status = "inconclusive"
                    reason = (
                        "backport: existing suite collection changed "
                        "from the target baseline"
                    )
                if status == "passed":
                    if reviewed_patch is not None:
                        (output / "implementation.patch").write_text(patch, "utf-8")
                        patch = repository.git(
                            workspace, "diff", "--no-ext-diff", "--no-textconv", "HEAD"
                        )
                    report.status = "verified"
                    report.reason = (
                        "All four revisions met the frozen security "
                        "and compatibility checks."
                    )
                    report.patch_sha256 = hashlib.sha256(patch.encode()).hexdigest()
                    (output / "backport.patch").write_text(patch, "utf-8")
                    return write_report(output, report)
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
        write_report(output, report)
        raise
    except (OSError, ValueError, RuntimeError) as error:
        report.status = "inconclusive"
        # Provider errors are sanitized before reaching the workflow.
        if isinstance(error, ValidationError):
            details = "; ".join(
                f"{'.'.join(map(str, item['loc']))}: {item['msg']}"
                for item in error.errors(include_input=False)
            )
        else:
            details = str(error)
        report.reason = f"Run could not complete: {details[:2000]}"
    finally:
        if proposer is not None:
            report.model_usage = proposer.usage
        write_report(output, report)
    return report
