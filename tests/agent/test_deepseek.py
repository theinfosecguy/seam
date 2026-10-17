"""Exercise DeepSeek requests through the real SDK without network access."""

import json
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import httpx
import pytest
from openai import OpenAI

from seam.agent import DeepSeekPatchAgent
from seam.agent.transport import create_client
from seam.constants import (
    DEEPSEEK,
    DEEPSEEK_MODELS,
    DEFAULT_DEEPSEEK_MODEL,
    MAX_ARGUMENT_BYTES,
)
from seam.exceptions import AgentError, BudgetExceeded
from seam.models import AgentContext

_PATCH = "--- a/example.py\n+++ b/example.py\n@@ -1 +1 @@\n-unsafe()\n+safe()\n"
_TEST_KEY = "offline-deepseek-test-key"


def _call(
    name: str,
    arguments: dict[str, object] | str,
    call_id: str,
) -> dict[str, object]:
    return {
        "type": "function_call",
        "id": f"fc_{call_id}",
        "call_id": call_id,
        "name": name,
        "arguments": arguments if isinstance(arguments, str) else json.dumps(arguments),
        "status": "completed",
    }


def _submission(call_id: str = "submit") -> dict[str, object]:
    return _call(
        "submit_patch",
        {"patch": _PATCH, "explanation": "Preserve the older release interface."},
        call_id,
    )


def _response(
    *items: dict[str, object],
    model: str = DEFAULT_DEEPSEEK_MODEL,
    input_tokens: int = 1000,
    output_tokens: int = 200,
    status: str = "completed",
) -> dict[str, object]:
    return {
        "id": "resp_offline",
        "created_at": 1,
        "object": "response",
        "model": model,
        "status": status,
        "parallel_tool_calls": True,
        "store": False,
        "previous_response_id": None,
        "error": None,
        "incomplete_details": None,
        "output": list(items) if items else [_submission()],
        "usage": {
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "total_tokens": input_tokens + output_tokens,
            "input_tokens_details": {"cached_tokens": input_tokens},
            "output_tokens_details": {"reasoning_tokens": 100},
        },
    }


class _Transport:
    def __init__(
        self, responses: list[dict[str, object] | httpx.Response | Exception]
    ) -> None:
        self.responses = responses
        self.requests: list[dict[str, Any]] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        assert str(request.url) == "https://api.deepseek.com/responses"
        assert request.headers["authorization"] == f"Bearer {_TEST_KEY}"
        self.requests.append(json.loads(request.content))
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        if isinstance(response, httpx.Response):
            return response
        return httpx.Response(200, json=response)


@pytest.fixture
def make_deepseek_agent() -> Iterator[
    Callable[..., tuple[DeepSeekPatchAgent, _Transport]]
]:
    agents: list[DeepSeekPatchAgent] = []

    def create(
        responses: list[dict[str, object] | httpx.Response | Exception],
        **options: Any,
    ) -> tuple[DeepSeekPatchAgent, _Transport]:
        transport = _Transport(responses)
        client = OpenAI(
            api_key=_TEST_KEY,
            base_url="https://api.deepseek.com",
            max_retries=0,
            http_client=httpx.Client(transport=httpx.MockTransport(transport)),
        )
        agent = DeepSeekPatchAgent(api_key=_TEST_KEY, client=client, **options)
        agents.append(agent)
        return agent, transport

    yield create
    for agent in agents:
        agent.close()


def _context(workspace: Path) -> AgentContext:
    return AgentContext(workspace=workspace, upstream_diff=_PATCH)


def test_deepseek_models_use_current_public_names() -> None:
    assert DEFAULT_DEEPSEEK_MODEL == "deepseek-flash"
    assert set(DEEPSEEK_MODELS) == {"deepseek-flash", "deepseek-v4-pro"}


