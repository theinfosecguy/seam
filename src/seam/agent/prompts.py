"""Load trusted instructions and keep untrusted evidence in bounded messages."""

import json
from collections.abc import Sequence
from functools import cache
from importlib.resources import files

from pydantic_ai.messages import (
    ModelMessage,
    ModelMessagesTypeAdapter,
    ModelRequest,
    SystemPromptPart,
    UserPromptPart,
)

from seam.constants.agent import MAX_CONTEXT_BYTES, MAX_CONVERSATION_BYTES
from seam.exceptions import AgentError
from seam.models import AgentContext
from seam.security import contains_secret


@cache
def instruction(name: str) -> str:
    """Read an instruction shipped with the installed package."""
    return (
        files("seam.agent")
        .joinpath("instructions", f"{name}.txt")
        .read_text(encoding="utf-8")
        .strip()
    )


def initial_conversation(context: AgentContext) -> list[ModelMessage]:
    """Serialize repository evidence as user data, separate from instructions."""
    payload = json.dumps(
        {"upstream_diff": context.upstream_diff, "feedback": context.feedback}
    )
    if len(payload.encode("utf-8")) > MAX_CONTEXT_BYTES:
        raise AgentError("patch context exceeds the supported prompt size")
    if contains_secret(payload):
        raise AgentError("patch context may contain credentials")
    return [
        ModelRequest(
            parts=[
                SystemPromptPart(instruction("system")),
                UserPromptPart(payload),
            ]
        )
    ]


def check_conversation_size(conversation: Sequence[ModelMessage]) -> None:
    """Bound and scan every outbound message, including reasoning and tool output."""
    serialized = ModelMessagesTypeAdapter.dump_json(list(conversation))
    if len(serialized) > MAX_CONVERSATION_BYTES:
        raise AgentError("conversation exceeds the supported size limit")
    if contains_secret(serialized.decode("utf-8")):
        raise AgentError("conversation may contain credentials")
