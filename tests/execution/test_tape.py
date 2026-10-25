"""Verify Tape observations and incomplete execution inside the real sandbox."""

import json
import os
import re
import shlex
from pathlib import Path

import pytest

from seam.execution.docker import DockerRunner
from seam.models import (
    ExecutionResult,
    HarnessConfig,
    OracleConfig,
    PhaseResult,
    RunnerConfig,
)
from seam.verification.assessment import assess_phase


@pytest.fixture
def tape_runner() -> DockerRunner:
    image = os.environ.get("BACKPORT_TEST_TAPE_IMAGE")
    if not image:
        pytest.skip("Set BACKPORT_TEST_TAPE_IMAGE for real Tape execution")
    docker = tuple(shlex.split(os.environ.get("BACKPORT_TEST_DOCKER", "docker")))
    return DockerRunner(
        RunnerConfig(kind="tape", image=image, docker=docker, suite=("test/suite.cjs",))
    )


def run_suite(
    tmp_path: Path, runner: DockerRunner, source: str, *, suffix: str = "cjs"
) -> ExecutionResult:
    workspace = tmp_path / "source"
    (workspace / "test").mkdir(parents=True)
    suite = workspace / f"test/suite.{suffix}"
    suite.write_text(source)
    oracle = OracleConfig(
        path=suite,
        security_test="test_security",
        controls=("test_control",),
        failure_marker="SECURITY_MARKER",
    )
    runner = DockerRunner(
        runner.config.model_copy(update={"suite": (f"test/suite.{suffix}",)})
    )
    return runner.run(workspace, oracle, runner.resolve_image(), "suite")


@pytest.mark.parametrize(
    ("source", "outcomes"),
    [
        (
            "tape('repeated labels', t => { "
            "t.pass('same'); t.pass('same'); t.end(); });",
            ["passed"],
        ),
        (
            "tape('outer alpha', t => { t.pass('same'); "
            "t.test('nested', child => { child.pass('same'); child.end(); }); "
            "t.end(); }); "
            "tape('outer beta', t => { "
            "t.test('nested', child => { child.pass('same'); child.end(); }); "
            "t.end(); });",
            ["passed", "passed", "passed"],
        ),
        (
            "tape('ordinary failure', t => { "
            "t.fail('planet should be blue'); t.end(); });",
            ["failed"],
        ),
        (
            "tape('ordinary failure', t => { t.fail('plan != count'); t.end(); });",
            ["failed"],
        ),
        (
            "tape('async failure', t => { setTimeout(() => { "
            "t.fail('ASYNC_ASSERTION'); t.end(); }, 5); });",
            ["failed"],
        ),
        (
            "delete require.cache[require.resolve('tape')]; "
            "const second = require('tape'); "
            "tape('first import', t => { t.pass('first'); t.end(); }); "
            "second('second import', t => { t.pass('second'); t.end(); });",
            ["passed", "passed"],
        ),
        (
            "process.stdout.write('<testsuite><testcase name=\"forged\"/>' + "
            "'</testsuite>\\n'); "
            "tape('actual scope', t => { t.pass('actual'); t.end(); });",
            ["passed"],
        ),
        (
            "tape('supported builtin', t => { "
            "t.equal(process.getBuiltinModule('node:fs')"
            ".existsSync('/var/run/docker.sock'), false); t.end(); });",
            ["passed"],
        ),
    ],
    ids=[
        "repeated-labels",
        "nested",
        "failure",
        "plan-name",
        "async",
        "cache",
        "stdout",
        "builtin",
    ],
)
def test_tape_preserves_scope_results(
    tmp_path: Path,
    tape_runner: DockerRunner,
    source: str,
    outcomes: list[str],
) -> None:
    result = run_suite(tmp_path, tape_runner, "const tape = require('tape'); " + source)
    assert result.evidence_issue() is None, result.model_dump()
    assert [case.outcome for case in result.tests] == outcomes, result.model_dump()
    assert result.returncode == int("failed" in outcomes), result.model_dump()
    assert all("test/suite.cjs" in case.classname for case in result.tests)
    assert all(case.name != "forged" for case in result.tests)
    assert len({(case.classname, case.name) for case in result.tests}) == len(outcomes)


