"""Run bounded host commands without a shell or inherited credentials."""

import os
import selectors
import shutil
import signal
import subprocess
import tempfile
import time
from collections.abc import Mapping, Sequence
from pathlib import Path

from backport_harness.models import ProcessResult


def safe_environment() -> dict[str, str]:
    """Keep executable discovery and locale while excluding caller secrets."""

    return {
        "PATH": os.environ.get("PATH", "/usr/local/bin:/usr/bin:/bin"),
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_CONFIG_GLOBAL": os.devnull,
        "GIT_TERMINAL_PROMPT": "0",
        "GIT_OPTIONAL_LOCKS": "0",
    }


def _kill_group(process: subprocess.Popen[bytes], command: Sequence[str]) -> None:
    """Terminate this spawned group, respecting an explicitly selected sudo CLI.

    Sudo may make the client root-owned, so the unprivileged controller cannot
    signal it directly. Only that operator-selected prefix permits a privileged
    kill, and the target is always the group this controller created.
    """
    try:
        os.killpg(process.pid, signal.SIGKILL)
        return
    except ProcessLookupError:
        return
    except PermissionError:
        if not command or Path(command[0]).name != "sudo":
            raise

    kill = shutil.which("kill", path=safe_environment()["PATH"])
    if kill is None:
        raise RuntimeError("Cannot find the process cleanup executable")
    try:
        cleanup = subprocess.run(
            [command[0], "-n", kill, "-KILL", "--", str(-process.pid)],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            env=safe_environment(),
            timeout=2,
            check=False,
            start_new_session=True,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise RuntimeError("Could not terminate the privileged process group") from exc
    if cleanup.returncode:
        try:
            os.killpg(process.pid, 0)
        except ProcessLookupError:
            return
        except PermissionError as exc:
            raise RuntimeError(
                "Sudo must permit process cleanup for privileged commands"
            ) from exc
        raise RuntimeError("Could not terminate the privileged process group")


def run_process(
    command: Sequence[str],
    *,
    cwd: Path | None = None,
    timeout: float = 120,
    max_output: int = 131072,
    input_text: str | None = None,
    env: Mapping[str, str] | None = None,
) -> ProcessResult:
    """Drain bounded output and kill the process group on timeout or cancellation.

    File-backed stdin prevents a writer deadlock when a child emits output before
    reading its input. Output beyond the limit is drained but never retained.
    """

    if timeout <= 0 or max_output < 1:
        raise ValueError("timeout and output limit must be positive")
    started = time.monotonic()
    buffers: dict[str, bytearray] = {"stdout": bytearray(), "stderr": bytearray()}
    timed_out = False
    truncated = False
    with tempfile.TemporaryFile() as stdin:
        if input_text is not None:
            stdin.write(input_text.encode("utf-8"))
        stdin.seek(0)
        with subprocess.Popen(
            list(command),
            cwd=cwd,
            env=dict(env) if env is not None else safe_environment(),
            stdin=stdin,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            start_new_session=True,
        ) as process:
            assert process.stdout is not None and process.stderr is not None
            with selectors.DefaultSelector() as selector:
                selector.register(process.stdout, selectors.EVENT_READ, "stdout")
                selector.register(process.stderr, selectors.EVENT_READ, "stderr")
                try:
                    while selector.get_map():
                        if time.monotonic() - started >= timeout:
                            timed_out = True
                            _kill_group(process, command)
                            break
                        for key, _ in selector.select(timeout=0.05):
                            chunk = os.read(key.fd, 65536)
                            if not chunk:
                                selector.unregister(key.fileobj)
                                continue
                            buffer = buffers[key.data]
                            available = max_output - sum(map(len, buffers.values()))
                            buffer.extend(chunk[: max(0, available)])
                            truncated |= len(chunk) > available
                    remaining = max(0.001, timeout - (time.monotonic() - started))
                    try:
                        process.wait(timeout=remaining)
                    except subprocess.TimeoutExpired:
                        timed_out = True
                        _kill_group(process, command)
                        process.wait(timeout=2)
                except BaseException:
                    _kill_group(process, command)
                    process.wait(timeout=2)
                    raise
                finally:
                    # Descendants can outlive the immediate process and hold pipes.
                    _kill_group(process, command)
    return ProcessResult(
        returncode=process.returncode,
        command=list(command),
        stdout=buffers["stdout"].decode("utf-8", errors="replace"),
        stderr=buffers["stderr"].decode("utf-8", errors="replace"),
        timed_out=timed_out,
        truncated=truncated,
        duration_seconds=round(time.monotonic() - started, 4),
    )
