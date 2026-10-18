"""Construct maintained model adapters with explicit endpoints and credentials."""

from __future__ import annotations

import json
import re
from contextlib import AsyncExitStack
from typing import TYPE_CHECKING, Any
from urllib.parse import urlsplit

import httpx
import httpx2
from anthropic import AsyncAnthropic
from google import genai
from google.genai.types import HttpOptions, HttpRetryOptions
from groq import AsyncGroq
from mistralai.client import Mistral
from mistralai.client.utils.logger import NoOpLogger
from openai import AsyncAzureOpenAI, AsyncOpenAI
from pydantic_ai.models import Model
from pydantic_ai.models.anthropic import AnthropicModel
from pydantic_ai.models.groq import GroqModel
from pydantic_ai.models.mistral import MistralModel
from pydantic_ai.models.openai import OpenAIChatModel, OpenAIResponsesModel
from pydantic_ai.models.openrouter import OpenRouterModel
from pydantic_ai.profiles.grok import grok_model_profile
from pydantic_ai.providers.anthropic import AnthropicProvider
from pydantic_ai.providers.deepseek import DeepSeekProvider
from pydantic_ai.providers.google import BaseGoogleProvider, GoogleProvider
from pydantic_ai.providers.google_cloud import GoogleCloudProvider
from pydantic_ai.providers.groq import GroqProvider
from pydantic_ai.providers.mistral import MistralProvider
from pydantic_ai.providers.openai import OpenAIProvider
from pydantic_ai.providers.openrouter import OpenRouterProvider

from seam.agent.google_model import BoundedGoogleModel
from seam.constants.providers import PROVIDERS
from seam.constants.security import MAX_CREDENTIAL_BYTES
from seam.exceptions import AgentError
from seam.models import ModelProvider, ProviderOptions
from seam.security.files import read_controller_text

if TYPE_CHECKING:
    from seam.agent.transport import NetworkGuard


def validate_options(provider: ModelProvider, options: ProviderOptions) -> None:
    """Validate explicit cloud routes before any credential or network operation."""
    if provider == ModelProvider.AZURE:
        endpoint = urlsplit(options.azure_endpoint or "")
        if (
            endpoint.scheme != "https"
            or not re.fullmatch(r"[a-z0-9-]+\.openai\.azure\.com", endpoint.netloc)
            or endpoint.path not in {"", "/"}
            or endpoint.query
            or endpoint.fragment
            or not re.fullmatch(
                r"\d{4}-\d{2}-\d{2}(?:-preview)?", options.azure_api_version or ""
            )
        ):
            raise ValueError("Azure needs an HTTPS resource endpoint and API version")
    elif provider == ModelProvider.BEDROCK:
        if (
            not re.fullmatch(r"[a-z]{2}(?:-[a-z]+)+-\d", options.aws_region or "")
            or not options.aws_access_key_id
            or not options.aws_secret_access_key
        ):
            raise ValueError("Bedrock needs an explicit region and AWS credential pair")
    elif provider == ModelProvider.VERTEX and (
        not re.fullmatch(r"[a-z][a-z0-9-]{4,61}[a-z0-9]", options.google_project or "")
        or not re.fullmatch(
            r"(?:global|[a-z]+(?:-[a-z]+)*\d)", options.google_location or ""
        )
        or options.google_credentials_path is None
    ):
        raise ValueError(
            "Vertex needs an explicit project, location and service account file"
        )


def validate_usage(payload: Any, provider: ModelProvider) -> None:
    """Reject raw missing/coerced usage before library normalization can default it."""
    if not isinstance(payload, dict):
        raise AgentError("provider returned missing or invalid token usage")
    usage = payload.get("usage")
    fields = ("input_tokens", "output_tokens")
    if provider in {ModelProvider.GOOGLE, ModelProvider.VERTEX}:
        usage = payload.get("usageMetadata")
        fields = ("promptTokenCount", "candidatesTokenCount")
    elif provider == ModelProvider.BEDROCK:
        fields = ("inputTokens", "outputTokens")
    elif provider not in {
        ModelProvider.OPENAI,
        ModelProvider.AZURE,
        ModelProvider.ANTHROPIC,
    }:
        fields = ("prompt_tokens", "completion_tokens")
    if (
        not isinstance(usage, dict)
        or any(
            type(usage.get(field)) is not int or usage[field] < 0 for field in fields
        )
        or any(
            type(value) is not int or value < 0
            for key, value in usage.items()
            if ("token" in key.lower())
            and not isinstance(value, dict)
            and value is not None
        )
    ):
        raise AgentError("provider returned missing or invalid token usage")