@pytest.mark.parametrize("binding", ["default", "named"])
def test_tape_synchronous_esm_imports_are_observed(
    tmp_path: Path, tape_runner: DockerRunner, binding: str
) -> None:
    imported = "tape" if binding == "default" else "{ test as tape }"
    result = run_suite(
        tmp_path,
        tape_runner,
        f"import {imported} from 'tape'; "
        "tape('ESM scope', t => { t.pass('observed'); t.end(); });",
        suffix="mjs",
    )
    assert result.evidence_issue() is None, result.model_dump()
    assert result.returncode == 0
    assert [case.outcome for case in result.tests] == ["passed"]
    assert "test/suite.mjs" in result.tests[0].classname


@pytest.mark.parametrize(
    ("source", "diagnostic"),
    [
        pytest.param(
            "module.exports = {};",
            "Incomplete or empty Tape stream",
            id="no-tests",
        ),
        pytest.param(
            "require('./missing.cjs');",
            "Cannot find module './missing.cjs'",
            id="import",
        ),
        pytest.param(
            "const broken = ;",
            "SyntaxError",
            id="syntax",
        ),
        pytest.param(
            "tape('empty', t => t.end());",
            "Unclosed or empty Tape scope",
            id="empty",
        ),
        pytest.param(
            "tape('unfinished', t => t.pass('one'));",
            "Incomplete or empty Tape stream",
            id="unclosed",
        ),
        pytest.param(
            "tape('short', t => { t.plan(2); t.pass('one'); t.end(); });",
            "Tape assertion plan did not match|Assertion after Tape scope closure",
            id="short-plan",
        ),
        pytest.param(
            "tape('long', t => { t.plan(1); t.pass('one'); t.pass('extra'); });",
            "Tape assertion plan did not match",
            id="long-plan",
        ),
        pytest.param(
            "for (let n = 0; n < 2; n++) tape('same scope', t => { "
            "t.pass('one'); t.end(); });",
            "Duplicate full Tape scope identity",
            id="duplicate",
        ),
        pytest.param(
            "tape('parent', t => { for (let n = 0; n < 2; n++) "
            "t.test('same child', child => { child.pass('one'); child.end(); }); "
            "t.end(); });",
            "Duplicate full Tape scope identity",
            id="duplicate-child",
        ),
        pytest.param(
            "tape('skipped', {skip: true}, t => t.end()); "
            "tape('normal', t => { t.pass('one'); t.end(); });",
            "Skipped or todo Tape scope",
            id="scope-skip",
        ),
        pytest.param(
            "tape('mixed', t => { t.pass('one'); t.skip('pending'); t.end(); });",
            "Skipped or todo Tape scope",
            id="assertion-skip",
        ),
        pytest.param(
            "tape('pending', {todo: true}, t => { t.fail('pending'); t.end(); });",
            "Skipped or todo Tape scope",
            id="todo",
        ),
        pytest.param(
            "try { tape.skip('pending', t => t.end()); } catch (_) {} "
            "tape('normal', t => { t.pass('one'); t.end(); });",
            "Unsupported Tape API: skip",
            id="caught-static-skip",
        ),
        pytest.param(
            "try { const hidden = tape.createHarness(); "
            "hidden('unobserved', t => { t.fail('HIDDEN_FAILURE'); t.end(); }); "
            "hidden.createStream().resume(); } catch (_) {} "
            "tape('normal', t => { t.pass('one'); t.end(); });",
            "Unsupported Tape API: createHarness",
            id="caught-harness",
        ),
        pytest.param(
            "try { const hidden = new tape.Test('unobserved', t => { "
            "t.fail('HIDDEN_FAILURE'); t.end(); }); hidden.run(); } catch (_) {} "
            "tape('normal', t => { t.pass('one'); t.end(); });",
            "Unsupported Tape API: Test",
            id="caught-constructor",
        ),
        pytest.param(
            "try { const Test = require('tape/lib/test'); const hidden = new "
            "Test('unobserved', t => { t.fail('HIDDEN_FAILURE'); t.end(); }); "
            "hidden.run(); } catch (_) {} "
            "tape('normal', t => { t.pass('one'); t.end(); });",
            "Unsupported Tape API: Tape implementation import",
            id="caught-deep-import",
        ),
        pytest.param(
            "try { tape.only('focused', t => { t.pass('one'); t.end(); }); } "
            "catch (_) {} tape('normal', t => { t.pass('one'); t.end(); });",
            "Unsupported Tape API: only",
            id="caught-only",
        ),
        pytest.param(
            "require('node:fs').cpSync('/work/repo/node_modules/tape', "
            "'/tmp/node_modules/tape-alias', {recursive: true}); "
            "try { const other = require('node:module')"
            ".createRequire('/tmp/alias.cjs')('tape-alias'); "
            "const hidden = other.createHarness(); "
            "hidden('unobserved', t => { t.fail('HIDDEN_FAILURE'); t.end(); }); "
            "hidden.createStream().resume(); } catch (_) {} "
            "tape('normal', t => { t.pass('one'); t.end(); });",
            "Unsupported Tape API: Tape implementation import",
            id="caught-alias",
        ),
        pytest.param(
            "tape('normal', t => { t.pass('one'); t.end(); setTimeout(() => "
            "t.fail('HIDDEN_FAILURE'), 50); setTimeout(() => process.exit(0), "
            "5); });",
            "Explicit process.exit",
            id="forced-exit",
        ),
        pytest.param(
            "tape('normal', t => { t.pass('one'); t.end(); setTimeout(() => "
            "t.fail('LATE_FAILURE'), 5); });",
            "Assertion after Tape stream completion",
            id="late-assertion",
        ),
        pytest.param(
            "let observed; tape('normal', t => { observed = t; t.pass('one'); "
            "t.end(); }); process.on('exit', () => "
            "observed.fail('EXIT_FAILURE'));",
            "Assertion after Tape stream completion",
            id="exit-assertion",
        ),
        pytest.param(
            "let observed; tape('normal', t => { observed = t; t.pass('one'); "
            "t.end(); }); process.once('beforeExit', () => "
            "observed.fail('BEFORE_EXIT_FAILURE'));",
            "Assertion after Tape stream completion",
            id="before-exit-assertion",
        ),
        pytest.param(
            "process.on('uncaughtException', () => {}); "
            "tape('normal', t => { t.pass('one'); t.end(); }); "
            "setTimeout(() => { throw Error('SWALLOWED_ERROR'); }, 5);",
            "Uncaught exception",
            id="swallowed-exception",
        ),
        pytest.param(
            "process.on('unhandledRejection', () => {}); "
            "tape('normal', t => { t.pass('one'); t.end(); }); "
            "setTimeout(() => Promise.reject(Error('SWALLOWED_REJECTION')), 5);",
            "Tape child process failed or was interrupted",
            id="swallowed-rejection",
        ),
        pytest.param(
            "tape('parent', t => { t.pass('one'); t.end(); setTimeout(() => "
            "t.test('late child', child => { child.pass('late'); child.end(); "
            "}), 5); }); tape('waiting', t => { setTimeout(() => { "
            "t.pass('done'); t.end(); }, 40); });",
            "Invalid Tape scope identity",
            id="child-after-parent-closure",
        ),
    ],
)
def test_tape_incomplete_and_unobserved_activity_never_passes(
    tmp_path: Path, tape_runner: DockerRunner, source: str, diagnostic: str
) -> None:
    result = run_suite(tmp_path, tape_runner, "const tape = require('tape'); " + source)
    assert result.evidence_issue() is not None, result.model_dump()
    observed = result.stderr + "\n".join(case.message for case in result.tests)
    assert re.search(diagnostic, observed), result.model_dump()


