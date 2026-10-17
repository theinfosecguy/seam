"""Reject unsafe or misspelled trusted configuration before execution."""

from pathlib import Path

import pytest

from backport_harness.verification.config import load_config


def test_config_unknown_fields_and_unsafe_suite_are_rejected(tmp_path: Path) -> None:
    oracle = tmp_path / "checks.py"
    oracle.write_text("# fixture\n")
    config = tmp_path / "harness.toml"
    text = """[oracle]
path = "checks.py"
security_test = "test_security"
controls = ["test_legitimate"]
failure_marker = "SECURITY_REGRESSION"
[runner]
image = "test-image"
suite = ["--override-ini=addopts=--ignore=tests"]
"""
    config.write_text(text)
    with pytest.raises(ValueError, match="relative pytest paths"):
        load_config(config)
    config.write_text(
        text.replace(
            'suite = ["--override-ini=addopts=--ignore=tests"]', "surprise = true"
        )
    )
    with pytest.raises(ValueError, match="surprise"):
        load_config(config)
