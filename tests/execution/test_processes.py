"""Exercise real process failure, output, and cleanup behavior."""

import os
import shutil
import subprocess
import sys
import time
from collections.abc import Sequence
from pathlib import Path
from unittest.mock import Mock

import pytest

import backport_harness.execution.processes as processes_module
from backport_harness.execution.processes import _kill_group, run_process


def test_process_does_not_inherit_credentials() -> None:
    # Use the environment directly so the test needs no secret fixture or real key.
    os.environ["BACKPORT_TEST_PRIVATE_VALUE"] = "private-sentinel"
    try:
        result = run_process(
            [
                sys.executable,
                "-c",
                "import os; print(os.getenv('BACKPORT_TEST_PRIVATE_VALUE'))",
            ]
        )
    finally:
        del os.environ["BACKPORT_TEST_PRIVATE_VALUE"]
    assert result.stdout == "None\n"
    assert result.returncode == 0


def test_large_output_is_drained_and_bounded() -> None:
    result = run_process(
        [
            sys.executable,
            "-c",
            "import sys; print('a'*100000); sys.stderr.write('b'*100000)",
        ],
        max_output=1024,
    )
    assert result.returncode == 0
    assert result.truncated
    assert len(result.stdout.encode()) + len(result.stderr.encode()) == 1024


def test_large_input_does_not_deadlock_with_early_output() -> None:
    result = run_process(
        [
            sys.executable,
            "-c",
            "import sys; print('x'*100000); print(len(sys.stdin.read()))",
        ],
        input_text="y" * 100000,
        max_output=200000,
        timeout=3,
    )
    assert result.returncode == 0
    assert result.stdout.endswith("100000\n")


def test_timeout_kills_grandchild(tmp_path: Path) -> None:
    marker = tmp_path / "unexpected-child"
    child = (
        f"import time,pathlib; time.sleep(.5); pathlib.Path({str(marker)!r}).touch()"
    )
    script = (
        "import subprocess,sys,time; "
        f"subprocess.Popen([sys.executable,'-c',{child!r}]); time.sleep(5)"
    )
    result = run_process([sys.executable, "-c", script], timeout=0.1)
    assert result.timed_out
    time.sleep(0.6)
    assert not marker.exists()


def test_nonzero_exit_is_preserved() -> None:
    result = run_process([sys.executable, "-c", "raise SystemExit(7)"])
    assert result.returncode == 7


def test_timeout_still_applies_after_child_closes_output() -> None:
    result = run_process(
        [
            sys.executable,
            "-c",
            "import os,time; os.close(1); os.close(2); time.sleep(5)",
        ],
        timeout=0.15,
    )
    assert result.timed_out
    assert result.duration_seconds < 1


def test_arguments_are_not_shell_interpreted(tmp_path: Path) -> None:
    argument = f"$(touch {tmp_path / 'should-not-exist'})"
    result = run_process(
        [sys.executable, "-c", "import sys; print(sys.argv[1])", argument]
    )
    assert result.stdout.strip() == argument
    assert not (tmp_path / "should-not-exist").exists()


def test_cleanup_escalates_only_for_explicit_sudo_prefix(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    privileged = Mock(return_value=subprocess.CompletedProcess([], 0))

    def denied(pid: int, sig: int) -> None:
        raise PermissionError("root-owned process")

    monkeypatch.setattr(os, "killpg", denied)
    monkeypatch.setattr(processes_module.subprocess, "run", privileged)
    with pytest.raises(PermissionError):
        _kill_group(Mock(pid=1234), ["docker", "start", "container"])
    privileged.assert_not_called()


def test_privileged_cleanup_targets_only_its_own_process_group(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[list[str], dict[str, object]]] = []

    def denied(pid: int, sig: int) -> None:
        raise PermissionError("root-owned process")

    def cleanup(
        command: Sequence[str], **kwargs: object
    ) -> subprocess.CompletedProcess[bytes]:
        calls.append((list(command), kwargs))
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(os, "killpg", denied)
    monkeypatch.setattr(processes_module.shutil, "which", lambda *a, **kw: "/bin/kill")
    monkeypatch.setattr(processes_module.subprocess, "run", cleanup)
    _kill_group(Mock(pid=1234), ["/usr/bin/sudo", "-n", "docker", "start", "name"])
    assert calls[0][0] == ["/usr/bin/sudo", "-n", "/bin/kill", "-KILL", "--", "-1234"]
    assert calls[0][1]["timeout"] == 2
    assert calls[0][1]["stdin"] == subprocess.DEVNULL
    assert calls[0][1]["stdout"] == subprocess.DEVNULL
    assert "OPENAI_API_KEY" not in calls[0][1]["env"]


def test_failed_privileged_cleanup_is_reported(monkeypatch: pytest.MonkeyPatch) -> None:
    def denied(pid: int, sig: int) -> None:
        raise PermissionError("root-owned process")

    monkeypatch.setattr(os, "killpg", denied)
    monkeypatch.setattr(processes_module.shutil, "which", lambda *a, **kw: "/bin/kill")
    monkeypatch.setattr(
        processes_module.subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess([], 1),
    )
    with pytest.raises(RuntimeError, match="Sudo must permit process cleanup"):
        _kill_group(Mock(pid=1234), ["sudo", "-n", "docker", "pull", "image"])


def test_process_group_exit_race_does_not_fail_cleanup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = 0

    def exited(pid: int, sig: int) -> None:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise PermissionError("root-owned process")
        raise ProcessLookupError

    monkeypatch.setattr(os, "killpg", exited)
    monkeypatch.setattr(processes_module.shutil, "which", lambda *a, **kw: "/bin/kill")
    monkeypatch.setattr(
        processes_module.subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess([], 1),
    )
    _kill_group(Mock(pid=1234), ["sudo", "-n", "docker", "pull", "image"])


def test_timeout_can_cleanup_operator_selected_sudo() -> None:
    if os.environ.get("BACKPORT_TEST_SUDO") != "1":
        pytest.skip("Set BACKPORT_TEST_SUDO=1 for the privileged client timeout check")
    sleep = shutil.which("sleep")
    assert sleep is not None
    result = run_process(["sudo", "-n", sleep, "10"], timeout=0.15)
    assert result.timed_out
    assert result.duration_seconds < 3
    assert result.returncode != 0