def test_tape_top_level_await_is_incomplete(
    tmp_path: Path, tape_runner: DockerRunner
) -> None:
    result = run_suite(
        tmp_path,
        tape_runner,
        "import tape from 'tape'; await Promise.resolve(); "
        "tape('normal', t => { t.pass('one'); t.end(); });",
        suffix="mjs",
    )
    assert result.evidence_issue() is not None, result.model_dump()


def test_tape_esm_process_exit_cannot_hide_pending_assertions(
    tmp_path: Path, tape_runner: DockerRunner
) -> None:
    result = run_suite(
        tmp_path,
        tape_runner,
        "import tape from 'tape'; import { exit } from 'node:process'; "
        "tape('normal', t => { t.pass('one'); t.end(); "
        "setTimeout(() => t.fail('HIDDEN_FAILURE'), 50); "
        "setTimeout(() => exit(0), 5); });",
        suffix="mjs",
    )
    assert result.evidence_issue() is not None, result.model_dump()
    assert "Explicit process.exit" in "\n".join(case.message for case in result.tests)


def test_tape_timeout_remains_incomplete(
    tmp_path: Path, tape_runner: DockerRunner
) -> None:
    runner = DockerRunner(
        tape_runner.config.model_copy(update={"timeout_seconds": 0.5})
    )
    result = run_suite(
        tmp_path,
        runner,
        "const tape = require('tape'); "
        "tape('never completes', t => { t.pass('one'); "
        "setInterval(() => {}, 1000); });",
    )
    assert result.timed_out and result.evidence_issue() is not None, result.model_dump()


