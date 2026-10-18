"""Run native API models on one owned event loop with sanitized failures."""

import asyncio
import json
import logging
import math
import warnings
from collections.abc import Iterator
from contextlib import AsyncExitStack, contextmanager

import httpx
import httpx2
from pydantic_ai.exceptions import UsageExtractionFailedWarning
from pydantic_ai.messages import ModelMessage, ModelMessagesTypeAdapter, ModelResponse
from pydantic_ai.models import Model, ModelRequestParameters
from pydantic_ai.settings import ModelSettings
from pydantic_ai.tools import ToolDefinition

from seam.agent.pricing import UsageLedger
from seam.agent.schemas import TOOL_SCHEMAS
from seam.constants.agent import MAX_REQUEST_TIMEOUT_SECONDS
from seam.exceptions import AgentError
from seam.models import ModelProvider, ProviderOptions


@contextmanager
def _quiet_sdk_logs() -> Iterator[None]:
    """Prevent provider SDK debug modes from logging raw requests or error bodies."""
    previous = logging.root.manager.disable
    logging.disable(logging.CRITICAL)
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", UsageExtractionFailedWarning)
            yield
    finally:
        logging.disable(previous)


def _contains_credentials(serialized: str, credentials: tuple[str, ...]) -> bool:
    """Recognize exact credentials through every nested JSON string encoding."""
    for credential in credentials:
        candidate = credential
        while len(candidate) <= len(serialized):
            if candidate in serialized:
                return True
            encoded = json.dumps(candidate, ensure_ascii=False)[1:-1]
            if encoded == candidate:
                break
            candidate = encoded
    return False


class NetworkGuard:
    """Permit exactly one outbound model request for each ledger reservation."""

    def __init__(self) -> None:
        self.available = False

    def consume(self) -> None:
        """Fail closed before any unaccounted SDK retry or continuation is sent."""
        if not self.available:
            raise AgentError("automatic provider follow-up requests are disabled")
        self.available = False

    async def inspect_request(self, request: httpx2.Request | httpx.Request) -> None:
        """Consume the single permit before a native HTTP request."""
        self.consume()


class ModelTransport:
    """Issue one bounded native request per reservation without automatic retries."""

    def __init__(
        self,
        provider: ModelProvider,
        ledger: UsageLedger,
        *,
        api_key: str | None,
        timeout_seconds: float,
        provider_options: ProviderOptions,
        model_instance: Model | None = None,
        http_transport: httpx2.AsyncBaseTransport | None = None,
        legacy_http_transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        if (
            not math.isfinite(timeout_seconds)
            or not 0 < timeout_seconds <= MAX_REQUEST_TIMEOUT_SECONDS
        ):
            raise ValueError("request timeout must be between zero and 300 seconds")
        self.provider = provider
        self.ledger = ledger
        self._timeout = timeout_seconds
        self._runner = asyncio.Runner()
        self._stack = AsyncExitStack()
        self._closed = False
        self._network_guard = NetworkGuard()
        self._credentials = tuple(
            value
            for value in (
                api_key,
                provider_options.aws_access_key_id,
                provider_options.aws_secret_access_key,
                provider_options.aws_session_token,
            )
            if value
        )
        self._settings: ModelSettings = {
            "max_tokens": ledger.max_output_tokens,
            "timeout": timeout_seconds,
        }
        if provider in {ModelProvider.OPENAI, ModelProvider.AZURE}:
            from pydantic_ai.models.openai import OpenAIResponsesModelSettings

            self._settings = OpenAIResponsesModelSettings(
                max_tokens=ledger.max_output_tokens,
                timeout=timeout_seconds,
                parallel_tool_calls=False,
                openai_store=False,
                openai_service_tier="default",
                openai_truncation="disabled",
            )
        self._parameters = ModelRequestParameters(
            function_tools=[
                ToolDefinition(
                    name=tool["name"],
                    description=tool["description"],
                    parameters_json_schema=tool["parameters"],
                    strict=True
                    if provider in {ModelProvider.OPENAI, ModelProvider.AZURE}
                    else None,
                )
                for tool in TOOL_SCHEMAS
            ],
            # Reasoning models may require automatic selection; local acceptance
            # always requires a valid standalone submit_patch tool call.
            allow_text_output=True,
        )
        try:
            from seam.agent.native import create_model

            self._model = model_instance or self._runner.run(
                create_model(
                    provider,
                    ledger.model,
                    api_key,
                    provider_options,
                    timeout_seconds,
                    self._stack,
                    self._network_guard,
                    http_transport=http_transport,
                    legacy_http_transport=legacy_http_transport,
                )
            )
        except Exception:
            self.close()
            raise

    def close(self) -> None:
        """Close connection pools on the same event loop used by every request."""
        if not self._closed:
            try:
                self._runner.run(self._stack.aclose())
            finally:
                self._runner.close()
                self._closed = True

    async def _request(self, conversation: list[ModelMessage]) -> ModelResponse:
        if self.provider == ModelProvider.BEDROCK:
            # boto runs in a worker thread; drain it before cleanup or log restoration.
            task = asyncio.create_task(
                self._model.request(conversation, self._settings, self._parameters)
            )
            try:
                async with asyncio.timeout(self._timeout):
                    return await asyncio.shield(task)
            except (TimeoutError, asyncio.CancelledError):
                await task
                raise
        async with asyncio.timeout(self._timeout):
            return await self._model.request(
                conversation, self._settings, self._parameters
            )

    def request(self, conversation: list[ModelMessage]) -> ModelResponse:
        """Reserve before networking and retain every unresolved reservation."""
        if self._closed:
            raise AgentError("provider session is closed")
        serialized = ModelMessagesTypeAdapter.dump_json(conversation).decode("utf-8")
        if _contains_credentials(serialized, self._credentials):
            raise AgentError("conversation may contain configured credentials")
        reservation = self.ledger.reserve()
        self._network_guard.available = True
        try:
            with _quiet_sdk_logs():
                response = self._runner.run(self._request(conversation))
            if not isinstance(response, ModelResponse):
                raise AgentError("provider returned an invalid response")
            self.ledger.settle(reservation, response.usage, response.model_name)
        except BaseException as error:
            # SDK/decoder errors can contain credentials or repository content.
            self.ledger.stop()
            if not isinstance(error, Exception):
                raise
            raise AgentError(
                f"{self.provider.value} request failed or returned invalid token usage;"
                " "
                "no automatic retry was made; session stopped"
            ) from None
        if response.finish_reason not in {"stop", "tool_call"}:
            self.ledger.stop()
            raise AgentError("provider response was incomplete; no patch was accepted")
        return response
