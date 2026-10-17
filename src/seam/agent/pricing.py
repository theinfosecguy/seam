"""Model price schedules and conservative session accounting."""

import math
from decimal import Decimal
from typing import cast

from openai.types.responses.response_usage import ResponseUsage

from seam.constants import MAX_API_CALLS, MAX_OUTPUT_TOKENS, MIN_OUTPUT_TOKENS
from seam.exceptions import AgentError, BudgetExceeded
from seam.models import ModelPrice


def resolve_price(
    model: str,
    prices: dict[str, ModelPrice],
    max_output_tokens: int,
    *,
    input_per_million: float | None = None,
    output_per_million: float | None = None,
    context_tokens: int | None = None,
) -> ModelPrice:
    """Require a known model or a complete, explicit custom price schedule."""
    overrides = (input_per_million, output_per_million, context_tokens)
    if not any(value is not None for value in overrides):
        if model not in prices:
            raise ValueError("unknown model; supply explicit prices and context")
        return prices[model]
    if any(value is None for value in overrides):
        raise ValueError("custom models need both prices and a context ceiling")
    input_price = cast(float, input_per_million)
    output_price = cast(float, output_per_million)
    context = cast(int, context_tokens)
    if (
        not math.isfinite(input_price)
        or not math.isfinite(output_price)
        or input_price <= 0
        or output_price <= 0
        or context < max_output_tokens
    ):
        raise ValueError("custom model prices and context ceiling must be valid")
    return ModelPrice(Decimal(str(input_price)), Decimal(str(output_price)), context)


class UsageLedger:
    """Reserve worst-case charges before a request and settle validated usage.

    A failed request or unknown usage retains its reservation and stops the
    session. Starting a new ledger starts a new budget; the caller owns session
    persistence. Estimates exclude taxes and unrelated account spending.
    """

    def __init__(
        self,
        *,
        provider: str,
        model: str,
        price: ModelPrice,
        budget_usd: float | None,
        max_calls: int,
        max_output_tokens: int,
    ) -> None:
        if budget_usd is not None and (
            not math.isfinite(budget_usd) or budget_usd <= 0
        ):
            raise ValueError("budget must be finite and greater than zero, or None")
        if (
            not 1 <= max_calls <= MAX_API_CALLS
            or not MIN_OUTPUT_TOKENS <= max_output_tokens <= MAX_OUTPUT_TOKENS
        ):
            raise ValueError(
                "call or output token limit is outside the supported range"
            )
        self.provider = provider
        self.model = model
        self.max_output_tokens = max_output_tokens
        self._price = price
        self._budget = Decimal(str(budget_usd)) if budget_usd is not None else None
        self._max_calls = max_calls
        self._returned_model = model
        self._calls = 0
        self._input_tokens = 0
        self._output_tokens = 0
        self._spent = Decimal(0)
        self._reserved = Decimal(0)
        self._stopped = False

    def reserve(self) -> Decimal:
        """Count one request only after checking its full possible charge."""
        if self._stopped:
            raise AgentError(
                "provider session stopped after an unresolved API response"
            )
        if self._calls >= self._max_calls:
            raise AgentError("model call limit reached")
        reservation = (
            self._price.context_tokens * self._price.input_per_million
            + self.max_output_tokens * self._price.output_per_million
        ) / 1000000
        if self._budget is not None and (
            self._spent + self._reserved + reservation > self._budget
        ):
            raise BudgetExceeded("remaining budget cannot cover the next request")
        self._reserved += reservation
        self._calls += 1
        return reservation

    def stop(self) -> None:
        """Retain outstanding reservations and forbid another request."""
        self._stopped = True

    def settle(
        self, reservation: Decimal, usage: ResponseUsage | None, returned_model: str
    ) -> None:
        """Replace a reservation with charges from bounded integer token counts."""
        if (
            usage is None
            or type(usage.input_tokens) is not int
            or type(usage.output_tokens) is not int
            or usage.input_tokens < 0
            or usage.output_tokens < 0
            or usage.input_tokens > self._price.context_tokens
            or usage.output_tokens > self.max_output_tokens
        ):
            self.stop()
            raise AgentError("provider returned missing or out-of-bounds token usage")
        self._input_tokens += usage.input_tokens
        self._output_tokens += usage.output_tokens
        self._spent += (
            usage.input_tokens * self._price.input_per_million
            + usage.output_tokens * self._price.output_per_million
        ) / 1000000
        self._reserved -= reservation
        if isinstance(returned_model, str) and returned_model:
            self._returned_model = returned_model

    def snapshot(self) -> dict[str, int | float | str]:
        """Report aggregate charges without source text or credentials."""
        return {
            "provider": self.provider,
            "model": self.model,
            "returned_model": self._returned_model,
            "calls": self._calls,
            "input_tokens": self._input_tokens,
            "output_tokens": self._output_tokens,
            "estimated_cost_usd": float(self._spent),
            "reserved_cost_usd": float(self._reserved),
            "budget_usd": float(self._budget)
            if self._budget is not None
            else "unlimited",
            "pricing": (
                "peak, uncached upper bound; checked 2026-10-17"
                if self.provider == "deepseek"
                else "standard tier; uncached input upper bound; checked 2026-10-17"
            ),
        }
