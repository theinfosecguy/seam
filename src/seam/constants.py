"""Shared defaults, provider schedules, and security policy limits."""

import re
from decimal import Decimal
from typing import Final

from seam.models import ModelPrice, ModelProvider, Provider

DEFAULT_MODEL: Final = "gpt-5.4-mini-2026-03-17"
DEFAULT_DEEPSEEK_MODEL: Final = "deepseek-flash"
DEFAULT_IMAGE: Final = "security-backport-demo:local"
FAILURE_MARKER: Final = "TRAVERSAL_SECURITY_ORACLE"

OPENAI: Final = Provider("openai", "https://api.openai.com/v1", False)
DEEPSEEK: Final = Provider("deepseek", "https://api.deepseek.com", True)
API_KEY_NAMES: Final = {
    ModelProvider.OPENAI: "OPENAI_API_KEY",
    ModelProvider.DEEPSEEK: "DEEPSEEK_API_KEY",
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
DEEPSEEK_MODELS: Final = frozenset(DEEPSEEK_PRICES)

MAX_PATCH_BYTES: Final = 262144
MAX_PATCH_CHARACTERS: Final = 262144
MAX_CONTEXT_BYTES: Final = 262144
MAX_CONVERSATION_BYTES: Final = 1048576
MAX_ARGUMENT_BYTES: Final = MAX_PATCH_BYTES + 8192
MAX_TEXT_BYTES: Final = 65536
MAX_ENTRIES: Final = 1000
MAX_API_CALLS: Final = 32
MIN_OUTPUT_TOKENS: Final = 256
MAX_OUTPUT_TOKENS: Final = 32768
MAX_REQUEST_TIMEOUT_SECONDS: Final = 300
MAX_PARALLEL_READ_CALLS: Final = 8
MAX_CREDENTIAL_BYTES: Final = 65536
MAX_CONFIG_BYTES: Final = 65536
MAX_ORACLE_BYTES: Final = 131072
MAX_REPORT_BYTES: Final = 1_048_576
MAX_SNAPSHOT_BYTES: Final = 256 * 1_048_576
MAX_SNAPSHOT_FILES: Final = 20_000

ALLOWED_SUFFIXES: Final = frozenset(
    {".py", ".md", ".rst", ".txt", ".toml", ".cfg", ".ini"}
)
SENSITIVE_NAME: Final = re.compile(
    r"(?:secret|credential|password|private[_-]?key|access[_-]?token|id_rsa)", re.I
)
SENSITIVE_CONTENT: Final = re.compile(
    r"sk-[A-Za-z0-9_-]{16,}|-----BEGIN [A-Z ]*PRIVATE KEY-----"
)
IMAGE_ID_PATTERN: Final = re.compile(r"sha256:[a-f0-9]{64}")
SNAPSHOT_EXCLUDED_NAMES: Final = frozenset(
    {
        ".git",
        ".hg",
        ".svn",
        ".venv",
        "venv",
        "__pycache__",
        ".pytest_cache",
        ".mypy_cache",
        ".ruff_cache",
        ".ssh",
        ".aws",
        ".azure",
        ".netrc",
        ".pypirc",
        "id_rsa",
        "id_ed25519",
        "credentials",
        "credentials.json",
        "secrets.json",
    }
)
