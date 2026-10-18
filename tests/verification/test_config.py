"""Reject unsafe or misspelled trusted configuration before execution."""

from pathlib import Path

import pytest

from seam.models import ReviewedTestsConfig, RunnerConfig
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


def test_reviewed_inputs_are_explicit_and_resolve_from_config(tmp_path: Path) -> None:
    (tmp_path / "oracle.py").write_text("# trusted oracle\n")
    config_path = tmp_path / "harness.toml"
    config_path.write_text(
        '[oracle]\npath = "oracle.py"\nsecurity_test = "test_security"\n'
        'controls = ["test_control"]\nfailure_marker = "REGRESSION"\n'
        '[reviewed_tests]\npath = "assertions.patch"\n'
        f'sha256 = "{"a" * 64}"\nreason = "Upstream changed the header policy"\n'
        '[runner]\nimage = "test-image"\n[runner.reviewed_fixtures]\n'
        f'"tests/files/public.pem" = ["{"b" * 64}", "{"c" * 64}"]\n'
    )
    config = load_config(config_path)
    assert config.reviewed_tests is not None
    assert config.reviewed_tests.path == tmp_path / "assertions.patch"
    assert config.runner.reviewed_fixtures == {
        "tests/files/public.pem": ("b" * 64, "c" * 64)
    }
    frozen = config.model_dump(mode="json")
    assert frozen["reviewed_tests"]["reason"] == "Upstream changed the header policy"
    assert frozen["runner"]["reviewed_fixtures"]["tests/files/public.pem"] == [
        "b" * 64,
        "c" * 64,
    ]


@pytest.mark.parametrize(
    "override",
    [
        {"sha256": "not-a-digest"},
        {"sha256": "A" * 64},
        {"reason": ""},
        {"reason": " \t\n"},
        {"reason": "x" * 1001},
        {"allow_test_deletion": True},
    ],
)
def test_reviewed_test_configuration_rejects_unreviewable_inputs(override) -> None:
    values = {"path": "reviewed.patch", "sha256": "a" * 64, "reason": "Reviewed"}
    with pytest.raises(ValueError):
        ReviewedTestsConfig.model_validate(values | override)


@pytest.mark.parametrize(
    "fixtures",
    [
        {"../credentials.pem": ("a" * 64,)},
        {"tests/files/public.pem": ()},
        {"tests/files/public.pem": ("A" * 64,)},
        {".aws/client.pem": ("a" * 64,)},
        {"tests/token.txt": ("a" * 64,)},
    ],
)
def test_fixture_allowances_cannot_disable_path_or_digest_policy(fixtures) -> None:
    with pytest.raises(ValueError):
        RunnerConfig(image="test-image", reviewed_fixtures=fixtures)
