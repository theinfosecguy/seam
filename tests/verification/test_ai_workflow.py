"""Exercise model-first adaptation, recovery, and evidence with real Git checkouts."""

from collections.abc import Callable
from pathlib import Path

import pytest

from seam.demo import DemoProject, create_demo
from seam.exceptions import AgentError, RunnerError
from seam.models import AgentContext, AgentProposal, ExecutionResult, RunReport
from seam.models import TestCaseResult as Case
from seam.verification import workflow


def install_runner(
    monkeypatch: pytest.MonkeyPatch,
    *,
    first_suite: ExecutionResult | None = None,
    baseline_failure: bool = False,
    cleanup_failure: bool = False,
    security_output: str = "",
) -> list[tuple[str, str]]:
    """Stub execution outcomes while leaving Git cloning and patch application real."""
    executions: list[tuple[str, str]] = []

    class Runner:
        def __init__(self, _config) -> None:
            pass

        def resolve_image(self) -> str:
            return "sha256:" + "a" * 64

        def run(self, workspace, _oracle, _image, kind) -> ExecutionResult:
            executions.append((workspace.name, kind))
            if cleanup_failure and workspace.name == "candidate-1":
                raise RunnerError("Docker could not confirm removal of test container")
            if baseline_failure and workspace.name == "target_baseline":
                return ExecutionResult(returncode=2, stderr="baseline import failed")
            if kind == "suite":
                if workspace.name == "candidate-1" and first_suite is not None:
                    return first_suite
                return ExecutionResult(
                    returncode=0, tests=[Case(name="test_existing", outcome="passed")]
                )
            vulnerable = workspace.name in {"upstream_parent", "target_baseline"}
            return ExecutionResult(
                returncode=1 if vulnerable else 0,
                stdout=security_output,
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
    return executions


class Proposer:
    """Record the evidence available to each independent candidate proposal."""

    def __init__(self, patch: Callable[[int], str]) -> None:
        self.patch = patch
        self.contexts: list[AgentContext] = []
        self.source_reads: list[tuple[str, str]] = []

    @property
    def usage(self) -> dict[str, int | float | str]:
        return {"calls": len(self.contexts), "provider": "test", "model": "test"}

    def propose(self, context: AgentContext) -> AgentProposal:
        assert context.upstream_parent_workspace is not None
        assert context.upstream_fix_workspace is not None
        self.source_reads.append(
            (
                (
                    context.upstream_parent_workspace / "src/parcel_paths/paths.py"
                ).read_text(),
                (
                    context.upstream_fix_workspace / "src/parcel_paths/paths.py"
                ).read_text(),
            )
        )
        self.contexts.append(context)
        return AgentProposal(
            patch=self.patch(len(self.contexts)),
            explanation=f"Compatibility explanation for candidate {len(self.contexts)}",
        )


@pytest.fixture
def project(tmp_path: Path) -> DemoProject:
    return create_demo(tmp_path / "project")


def run(project: DemoProject, output: Path, proposer: Proposer) -> RunReport:
    return workflow.run_backport(
        project.repo,
        project.fix,
        project.target,
        project.config_path,
        output,
        proposer=proposer,
    )


def test_model_creates_first_candidate_even_when_upstream_patch_applies(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, project: DemoProject
) -> None:
    install_runner(monkeypatch)
    project.config_path.write_text(
        project.config_path.read_text().replace("max_attempts = 3", "max_attempts = 1")
    )
    parent = workflow.repository.parent(project.repo, project.fix)
    upstream = workflow.repository.upstream_patch(project.repo, parent, project.fix)
    proposer = Proposer(lambda _: upstream)
    output = tmp_path / "result"
    report = workflow.run_backport(
        project.repo,
        project.fix,
        parent,
        project.config_path,
        output,
        proposer=proposer,
    )
    assert report.status == "verified", report.reason
    assert report.adaptation == "agent" and report.attempts == 1
    assert report.model_usage["calls"] == 1
    assert len(proposer.contexts) == 1
    assert proposer.contexts[0].previous_patch == ""
    assert proposer.contexts[0].feedback == ""
    assert proposer.source_reads[0][0] != proposer.source_reads[0][1]
    assert (
        (output / "attempt-1.explanation.txt")
        .read_text()
        .startswith("Compatibility explanation for candidate 1")
    )
    assert "Model: test" in (output / "report.md").read_text()
    assert "Requests: 1" in (output / "report.md").read_text()


@pytest.mark.parametrize(
    "first_suite",
    [
        ExecutionResult(
            returncode=1,
            tests=[Case(name="test_existing", outcome="failed", message="wrong API")],
        ),
        ExecutionResult(returncode=2, stderr="SyntaxError: invalid candidate"),
        ExecutionResult(returncode=-9, timed_out=True),
        ExecutionResult(
            returncode=0, tests=[Case(name="test_existing", outcome="skipped")]
        ),
        ExecutionResult(
            returncode=0, tests=[Case(name="test_different", outcome="passed")]
        ),
    ],
    ids=["assertion", "syntax", "timeout", "skipped", "collection"],
)
def test_rejected_candidate_and_evidence_reach_next_model_attempt(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    project: DemoProject,
    first_suite: ExecutionResult,
) -> None:
    executions = install_runner(monkeypatch, first_suite=first_suite)
    patch = project.candidate_patch.read_text()
    proposer = Proposer(lambda _: patch)
    output = tmp_path / "result"
    report = run(project, output, proposer)
    assert report.status == "verified", report.reason
    assert report.attempts == 2 and report.model_usage["calls"] == 2
    assert proposer.contexts[1].previous_patch == patch
    assert "backport" in proposer.contexts[1].feedback
    assert len(report.phases) == 5
    assert report.phases[3].suite == first_suite
    assert executions[-2:] == [("candidate-2", "security"), ("candidate-2", "suite")]
    for attempt in (1, 2):
        assert (output / f"attempt-{attempt}.patch").read_text() == patch
        assert (
            (output / f"attempt-{attempt}.explanation.txt")
            .read_text()
            .startswith(f"Compatibility explanation for candidate {attempt}")
        )
    assert not workflow.repository.git(project.repo, "status", "--porcelain")
    assert (
        RunReport.model_validate_json((output / "report.json").read_bytes()) == report
    )


def test_apply_rejection_is_repairable_and_keeps_the_rejected_diff(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, project: DemoProject
) -> None:
    install_runner(monkeypatch)
    patch = project.candidate_patch.read_text()
    proposer = Proposer(
        lambda attempt: "invalid unified diff" if attempt == 1 else patch
    )
    report = run(project, tmp_path / "result", proposer)
    assert report.status == "verified", report.reason
    assert proposer.contexts[1].previous_patch == "invalid unified diff"
    assert proposer.contexts[1].feedback
    assert len(report.phases) == 4


def test_final_apply_rejection_does_not_reuse_previous_failed_verdict(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, project: DemoProject
) -> None:
    install_runner(
        monkeypatch,
        first_suite=ExecutionResult(
            returncode=1, tests=[Case(name="test_existing", outcome="failed")]
        ),
    )
    project.config_path.write_text(
        project.config_path.read_text().replace("max_attempts = 3", "max_attempts = 2")
    )
    patch = project.candidate_patch.read_text()
    proposer = Proposer(lambda attempt: patch if attempt == 1 else "invalid diff")
    output = tmp_path / "result"
    report = run(project, output, proposer)
    assert report.status == "inconclusive" and "could not be applied" in report.reason
    assert report.attempts == 2 and len(proposer.contexts) == 2
    assert not (output / "backport.patch").exists() and report.patch_sha256 is None


def test_exhausted_incomplete_candidate_stays_inconclusive(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, project: DemoProject
) -> None:
    install_runner(
        monkeypatch, first_suite=ExecutionResult(returncode=-9, timed_out=True)
    )
    project.config_path.write_text(
        project.config_path.read_text().replace("max_attempts = 3", "max_attempts = 1")
    )
    proposer = Proposer(lambda _: project.candidate_patch.read_text())
    output = tmp_path / "result"
    report = run(project, output, proposer)
    assert report.status == "inconclusive" and "timed out" in report.reason
    assert report.attempts == 1 and len(proposer.contexts) == 1
    assert report.patch_sha256 is None and not (output / "backport.patch").exists()


def test_unusable_baseline_stops_before_any_model_call(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, project: DemoProject
) -> None:
    install_runner(monkeypatch, baseline_failure=True)
    proposer = Proposer(lambda _: pytest.fail("Model must wait for usable baselines"))
    report = run(project, tmp_path / "result", proposer)
    assert report.status == "inconclusive" and "prerequisites" in report.reason
    assert proposer.contexts == [] and report.attempts == 0


def test_provider_error_cannot_fall_back_to_applicable_upstream_patch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, project: DemoProject
) -> None:
    executions = install_runner(monkeypatch)
    parent = workflow.repository.parent(project.repo, project.fix)

    def unavailable(_attempt: int) -> str:
        raise AgentError("provider unavailable")

    proposer = Proposer(unavailable)
    output = tmp_path / "result"
    report = workflow.run_backport(
        project.repo,
        project.fix,
        parent,
        project.config_path,
        output,
        proposer=proposer,
    )
    assert report.status == "inconclusive" and "provider unavailable" in report.reason
    assert report.adaptation == "agent" and report.attempts == 1
    assert report.model_usage["calls"] == 1 and len(executions) == 6
    assert not (output / "backport.patch").exists()


