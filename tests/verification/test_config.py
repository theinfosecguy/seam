"""Reject unsafe or misspelled trusted configuration before execution."""

from pathlib import Path

import pytest

from seam.models import ReviewedTestsConfig, RunnerConfig
from seam.verification.config import load_config


@pytest.mark.parametrize("kind", ["node", "mocha"])
def test_javascript_config_selects_language_and_preserves_oracle(
    tmp_path: Path, kind: str
) -> None:
    (tmp_path / "oracle.mjs").write_text("// external oracle\n")
    path = tmp_path / "harness.toml"
    path.write_text(
        '[oracle]\npath = "oracle.mjs"\nsecurity_test = "test_security"\n'
        'controls = ["test_control"]\nfailure_marker = "REGRESSION"\n'
        f'[runner]\nkind = "{kind}"\nimage = "test-image"\n'
        'suite = ["test/existing.cjs"]\n'
    )
    config = load_config(path)
    assert config.runner.language == "javascript"
    assert config.oracle.path == tmp_path / "oracle.mjs"
    path.write_text(path.read_text().replace('kind = "' + kind + '"\n', ""))
    with pytest.raises(ValueError, match="regular python file"):
        load_config(path)


@pytest.mark.parametrize(
    "settings",
    [
        {"plugins": ["project.plugin"]},
        {"suite_markers": "smoke"},
        {"import_mode": "prepend"},
    ],
)
def test_javascript_runner_rejects_python_settings(settings: dict[str, object]) -> None:
    with pytest.raises(ValueError, match="pytest settings"):
        RunnerConfig.model_validate({"kind": "node", "image": "image", **settings})


@pytest.mark.parametrize(
    "mapping",
    [
        {"main": "/opt/seam/revision/node_modules"},
        {"a" * 40: "/home/dev/node_modules"},
        {"a" * 40: "/opt/seam/../private/node_modules"},
        {"a" * 40: "/opt/seam/./private/node_modules"},
        {"a" * 40: "/opt/seam/revision/not-modules"},
    ],
)
def test_node_dependencies_are_commit_pinned_image_paths(
    mapping: dict[str, str],
) -> None:
    with pytest.raises(ValueError, match="commit IDs"):
        RunnerConfig(kind="node", image="image", node_dependencies=mapping)


def test_python_runner_rejects_node_dependency_mapping() -> None:
    with pytest.raises(ValueError, match="JavaScript runner"):
        RunnerConfig(
            image="image", node_dependencies={"a" * 40: "/opt/seam/a/node_modules"}
        )


@pytest.mark.parametrize(
    "pattern", ["", "line\nbreak", "line\rbreak", "nul\x00byte", "x" * 1025]
)
def test_mocha_grep_is_bounded_and_cannot_contain_line_breaks(pattern: str) -> None:
    with pytest.raises(ValueError, match="mocha_grep"):
        RunnerConfig(kind="mocha", image="image", mocha_grep=pattern)


@pytest.mark.parametrize("kind", ["pytest", "node"])
def test_mocha_grep_requires_the_mocha_runner(kind: str) -> None:
    with pytest.raises(ValueError, match="Mocha runner"):
        RunnerConfig.model_validate(
            {"kind": kind, "image": "image", "mocha_grep": "^relevant "}
        )


def test_mocha_grep_is_preserved_in_frozen_configuration() -> None:
    config = RunnerConfig(kind="mocha", image="image", mocha_grep="^relevant ")
    assert config.model_dump(mode="json")["mocha_grep"] == "^relevant "


@pytest.mark.parametrize(
    "modules",
    [
        {".": ("a" * 40,)},
        {"../outside": ("a" * 40,)},
        {"/absolute": ("a" * 40,)},
        {"fixtures/./module": ("a" * 40,)},
        {"fixtures//module": ("a" * 40,)},
        {"fixtures/.hidden": ("a" * 40,)},
        {"fixtures\\module": ("a" * 40,)},
        {"fixtures/module": ()},
        {"fixtures/module": ("a" * 40, "a" * 40)},
        {"fixtures/module": ("main",)},
        {"fixtures/module": ("A" * 40,)},
        {"fixtures/module": tuple(f"{number:040x}" for number in range(17))},
        {f"fixtures/module{number}": ("a" * 40,) for number in range(17)},
    ],
)
def test_reviewed_submodules_require_exact_bounded_paths_and_objects(
    modules: dict[str, tuple[str, ...]],
) -> None:
    with pytest.raises(ValueError):
        RunnerConfig(image="fixture-image", reviewed_submodules=modules)


def test_reviewed_submodules_are_preserved_in_frozen_configuration() -> None:
    modules = {"test/cache-fixtures": ("a" * 40, "b" * 64)}
    config = RunnerConfig(image="fixture-image", reviewed_submodules=modules)
    assert config.model_dump(mode="json")["reviewed_submodules"] == {
        "test/cache-fixtures": ["a" * 40, "b" * 64]
    }


@pytest.mark.parametrize(
    "selector",
    ["--help", "../test.js", "/test.js", "test/*.js", "test.js::test_one", "test.ts"],
)
def test_javascript_suite_requires_exact_contained_files(
    tmp_path: Path, selector: str
) -> None:
    (tmp_path / "oracle.mjs").write_text("// external oracle\n")
    path = tmp_path / "harness.toml"
    path.write_text(
        '[oracle]\npath = "oracle.mjs"\nsecurity_test = "test_security"\n'
        'controls = ["test_control"]\nfailure_marker = "REGRESSION"\n'
        '[runner]\nkind = "node"\nimage = "test-image"\n'
        f'suite = ["{selector}"]\n'
    )
    with pytest.raises(ValueError):
        load_config(path)


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
