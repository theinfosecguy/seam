"""Run real JavaScript modules and incomplete suites inside the fixed sandbox."""

import os
import shlex
from pathlib import Path

import pytest

from seam import repository
from seam.execution.container import build_container_arguments
from seam.execution.docker import DockerRunner
from seam.models import (
    HarnessConfig,
    OracleConfig,
    PhaseResult,
    ProcessResult,
    RunnerConfig,
)
from seam.verification.assessment import assess_phase


@pytest.fixture
def node_runner() -> DockerRunner:
    image = os.environ.get("BACKPORT_TEST_NODE_IMAGE")
    if not image:
        pytest.skip("Set BACKPORT_TEST_NODE_IMAGE for real JavaScript execution")
    docker = tuple(shlex.split(os.environ.get("BACKPORT_TEST_DOCKER", "docker")))
    return DockerRunner(
        RunnerConfig(kind="node", image=image, docker=docker, suite=("test/suite.cjs",))
    )


def test_node_and_mocha_commands_have_fixed_reporters_and_no_discovered_config(
    tmp_path: Path,
) -> None:
    oracle = OracleConfig(
        path=tmp_path / "oracle.mjs",
        security_test="test_security",
        controls=("test_control",),
        failure_marker="SECURITY_MARKER",
    )
    for runner_kind in ("node", "mocha"):
        config = RunnerConfig.model_validate(
            {"kind": runner_kind, "image": "pinned-image", "suite": ["test/unit.js"]}
        )
        for kind in ("security", "suite"):
            command = build_container_arguments(
                config,
                "container-name",
                "pinned-image",
                tmp_path,
                tmp_path,
                tmp_path / "report.xml",
                oracle,
                kind,
            )
            assert command[command.index("--entrypoint") + 1] == "node"
            assert "NODE_OPTIONS=" in command and "NODE_PATH=" in command
            assert command[command.index("--network") + 1] == "none"
            if kind == "security":
                assert command[-1] == "/oracle/oracle.mjs"
                assert "--test-reporter=junit" in command
                assert "--test-reporter=spec" in command
                assert "--test-reporter-destination=stderr" in command
                assert not any(argument.startswith("--ui=") for argument in command)
            elif runner_kind == "node":
                assert command[-1] == "/work/repo/test/unit.js"
            else:
                assert "--no-config" in command and "--no-package" in command
                assert "--posix-exit-codes" in command and "--forbid-only" in command
                assert "output=/report.xml" in command
                assert "--ui=bdd" in command


