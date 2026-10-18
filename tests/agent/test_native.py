"""Exercise native provider SDK wire formats using synthetic in-memory replies."""

import asyncio
import json
from pathlib import Path
from typing import Any

import httpx
import httpx2
import pytest
from pydantic_ai.messages import ModelResponse, ToolCallPart
from pydantic_ai.models.function import FunctionModel
from pydantic_ai.usage import RequestUsage

from seam.agent import PatchAgent
from seam.exceptions import AgentError, BudgetExceeded
from seam.models import AgentContext, ProviderOptions

PATCH = "--- a/example.py\n+++ b/example.py\n@@ -1 +1 @@\n-unsafe()\n+safe()\n"
MODELS = {
    "openai": "gpt-5.4-mini",
    "anthropic": "claude-sonnet-4-6",
    "google": "gemini-2.5-pro",
    "deepseek": "deepseek-flash",
    "xai": "grok-4",
    "mistral": "mistral-large-latest",
    "groq": "llama-3.3-70b-versatile",
    "openrouter": "anthropic/claude-sonnet-4.5",
    "together": "meta-llama/Llama-3.3-70B-Instruct-Turbo",
    "azure": "my-private-deployment",
}


def reply(
    provider: str, name: str = "submit_patch", args: Any = None, call_id: str = "call_1"
) -> dict[str, Any]:
    """Build a native SDK response, including real token and completion fields."""
    if args is None:
        args = {"patch": PATCH, "explanation": "Preserve the release API."}
    if provider in {"openai", "azure"}:
        return {
            "id": "resp_1",
            "created_at": 1,
            "object": "response",
            "model": MODELS[provider],
            "status": "completed",
            "parallel_tool_calls": False,
            "tools": [],
            "tool_choice": "auto",
            "output": [
                {
                    "type": "function_call",
                    "id": "fc_1",
                    "call_id": call_id,
                    "name": name,
                    "arguments": json.dumps(args),
                    "status": "completed",
                }
            ],
            "usage": {
                "input_tokens": 100,
                "output_tokens": 50,
                "total_tokens": 150,
                "input_tokens_details": {"cached_tokens": 0},
                "output_tokens_details": {"reasoning_tokens": 20},
            },
        }
    if provider == "anthropic":
        return {
            "id": "msg_1",
            "type": "message",
            "role": "assistant",
            "model": MODELS[provider],
            "content": [
                {"type": "tool_use", "id": call_id, "name": name, "input": args}
            ],
            "stop_reason": "tool_use",
            "stop_sequence": None,
            "usage": {"input_tokens": 100, "output_tokens": 50},
        }
    if provider == "google":
        return {
            "candidates": [
                {
                    "content": {
                        "role": "model",
                        "parts": [
                            {
                                "functionCall": {
                                    "name": name,
                                    "args": args,
                                    "id": call_id,
                                }
                            }
                        ],
                    },
                    "finishReason": "STOP",
                    "index": 0,
                }
            ],
            "usageMetadata": {
                "promptTokenCount": 100,
                "candidatesTokenCount": 30,
                "thoughtsTokenCount": 20,
                "totalTokenCount": 150,
            },
            "modelVersion": MODELS[provider],
            "responseId": "resp_1",
        }
    return {
        "id": "chat_1",
        "object": "chat.completion",
        "provider": "Anthropic" if provider == "openrouter" else provider,
        "created": 1,
        "model": MODELS[provider],
        "choices": [
            {
                "index": 0,
                "finish_reason": "tool_calls",
                "message": {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": call_id,
                            "type": "function",
                            "function": {
                                "name": name,
                                "arguments": json.dumps(args),
                            },
                        }
                    ],
                },
            }
        ],
        "usage": {"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150},
    }


