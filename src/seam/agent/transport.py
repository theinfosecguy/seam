"""Fixed provider endpoints, request dialects, and sanitized Responses I/O."""

import math

import httpx
from openai import APIConnectionError, APIError, APIStatusError, APITimeoutError, OpenAI
from openai.types.responses import Response, ResponseInputParam
from openai.types.responses.response_create_params import (
    ResponseCreateParamsNonStreaming,
)

from seam.agent.pricing import UsageLedger
from seam.agent.prompts import instruction
from seam.agent.schemas import TOOL_SCHEMAS
from seam.constants import DEEPSEEK, MAX_REQUEST_TIMEOUT_SECONDS
from seam.exceptions import AgentError
from seam.models import Provider


def create_client(provider: Provider, api_key: str, timeout_seconds: float) -> OpenAI:
    """Disable implicit environment routing, proxies, and automatic retries."""
    client = OpenAI(
        api_key=api_key,
        base_url=provider.base_url,
        organization="",
        project="",
        max_retries=0,
        timeout=timeout_seconds,
        http_client=httpx.Client(trust_env=False, timeout=timeout_seconds),
    )
    # Suppress SDK environment routing without sending empty API headers.
    client.organization = None
    client.project = None
    return client


class ResponsesTransport:
    """Send provider-specific requests while sharing one cumulative usage ledger."""

    def __init__(
        self,
        provider: Provider,
        ledger: UsageLedger,
        *,
        api_key: str,
        timeout_seconds: float,
        client: OpenAI | None,
    ) -> None:
        if not api_key.strip():
            raise ValueError("an explicit API key is required")
        if (
            not math.isfinite(timeout_seconds)
            or not 0 < timeout_seconds <= MAX_REQUEST_TIMEOUT_SECONDS
        ):
            raise ValueError("request timeout must be between zero and 300 seconds")
        self.provider = provider
        self.ledger = ledger
        self._client = client or create_client(provider, api_key, timeout_seconds)

    def close(self) -> None:
        """Release the SDK HTTP connection pool."""
        self._client.close()

    def request(self, conversation: ResponseInputParam) -> Response:
        """Reserve charges, send one request, and settle validated usage."""
        reservation = self.ledger.reserve()
        parameters: ResponseCreateParamsNonStreaming = {
            "model": self.ledger.model,
            "instructions": instruction("system"),
            "input": conversation,
            "tool_choice": "required",
            "max_output_tokens": self.ledger.max_output_tokens,
        }
        extra_body: dict[str, object] | None = None
        if self.provider == DEEPSEEK:
            # Thinking mode rejects forced tool selection. Every response is
            # still checked locally for a valid, standalone patch submission.
            parameters["tool_choice"] = "auto"
            # Responses strict schemas are not documented for this endpoint.
            # SDK types require strict, so extra_body supplies its dialect.
            extra_body = {
                "tools": [
                    {key: value for key, value in tool.items() if key != "strict"}
                    for tool in TOOL_SCHEMAS
                ]
            }
        else:
            parameters["tools"] = TOOL_SCHEMAS
            parameters["parallel_tool_calls"] = False
            parameters["store"] = False
            parameters["include"] = ["reasoning.encrypted_content"]
            parameters["truncation"] = "disabled"
            parameters["service_tier"] = "default"
        try:
            response = self._client.responses.create(
                **parameters, extra_body=extra_body
            )
        except APIError as error:
            self.ledger.stop()
            if isinstance(error, APIStatusError):
                detail = f" (HTTP {error.status_code})"
            elif isinstance(error, APITimeoutError):
                detail = " (timeout)"
            elif isinstance(error, APIConnectionError):
                detail = " (connection error)"
            else:
                detail = ""
            raise AgentError(
                f"{self.provider.name} request failed{detail}; "
                "no automatic retry was made"
            ) from None
        self.ledger.settle(reservation, response.usage, response.model)
        if response.status != "completed":
            raise AgentError("provider response was incomplete; no patch was accepted")
        return response
