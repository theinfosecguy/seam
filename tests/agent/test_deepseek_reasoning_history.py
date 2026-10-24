"""Preserve native DeepSeek reasoning across corrective no-tool turns offline."""

import json
from pathlib import Path
from typing import Any

import httpx2

from seam.agent import DeepSeekPatchAgent
from seam.constants.providers import DEFAULT_DEEPSEEK_MODEL
from seam.models import AgentContext


def test_reasoning_survives_a_no_tool_turn_and_submission_correction(
    tmp_path: Path,
) -> None:
    patch = "--- a/example.py\n+++ b/example.py\n@@ -1 +1 @@\n-unsafe()\n+safe()\n"
    (tmp_path / "example.py").write_text("unsafe()\n", encoding="utf-8")
    messages = [
        {
            "role": "assistant",
            "content": None,
            "reasoning_content": "Inspect the target implementation.",
            "tool_calls": [
                {
                    "id": "read_target",
                    "type": "function",
                    "function": {
                        "name": "read_file",
                        "arguments": json.dumps(
                            {
                                "path": "example.py",
                                "start_line": 1,
                                "line_count": 10,
                            }
                        ),
                    },
                }
            ],
        },
        {
            "role": "assistant",
            "content": "The compatibility change is ready.",
            "reasoning_content": "Preserve the older public interface.",
        },
        {
            "role": "assistant",
            "content": None,
            "reasoning_content": "Submit the complete replacement diff.",
            "tool_calls": [
                {
                    "id": "submit_candidate",
                    "type": "function",
                    "function": {
                        "name": "submit_patch",
                        "arguments": json.dumps(
                            {"patch": patch, "explanation": "Keep the older API."}
                        ),
                    },
                }
            ],
        },
    ]
    requests: list[dict[str, Any]] = []

    def respond(request: httpx2.Request) -> httpx2.Response:
        assert str(request.url) == "https://api.deepseek.com/chat/completions"
        requests.append(json.loads(request.content))
        message = messages[len(requests) - 1]
        return httpx2.Response(
            200,
            json={
                "id": f"chat_{len(requests)}",
                "created": 1,
                "object": "chat.completion",
                "model": DEFAULT_DEEPSEEK_MODEL,
                "choices": [
                    {
                        "index": 0,
                        "message": message,
                        "finish_reason": "tool_calls"
                        if "tool_calls" in message
                        else "stop",
                    }
                ],
                "usage": {
                    "prompt_tokens": 200,
                    "completion_tokens": 100,
                    "total_tokens": 300,
                },
            },
        )

    agent = DeepSeekPatchAgent(
        api_key="offline-history-test-key",
        http_transport=httpx2.MockTransport(respond),
    )
    try:
        proposal = agent.propose(AgentContext(workspace=tmp_path, upstream_diff=patch))
    finally:
        agent.close()

    assert proposal.patch == patch
    assert agent.usage["calls"] == len(requests) == 3
    history = requests[-1]["messages"]
    assistants = [message for message in history if message["role"] == "assistant"]
    assert [message["reasoning_content"] for message in assistants] == [
        "Inspect the target implementation.",
        "Preserve the older public interface.",
    ]
    assert assistants[-1]["content"] == "The compatibility change is ready."
    assert "tool_calls" not in assistants[-1]
    assert history[-1]["role"] == "user"
    assert "submit_patch" in history[-1]["content"]