@pytest.mark.parametrize("provider", MODELS)
def test_native_sdk_tool_round_trip(
    provider: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Each registered protocol sends tools/results and ignores ambient routing."""
    (tmp_path / "example.py").write_text("unsafe()\n")
    for variable in (
        "OPENAI_BASE_URL",
        "ANTHROPIC_BASE_URL",
        "GROQ_BASE_URL",
        "GOOGLE_GEMINI_BASE_URL",
        "GOOGLE_VERTEX_BASE_URL",
        "HTTPS_PROXY",
    ):
        monkeypatch.setenv(variable, "https://unintended.invalid")
    monkeypatch.setenv("OPENAI_ORG_ID", "unintended-org")
    monkeypatch.setenv("OPENAI_PROJECT_ID", "unintended-project")
    monkeypatch.setenv("AZURE_OPENAI_AD_TOKEN", "unintended-token")
    monkeypatch.setenv("ANTHROPIC_AUTH_TOKEN", "unintended-token")
    requests: list[dict[str, Any]] = []
    urls: list[str] = []
    headers: list[dict[str, str]] = []

    def handle(request: Any) -> Any:
        urls.append(str(request.url))
        headers.append(dict(request.headers))
        requests.append(json.loads(request.content))
        result = (
            reply(
                provider,
                "read_file",
                {"path": "example.py", "start_line": 1, "line_count": 1},
            )
            if len(requests) == 1
            else reply(provider, call_id="call_2")
        )
        response = httpx.Response if provider == "groq" else httpx2.Response
        return response(200, json=result)

    options = (
        ProviderOptions(
            azure_endpoint="https://synthetic-resource.openai.azure.com",
            azure_api_version="2025-04-01-preview",
        )
        if provider == "azure"
        else ProviderOptions()
    )
    agent = PatchAgent(
        provider=provider,
        model=MODELS[provider],
        api_key="synthetic-key",
        budget_usd=None,
        provider_options=options,
        http_transport=httpx2.MockTransport(handle),
        legacy_http_transport=httpx.MockTransport(handle),
    )
    try:
        proposal = agent.propose(AgentContext(workspace=tmp_path, upstream_diff=PATCH))
        assert proposal.patch == PATCH
        assert agent.usage["calls"] == 2
        assert agent.usage["input_tokens"] == 200
        assert agent.usage["output_tokens"] == 100
    finally:
        agent.close()
    assert len(requests) == 2
    assert all("unintended" not in url for url in urls)
    assert all("unintended" not in json.dumps(header) for header in headers)
    assert all("synthetic-key" not in json.dumps(body) for body in requests)
    if provider in {"openai", "azure"}:
        assert "/responses" in urls[0]
        assert requests[0]["store"] is False
        assert requests[0]["parallel_tool_calls"] is False
        assert requests[1]["input"][-1]["type"] == "function_call_output"
    elif provider == "anthropic":
        assert urls[0].startswith("https://api.anthropic.com/v1/messages")
        assert requests[0]["tools"][0]["input_schema"]["additionalProperties"] is False
        assert requests[1]["messages"][-1]["content"][0]["type"] == "tool_result"
    elif provider == "google":
        assert urls[0].startswith("https://generativelanguage.googleapis.com/")
        assert ":generateContent" in urls[0]
        assert requests[0]["tools"][0]["functionDeclarations"]
        assert (
            requests[1]["contents"][-1]["parts"][0]["functionResponse"]["name"]
            == "read_file"
        )
    else:
        assert urls[0].endswith("/chat/completions")
        assert (
            requests[0]["tools"][0]["function"]["parameters"]["additionalProperties"]
            is False
        )
        assert requests[1]["messages"][-1]["role"] == "tool"


@pytest.mark.parametrize(
    "provider",
    [
        "anthropic",
        "google",
        "groq",
        "mistral",
        "openrouter",
        "together",
        "xai",
        "azure",
    ],
)
@pytest.mark.parametrize("failure", ["missing", "malformed", "http", "network"])
def test_native_failures_stop_with_sanitized_error_and_retained_reservation(
    provider: str, failure: str, tmp_path: Path
) -> None:
    attempts = 0

    def handle(request: Any) -> Any:
        nonlocal attempts
        attempts += 1
        http = httpx if provider == "groq" else httpx2
        if failure == "network":
            raise http.ConnectError("PRIVATE-CONTENT synthetic-key")
        if failure == "http":
            return http.Response(
                500, json={"error": {"message": "PRIVATE-CONTENT synthetic-key"}}
            )
        body = reply(provider)
        usage_field = "usageMetadata" if provider == "google" else "usage"
        if failure == "missing":
            body.pop(usage_field)
        else:
            body[usage_field][
                "promptTokenCount"
                if provider == "google"
                else "input_tokens"
                if provider in {"anthropic", "azure"}
                else "prompt_tokens"
            ] = True
        return http.Response(200, json=body)

    agent = PatchAgent(
        provider=provider,
        model=MODELS[provider],
        api_key="synthetic-key",
        budget_usd=10,
        input_price_per_million=1,
        output_price_per_million=2,
        context_tokens=200000,
        provider_options=ProviderOptions(
            azure_endpoint="https://synthetic.openai.azure.com",
            azure_api_version="2025-04-01-preview",
        ),
        http_transport=httpx2.MockTransport(handle),
        legacy_http_transport=httpx.MockTransport(handle),
    )
    try:
        for _ in range(2):
            with pytest.raises(AgentError) as caught:
                agent.propose(AgentContext(workspace=tmp_path, upstream_diff=PATCH))
            assert "PRIVATE-CONTENT" not in str(caught.value)
            assert "synthetic-key" not in str(caught.value)
        assert attempts == 1
        assert agent.usage["reserved_cost_usd"] > 0
        assert agent.usage["calls"] == 1
    finally:
        agent.close()


def test_unknown_models_need_prices_for_cap_and_are_opaque_when_uncapped() -> None:
    with pytest.raises(ValueError, match="explicit prices and context"):
        PatchAgent(provider="anthropic", model="future-model", api_key="synthetic-key")
    agent = PatchAgent(
        provider="anthropic",
        model="future-model",
        api_key="synthetic-key",
        budget_usd=None,
    )
    try:
        assert agent.usage["estimated_cost_usd"] == "unknown"
    finally:
        agent.close()


def test_owned_event_loop_is_reused_and_closed(tmp_path: Path) -> None:
    (tmp_path / "example.py").write_text("unsafe()\n")
    loops = []

    async def model(messages: Any, info: Any) -> ModelResponse:
        loops.append(asyncio.get_running_loop())
        call = (
            ToolCallPart(
                "read_file",
                {"path": "example.py", "start_line": 1, "line_count": 1},
            )
            if len(messages) == 1
            else ToolCallPart("submit_patch", {"patch": PATCH, "explanation": "ok"})
        )
        return ModelResponse(
            parts=[call],
            usage=RequestUsage(input_tokens=100, output_tokens=50),
            finish_reason="tool_call",
        )

    agent = PatchAgent(
        provider="openai", model=MODELS["openai"], model_instance=FunctionModel(model)
    )
    agent.propose(AgentContext(workspace=tmp_path, upstream_diff=PATCH))
    agent.propose(AgentContext(workspace=tmp_path, upstream_diff=PATCH))
    agent.close()
    assert len(loops) == 4 and all(loop is loops[0] for loop in loops)
    assert loops[0].is_closed()


def test_finite_budget_reserves_before_any_api(tmp_path: Path) -> None:
    def forbidden(request: Any) -> Any:
        pytest.fail("budget must prevent the request")

    agent = PatchAgent(
        provider="anthropic",
        model=MODELS["anthropic"],
        api_key="synthetic-key",
        budget_usd=0.01,
        http_transport=httpx2.MockTransport(forbidden),
    )
    try:
        with pytest.raises(BudgetExceeded):
            agent.propose(AgentContext(workspace=tmp_path, upstream_diff=PATCH))
    finally:
        agent.close()


def test_gemini_continuation_does_not_make_unaccounted_follow_up(
    tmp_path: Path,
) -> None:
    attempts = 0

    def handle(request: httpx2.Request) -> httpx2.Response:
        nonlocal attempts
        attempts += 1
        body = reply("google")
        body["candidates"][0]["finishReason"] = "CONTINUATION"
        body["candidates"][0]["continuationToken"] = "must-not-be-followed"
        return httpx2.Response(200, json=body)

    agent = PatchAgent(
        provider="google",
        model=MODELS["google"],
        api_key="synthetic-key",
        budget_usd=None,
        http_transport=httpx2.MockTransport(handle),
    )
    try:
        with pytest.raises(AgentError, match="incomplete"):
            agent.propose(AgentContext(workspace=tmp_path, upstream_diff=PATCH))
        assert attempts == 1
    finally:
        agent.close()


def test_selected_credentials_are_blocked_before_the_first_request(
    tmp_path: Path,
) -> None:
    def forbidden(request: httpx2.Request) -> httpx2.Response:
        pytest.fail("configured credentials must not reach the API as evidence")

    agent = PatchAgent(
        provider="anthropic",
        model=MODELS["anthropic"],
        api_key='opaque-current-secret-with-"-and-\\',
        budget_usd=None,
        http_transport=httpx2.MockTransport(forbidden),
    )
    try:
        with pytest.raises(AgentError, match="credentials"):
            agent.propose(
                AgentContext(
                    workspace=tmp_path,
                    upstream_diff='opaque-current-secret-with-"-and-\\',
                )
            )
        assert agent.usage["calls"] == 0
    finally:
        agent.close()


def test_network_guard_blocks_sdk_internal_second_requests() -> None:
    from seam.agent.transport import NetworkGuard

    guard = NetworkGuard()
    guard.available = True
    guard.consume()
    with pytest.raises(AgentError, match="follow-up"):
        guard.consume()


def test_bedrock_native_converse_with_explicit_auth_and_zero_retries(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from botocore.stub import Stubber

    (tmp_path / "example.py").write_text("unsafe()\n")
    monkeypatch.setenv("AWS_BEARER_TOKEN_BEDROCK", "unintended-token")
    monkeypatch.setenv("AWS_ENDPOINT_URL_BEDROCK_RUNTIME", "https://unintended.invalid")
    monkeypatch.setenv("HTTPS_PROXY", "https://unintended.invalid")
    agent = PatchAgent(
        provider="bedrock",
        model="anthropic.claude-sonnet-4-6",
        budget_usd=None,
        provider_options=ProviderOptions(
            aws_region="us-east-1",
            aws_access_key_id="synthetic-access-key",
            aws_secret_access_key="synthetic-secret-key",
        ),
    )
    client = agent._transport._model.client
    assert client.meta.endpoint_url == "https://bedrock-runtime.us-east-1.amazonaws.com"
    assert client.meta.config.signature_version == "v4"
    assert client.meta.config.retries["total_max_attempts"] == 1
    assert client.meta.config.proxies == {}
    stubber = Stubber(client)
    stubber.add_response(
        "converse",
        {
            "output": {
                "message": {
                    "role": "assistant",
                    "content": [
                        {
                            "toolUse": {
                                "toolUseId": "inspect",
                                "name": "read_file",
                                "input": {
                                    "path": "example.py",
                                    "start_line": 1,
                                    "line_count": 1,
                                },
                            }
                        }
                    ],
                }
            },
            "stopReason": "tool_use",
            "usage": {"inputTokens": 100, "outputTokens": 50, "totalTokens": 150},
            "metrics": {"latencyMs": 1},
        },
    )
    stubber.add_response(
        "converse",
        {
            "output": {
                "message": {
                    "role": "assistant",
                    "content": [
                        {
                            "toolUse": {
                                "toolUseId": "call_1",
                                "name": "submit_patch",
                                "input": {
                                    "patch": PATCH,
                                    "explanation": "Preserve release API.",
                                },
                            }
                        }
                    ],
                }
            },
            "stopReason": "tool_use",
            "usage": {"inputTokens": 100, "outputTokens": 50, "totalTokens": 150},
            "metrics": {"latencyMs": 1},
        },
    )
    try:
        with stubber:
            assert (
                agent.propose(
                    AgentContext(workspace=tmp_path, upstream_diff=PATCH)
                ).patch
                == PATCH
            )
        assert agent.usage["input_tokens"] == 200
        assert agent.usage["output_tokens"] == 100
    finally:
        agent.close()


def test_vertex_uses_explicit_service_account_without_refresh_network(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa

    (tmp_path / "example.py").write_text("unsafe()\n")
    private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    credential_file = tmp_path / "synthetic-account.json"
    credential_file.write_text(
        json.dumps(
            {
                "type": "service_account",
                "project_id": "synthetic-project",
                "private_key_id": "synthetic",
                "private_key": private.private_bytes(
                    serialization.Encoding.PEM,
                    serialization.PrivateFormat.PKCS8,
                    serialization.NoEncryption(),
                ).decode(),
                "client_email": "synthetic@synthetic-project.iam.gserviceaccount.com",
                "client_id": "123",
                "token_uri": "https://oauth2.googleapis.com/token",
            }
        )
    )
    monkeypatch.setenv("GOOGLE_APPLICATION_CREDENTIALS", "/must-not-be-read.json")
    monkeypatch.setenv("GOOGLE_VERTEX_BASE_URL", "https://unintended.invalid")
    monkeypatch.setenv("HTTPS_PROXY", "https://unintended.invalid")
    requests = []

    def handle(request: httpx2.Request) -> httpx2.Response:
        requests.append(request)
        assert request.url.host == "us-central1-aiplatform.googleapis.com"
        assert request.headers["authorization"].startswith("Bearer ey")
        result = (
            reply(
                "google",
                "read_file",
                {"path": "example.py", "start_line": 1, "line_count": 1},
            )
            if len(requests) == 1
            else reply("google", call_id="submit")
        )
        return httpx2.Response(200, json=result)

    agent = PatchAgent(
        provider="vertex",
        model=MODELS["google"],
        budget_usd=None,
        provider_options=ProviderOptions(
            google_project="synthetic-project",
            google_location="us-central1",
            google_credentials_path=credential_file,
        ),
        http_transport=httpx2.MockTransport(handle),
    )
    try:
        proposal = agent.propose(AgentContext(workspace=tmp_path, upstream_diff=PATCH))
        assert proposal.patch == PATCH
        assert len(requests) == 2
        assert agent.usage["output_tokens"] == 100
    finally:
        agent.close()


def test_offline_price_catalog_never_updates_and_completes_known_metadata() -> None:
    from decimal import Decimal

    from seam.agent.pricing import catalog_price, resolve_price

    price = catalog_price("anthropic", "claude-sonnet-4-6")
    assert price is not None
    assert price[0] > 0 and price[1] > 0
    assert (
        resolve_price("unrecognized", {}, 8192, provider="anthropic", budget_usd=None)
        is None
    )
    custom = resolve_price(
        "unrecognized",
        {},
        8192,
        provider="anthropic",
        input_per_million=1,
        output_per_million=2,
        context_tokens=100000,
    )
    assert custom is not None and custom.input_per_million == Decimal(1)


def test_bedrock_timeout_drains_sdk_thread_before_cleanup(tmp_path: Path) -> None:
    import time

    import anyio

    completed = []

    def worker() -> None:
        time.sleep(0.04)
        completed.append(True)

    async def model(messages: Any, info: Any) -> ModelResponse:
        await anyio.to_thread.run_sync(worker)
        return ModelResponse(
            parts=[ToolCallPart("submit_patch", {"patch": PATCH, "explanation": "ok"})],
            usage=RequestUsage(input_tokens=100, output_tokens=50),
            finish_reason="tool_call",
        )

    agent = PatchAgent(
        provider="bedrock",
        model="synthetic-model",
        model_instance=FunctionModel(model),
        budget_usd=None,
        timeout_seconds=0.01,
    )
    try:
        with pytest.raises(AgentError):
            agent.propose(AgentContext(workspace=tmp_path, upstream_diff=PATCH))
        assert completed == [True]
        assert agent.usage["calls"] == 1
    finally:
        agent.close()


def test_sdk_debug_logging_cannot_record_source_or_api_errors(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    import logging

    def handle(request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(
            500, json={"error": {"message": "PRIVATE-ERROR-CONTENT"}}
        )

    agent = PatchAgent(
        provider="anthropic",
        model=MODELS["anthropic"],
        api_key="synthetic-key",
        budget_usd=None,
        http_transport=httpx2.MockTransport(handle),
    )
    previous = logging.root.manager.disable
    try:
        with caplog.at_level(logging.DEBUG), pytest.raises(AgentError):
            agent.propose(
                AgentContext(workspace=tmp_path, upstream_diff="PRIVATE-SOURCE-CONTENT")
            )
        assert "PRIVATE-SOURCE-CONTENT" not in caplog.text
        assert "PRIVATE-ERROR-CONTENT" not in caplog.text
        assert logging.root.manager.disable == previous
    finally:
        agent.close()


@pytest.mark.parametrize(
    "kind", ["fifo", "device", "oversized", "json", "object", "key"]
)
def test_vertex_rejects_unbounded_or_invalid_credential_files_before_network(
    tmp_path: Path, kind: str
) -> None:
    import os

    from seam.constants.security import MAX_CREDENTIAL_BYTES

    credential_path = tmp_path / "selected-account.json"
    expected = "Invalid Vertex service account credentials"
    if kind == "fifo":
        os.mkfifo(credential_path)
        expected = "regular file"
    elif kind == "device":
        credential_path = Path("/dev/null")
        expected = "regular file"
    elif kind == "oversized":
        credential_path.write_bytes(b"x" * (MAX_CREDENTIAL_BYTES + 1))
        expected = "size limit"
    elif kind == "json":
        credential_path.write_text('{"private_key":"PRIVATE-CONTENT-MARKER",')
    elif kind == "object":
        credential_path.write_text('["PRIVATE-CONTENT-MARKER"]')
    else:
        credential_path.write_text(
            json.dumps(
                {
                    "private_key": "PRIVATE-CONTENT-MARKER",
                    "client_email": "synthetic@example.invalid",
                    "token_uri": "https://oauth2.googleapis.com/token",
                }
            )
        )

    def forbidden(request: httpx2.Request) -> httpx2.Response:
        pytest.fail("invalid controller credentials must fail before network access")

    with pytest.raises(ValueError, match=expected) as error:
        PatchAgent(
            provider="vertex",
            model=MODELS["google"],
            budget_usd=None,
            provider_options=ProviderOptions(
                google_project="synthetic-project",
                google_location="us-central1",
                google_credentials_path=credential_path,
            ),
            http_transport=httpx2.MockTransport(forbidden),
        )
    assert "PRIVATE-CONTENT-MARKER" not in str(error.value)