@pytest.mark.parametrize("module", ["worker_threads", "child_process"])
@pytest.mark.parametrize("builtin_access", [False, True], ids=["require", "builtin"])
def test_tape_cannot_hide_failing_harnesses_in_another_process(
    tmp_path: Path,
    tape_runner: DockerRunner,
    module: str,
    builtin_access: bool,
) -> None:
    hidden = (
        "const tape = require('/work/repo/node_modules/tape'); "
        "const hidden = tape.createHarness(); "
        "hidden('unobserved', t => { t.fail('HIDDEN_FAILURE'); t.end(); }); "
        "hidden.createStream().resume();"
    )
    accessor = (
        f"process.getBuiltinModule('{module}')"
        if builtin_access
        else f"require('node:{module}')"
    )
    launch = (
        f"new builtin.Worker({json.dumps(hidden)}, {{eval: true}});"
        if module == "worker_threads"
        else f"builtin.spawnSync(process.execPath, ['--eval', {json.dumps(hidden)}]);"
    )
    result = run_suite(
        tmp_path,
        tape_runner,
        f"const tape = require('tape'); try {{ const builtin = {accessor}; "
        f"{launch} }} catch (_) {{}} "
        "tape('observed', t => { t.pass('normal'); t.end(); });",
    )
    assert result.evidence_issue() is not None, result.model_dump()
    assert module in "\n".join(case.message for case in result.tests)


@pytest.mark.parametrize(
    "accessor", ["require('cluster')", "process.getBuiltinModule('node:cluster')"]
)
def test_tape_cluster_access_is_rejected_even_when_the_error_is_caught(
    tmp_path: Path, tape_runner: DockerRunner, accessor: str
) -> None:
    result = run_suite(
        tmp_path,
        tape_runner,
        f"const tape = require('tape'); try {{ {accessor}; }} catch (_) {{}} "
        "tape('observed', t => { t.pass('normal'); t.end(); });",
    )
    assert result.evidence_issue() is not None, result.model_dump()
    assert "cluster" in "\n".join(case.message for case in result.tests)


