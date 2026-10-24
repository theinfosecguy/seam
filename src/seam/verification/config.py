"""Load an explicitly selected trusted harness configuration."""

import tomllib
from pathlib import Path

from seam.constants.repository import SOURCE_SUFFIXES
from seam.constants.verification import MAX_CONFIG_BYTES, MAX_ORACLE_BYTES
from seam.models import HarnessConfig


def load_config(path: Path) -> HarnessConfig:
    """Read one explicitly selected TOML file, resolving its oracle relative to it."""

    if path.stat().st_size > MAX_CONFIG_BYTES:
        raise ValueError("configuration exceeds 64 KiB")
    config = HarnessConfig.model_validate(tomllib.loads(path.read_text("utf-8")))
    original = config.oracle.path
    if not original.is_absolute():
        original = path.resolve().parent / original
    language = config.runner.language
    if (
        original.is_symlink()
        or not original.is_file()
        or original.suffix not in SOURCE_SUFFIXES[language]
    ):
        raise ValueError(f"oracle must be a regular {language} file")
    if original.stat().st_size > MAX_ORACLE_BYTES:
        raise ValueError("oracle exceeds 128 KiB")
    config.oracle.path = original.resolve()
    if (
        config.reviewed_tests is not None
        and not config.reviewed_tests.path.is_absolute()
    ):
        config.reviewed_tests.path = path.resolve().parent / config.reviewed_tests.path
    if config.oracle.security_test in config.oracle.controls:
        raise ValueError("security test cannot also be a normal-behavior control")
    if config.reviewed_tests is not None and language != "python":
        raise ValueError("reviewed assertion patches currently support Python only")
    for selector in config.runner.suite:
        file = selector.split("::", 1)[0]
        candidate = Path(file)
        if (
            selector.startswith("-")
            or candidate.is_absolute()
            or ".." in candidate.parts
            or "\\" in selector
        ):
            raise ValueError(
                "suite selectors must be relative pytest paths, not options"
            )
        if language == "javascript" and (
            candidate.suffix not in SOURCE_SUFFIXES[language]
            or "::" in selector
            or any(character in selector for character in "*?[]")
        ):
            raise ValueError("Node suites require explicit JavaScript file paths")
    return config