def test_unconfirmed_container_cleanup_stops_before_more_execution_or_proposals(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, project: DemoProject
) -> None:
    executions = install_runner(monkeypatch, cleanup_failure=True)
    proposer = Proposer(lambda _: project.candidate_patch.read_text())
    output = tmp_path / "result"
    report = run(project, output, proposer)
    assert report.status == "inconclusive" and "confirm removal" in report.reason
    assert report.attempts == 1 and len(proposer.contexts) == 1
    assert executions[-1] == ("candidate-1", "security") and len(executions) == 7
    assert not (output / "backport.patch").exists()


def test_suite_diagnostic_survives_large_security_output_in_retry_context(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, project: DemoProject
) -> None:
    install_runner(
        monkeypatch,
        first_suite=ExecutionResult(
            returncode=2, stderr="SyntaxError: unique-broken-target-line"
        ),
        security_output="ordinary security output\n" * 2000,
    )
    proposer = Proposer(lambda _: project.candidate_patch.read_text())
    report = run(project, tmp_path / "result", proposer)
    assert report.status == "verified", report.reason
    assert "unique-broken-target-line" in proposer.contexts[1].feedback


def test_ai_report_cannot_export_verified_patch_without_recorded_api_calls(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, project: DemoProject
) -> None:
    install_runner(monkeypatch)

    class NoCalls(Proposer):
        @property
        def usage(self) -> dict[str, int | float | str]:
            return {"calls": 0}

    proposer = NoCalls(lambda _: project.candidate_patch.read_text())
    output = tmp_path / "result"
    report = run(project, output, proposer)
    assert report.status == "inconclusive" and "recorded model request" in report.reason
    assert report.patch_sha256 is None and not (output / "backport.patch").exists()


def test_no_implicit_offline_mode_writes_nothing(tmp_path: Path) -> None:
    output = tmp_path / "result"
    with pytest.raises(ValueError, match="model proposer"):
        workflow.run_backport(tmp_path, "fix", "target", tmp_path / "none", output)
    assert not output.exists()
