"""Run a bounded tool conversation over an independently configured transport."""

import json
from typing import cast

from openai.types.responses import (
    Response,
    ResponseFunctionToolCall,
    ResponseInputParam,
)

from seam.agent.prompts import (
    check_conversation_size,
    initial_conversation,
    instruction,
)
from seam.agent.tools import WorkspaceTools
from seam.agent.transport import ResponsesTransport
from seam.constants import MAX_PARALLEL_READ_CALLS
from seam.exceptions import AgentError
from seam.models import AgentContext, AgentProposal


def _calls(
    response: Response, *, parallel_reads: bool, seen_ids: set[str]
) -> list[ResponseFunctionToolCall]:
    """Reject malformed batches before any workspace operation can run."""
    calls = [
        item for item in response.output if isinstance(item, ResponseFunctionToolCall)
    ]
    limit = MAX_PARALLEL_READ_CALLS if parallel_reads else 1
    if (
        not calls
        or len(calls) > limit
        or any(call.status not in {None, "completed"} for call in calls)
    ):
        raise AgentError("provider returned an invalid or oversized tool-call batch")
    ids = [call.call_id for call in calls]
    if parallel_reads and (
        not all(ids) or len(set(ids)) != len(ids) or seen_ids.intersection(ids)
    ):
        raise AgentError("provider returned duplicate or empty tool call IDs")
    seen_ids.update(ids)
    return calls


class PatchSession:
    """Coordinate evidence, workspace tools, and one cumulative provider ledger."""

    def __init__(self, transport: ResponsesTransport) -> None:
        self._transport = transport

    @property
    def usage(self) -> dict[str, int | float | str]:
        """Return cumulative usage without source text or provider error bodies."""
        return self._transport.ledger.snapshot()

    def close(self) -> None:
        """Release the provider connection pool."""
        self._transport.close()

    def propose(self, context: AgentContext) -> AgentProposal:
        """Inspect bounded project evidence and return one unexecuted diff."""
        tools = WorkspaceTools(context.workspace)
        conversation = initial_conversation(context)
        seen_ids: set[str] = set()
        parallel_reads = self._transport.provider.parallel_reads
        while True:
            check_conversation_size(conversation)
            response = self._transport.request(conversation)
            if not isinstance(response.output, list):
                raise AgentError("provider returned invalid output items")
            # Preserve each provider's reasoning representation in stateless loops.
            conversation.extend(cast(ResponseInputParam, response.output))
            if (
                parallel_reads
                and not any(
                    isinstance(item, ResponseFunctionToolCall)
                    for item in response.output
                )
                and any(item.type == "message" for item in response.output)
            ):
                conversation.append(
                    {"role": "user", "content": instruction("require_submission")}
                )
                continue
            calls = _calls(response, parallel_reads=parallel_reads, seen_ids=seen_ids)
            if len(calls) > 1 and any(call.name == "submit_patch" for call in calls):
                for call in calls:
                    conversation.append(
                        {
                            "type": "function_call_output",
                            "call_id": call.call_id,
                            "output": json.dumps(
                                {"error": instruction("standalone_submission")}
                            ),
                        }
                    )
                continue
            for call in calls:
                result = tools.execute(call.name, call.arguments)
                if isinstance(result, AgentProposal):
                    return result
                conversation.append(
                    {
                        "type": "function_call_output",
                        "call_id": call.call_id,
                        "output": json.dumps(result),
                    }
                )
