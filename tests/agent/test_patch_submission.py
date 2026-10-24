"""Recover malformed newline encoding without changing submitted source text."""

from pathlib import Path

import pytest
from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    ModelResponse,
    ToolCallPart,
    ToolReturnPart,
)
from pydantic_ai.models.function import AgentInfo, FunctionModel
from pydantic_ai.usage import RequestUsage

from seam.agent import PatchAgent
from seam.constants.providers import DEFAULT_MODEL
from seam.exceptions import AgentError
from seam.models import AgentContext


@pytest.mark.parametrize("repeats_malformed_patch", [False, True])
def test_malformed_line_breaks_are_corrected_within_the_bounded_session(
    tmp_path: Path, repeats_malformed_patch: bool
) -> None:
    (tmp_path / "source.py").write_text('VALUE = "\\n"\n')
    patch = (
        "--- a/source.py\n"
        "+++ b/source.py\n"
        "@@ -1 +1 @@\n"
        '-VALUE = "\\n"\n'
        '+VALUE = "prefix\\n"\n'
    )
    escaped_patch = patch.replace("\n", "\\n")
    corrections: list[object] = []
    calls = 0

    def model(messages: list[ModelMessage], _info: AgentInfo) -> ModelResponse:
        nonlocal calls
        calls += 1
        latest = messages[-1]
        assert isinstance(latest, ModelRequest)
        corrections.extend(
            part.content
            for part in latest.parts
            if isinstance(part, ToolReturnPart) and part.tool_name == "submit_patch"
        )
        if calls == 1:
            call = ToolCallPart(
                "read_file",
                {"path": "source.py", "start_line": 1, "line_count": 1},
                f"read_{calls}",
            )
        else:
            call = ToolCallPart(
                "submit_patch",
                {
                    "patch": escaped_patch
                    if calls == 2 or repeats_malformed_patch
                    else patch,
                    "explanation": "Preserve the literal newline escape in Python.",
                },
                f"submit_{calls}",
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
    context = AgentContext(workspace=tmp_path, upstream_diff=patch)
    try:
        if repeats_malformed_patch:
            with pytest.raises(AgentError, match="model call limit reached"):
                agent.propose(context)
            assert agent.usage["calls"] == calls == 4
        else:
            proposal = agent.propose(context)
            assert proposal.patch == patch
            assert agent.usage["calls"] == calls == 3
    finally:
        agent.close()

    assert len(corrections) == (2 if repeats_malformed_patch else 1)
    for correction in corrections:
        assert isinstance(correction, dict)
        assert "actual line breaks" in correction["error"]
        assert "literal \\n" in correction["error"]
        assert escaped_patch not in str(correction)
