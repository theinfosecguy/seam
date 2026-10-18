"""Read only explicitly selected controller credentials without shell evaluation."""

import os
from pathlib import Path

from seam.constants.providers import API_KEY_NAMES, AWS_CREDENTIAL_NAMES
from seam.constants.security import MAX_CREDENTIAL_BYTES
from seam.models import ModelProvider
from seam.security.files import read_controller_text


def load_credentials(env_file: Path | None, names: tuple[str, ...]) -> dict[str, str]:
    """Select named credentials from the controller environment or explicit file."""
    if env_file is None:
        selected = {name: os.environ.get(name, "").strip() for name in names}
    else:
        allowed = {*API_KEY_NAMES.values(), *AWS_CREDENTIAL_NAMES}
        assignments: dict[str, str] = {}
        for line in read_controller_text(env_file, MAX_CREDENTIAL_BYTES).splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            name, separator, value = line.partition("=")
            name = name.strip()
            if not separator or name not in allowed or name in assignments:
                raise ValueError(
                    "Credential file accepts supported provider key assignments "
                    "once each, plus optional comments"
                )
            value = value.strip()
            if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
                value = value[1:-1]
            assignments[name] = value
        selected = {name: assignments.get(name, "") for name in names}
    if any(
        any(ord(character) < 32 or ord(character) == 127 for character in value)
        for value in selected.values()
    ):
        raise ValueError("Controller credentials must not contain control characters")
    return selected


def load_api_key(
    env_file: Path | None, provider: ModelProvider = ModelProvider.OPENAI
) -> str:
    """Read the selected service's key without discovering target config files."""
    if provider not in API_KEY_NAMES:
        raise ValueError(
            "This provider uses explicit cloud credentials, not an API key"
        )
    key_name = API_KEY_NAMES[provider]
    value = load_credentials(env_file, (key_name,))[key_name]
    if not value:
        raise ValueError(
            f"Set {key_name} in the controller environment or use --env-file"
        )
    return value
