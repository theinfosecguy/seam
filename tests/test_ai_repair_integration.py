"""Connect offline model repair with real Git and independent Docker evidence."""

import difflib
import hashlib
import json
import os
import shlex
from pathlib import Path
from typing import Any

import pytest
from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    ModelResponse,
    ToolCallPart,
    ToolReturnPart,
    UserPromptPart,
)
from pydantic_ai.models.function import AgentInfo, FunctionModel
from pydantic_ai.usage import RequestUsage

from seam.agent import PatchAgent
from seam.constants.demo import FAILURE_MARKER
from seam.constants.providers import DEFAULT_MODEL
from seam.demo import DemoProject, create_demo
from seam.models import RunReport
from seam.repository import git
from seam.verification.workflow import run_backport


@pytest.fixture
def project(tmp_path: Path) -> DemoProject:
    image = os.environ.get("BACKPORT_TEST_IMAGE")
    if not image:
        pytest.skip("Set BACKPORT_TEST_IMAGE for the complete Docker repair flow")
    docker = tuple(shlex.split(os.environ.get("BACKPORT_TEST_DOCKER", "docker")))
    return create_demo(tmp_path / "project", image=image, docker=docker)


def test_model_repairs_rejected_candidate_using_real_execution_feedback(
    tmp_path: Path, project: DemoProject
) -> None:
    source_path = "src/parcel_paths/legacy.py"
    original_source = (project.repo / source_path).read_text()
    first_patch = "".join(
        difflib.unified_diff(
            original_source.splitlines(keepends=True),
            (
                original_source + "\n# Preserve the maintained release interface.\n"
            ).splitlines(keepends=True),
            fromfile=f"a/{source_path}",
            tofile=f"b/{source_path}",
        )
    )
    patches = [first_patch, project.candidate_patch.read_text()]
    explanations = [
        "Document the existing maintained release interface.",
        "Add containment checks while preserving the older public API.",
    ]
    initial_payloads: list[dict[str, Any]] = []
    target_reads: list[dict[str, Any]] = []

    def model(messages: list[ModelMessage], _info: AgentInfo) -> ModelResponse:
        latest = messages[-1]
        assert isinstance(latest, ModelRequest)
        if len(messages) == 1:
            prompt = next(
                part for part in latest.parts if isinstance(part, UserPromptPart)
            )
            assert isinstance(prompt.content, str)
            initial_payloads.append(json.loads(prompt.content))
            call = ToolCallPart(
                "read_file",
                {"path": source_path, "start_line": 1, "line_count": 200},
                "read_target",
            )
        else:
            result = next(
                part for part in latest.parts if isinstance(part, ToolReturnPart)
            )
            assert result.tool_name == "read_file"
            target_reads.append(result.content)
            candidate = len(initial_payloads) - 1
            call = ToolCallPart(
                "submit_patch",
                {"patch": patches[candidate], "explanation": explanations[candidate]},
                "submit_candidate",
            )
        return ModelResponse(
            parts=[call],
            usage=RequestUsage(input_tokens=100, output_tokens=50),
            finish_reason="tool_call",
        )

    agent = PatchAgent(
        provider="openai",
        model=DEFAULT_MODEL,
        model_instance=FunctionModel(model),
        budget_usd=None,
        max_calls=4,
    )
    original_head = git(project.repo, "rev-parse", "HEAD")
    original_status = git(project.repo, "status", "--porcelain")
    oracle_path = project.config_path.parent / "oracle.py"
    original_oracle = oracle_path.read_bytes()
    output = tmp_path / "result"
    try:
        report = run_backport(
            project.repo,
            project.fix,
            project.target,
            project.config_path,
            output,
            proposer=agent,
        )
    finally:
        agent.close()

    assert report.status == "verified", report.model_dump()
    assert report.adaptation == "agent" and report.attempts == 2
    assert [phase.name for phase in report.phases] == [
        "upstream_parent",
        "upstream_fix",
        "target_baseline",
        "backport",
        "backport",
    ]
    rejected, accepted = report.phases[3:]
    assert rejected.security.returncode == 1
    security = next(
        case
        for case in rejected.security.tests
        if case.name == "test_security_traversal"
    )
    assert security.outcome == "failed"
    assert "AssertionError" in security.message and FAILURE_MARKER in security.message
    assert all(
        case.outcome == "passed"
        for case in rejected.security.tests
        if case.name != security.name
    )
    assert rejected.suite.returncode == 0
    assert all(case.outcome == "passed" for case in rejected.suite.tests)
    for execution in (accepted.security, accepted.suite):
        assert execution.returncode == 0 and execution.tests
        assert all(case.outcome == "passed" for case in execution.tests)

    assert len(initial_payloads) == len(target_reads) == 2
    assert (
        initial_payloads[0]["previous_patch"] == initial_payloads[0]["feedback"] == ""
    )
    assert initial_payloads[1]["previous_patch"] == first_patch
    assert "security regression still fails" in initial_payloads[1]["feedback"]
    assert FAILURE_MARKER in initial_payloads[1]["feedback"]
    assert all(
        read["revision"] == "target"
        and read["content"] == "\n".join(original_source.splitlines())
        for read in target_reads
    )
    assert report.model_usage["calls"] == 4
    assert report.model_usage["input_tokens"] == 400
    assert report.model_usage["output_tokens"] == 200
    for attempt, (patch, explanation) in enumerate(
        zip(patches, explanations, strict=True), start=1
    ):
        assert (output / f"attempt-{attempt}.patch").read_text() == patch
        assert (output / f"attempt-{attempt}.explanation.txt").read_text() == (
            explanation + "\n"
        )
    assert (
        report.patch_sha256
        == hashlib.sha256((output / "backport.patch").read_bytes()).hexdigest()
    )
    assert report.oracle_sha256 == hashlib.sha256(original_oracle).hexdigest()
    assert git(project.repo, "rev-parse", "HEAD") == original_head
    assert git(project.repo, "status", "--porcelain") == original_status
    assert (project.repo / source_path).read_text() == original_source
    assert oracle_path.read_bytes() == original_oracle
    assert (
        RunReport.model_validate_json((output / "report.json").read_bytes()) == report
    )
