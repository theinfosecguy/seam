"""Load trusted instructions and keep untrusted evidence in bounded messages."""

import json
from functools import cache
from importlib.resources import files

from openai.types.responses import ResponseInputParam

from seam.constants import MAX_CONTEXT_BYTES, MAX_CONVERSATION_BYTES, SENSITIVE_CONTENT
from seam.exceptions import AgentError
from seam.models import AgentContext


@cache
def instruction(name: str) -> str:
    """Read an instruction shipped with the installed package."""
    return (
        files("seam.agent")
        .joinpath("instructions", f"{name}.txt")
        .read_text(encoding="utf-8")
        .strip()
    )


def initial_conversation(context: AgentContext) -> ResponseInputParam:
    """Serialize repository evidence as user data, separate from instructions."""
    payload = json.dumps(
        {"upstream_diff": context.upstream_diff, "feedback": context.feedback}
    )
    if len(payload.encode("utf-8")) > MAX_CONTEXT_BYTES:
        raise AgentError("patch context exceeds the supported prompt size")
    if SENSITIVE_CONTENT.search(payload):
        raise AgentError("patch context may contain credentials")
    return [{"role": "user", "content": payload}]


def check_conversation_size(conversation: ResponseInputParam) -> None:
    """Bound accumulated provider reasoning, calls, and read results."""
    serialized = json.dumps(
        conversation, default=lambda item: item.model_dump(mode="json")
    )
    if len(serialized.encode("utf-8")) > MAX_CONVERSATION_BYTES:
        raise AgentError("conversation exceeds the supported size limit")
