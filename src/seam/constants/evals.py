"""Bound public evaluation catalogues and reproducible image builds."""

from typing import Final

DATASET_VERSION: Final = "0.1.0"
MAX_EVAL_ASSET_BYTES: Final = 1_048_576
MAX_EVAL_CASES: Final = 100
EVAL_BUILD_TIMEOUT_SECONDS: Final = 900
REQUIRED_EVAL_ASSETS: Final = frozenset(
    {
        "harness.toml",
        "oracle.py",
        "Dockerfile",
        "requirements.lock",
        "reference.patch",
        "LICENSE.upstream",
    }
)
