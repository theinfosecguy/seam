"""Parse operator commands and run bounded demonstration setup tools."""

import shlex
from pathlib import Path

from seam.execution.processes import run_process


def docker_arguments(value: str) -> tuple[str, ...]:
    """Parse an operator-selected Docker command without invoking a shell."""
    arguments = tuple(shlex.split(value))
    if not arguments or any("\x00" in argument for argument in arguments):
        raise ValueError("Docker command must contain nonempty arguments")
    return arguments


def execute_setup(
    command: list[str],
    cwd: Path,
    *,
    timeout: float = 30,
    env: dict[str, str] | None = None,
) -> str:
    """Run a bounded command against the generated public fixture."""
    result = run_process(command, cwd=cwd, timeout=timeout, env=env)
    if result.returncode or result.timed_out or result.truncated:
        # Commands and output here contain only the generated, public fixture.
        detail = (result.stderr or result.stdout).strip()[-4000:]
        raise RuntimeError(f"Demo setup failed: {command[0]}: {detail}")
    return result.stdout.strip()