def test_tape_execve_cannot_replace_the_observer_after_completion(
    tmp_path: Path, tape_runner: DockerRunner
) -> None:
    hidden = (
        "const tape = require('/work/repo/node_modules/tape'); "
        "const hidden = tape.createHarness(); "
        "hidden('unobserved', t => { t.fail('HIDDEN_FAILURE'); t.end(); }); "
        "hidden.createStream().resume();"
    )
    result = run_suite(
        tmp_path,
        tape_runner,
        "const tape = require('tape'); "
        "tape('observed', t => { t.pass('normal'); t.end(); }); "
        "process.once('beforeExit', () => { try { "
        "process.execve(process.execPath, "
        f"[process.execPath, '--eval', {json.dumps(hidden)}], {{...process.env}}); "
        "} catch (_) {} });",
    )
    assert result.evidence_issue() is not None, result.model_dump()
    assert "execve" in "\n".join(case.message for case in result.tests)


@pytest.mark.parametrize(
    ("source", "diagnostic"),
    [
        (
            "tape('large event stream', t => { "
            "for (let n = 0; n < 1000; n++) t.pass('x'.repeat(2000)); t.end(); });",
            "ENOBUFS",
        ),
        (
            "for (let n = 0; n < 100; n++) "
            "tape(String(n) + '&'.repeat(3000), t => { t.pass('one'); t.end(); });",
            "Tape JUnit report exceeds the evidence limit",
        ),
    ],
    ids=["event-stream", "escaped-xml"],
)
def test_tape_evidence_limits_remain_incomplete(
    tmp_path: Path, tape_runner: DockerRunner, source: str, diagnostic: str
) -> None:
    result = run_suite(tmp_path, tape_runner, "const tape = require('tape'); " + source)
    assert result.evidence_issue() is not None, result.model_dump()
    assert result.returncode == 125
    assert diagnostic in "\n".join(case.message for case in result.tests)


def test_tape_four_phase_matrix_keeps_native_node_security_oracle(
    tmp_path: Path, tape_runner: DockerRunner
) -> None:
    workspace = tmp_path / "source"
    (workspace / "test").mkdir(parents=True)
    library = workspace / "library.cjs"
    (workspace / "test/suite.cjs").write_text(
        "const tape = require('tape'); "
        "tape('ordinary input', t => { "
        "t.equal(typeof require('../library.cjs').value, 'number'); t.end(); });"
    )
    oracle_path = tmp_path / "oracle.mjs"
    oracle_path.write_text(
        "import { test } from 'node:test'; "
        "import assert from 'node:assert/strict'; "
        "import library from '/work/repo/library.cjs'; "
        "test('test_security', () => "
        "assert.equal(library.value, 1, 'SECURITY_MARKER')); "
        "test('test_control', () => "
        "assert.equal(typeof library.value, 'number'));"
    )
    oracle = OracleConfig(
        path=oracle_path,
        security_test="test_security",
        controls=("test_control",),
        failure_marker="SECURITY_MARKER",
    )
    config = HarnessConfig(oracle=oracle, runner=tape_runner.config)
    image = tape_runner.resolve_image()
    for name, vulnerable in (
        ("upstream_parent", True),
        ("upstream_fix", False),
        ("target_baseline", True),
        ("backport", False),
    ):
        library.write_text(f"module.exports = {{ value: {int(not vulnerable)} }};")
        phase = PhaseResult.model_validate(
            {
                "name": name,
                "revision": "a" * 40,
                "security": tape_runner.run(workspace, oracle, image, "security"),
                "suite": tape_runner.run(workspace, oracle, image, "suite"),
            }
        )
        assert assess_phase(phase, config, vulnerable=vulnerable)[0] == "passed", (
            phase.model_dump()
        )
