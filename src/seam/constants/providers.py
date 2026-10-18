"""Define supported provider endpoints, model defaults, and text pricing."""

from decimal import Decimal
from typing import Final

from seam.models import ModelPrice, ModelProvider

DEFAULT_MODEL: Final = "gpt-5.4-mini-2026-03-17"

DEFAULT_DEEPSEEK_MODEL: Final = "deepseek-flash"

API_KEY_NAMES: Final = {
    ModelProvider.OPENAI: "OPENAI_API_KEY",
    ModelProvider.DEEPSEEK: "DEEPSEEK_API_KEY",
    ModelProvider.ANTHROPIC: "ANTHROPIC_API_KEY",
    ModelProvider.GOOGLE: "GOOGLE_API_KEY",
    ModelProvider.XAI: "XAI_API_KEY",
    ModelProvider.MISTRAL: "MISTRAL_API_KEY",
    ModelProvider.GROQ: "GROQ_API_KEY",
    ModelProvider.OPENROUTER: "OPENROUTER_API_KEY",
    ModelProvider.TOGETHER: "TOGETHER_API_KEY",
    ModelProvider.AZURE: "AZURE_OPENAI_API_KEY",
}

# Uncached, standard-tier rates checked 2026-10-17:
# https://developers.openai.com/api/docs/models/gpt-5.4-mini
# https://developers.openai.com/api/docs/models/gpt-5-mini
OPENAI_PRICES: Final = {
    "gpt-5.4-mini": ModelPrice(Decimal("0.75"), Decimal("4.50"), 400000),
    DEFAULT_MODEL: ModelPrice(Decimal("0.75"), Decimal("4.50"), 400000),
    "gpt-5-mini": ModelPrice(Decimal("0.25"), Decimal("2.00"), 400000),
    "gpt-5-mini-2025-08-07": ModelPrice(Decimal("0.25"), Decimal("2.00"), 400000),
}

# Peak, uncached rates checked 2026-10-17:
# https://api-docs.deepseek.com/quick_start/pricing/
DEEPSEEK_PRICES: Final = {
    DEFAULT_DEEPSEEK_MODEL: ModelPrice(Decimal("0.30"), Decimal("1.20"), 1048576),
    "deepseek-v4-pro": ModelPrice(Decimal("1.32"), Decimal("3.96"), 1048576),
}


PROVIDERS: Final = {
    ModelProvider.OPENAI: "https://api.openai.com/v1",
    ModelProvider.DEEPSEEK: "https://api.deepseek.com",
    ModelProvider.ANTHROPIC: "https://api.anthropic.com",
    ModelProvider.GOOGLE: "https://generativelanguage.googleapis.com",
    ModelProvider.XAI: "https://api.x.ai/v1",
    ModelProvider.MISTRAL: "https://api.mistral.ai",
    ModelProvider.GROQ: "https://api.groq.com/openai/v1",
    ModelProvider.OPENROUTER: "https://openrouter.ai/api/v1",
    ModelProvider.TOGETHER: "https://api.together.xyz/v1",
    ModelProvider.AZURE: "",
    ModelProvider.BEDROCK: "",
    ModelProvider.VERTEX: "",
}

AWS_CREDENTIAL_NAMES: Final = (
    "AWS_ACCESS_KEY_ID",
    "AWS_SECRET_ACCESS_KEY",
    "AWS_SESSION_TOKEN",
)

PROVIDER_OPTIONS_PREFIXES: Final = {
    ModelProvider.AZURE: "azure_",
    ModelProvider.BEDROCK: "aws_",
    ModelProvider.VERTEX: "google_",
}
