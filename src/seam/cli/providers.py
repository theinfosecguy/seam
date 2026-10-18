"""Construct a model from explicit operator settings and selected credentials."""

from __future__ import annotations

import tomllib
from dataclasses import replace
from pathlib import Path
from typing import TYPE_CHECKING, Annotated

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from seam.cli.credentials import load_api_key, load_credentials
from seam.constants.agent import (
    CLI_MODEL_CALLS,
    CLI_OUTPUT_TOKENS,
    CLI_REQUEST_TIMEOUT_SECONDS,
    MAX_API_CALLS,
)
from seam.constants.providers import AWS_CREDENTIAL_NAMES, PROVIDER_OPTIONS_PREFIXES
from seam.constants.verification import MAX_CONFIG_BYTES
from seam.models import ModelProvider, ProviderOptions
from seam.security.files import read_controller_text

if TYPE_CHECKING:
    from seam.agent import PatchAgent


class ProviderConfiguration(BaseModel):
    """Non-secret cloud resource settings from an explicit operator TOML file."""

    model_config = ConfigDict(extra="forbid", strict=True)

    azure_endpoint: Annotated[str | None, Field(min_length=1, max_length=2048)] = None
    azure_api_version: Annotated[str | None, Field(min_length=1, max_length=100)] = None
    aws_region: Annotated[str | None, Field(min_length=1, max_length=100)] = None
    google_project: Annotated[str | None, Field(min_length=1, max_length=200)] = None
    google_location: Annotated[str | None, Field(min_length=1, max_length=100)] = None
    google_credentials_path: Annotated[
        str | None, Field(min_length=1, max_length=4096)
    ] = None


def load_provider_options(
    path: Path | None, provider: ModelProvider
) -> ProviderOptions:
    """Load provider-specific metadata; credential values never belong in this file."""
    if path is None:
        return ProviderOptions()
    try:
        record = ProviderConfiguration.model_validate(
            tomllib.loads(read_controller_text(path, MAX_CONFIG_BYTES))
        )
    except (tomllib.TOMLDecodeError, ValidationError):
        raise ValueError(
            "Invalid provider configuration; use the documented non-secret fields"
        ) from None
    data = record.model_dump(exclude_none=True)
    prefix = PROVIDER_OPTIONS_PREFIXES.get(provider)
    if data and (prefix is None or any(not name.startswith(prefix) for name in data)):
        raise ValueError("Provider configuration contains settings for another service")
    if record.google_credentials_path is not None:
        credentials_path = Path(record.google_credentials_path)
        if not credentials_path.is_absolute():
            credentials_path = path.resolve().parent / credentials_path
        data["google_credentials_path"] = credentials_path
    return ProviderOptions(**data)


def make_proposer(
    provider: ModelProvider,
    model: str,
    budget_usd: float | None,
    env_file: Path | None,
    *,
    max_model_calls: int = CLI_MODEL_CALLS,
    provider_config: Path | None = None,
    input_price_per_million: float | None = None,
    output_price_per_million: float | None = None,
    context_tokens: int | None = None,
) -> PatchAgent:
    """Keep all provider construction behind one entry point for the CLI."""
    if type(max_model_calls) is not int or not 1 <= max_model_calls <= MAX_API_CALLS:
        raise ValueError(
            f"model call limit must be an integer from 1 to {MAX_API_CALLS}"
        )
    options = load_provider_options(provider_config, provider)
    api_key = None
    if provider == ModelProvider.BEDROCK:
        values = load_credentials(env_file, AWS_CREDENTIAL_NAMES)
        if not values["AWS_ACCESS_KEY_ID"] or not values["AWS_SECRET_ACCESS_KEY"]:
            raise ValueError("Set AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY")
        options = replace(
            options,
            aws_access_key_id=values["AWS_ACCESS_KEY_ID"],
            aws_secret_access_key=values["AWS_SECRET_ACCESS_KEY"],
            aws_session_token=values["AWS_SESSION_TOKEN"] or None,
        )
    elif provider == ModelProvider.VERTEX:
        if env_file is not None:
            raise ValueError(
                "Vertex credentials use google_credentials_path in --provider-config"
            )
    else:
        api_key = load_api_key(env_file, provider)
    from seam.agent import PatchAgent

    return PatchAgent(
        provider=provider,
        model=model,
        api_key=api_key,
        budget_usd=budget_usd,
        max_calls=max_model_calls,
        max_output_tokens=CLI_OUTPUT_TOKENS,
        timeout_seconds=CLI_REQUEST_TIMEOUT_SECONDS,
        provider_options=options,
        input_price_per_million=input_price_per_million,
        output_price_per_million=output_price_per_million,
        context_tokens=context_tokens,
    )