def test_default_client_uses_fixed_endpoint_and_ignores_environment_routing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENAI_BASE_URL", "https://unintended.invalid")
    monkeypatch.setenv("OPENAI_ORG_ID", "unintended-organization")
    monkeypatch.setenv("OPENAI_PROJECT_ID", "unintended-project")
    client = create_client(DEEPSEEK, _TEST_KEY, 37)
    try:
        assert str(client.base_url).rstrip("/") == "https://api.deepseek.com"
        assert client.max_retries == 0
        assert client.timeout == 37
        assert client.organization is None
        assert client.project is None
    finally:
        client.close()


def test_request_uses_supported_parameters_and_locally_validated_tools(
    tmp_path: Path, make_deepseek_agent: Callable[..., Any]
) -> None:
    agent, transport = make_deepseek_agent([_response()])
    proposal = agent.propose(_context(tmp_path))
    assert proposal.patch == _PATCH
    request = transport.requests[0]
    assert request["model"] == "deepseek-flash"
    assert request["tool_choice"] == "auto"
    assert request["max_output_tokens"] == 16384
    assert not {
        "include",
        "store",
        "truncation",
        "service_tier",
        "parallel_tool_calls",
        "previous_response_id",
    }.intersection(request)
    assert {tool["name"] for tool in request["tools"]} == {
        "list_files",
        "read_file",
        "submit_patch",
    }
    assert all("strict" not in tool for tool in request["tools"])
    assert all(
        tool["parameters"]["additionalProperties"] is False for tool in request["tools"]
    )
    assert _TEST_KEY not in json.dumps(request)


def test_parallel_read_calls_return_every_result_before_next_request(
    tmp_path: Path, make_deepseek_agent: Callable[..., Any]
) -> None:
    (tmp_path / "example.py").write_text("unsafe()\n")
    agent, transport = make_deepseek_agent(
        [
            _response(
                _call("list_files", {"directory": "."}, "listing"),
                _call(
                    "read_file",
                    {"path": "example.py", "start_line": 1, "line_count": 1},
                    "reading",
                ),
            ),
            _response(),
        ]
    )
    agent.propose(_context(tmp_path))
    history = transport.requests[1]["input"]
    outputs = [item for item in history if item.get("type") == "function_call_output"]
    assert [item["call_id"] for item in outputs] == ["listing", "reading"]
    assert json.loads(outputs[0]["output"])["entries"] == ["example.py"]
    assert json.loads(outputs[1]["output"])["content"] == "unsafe()"
    assert [
        item["call_id"] for item in history if item.get("type") == "function_call"
    ] == [
        "listing",
        "reading",
    ]
    assert len(transport.requests) == 2


def test_plaintext_reasoning_is_preserved_in_stateless_tool_history(
    tmp_path: Path, make_deepseek_agent: Callable[..., Any]
) -> None:
    reasoning = {
        "type": "reasoning",
        "id": "rs_offline",
        "status": "completed",
        "content": [{"type": "reasoning_text", "text": "Inspect the older API first."}],
        "summary": [],
    }
    agent, transport = make_deepseek_agent(
        [
            _response(reasoning, _call("list_files", {"directory": "."}, "listing")),
            _response(),
        ]
    )
    agent.propose(_context(tmp_path))
    history = transport.requests[1]["input"]
    preserved = [item for item in history if item.get("type") == "reasoning"]
    assert len(preserved) == 1
    assert preserved[0]["content"] == reasoning["content"]
    assert not preserved[0].get("encrypted_content")


def _message(text: str) -> dict[str, object]:
    return {
        "type": "message",
        "id": "msg_offline",
        "status": "completed",
        "role": "assistant",
        "content": [{"type": "output_text", "text": text, "annotations": []}],
    }


def test_text_only_response_is_corrected_before_accepting_a_tool_submission(
    tmp_path: Path, make_deepseek_agent: Callable[..., Any]
) -> None:
    text = f"Here is my proposed patch:\n{_PATCH}"
    agent, transport = make_deepseek_agent([_response(_message(text)), _response()])
    proposal = agent.propose(_context(tmp_path))
    assert proposal.patch == _PATCH
    assert len(transport.requests) == 2
    history = transport.requests[1]["input"]
    assert history[-2]["type"] == "message"
    assert history[-2]["content"][0]["text"] == text
    assert history[-1]["role"] == "user"
    assert "submit_patch" in history[-1]["content"]
    assert "text message cannot submit a patch" in history[-1]["content"]
    assert agent.usage["calls"] == 2
    assert agent.usage["input_tokens"] == 2000
    assert agent.usage["output_tokens"] == 400


