"""Keep native reasoning/history while validating every bounded tool batch locally."""

import json

from pydantic_ai.messages import (
    ModelRequest,
    ModelResponse,
    ToolCallPart,
    ToolReturnPart,
    UserPromptPart,
)

from seam.agent.prompts import (
    check_conversation_size,
    initial_conversation,
    instruction,
)
from seam.agent.tools import WorkspaceTools
from seam.agent.transport import ModelTransport
from seam.constants.agent import MAX_ARGUMENT_BYTES, MAX_PARALLEL_READ_CALLS
from seam.exceptions import AgentError
from seam.models import AgentContext, AgentProposal


def _arguments(call: ToolCallPart) -> str:
    """Keep JSON strings intact and serialize native object-argument dialects."""
    if isinstance(call.args, str):
        return call.args
    if isinstance(call.args, dict):
        return json.dumps(call.args)
    raise AgentError("provider returned invalid tool arguments")


def _calls(response: ModelResponse, seen_ids: set[str]) -> list[ToolCallPart]:
    """Preflight an entire batch before it can inspect any workspace file."""
    calls = [part for part in response.parts if isinstance(part, ToolCallPart)]
    if not calls or len(calls) > MAX_PARALLEL_READ_CALLS:
        raise AgentError("provider returned an invalid or oversized tool-call batch")
    ids = [call.tool_call_id for call in calls]
    if (
        not all(isinstance(value, str) and value for value in ids)
        or len(set(ids)) != len(ids)
        or seen_ids.intersection(ids)
    ):
        raise AgentError("provider returned duplicate or empty tool call IDs")
    for call in calls:
        if call.tool_name not in {"list_files", "read_file", "submit_patch"}:
            raise AgentError("provider returned an unauthorized tool")
        if len(_arguments(call).encode("utf-8")) > MAX_ARGUMENT_BYTES:
            raise AgentError("provider returned oversized tool arguments")
    seen_ids.update(ids)
    return calls


class PatchSession:
    """Coordinate local workspace tools with one cumulative native provider ledger."""

    def __init__(self, transport: ModelTransport) -> None:
        self._transport = transport

    @property
    def usage(self) -> dict[str, int | float | str]:
        """Return aggregate usage without provider errors, source or credentials."""
        return self._transport.ledger.snapshot()

    def close(self) -> None:
        """Release provider connections."""
        self._transport.close()

    def propose(self, context: AgentContext) -> AgentProposal:
        """Inspect bounded evidence and return one diff for independent verification."""
        tools = WorkspaceTools(context.workspace)
        conversation = initial_conversation(context)
        seen_ids: set[str] = set()
        while True:
            check_conversation_size(conversation)
            response = self._transport.request(conversation)
            conversation.append(response)
            if not any(isinstance(part, ToolCallPart) for part in response.parts):
                conversation.append(
                    ModelRequest(
                        parts=[UserPromptPart(instruction("require_submission"))]
                    )
                )
                continue
            calls = _calls(response, seen_ids)
            if len(calls) > 1 and any(
                call.tool_name == "submit_patch" for call in calls
            ):
                conversation.append(
                    ModelRequest(
                        parts=[
                            ToolReturnPart(
                                tool_name=call.tool_name,
                                tool_call_id=call.tool_call_id,
                                content={"error": instruction("standalone_submission")},
                            )
                            for call in calls
                        ]
                    )
                )
                continue
            outputs: list[ToolReturnPart] = []
            for call in calls:
                result = tools.execute(call.tool_name, _arguments(call))
                if isinstance(result, AgentProposal):
                    return result
                outputs.append(
                    ToolReturnPart(
                        tool_name=call.tool_name,
                        tool_call_id=call.tool_call_id,
                        content=result,
                    )
                )
            conversation.append(ModelRequest(parts=outputs))
