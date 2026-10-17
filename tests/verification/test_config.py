"""Reject unsafe or misspelled trusted configuration before execution."""

from pathlib import Path

import pytest

from seam.models import RunnerConfig
from seam.verification.config import load_config


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


@pytest.mark.parametrize(
    "plugins",
    [
        ("anyio.pytest_plugin", "anyio.pytest_plugin"),
        ("no:cacheprovider",),
        ("--help",),
        ("./plugin",),
        ("plugin\x00name",),
        ("plugin-name",),
        ("plugin." + "x" * 200,),
        tuple(f"plugin{index}" for index in range(33)),
    ],
)
def test_plugin_names_are_bounded_explicit_modules(plugins: tuple[str, ...]) -> None:
    with pytest.raises(ValueError):
        RunnerConfig(image="test-image", plugins=plugins)


@pytest.mark.parametrize("mode", ["importlib", "prepend", "append"])
def test_runner_accepts_supported_pytest_import_modes(mode: str) -> None:
    config = RunnerConfig.model_validate({"image": "test-image", "import_mode": mode})
    assert config.import_mode == mode


def test_runner_rejects_unknown_import_mode() -> None:
    with pytest.raises(ValueError, match="import_mode"):
        RunnerConfig.model_validate({"image": "test-image", "import_mode": "legacy"})


@pytest.mark.parametrize(
    "expression", ["", " ", "--help", "xfail\n", "'xfail'", "x" * 1025]
)
def test_suite_marker_expression_cannot_inject_options(expression: str) -> None:
    with pytest.raises(ValueError, match="suite_markers"):
        RunnerConfig(image="test-image", suite_markers=expression)


def test_runner_integration_settings_are_serialized_for_frozen_evidence() -> None:
    config = RunnerConfig(
        image="test-image",
        plugins=("anyio.pytest_plugin", "pytest_django.plugin"),
        import_mode="prepend",
        suite_markers="not xfail and (unit or smoke)",
    )
    frozen = config.model_dump(mode="json")
    assert frozen["plugins"] == ["anyio.pytest_plugin", "pytest_django.plugin"]
    assert frozen["import_mode"] == "prepend"
    assert frozen["suite_markers"] == "not xfail and (unit or smoke)"
    assert (
        config.model_dump_json() != RunnerConfig(image="test-image").model_dump_json()
    )