def test_text_only_correction_loop_stops_at_call_ceiling(
    tmp_path: Path, make_deepseek_agent: Callable[..., Any]
) -> None:
    agent, transport = make_deepseek_agent(
        [
            _response(_message("The patch is ready.")),
            _response(_message("I already provided the patch.")),
        ],
        max_calls=2,
    )
    with pytest.raises(AgentError, match="call limit"):
        agent.propose(_context(tmp_path))
    assert len(transport.requests) == 2
    assert agent.usage["calls"] == 2
    assert agent.usage["reserved_cost_usd"] == 0


@pytest.mark.parametrize("submission_count", [1, 2])
def test_mixed_submission_batch_is_rejected_before_standalone_retry(
    tmp_path: Path,
    make_deepseek_agent: Callable[..., Any],
    monkeypatch: pytest.MonkeyPatch,
    submission_count: int,
) -> None:
    def forbidden(*args: object, **kwargs: object) -> None:
        pytest.fail("A rejected submission batch must not execute any read tools")

    monkeypatch.setattr("seam.agent.tools.WorkspaceTools.list_files", forbidden)
    monkeypatch.setattr("seam.agent.tools.WorkspaceTools.read_file", forbidden)
    calls = [_submission("submit_one")]
    if submission_count == 1:
        calls.append(_call("list_files", {"directory": "."}, "listing"))
        calls.append(
            _call(
                "read_file",
                {"path": "example.py", "start_line": 1, "line_count": 1},
                "reading",
            )
        )
    else:
        calls.append(_submission("submit_two"))
    retry_patch = _PATCH.replace("safe()", "safe_retry()")
    agent, transport = make_deepseek_agent(
        [
            _response(*calls),
            _response(
                _call(
                    "submit_patch",
                    {"patch": retry_patch, "explanation": "Standalone retry."},
                    "submit_retry",
                )
            ),
        ]
    )
    proposal = agent.propose(_context(tmp_path))
    assert proposal.patch == retry_patch
    assert len(transport.requests) == 2
    outputs = [
        item
        for item in transport.requests[1]["input"]
        if item.get("type") == "function_call_output"
    ]
    assert [output["call_id"] for output in outputs] == [
        call["call_id"] for call in calls
    ]
    for output in outputs:
        result = json.loads(output["output"])
        assert set(result) == {"error"}
        assert "entire batch was rejected" in result["error"]
        assert "no tools ran" in result["error"]
        assert "submit_patch alone" in result["error"]
    assert agent.usage["calls"] == 2