@pytest.mark.parametrize("suffix", ["cjs", "mjs"])
def test_node_cjs_and_esm_four_phase_security_matrix(
    tmp_path: Path,
    node_runner: DockerRunner,
    suffix: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace = tmp_path / "source"
    (workspace / "test").mkdir(parents=True)
    library = workspace / f"library.{suffix}"
    imports = (
        "import library from '/work/repo/library.cjs';\nconst { value } = library;"
        if suffix == "cjs"
        else "import { value } from '/work/repo/library.mjs';"
    )
    common = (
        "import { test } from 'node:test';\n"
        "import assert from 'node:assert/strict';\n"
        "import fs from 'node:fs';\n" + imports + "\n"
    )
    oracle_path = tmp_path / "oracle.mjs"
    oracle_path.write_text(
        common
        + "test('test_security', () => assert.equal(value, 1, 'SECURITY_MARKER'));\n"
        + "test('test_control', () => {\n"
        "assert.equal(process.cwd(), '/work/repo');\n"
        "assert.notEqual(process.getuid(), 0);\n"
        "assert.equal(process.env.OPENAI_API_KEY, undefined);\n"
        "assert.equal(fs.existsSync('/source/.env'), false);\n"
        "assert.equal(fs.existsSync('/var/run/docker.sock'), false);\n"
        "assert.throws(() => fs.writeFileSync('/oracle/oracle.mjs', 'changed'));\n"
        "});\n"
    )
    value_expression = "library.default.value" if suffix == "cjs" else "library.value"
    (workspace / "test/suite.cjs").write_text(
        "const { test } = require('node:test');\n"
        "const assert = require('node:assert/strict');\n"
        f"test('compatibility', async () => {{\n"
        f"const library = await import('/work/repo/library.{suffix}');\n"
        f"assert.equal(typeof {value_expression}, 'number');\n"
        "});\n"
    )
    (workspace / ".env").write_text("must-remain-on-host")
    monkeypatch.setenv("OPENAI_API_KEY", "must-remain-on-host")
    oracle = OracleConfig(
        path=oracle_path,
        security_test="test_security",
        controls=("test_control",),
        failure_marker="SECURITY_MARKER",
    )
    config = HarnessConfig(oracle=oracle, runner=node_runner.config)
    image = node_runner.resolve_image()
    for name, vulnerable in (
        ("upstream_parent", True),
        ("upstream_fix", False),
        ("target_baseline", True),
        ("backport", False),
    ):
        value = int(not vulnerable)
        original_source = (
            f"module.exports = {{ value: {value} }};\n"
            if suffix == "cjs"
            else f"export const value = {value};\n"
        )
        library.write_text(original_source)
        phase = PhaseResult.model_validate(
            {
                "name": name,
                "revision": "a" * 40,
                "security": node_runner.run(workspace, oracle, image, "security"),
                "suite": node_runner.run(workspace, oracle, image, "suite"),
            }
        )
        assert assess_phase(phase, config, vulnerable=vulnerable)[0] == "passed", (
            phase.model_dump()
        )
        assert library.read_text() == original_source


@pytest.mark.parametrize(
    "source",
    [
        "require('./missing.cjs');",
        "const broken = ;",
        "module.exports = {};",
        "require('node:test').test.skip('pending', () => {});",
        "require('node:test').test.todo('pending');",
    ],
)
def test_node_setup_empty_and_skipped_suites_are_incomplete(
    tmp_path: Path,
    node_runner: DockerRunner,
    source: str,
) -> None:
    workspace = tmp_path / "source"
    (workspace / "test").mkdir(parents=True)
    (workspace / "test/suite.cjs").write_text(source)
    oracle = OracleConfig(
        path=workspace / "test/suite.cjs",
        security_test="test_security",
        controls=("test_control",),
        failure_marker="SECURITY_MARKER",
    )
    result = node_runner.run(workspace, oracle, node_runner.resolve_image(), "suite")
    assert result.evidence_issue() is not None, result.model_dump()
    if source == "require('./missing.cjs');":
        assert "Cannot find module './missing.cjs'" in result.stderr
        assert "/work/repo/test/suite.cjs" in result.stderr
        assert [case.outcome for case in result.tests] == ["error"]


@pytest.mark.parametrize("ui", ["bdd", "tdd"])
@pytest.mark.parametrize(
    ("source", "outcomes"),
    [
        ("it('works', () => {});", ["passed"]),
        ("it('pending');", ["skipped"]),
        ("it.skip('pending', () => {});", ["skipped"]),
        ("require('./missing.cjs');", []),
        ("const broken = ;", []),
        ("module.exports = {};", []),
        ("it.only('partial suite', () => {});", []),
        ("it('duplicate', () => {}); it('duplicate', () => {});", []),
        (
            "const assert = require('node:assert/strict');\n"
            "it('first', () => assert.fail('first assertion'));\n"
            "it('second', () => assert.fail('second assertion'));\n",
            ["failed", "failed"],
        ),
    ],
)
def test_mocha_native_xunit_preserves_results_and_rejects_incomplete_suites(
    tmp_path: Path,
    node_runner: DockerRunner,
    source: str,
    outcomes: list[str],
    ui: str,
) -> None:
    workspace = tmp_path / "source"
    (workspace / "test").mkdir(parents=True)
    if ui == "tdd":
        source = source.replace("it(", "test(").replace("it.", "test.")
    (workspace / "test/suite.cjs").write_text(source)
    (workspace / ".mocharc.json").write_text('{"require": "./missing-config.cjs"}')
    (workspace / "package.json").write_text(
        '{"mocha": {"require": "./missing-package-config.cjs"}}'
    )
    oracle = OracleConfig(
        path=workspace / "test/suite.cjs",
        security_test="test_security",
        controls=("test_control",),
        failure_marker="SECURITY_MARKER",
    )
    config = node_runner.config.model_copy(update={"kind": "mocha", "mocha_ui": ui})
    runner = DockerRunner(config)
    result = runner.run(workspace, oracle, runner.resolve_image(), "suite")
    assert f"--ui={ui}" in result.command
    assert [case.outcome for case in result.tests] == outcomes, result.model_dump()
    if outcomes == ["passed"]:
        assert result.returncode == 0 and result.evidence_issue() is None
    elif outcomes == ["failed", "failed"]:
        assert result.returncode == 1 and result.evidence_issue() is None
    else:
        assert result.evidence_issue() is not None, result.model_dump()


def test_node_timeout_removes_the_container(
    tmp_path: Path,
    node_runner: DockerRunner,
) -> None:
    workspace = tmp_path / "source"
    (workspace / "test").mkdir(parents=True)
    (workspace / "test/suite.cjs").write_text("setInterval(() => {}, 1000);")
    oracle = OracleConfig(
        path=workspace / "test/suite.cjs",
        security_test="test_security",
        controls=("test_control",),
        failure_marker="SECURITY_MARKER",
    )
    config = node_runner.config.model_copy(update={"timeout_seconds": 0.25})
    runner = DockerRunner(config)
    result = runner.run(workspace, oracle, runner.resolve_image(), "suite")
    assert result.timed_out and result.evidence_issue() is not None, result.model_dump()


def test_mocha_interfaces_follow_exact_head_and_keep_native_node_oracle(
    tmp_path: Path,
    node_runner: DockerRunner,
) -> None:
    workspace = tmp_path / "source"
    (workspace / "test").mkdir(parents=True)
    repository.git(workspace, "init")
    repository.git(workspace, "config", "user.name", "Test Maintainer")
    repository.git(workspace, "config", "user.email", "maintainer@example.invalid")
    library = workspace / "library.cjs"
    library.write_text("module.exports = { value: 1 };\n")
    interfaces = {}
    for ui, suite, test in (("bdd", "describe", "it"), ("tdd", "suite", "test")):
        (workspace / "test/suite.cjs").write_text(
            "const assert = require('node:assert/strict');\n"
            f"{suite}('compatibility', () => {{\n"
            f"{test}('ordinary input', () => {{\n"
            "assert.equal(require('../library.cjs').value, 1);\n"
            "}); });\n"
        )
        repository.git(workspace, "add", "library.cjs", "test/suite.cjs")
        repository.git(workspace, "commit", "-m", f"Use the {ui} test interface")
        interfaces[repository.resolve(workspace, "HEAD")] = ui
    oracle_path = tmp_path / "oracle.cjs"
    oracle_path.write_text(
        "const { test } = require('node:test');\n"
        "const assert = require('node:assert/strict');\n"
        "test('test_security', () => {\n"
        "assert.equal(require('/work/repo/library.cjs').value, 1, 'SECURITY_MARKER');\n"
        "});\n"
        "test('test_control', () => assert.equal(typeof test, 'function'));\n"
    )
    oracle = OracleConfig(
        path=oracle_path,
        security_test="test_security",
        controls=("test_control",),
        failure_marker="SECURITY_MARKER",
    )
    config = RunnerConfig.model_validate(
        {
            **node_runner.config.model_dump(),
            "kind": "mocha",
            "mocha_ui": "tdd",
            "mocha_interfaces": interfaces,
        }
    )
    runner = DockerRunner(config)
    image = runner.resolve_image()
    for revision, ui in interfaces.items():
        repository.git(workspace, "checkout", "--detach", revision)
        library.write_text(library.read_text() + "// candidate implementation edit\n")
        original = library.read_bytes()
        suite_result = runner.run(workspace, oracle, image, "suite")
        assert suite_result.returncode == 0 and suite_result.evidence_issue() is None
        assert f"--ui={ui}" in suite_result.command
        assert [(case.classname, case.name) for case in suite_result.tests] == [
            ("/work/repo/test/suite.cjs::compatibility", "ordinary input")
        ]
        security_result = runner.run(workspace, oracle, image, "security")
        assert security_result.returncode == 0
        assert security_result.evidence_issue() is None
        assert len(security_result.tests) == 2
        assert not any(arg.startswith("--ui=") for arg in security_result.command)
        assert library.read_bytes() == original
        repository.git(workspace, "restore", "library.cjs")
    del config.mocha_interfaces[revision]
    missing = runner.run(workspace, oracle, image, "suite")
    assert missing.returncode == 125 and missing.tests == []
    assert missing.evidence_error is not None
    assert f"No Mocha interface is configured for {revision}" in missing.evidence_error


@pytest.mark.parametrize("pattern", ["^relevant ", "^does not match$"])
def test_mocha_grep_uses_native_selection_without_relabeling_cases(
    tmp_path: Path,
    node_runner: DockerRunner,
    pattern: str,
) -> None:
    workspace = tmp_path / "source"
    (workspace / "test").mkdir(parents=True)
    (workspace / "test/suite.cjs").write_text(
        "describe('unselected', () => {\n"
        "it('duplicate', () => {}); it('duplicate', () => {});\n"
        "it.skip('unsupported feature', () => {});\n"
        "});\n"
        "describe('relevant', () => { it('compatibility', () => {}); });\n"
    )
    oracle_path = tmp_path / "oracle.cjs"
    oracle_path.write_text(
        "const { test } = require('node:test');\n"
        "test('test_security', () => {}); test('test_control', () => {});\n"
    )
    oracle = OracleConfig(
        path=oracle_path,
        security_test="test_security",
        controls=("test_control",),
        failure_marker="SECURITY_MARKER",
    )
    config = node_runner.config.model_copy(
        update={"kind": "mocha", "mocha_grep": pattern}
    )
    runner = DockerRunner(config)
    image = runner.resolve_image()
    result = runner.run(workspace, oracle, image, "suite")
    assert f"--grep={pattern}" in result.command
    if pattern == "^relevant ":
        assert result.evidence_issue() is None and result.returncode == 0
        assert [(case.name, case.outcome) for case in result.tests] == [
            ("compatibility", "passed")
        ]
        security = runner.run(workspace, oracle, image, "security")
        assert security.returncode == 0 and len(security.tests) == 2
        assert not any(argument.startswith("--grep=") for argument in security.command)
    else:
        assert result.evidence_issue() is not None and result.tests == []


def test_node_dependencies_follow_git_head_and_keep_candidate_edits(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace = tmp_path / "source"
    workspace.mkdir()
    repository.git(workspace, "init")
    repository.git(workspace, "config", "user.name", "Test Maintainer")
    repository.git(workspace, "config", "user.email", "maintainer@example.invalid")
    library = workspace / "library.cjs"
    revisions = []
    for version in (1, 2):
        library.write_text(f"module.exports = {version};\n")
        repository.git(workspace, "add", "library.cjs")
        repository.git(
            workspace,
            "-c",
            "core.hooksPath=/dev/null",
            "commit",
            "-m",
            f"Dependency fixture version {version}",
        )
        revisions.append(repository.resolve(workspace, "HEAD"))
    dependencies = {
        revisions[0]: "/opt/seam/old/node_modules",
        revisions[1]: "/opt/seam/new/node_modules",
    }
    oracle_path = tmp_path / "oracle.cjs"
    oracle_path.write_text("// frozen oracle")
    oracle = OracleConfig(
        path=oracle_path,
        security_test="test_security",
        controls=("test_control",),
        failure_marker="SECURITY_MARKER",
    )
    config = RunnerConfig(
        kind="node",
        image="pinned-image",
        suite=("test.cjs",),
        node_dependencies=dependencies,
    )
    runner = DockerRunner(config)
    selected_paths: list[str] = []

    def docker(arguments: list[str], *, timeout: float = 30) -> ProcessResult:
        if arguments[0] == "create":
            selected_paths.append(arguments[arguments.index("--") + 1])
            mount = next(arg for arg in arguments if "dst=/report.xml" in arg)
            report = Path(mount.split("src=", 1)[1].split(",", 1)[0])
            report.write_bytes(
                b'<testsuites><testcase name="test_security" '
                b'file="/oracle/oracle.cjs"/></testsuites>'
            )
        return ProcessResult(returncode=0)

    monkeypatch.setattr(runner, "_docker", docker)
    image = "sha256:" + "a" * 64
    repository.git(workspace, "checkout", "--detach", revisions[0])
    for candidate in (False, True):
        if candidate:
            library.write_text("module.exports = 'candidate';\n")
        result = runner.run(workspace, oracle, image, "security")
        assert result.evidence_error is None, result.model_dump()
        assert dependencies[revisions[0]] in result.command
    assert library.read_text() == "module.exports = 'candidate';\n"
    repository.git(workspace, "restore", "library.cjs")
    repository.git(workspace, "checkout", "--detach", revisions[1])
    assert runner.run(workspace, oracle, image, "security").evidence_error is None
    assert selected_paths == [
        dependencies[revisions[0]],
        dependencies[revisions[0]],
        dependencies[revisions[1]],
    ]
    config.node_dependencies = {revisions[0]: dependencies[revisions[0]]}
    missing = runner.run(workspace, oracle, image, "security")
    assert "No Node dependencies" in (missing.evidence_error or "")
    assert len(selected_paths) == 3


@pytest.mark.parametrize("present", [True, False])
def test_node_explicit_image_dependencies_never_fall_back(
    tmp_path: Path,
    node_runner: DockerRunner,
    monkeypatch: pytest.MonkeyPatch,
    present: bool,
) -> None:
    workspace = tmp_path / "source"
    (workspace / "test").mkdir(parents=True)
    (workspace / "test/suite.cjs").write_text(
        "const fs = require('node:fs');\n"
        "const assert = require('node:assert/strict');\n"
        "require('node:test').test('selected dependencies', () => {\n"
        "assert.equal(fs.realpathSync('/work/repo/node_modules'), "
        "'/opt/seam/node_modules');\n"
        "});\n"
    )
    oracle = OracleConfig(
        path=workspace / "test/suite.cjs",
        security_test="test_security",
        controls=("test_control",),
        failure_marker="SECURITY_MARKER",
    )
    revision = "b" * 40
    modules = "/opt/seam/node_modules" if present else "/opt/seam/missing/node_modules"
    monkeypatch.setattr(repository, "resolve", lambda workspace, ref: revision)
    runner = DockerRunner(
        node_runner.config.model_copy(update={"node_dependencies": {revision: modules}})
    )
    result = runner.run(workspace, oracle, runner.resolve_image(), "suite")
    assert modules in result.command
    if present:
        assert result.returncode == 0 and result.evidence_issue() is None
    else:
        assert result.returncode != 0 and result.evidence_issue() is not None
        assert result.tests == []