def validate_calls(payload: Any, provider: ModelProvider) -> None:
    """Check raw SDK fields that some adapters otherwise replace or coerce."""
    if provider in {ModelProvider.OPENAI, ModelProvider.AZURE}:
        calls = payload.get("output", [])
        for call in calls if isinstance(calls, list) else ():
            if (
                isinstance(call, dict)
                and call.get("type") == "function_call"
                and (
                    not isinstance(call.get("call_id"), str)
                    or not call["call_id"]
                    or not isinstance(call.get("arguments"), str)
                    or call.get("status") not in {None, "completed"}
                )
            ):
                raise AgentError("provider returned an invalid tool call")
    elif provider not in {
        ModelProvider.GOOGLE,
        ModelProvider.VERTEX,
        ModelProvider.ANTHROPIC,
        ModelProvider.BEDROCK,
    }:
        for choice in payload.get("choices", []):
            for call in choice.get("message", {}).get("tool_calls", []) or ():
                if not isinstance(call.get("id"), str) or not call["id"]:
                    raise AgentError("provider returned an invalid tool call ID")
                arguments = call.get("function", {}).get("arguments")
                if not isinstance(arguments, str) and not (
                    provider == ModelProvider.MISTRAL and isinstance(arguments, dict)
                ):
                    raise AgentError("provider returned invalid tool arguments")