def test_repeated_mixed_submission_batches_stop_at_call_ceiling(
    tmp_path: Path,
    make_deepseek_agent: Callable[..., Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def forbidden(*args: object, **kwargs: object) -> None:
        pytest.fail("Rejected batches must not run source-read tools")

    monkeypatch.setattr("seam.agent.tools.WorkspaceTools.list_files", forbidden)
    agent, transport = make_deepseek_agent(
        [
            _response(
                _submission(f"submit_{index}"),
                _call("list_files", {"directory": "."}, f"listing_{index}"),
            )
            for index in range(2)
        ],
        max_calls=2,
    )
    with pytest.raises(AgentError, match="call limit"):
        agent.propose(_context(tmp_path))
    assert len(transport.requests) == 2
    assert agent.usage["calls"] == 2
    assert agent.usage["reserved_cost_usd"] == 0


def test_oversized_read_batch_is_rejected_without_another_request(
    tmp_path: Path, make_deepseek_agent: Callable[..., Any]
) -> None:
    calls = [
        _call("list_files", {"directory": "."}, f"list_{index}") for index in range(9)
    ]
    agent, transport = make_deepseek_agent([_response(*calls)])
    with pytest.raises(AgentError):
        agent.propose(_context(tmp_path))
    assert len(transport.requests) == 1


@pytest.mark.parametrize("across_responses", [False, True])
def test_duplicate_call_ids_are_rejected(
    tmp_path: Path,
    make_deepseek_agent: Callable[..., Any],
    across_responses: bool,
) -> None:
    call = _call("list_files", {"directory": "."}, "repeated")
    responses = (
        [_response(call), _response(call)]
        if across_responses
        else [_response(call, call)]
    )
    agent, transport = make_deepseek_agent(responses)
    with pytest.raises(AgentError):
        agent.propose(_context(tmp_path))
    assert len(transport.requests) == (2 if across_responses else 1)


@pytest.mark.parametrize(
    ("name", "arguments"),
    [
        ("submit_patch", "{"),
        ("submit_patch", "[]"),
        ("submit_patch", {"patch": "", "explanation": "empty patch"}),
        ("submit_patch", {"patch": _PATCH, "explanation": "ok", "shell": "id"}),
        ("read_file", {"path": 42, "start_line": 1, "line_count": 1}),
        ("read_file", {"path": "example.py", "start_line": 0, "line_count": 1}),
        ("read_file", {"path": "example.py", "start_line": "1", "line_count": 1}),
        ("read_file", {"path": "example.py", "start_line": True, "line_count": 1}),
        ("read_file", {"path": "example.py", "start_line": 1}),
        ("read_file", {"path": "example.py", "start_line": 1, "line_count": 201}),
        ("list_files", {"directory": ".", "endpoint": "https://unintended.invalid"}),
        ("list_files", {"directory": "rejected-input-marker", "schema": {"evil": 1}}),
    ],
)
def test_invalid_tool_arguments_return_only_declared_schema_before_valid_submission(
    tmp_path: Path,
    make_deepseek_agent: Callable[..., Any],
    monkeypatch: pytest.MonkeyPatch,
    name: str,
    arguments: dict[str, object] | str,
) -> None:
    def forbidden(*args: object, **kwargs: object) -> None:
        pytest.fail("Invalid arguments must not execute a workspace operation")

    monkeypatch.setattr("seam.agent.tools.WorkspaceTools.list_files", forbidden)
    monkeypatch.setattr("seam.agent.tools.WorkspaceTools.read_file", forbidden)
    agent, transport = make_deepseek_agent(
        [_response(_call(name, arguments, "invalid")), _response()]
    )
    proposal = agent.propose(_context(tmp_path))
    assert proposal.patch == _PATCH
    feedback = json.loads(transport.requests[1]["input"][-1]["output"])
    schema = next(
        tool["parameters"]
        for tool in transport.requests[0]["tools"]
        if tool["name"] == name
    )
    assert feedback == {
        "error": "invalid tool arguments; retry using the declared parameters",
        "parameters": schema,
    }
    assert "rejected-input-marker" not in json.dumps(feedback)
    assert len(transport.requests) == 2
    assert agent.usage["calls"] == 2
    assert agent.usage["input_tokens"] == 2000
    assert agent.usage["output_tokens"] == 400


def test_invalid_read_can_be_corrected_before_submitting_a_patch(
    tmp_path: Path, make_deepseek_agent: Callable[..., Any]
) -> None:
    (tmp_path / "example.py").write_text("unsafe()\n")
    agent, transport = make_deepseek_agent(
        [
            _response(_call("read_file", {"file": "example.py"}, "invalid")),
            _response(
                _call(
                    "read_file",
                    {"path": "example.py", "start_line": 1, "line_count": 1},
                    "corrected",
                )
            ),
            _response(),
        ]
    )
    proposal = agent.propose(_context(tmp_path))
    assert proposal.patch == _PATCH
    feedback = json.loads(transport.requests[1]["input"][-1]["output"])
    assert feedback["parameters"]["required"] == ["path", "start_line", "line_count"]
    output = json.loads(transport.requests[2]["input"][-1]["output"])
    assert output["content"] == "unsafe()"
    assert agent.usage["calls"] == 3


def test_repeated_invalid_arguments_exhaust_cumulative_call_budget(
    tmp_path: Path,
    make_deepseek_agent: Callable[..., Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def forbidden(*args: object, **kwargs: object) -> None:
        pytest.fail("Invalid arguments must not execute a workspace operation")

    monkeypatch.setattr("seam.agent.tools.WorkspaceTools.read_file", forbidden)
    agent, transport = make_deepseek_agent(
        [
            _response(_call("read_file", {"path": "example.py"}, f"invalid_{index}"))
            for index in range(2)
        ],
        max_calls=2,
    )
    for _ in range(2):
        with pytest.raises(AgentError, match="call limit"):
            agent.propose(_context(tmp_path))
    assert len(transport.requests) == 2
    assert agent.usage["calls"] == 2
    assert agent.usage["input_tokens"] == 2000
    assert agent.usage["output_tokens"] == 400
    assert agent.usage["estimated_cost_usd"] == pytest.approx(0.00108)
    assert agent.usage["reserved_cost_usd"] == 0


def test_invalid_arguments_cannot_bypass_finite_budget_for_correction(
    tmp_path: Path, make_deepseek_agent: Callable[..., Any]
) -> None:
    agent, transport = make_deepseek_agent(
        [_response(_call("read_file", {"path": "example.py"}, "invalid"))],
        budget_usd=0.3345,
    )
    with pytest.raises(BudgetExceeded):
        agent.propose(_context(tmp_path))
    assert len(transport.requests) == 1
    assert agent.usage["calls"] == 1
    assert agent.usage["estimated_cost_usd"] == pytest.approx(0.00054)
    assert agent.usage["reserved_cost_usd"] == 0
    assert agent.usage["budget_usd"] == 0.3345


@pytest.mark.parametrize(
    ("name", "arguments"),
    [
        ("shell", "{}"),
        ("read_file", None),
        ("read_file", {"path": "example.py"}),
        ("read_file", "x" * (MAX_ARGUMENT_BYTES + 1)),
    ],
    ids=["unknown-tool", "null-arguments", "object-arguments", "oversized-arguments"],
)
def test_unauthorized_or_unbounded_calls_still_stop_without_recovery(
    tmp_path: Path,
    make_deepseek_agent: Callable[..., Any],
    monkeypatch: pytest.MonkeyPatch,
    name: str,
    arguments: object,
) -> None:
    def forbidden(*args: object, **kwargs: object) -> None:
        pytest.fail("Rejected calls must not execute a workspace operation")

    monkeypatch.setattr("seam.agent.tools.WorkspaceTools.read_file", forbidden)
    call = _call(name, "{}", "invalid")
    call["arguments"] = arguments
    agent, transport = make_deepseek_agent([_response(call)])
    with pytest.raises(AgentError):
        agent.propose(_context(tmp_path))
    assert len(transport.requests) == 1


@pytest.mark.parametrize("failure_kind", ["network", "http"])
def test_provider_errors_do_not_leak_credentials_or_error_bodies(
    tmp_path: Path,
    make_deepseek_agent: Callable[..., Any],
    failure_kind: str,
) -> None:
    sensitive = f"sensitive-provider-body {_TEST_KEY}"
    failure: httpx.Response | Exception
    if failure_kind == "network":
        failure = httpx.ConnectError(sensitive)
    else:
        failure = httpx.Response(401, json={"error": {"message": sensitive}})
    agent, transport = make_deepseek_agent([failure])
    with pytest.raises(AgentError, match="no automatic retry") as caught:
        agent.propose(_context(tmp_path))
    assert sensitive not in str(caught.value)
    assert _TEST_KEY not in str(caught.value)
    assert len(transport.requests) == 1
    assert agent.usage["reserved_cost_usd"] > 0
    with pytest.raises(AgentError, match="session stopped"):
        agent.propose(_context(tmp_path))
    assert len(transport.requests) == 1


@pytest.mark.parametrize(
    ("model", "expected_cost"),
    [("deepseek-flash", 0.00054), ("deepseek-v4-pro", 0.002112)],
)
def test_usage_uses_peak_uncached_upper_prices_even_when_input_was_cached(
    tmp_path: Path,
    make_deepseek_agent: Callable[..., Any],
    model: str,
    expected_cost: float,
) -> None:
    agent, transport = make_deepseek_agent([_response(model=model)], model=model)
    agent.propose(_context(tmp_path))
    assert transport.requests[0]["model"] == model
    assert agent.usage["model"] == model
    assert agent.usage["calls"] == 1
    assert agent.usage["input_tokens"] == 1000
    assert agent.usage["output_tokens"] == 200
    assert agent.usage["estimated_cost_usd"] == pytest.approx(expected_cost)
    assert agent.usage["reserved_cost_usd"] == 0
    assert agent.usage["budget_usd"] == "unlimited"


def test_unlimited_budget_still_obeys_call_ceiling(
    tmp_path: Path, make_deepseek_agent: Callable[..., Any]
) -> None:
    agent, transport = make_deepseek_agent(
        [_response(_call("list_files", {"directory": "."}, "listing"))],
        budget_usd=None,
        max_calls=1,
    )
    with pytest.raises(AgentError, match="call limit"):
        agent.propose(_context(tmp_path))
    assert len(transport.requests) == 1
    assert agent.usage["budget_usd"] == "unlimited"


def test_explicit_finite_budget_reserves_before_contacting_deepseek(
    tmp_path: Path, make_deepseek_agent: Callable[..., Any]
) -> None:
    agent, transport = make_deepseek_agent([_response()], budget_usd=0.30)
    with pytest.raises(BudgetExceeded):
        agent.propose(_context(tmp_path))
    assert transport.requests == []
    assert agent.usage["calls"] == 0


def test_explicit_budget_can_exceed_old_ten_dollar_limit(
    tmp_path: Path, make_deepseek_agent: Callable[..., Any]
) -> None:
    agent, transport = make_deepseek_agent([_response()], budget_usd=25)
    agent.propose(_context(tmp_path))
    assert len(transport.requests) == 1
    assert agent.usage["budget_usd"] == 25


@pytest.mark.parametrize("kind", ["incomplete", "missing_usage", "too_many_tokens"])
def test_unresolved_response_cannot_submit_a_patch(
    tmp_path: Path, make_deepseek_agent: Callable[..., Any], kind: str
) -> None:
    response = _response()
    if kind == "incomplete":
        response["status"] = "incomplete"
    elif kind == "missing_usage":
        response["usage"] = None
    else:
        response = _response(output_tokens=16385)
    agent, transport = make_deepseek_agent([response])
    with pytest.raises(AgentError):
        agent.propose(_context(tmp_path))
    assert len(transport.requests) == 1


@pytest.mark.parametrize("field", ["input_tokens", "output_tokens"])
@pytest.mark.parametrize("value", [None, "sensitive-provider-usage", True])
def test_malformed_token_usage_stops_without_exposing_provider_values(
    tmp_path: Path,
    make_deepseek_agent: Callable[..., Any],
    field: str,
    value: object,
) -> None:
    response = _response()
    usage = response["usage"]
    assert isinstance(usage, dict)
    usage[field] = value
    agent, transport = make_deepseek_agent([response])
    with pytest.raises(AgentError, match="token usage") as caught:
        agent.propose(_context(tmp_path))
    assert "sensitive-provider-usage" not in str(caught.value)
    assert _TEST_KEY not in str(caught.value)
    assert len(transport.requests) == 1
    assert agent.usage["input_tokens"] == 0
    assert agent.usage["output_tokens"] == 0
    assert agent.usage["reserved_cost_usd"] > 0
    with pytest.raises(AgentError, match="session stopped"):
        agent.propose(_context(tmp_path))
    assert len(transport.requests) == 1


def test_unknown_model_is_rejected_before_any_request(
    make_deepseek_agent: Callable[..., Any],
) -> None:
    with pytest.raises(ValueError):
        make_deepseek_agent([], model="unrelated-provider-model")
