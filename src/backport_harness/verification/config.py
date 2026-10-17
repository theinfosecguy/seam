"""Load an explicitly selected trusted harness configuration."""

import tomllib
from pathlib import Path

from backport_harness.models import HarnessConfig


def load_config(path: Path) -> HarnessConfig:
    """Read one explicitly selected TOML file, resolving its oracle relative to it."""

    if path.stat().st_size > 65536:
        raise ValueError("configuration exceeds 64 KiB")
    config = HarnessConfig.model_validate(tomllib.loads(path.read_text("utf-8")))
    original = config.oracle.path
    if not original.is_absolute():
        original = path.resolve().parent / original
    if original.is_symlink() or not original.is_file() or original.suffix != ".py":
        raise ValueError("oracle must be a regular Python file")
    if original.stat().st_size > 131072:
        raise ValueError("oracle exceeds 128 KiB")
    config.oracle.path = original.resolve()
    if config.oracle.security_test in config.oracle.controls:
        raise ValueError("security test cannot also be a normal-behavior control")
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
    return config
