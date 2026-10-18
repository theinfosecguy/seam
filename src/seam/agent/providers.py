"""One bounded patch agent over maintained native model/provider adapters."""

import httpx
import httpx2
from pydantic_ai.models import Model

from seam.agent.pricing import UsageLedger, resolve_price
from seam.agent.session import PatchSession
from seam.agent.transport import ModelTransport
from seam.constants.providers import (
    DEEPSEEK_PRICES,
    DEFAULT_DEEPSEEK_MODEL,
    DEFAULT_MODEL,
    OPENAI_PRICES,
)
from seam.models import ModelProvider, ProviderOptions


class PatchAgent(PatchSession):
    """Select a fixed provider and an opaque model ID without a model allowlist."""

    def __init__(
        self,
        *,
        provider: ModelProvider | str,
        model: str,
        api_key: str | None = None,
        budget_usd: float | None = 1.0,
        max_calls: int = 8,
        max_output_tokens: int = 8192,
        timeout_seconds: float = 90,
        input_price_per_million: float | None = None,
        output_price_per_million: float | None = None,
        context_tokens: int | None = None,
        provider_options: ProviderOptions | None = None,
        model_instance: Model | None = None,
        http_transport: httpx2.AsyncBaseTransport | None = None,
        legacy_http_transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        provider = ModelProvider(provider)
        if (
            not model.strip()
            or len(model) > 500
            or any(ord(char) < 32 for char in model)
        ):
            raise ValueError("model must be a nonempty provider model identifier")
        prices = {
            ModelProvider.OPENAI: OPENAI_PRICES,
            ModelProvider.DEEPSEEK: DEEPSEEK_PRICES,
        }.get(provider, {})
        price = resolve_price(
            model,
            prices,
            max_output_tokens,
            provider=provider.value,
            budget_usd=budget_usd,
            input_per_million=input_price_per_million,
            output_per_million=output_price_per_million,
            context_tokens=context_tokens,
        )
        ledger = UsageLedger(
            provider=provider.value,
            model=model,
            price=price,
            budget_usd=budget_usd,
            max_calls=max_calls,
            max_output_tokens=max_output_tokens,
            context_tokens=context_tokens,
        )
        super().__init__(
            ModelTransport(
                provider,
                ledger,
                api_key=api_key,
                timeout_seconds=timeout_seconds,
                provider_options=provider_options or ProviderOptions(),
                model_instance=model_instance,
                http_transport=http_transport,
                legacy_http_transport=legacy_http_transport,
            )
        )


class OpenAIPatchAgent(PatchAgent):
    """Keep the established OpenAI entry point on the common implementation."""

    def __init__(
        self,
        *,
        api_key: str,
        model: str = DEFAULT_MODEL,
        budget_usd: float | None = 1.0,
        **options: object,
    ) -> None:
        super().__init__(
            provider=ModelProvider.OPENAI,
            api_key=api_key,
            model=model,
            budget_usd=budget_usd,
            **options,  # type: ignore[arg-type]
        )


class DeepSeekPatchAgent(PatchAgent):
    """Keep the established DeepSeek entry point on the common implementation."""

    def __init__(
        self,
        *,
        api_key: str,
        model: str = DEFAULT_DEEPSEEK_MODEL,
        budget_usd: float | None = None,
        max_calls: int = 16,
        max_output_tokens: int = 16384,
        timeout_seconds: float = 120,
        **options: object,
    ) -> None:
        super().__init__(
            provider=ModelProvider.DEEPSEEK,
            api_key=api_key,
            model=model,
            budget_usd=budget_usd,
            max_calls=max_calls,
            max_output_tokens=max_output_tokens,
            timeout_seconds=timeout_seconds,
            **options,  # type: ignore[arg-type]
        )
