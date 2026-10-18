"""Conservative text prices from a pinned offline catalog and session accounting."""

import math
from decimal import Decimal
from importlib.metadata import version

from genai_prices.data import providers as price_providers
from genai_prices.data_snapshot import DataSnapshot
from genai_prices.types import ModelPrice as CatalogPrice
from genai_prices.types import TieredPrices
from pydantic_ai.usage import RequestUsage

from seam.constants.agent import MAX_API_CALLS, MAX_OUTPUT_TOKENS, MIN_OUTPUT_TOKENS
from seam.exceptions import AgentError, BudgetExceeded
from seam.models import ModelPrice


def _maximum(rate: Decimal | TieredPrices | None) -> Decimal:
    if isinstance(rate, TieredPrices):
        return max([rate.base, *(tier.price for tier in rate.tiers)])
    return rate or Decimal(0)


def catalog_price(
    provider: str, model: str
) -> tuple[Decimal, Decimal, int | None] | None:
    """Read bundled metadata without network updates or global price overrides."""
    catalog_provider = {"azure": "openai", "vertex": "google"}.get(provider, provider)
    snapshot = DataSnapshot(price_providers, from_auto_update=False)
    try:
        _, info = snapshot.find_provider_model(model, None, catalog_provider, None)
    except LookupError:
        return None
    schedules = (
        [info.prices]
        if isinstance(info.prices, CatalogPrice)
        else [entry.prices for entry in info.prices]
    )
    schedules.extend(variant.prices for variant in info.price_variants or ())
    input_rates = [
        _maximum(getattr(schedule, field))
        for schedule in schedules
        for field in (
            "input_mtok",
            "cache_read_mtok",
            "cache_write_mtok",
            "cache_write_1h_mtok",
        )
    ]
    output_rates = [_maximum(schedule.output_mtok) for schedule in schedules]
    if not input_rates or not output_rates:
        return None
    input_rate, output_rate = max(input_rates), max(output_rates)
    if not input_rate.is_finite() or not output_rate.is_finite():
        return None
    if input_rate <= 0 or output_rate <= 0:
        return None
    return input_rate, output_rate, info.context_window


def resolve_price(
    model: str,
    prices: dict[str, ModelPrice],
    max_output_tokens: int,
    *,
    provider: str = "openai",
    budget_usd: float | None = 1.0,
    input_per_million: float | None = None,
    output_per_million: float | None = None,
    context_tokens: int | None = None,
) -> ModelPrice | None:
    """Complete offline prices with operator values; never guess missing metadata."""
    known = prices.get(model)
    catalog = catalog_price(provider, model) if known is None else None
    input_rate = known.input_per_million if known else catalog[0] if catalog else None
    output_rate = known.output_per_million if known else catalog[1] if catalog else None
    context = known.context_tokens if known else catalog[2] if catalog else None
    if input_per_million is not None:
        input_rate = Decimal(str(input_per_million))
    if output_per_million is not None:
        output_rate = Decimal(str(output_per_million))
    if context_tokens is not None:
        context = context_tokens
    for rate in (input_rate, output_rate):
        if rate is not None and (not rate.is_finite() or rate <= 0):
            raise ValueError("model prices must be finite and greater than zero")
    if context is not None and (
        type(context) is not int or context < max_output_tokens
    ):
        raise ValueError("model context ceiling must cover the output token limit")
    if input_rate is None or output_rate is None or context is None:
        if budget_usd is not None:
            raise ValueError(
                "unknown model pricing or context; supply explicit prices and context "
                "or disable the dollar cap"
            )
        return None
    return ModelPrice(input_rate, output_rate, context)


class UsageLedger:
    """Reserve a full-context upper bound and retain unresolved reservations."""

    def __init__(
        self,
        *,
        provider: str,
        model: str,
        price: ModelPrice | None,
        budget_usd: float | None,
        max_calls: int,
        max_output_tokens: int,
        context_tokens: int | None = None,
    ) -> None:
        if budget_usd is not None and (
            not math.isfinite(budget_usd) or budget_usd <= 0
        ):
            raise ValueError("budget must be finite and greater than zero, or None")
        if price is None and budget_usd is not None:
            raise ValueError("a dollar budget requires known prices and context")
        if (
            type(max_calls) is not int
            or type(max_output_tokens) is not int
            or not 1 <= max_calls <= MAX_API_CALLS
            or not MIN_OUTPUT_TOKENS <= max_output_tokens <= MAX_OUTPUT_TOKENS
        ):
            raise ValueError(
                "call or output token limit is outside the supported range"
            )
        self.provider = provider
        self.model = model
        self.max_output_tokens = max_output_tokens
        self._context_tokens = price.context_tokens if price else context_tokens
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
        """Count a call only after the budget covers its worst possible charge."""
        if self._stopped:
            raise AgentError(
                "provider session stopped after an unresolved API response"
            )
        if self._calls >= self._max_calls:
            raise AgentError("model call limit reached")
        reservation = Decimal(0)
        if self._price is not None:
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
        """Forbid another request while retaining unresolved reservations."""
        self._stopped = True

    def settle(
        self, reservation: Decimal, usage: RequestUsage, returned_model: str | None
    ) -> None:
        """Accept only bounded integer usage and charge each output token once."""
        if (
            type(usage.input_tokens) is not int
            or type(usage.output_tokens) is not int
            or usage.input_tokens < 0
            or usage.output_tokens < 0
            or (
                self._context_tokens is not None
                and usage.input_tokens > self._context_tokens
            )
            or usage.output_tokens > self.max_output_tokens
        ):
            self.stop()
            raise AgentError("provider returned missing or out-of-bounds token usage")
        self._input_tokens += usage.input_tokens
        self._output_tokens += usage.output_tokens
        if self._price is not None:
            self._spent += (
                usage.input_tokens * self._price.input_per_million
                + usage.output_tokens * self._price.output_per_million
            ) / 1000000
        self._reserved -= reservation
        if isinstance(returned_model, str) and returned_model:
            self._returned_model = returned_model

    def snapshot(self) -> dict[str, int | float | str]:
        """Expose aggregate counters without request content or error bodies."""
        return {
            "provider": self.provider,
            "model": self.model,
            "returned_model": self._returned_model,
            "calls": self._calls,
            "input_tokens": self._input_tokens,
            "output_tokens": self._output_tokens,
            "estimated_cost_usd": float(self._spent) if self._price else "unknown",
            "reserved_cost_usd": float(self._reserved) if self._price else "unknown",
            "budget_usd": float(self._budget)
            if self._budget is not None
            else "unlimited",
            "pricing": (
                "conservative text upper bounds; operator rates, checked schedules, "
                f"or bundled genai-prices {version('genai-prices')}; no network updates"
                if self._price
                else "unknown; dollar cap disabled"
            ),
        }