async def create_model(
    provider: ModelProvider,
    model: str,
    api_key: str | None,
    options: ProviderOptions,
    timeout: float,
    stack: AsyncExitStack,
    network_guard: NetworkGuard,
    *,
    http_transport: httpx2.AsyncBaseTransport | None = None,
    legacy_http_transport: httpx.AsyncBaseTransport | None = None,
) -> Model:
    """Use native protocols and library profiles without ambient SDK routing."""
    validate_options(provider, options)
    if provider not in {ModelProvider.BEDROCK, ModelProvider.VERTEX} and (
        not api_key or not api_key.strip()
    ):
        raise ValueError("an explicit API key is required")

    async def inspect_response(response: httpx2.Response | httpx.Response) -> None:
        if response.is_success:
            await response.aread()
            payload = response.json()
            validate_usage(payload, provider)
            validate_calls(payload, provider)

    client = await stack.enter_async_context(
        httpx2.AsyncClient(
            trust_env=False,
            timeout=timeout,
            follow_redirects=False,
            transport=http_transport,
            event_hooks={
                "request": [network_guard.inspect_request],
                "response": [inspect_response],
            },
        )
    )
    endpoint = PROVIDERS[provider]
    if provider in {
        ModelProvider.OPENAI,
        ModelProvider.DEEPSEEK,
        ModelProvider.XAI,
        ModelProvider.OPENROUTER,
        ModelProvider.TOGETHER,
        ModelProvider.AZURE,
    }:
        kwargs: dict[str, Any] = {
            "api_key": api_key,
            "organization": "",
            "project": "",
            "max_retries": 0,
            "timeout": timeout,
            "http_client": client,
        }
        sdk: AsyncOpenAI
        if provider == ModelProvider.AZURE:
            assert options.azure_endpoint is not None
            sdk = AsyncAzureOpenAI(
                **kwargs,
                azure_endpoint=options.azure_endpoint,
                api_version=options.azure_api_version,
            )
        else:
            sdk = AsyncOpenAI(**kwargs, base_url=endpoint)
        sdk.organization = None
        sdk.project = None
        if provider == ModelProvider.DEEPSEEK:
            return OpenAIChatModel(model, provider=DeepSeekProvider(openai_client=sdk))
        if provider == ModelProvider.OPENROUTER:
            return OpenRouterModel(
                model, provider=OpenRouterProvider(openai_client=sdk)
            )
        if provider in {ModelProvider.OPENAI, ModelProvider.AZURE}:
            return OpenAIResponsesModel(
                model, provider=OpenAIProvider(openai_client=sdk)
            )
        return OpenAIChatModel(
            model,
            provider=OpenAIProvider(openai_client=sdk),
            profile=(
                grok_model_profile(model) if provider == ModelProvider.XAI else None
            ),
        )
    if provider == ModelProvider.ANTHROPIC:
        anthropic = AsyncAnthropic(
            api_key=api_key,
            base_url=endpoint,
            max_retries=0,
            timeout=timeout,
            http_client=client,
        )
        return AnthropicModel(
            model, provider=AnthropicProvider(anthropic_client=anthropic)
        )
    if provider in {ModelProvider.GOOGLE, ModelProvider.VERTEX}:
        sync_client = httpx2.Client(
            trust_env=False, timeout=timeout, follow_redirects=False
        )
        stack.callback(sync_client.close)
        google_options = HttpOptions(
            base_url=endpoint
            if provider == ModelProvider.GOOGLE
            else (
                "https://aiplatform.googleapis.com"
                if options.google_location == "global"
                else f"https://{options.google_location}-aiplatform.googleapis.com"
            ),
            timeout=int(timeout * 1000),
            httpx_client=sync_client,
            httpx_async_client=client,
            retry_options=HttpRetryOptions(attempts=1),
        )
        google_provider: BaseGoogleProvider
        if provider == ModelProvider.VERTEX:
            from google.oauth2 import service_account

            assert options.google_credentials_path is not None
            content = read_controller_text(
                options.google_credentials_path, MAX_CREDENTIAL_BYTES
            )
            try:
                account_info = json.loads(content)
                if not isinstance(account_info, dict):
                    raise ValueError("service account must be a JSON object")
                credentials = service_account.Credentials.from_service_account_info(  # type: ignore[no-untyped-call]
                    account_info,
                    scopes=["https://www.googleapis.com/auth/cloud-platform"],
                    always_use_jwt_access=True,
                )
            except (ValueError, TypeError, RecursionError):
                raise ValueError("Invalid Vertex service account credentials") from None
            google_sdk = genai.Client(
                vertexai=True,
                credentials=credentials,
                project=options.google_project,
                location=options.google_location,
                http_options=google_options,
            )
            google_provider = GoogleCloudProvider(client=google_sdk)
        else:
            google_sdk = genai.Client(
                vertexai=False,
                api_key=api_key,
                http_options=google_options,
            )
            google_provider = GoogleProvider(client=google_sdk)
        stack.callback(google_sdk.close)
        stack.push_async_callback(google_sdk.aio.aclose)
        return BoundedGoogleModel(model, provider=google_provider)
    if provider == ModelProvider.GROQ:
        legacy_client = await stack.enter_async_context(
            httpx.AsyncClient(
                trust_env=False,
                timeout=timeout,
                follow_redirects=False,
                transport=legacy_http_transport,
                event_hooks={
                    "request": [network_guard.inspect_request],
                    "response": [inspect_response],
                },
            )
        )
        groq = AsyncGroq(
            api_key=api_key,
            base_url=endpoint,
            max_retries=0,
            timeout=timeout,
            http_client=legacy_client,
        )
        return GroqModel(model, provider=GroqProvider(groq_client=groq))
    if provider == ModelProvider.MISTRAL:
        sync_client = httpx2.Client(
            trust_env=False, timeout=timeout, follow_redirects=False
        )
        stack.callback(sync_client.close)
        mistral = Mistral(
            api_key=api_key,
            server_url=endpoint,
            async_client=client,
            client=sync_client,
            retry_config=None,
            timeout_ms=int(timeout * 1000),
            debug_logger=NoOpLogger(),
        )
        return MistralModel(model, provider=MistralProvider(mistral_client=mistral))
    if provider == ModelProvider.BEDROCK:
        import boto3
        from botocore.config import Config
        from pydantic_ai.models.bedrock import BedrockConverseModel
        from pydantic_ai.providers.bedrock import BedrockProvider

        suffix = (
            "amazonaws.com.cn"
            if (options.aws_region or "").startswith("cn-")
            else "amazonaws.com"
        )
        bedrock = boto3.client(
            "bedrock-runtime",
            region_name=options.aws_region,
            aws_access_key_id=options.aws_access_key_id,
            aws_secret_access_key=options.aws_secret_access_key,
            aws_session_token=options.aws_session_token or "",
            endpoint_url=f"https://bedrock-runtime.{options.aws_region}.{suffix}",
            config=Config(
                signature_version="v4",
                retries={"total_max_attempts": 1, "mode": "standard"},
                proxies={},
                connect_timeout=timeout,
                read_timeout=timeout,
                ignore_configured_endpoint_urls=True,
            ),
        )
        stack.callback(bedrock.close)

        def inspect_bedrock(parsed: Any, **kwargs: Any) -> None:
            validate_usage(parsed, provider)

        bedrock.meta.events.register(
            "after-call.bedrock-runtime.Converse", inspect_bedrock
        )

        def inspect_bedrock_request(**kwargs: Any) -> None:
            network_guard.consume()

        bedrock.meta.events.register(
            "before-send.bedrock-runtime.Converse", inspect_bedrock_request
        )
        return BedrockConverseModel(
            model, provider=BedrockProvider(bedrock_client=bedrock)
        )
    raise ValueError("unsupported provider")
