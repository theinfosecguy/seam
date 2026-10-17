"""Load explicitly selected controller credentials and construct providers."""

import os
from enum import StrEnum
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from backport_harness.agent import DeepSeekPatchAgent, OpenAIPatchAgent


class ModelProvider(StrEnum):
    """Limit paid adaptation to explicitly supported provider endpoints."""

    OPENAI = "openai"
    DEEPSEEK = "deepseek"


_KEY_NAMES = {
    ModelProvider.OPENAI: "OPENAI_API_KEY",
    ModelProvider.DEEPSEEK: "DEEPSEEK_API_KEY",
}


def load_api_key(
    env_file: Path | None, provider: ModelProvider = ModelProvider.OPENAI
) -> str:
    """Read only explicitly selected local credentials, never target config."""
    key_name = _KEY_NAMES[provider]
    if env_file is None:
        value = os.environ.get(key_name, "").strip()
    else:
        value = ""
        found: set[str] = set()
        if env_file.stat().st_size > 65536:
            raise ValueError("Credential file exceeds 64 KiB")
        for line in env_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            name, separator, candidate = line.partition("=")
            name = name.strip()
            if name not in _KEY_NAMES.values() or not separator or name in found:
                raise ValueError(
                    "Credential file accepts only OPENAI_API_KEY and "
                    "DEEPSEEK_API_KEY assignments, once each, and optional comments"
                )
            found.add(name)
            if name == key_name:
                value = candidate.strip()
                if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
                    value = value[1:-1]
    if not value or "\n" in value or "\r" in value:
        raise ValueError(
            f"Set {key_name} in the controller environment or use --env-file"
        )
    return value


def make_openai_proposer(
    model: str, api_budget_usd: float | None, env_file: Path | None
) -> "OpenAIPatchAgent":
    """Create a paid proposer only when the operator explicitly selects a model."""
    from backport_harness.agent import OpenAIPatchAgent

    return OpenAIPatchAgent(
        api_key=load_api_key(env_file), model=model, budget_usd=api_budget_usd
    )


def make_deepseek_proposer(
    model: str, api_budget_usd: float | None, env_file: Path | None
) -> "DeepSeekPatchAgent":
    """Keep DeepSeek credentials separate from the OpenAI integration."""
    from backport_harness.agent import DEEPSEEK_MODELS, DeepSeekPatchAgent

    if model not in DEEPSEEK_MODELS:
        raise ValueError("Unsupported DeepSeek model")
    return DeepSeekPatchAgent(
        api_key=load_api_key(env_file, ModelProvider.DEEPSEEK),
        model=model,
        budget_usd=api_budget_usd,
    )
