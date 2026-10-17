"""Public provider adapters with explicit model, budget, and request limits."""

from openai import OpenAI

from seam.agent.pricing import UsageLedger, resolve_price
from seam.agent.session import PatchSession
from seam.agent.transport import ResponsesTransport
from seam.constants import (
    DEEPSEEK,
    DEEPSEEK_PRICES,
    DEFAULT_DEEPSEEK_MODEL,
    DEFAULT_MODEL,
    OPENAI,
    OPENAI_PRICES,
)


class OpenAIPatchAgent(PatchSession):
    """Use the official OpenAI endpoint with strict single-call tool schemas."""

    def __init__(
        self,
        *,
        api_key: str,
        model: str = DEFAULT_MODEL,
        budget_usd: float | None = 1.0,
        max_calls: int = 8,
        max_output_tokens: int = 8192,
        timeout_seconds: float = 90,
        input_price_per_million: float | None = None,
        output_price_per_million: float | None = None,
        context_tokens: int | None = None,
        client: OpenAI | None = None,
    ) -> None:
        price = resolve_price(
            model,
            OPENAI_PRICES,
            max_output_tokens,
            input_per_million=input_price_per_million,
            output_per_million=output_price_per_million,
            context_tokens=context_tokens,
        )
        ledger = UsageLedger(
            provider=OPENAI.name,
            model=model,
            price=price,
            budget_usd=budget_usd,
            max_calls=max_calls,
            max_output_tokens=max_output_tokens,
        )
        super().__init__(
            ResponsesTransport(
                OPENAI,
                ledger,
                api_key=api_key,
                timeout_seconds=timeout_seconds,
                client=client,
            )
        )


class DeepSeekPatchAgent(PatchSession):
    """Use DeepSeek Flash or Pro with validated tools and bounded read batches."""

    def __init__(
        self,
        *,
        api_key: str,
        model: str = DEFAULT_DEEPSEEK_MODEL,
        budget_usd: float | None = None,
        max_calls: int = 16,
        max_output_tokens: int = 16384,
        timeout_seconds: float = 120,
        client: OpenAI | None = None,
    ) -> None:
        price = resolve_price(model, DEEPSEEK_PRICES, max_output_tokens)
        ledger = UsageLedger(
            provider=DEEPSEEK.name,
            model=model,
            price=price,
            budget_usd=budget_usd,
            max_calls=max_calls,
            max_output_tokens=max_output_tokens,
        )
        super().__init__(
            ResponsesTransport(
                DEEPSEEK,
                ledger,
                api_key=api_key,
                timeout_seconds=timeout_seconds,
                client=client,
            )
        )
