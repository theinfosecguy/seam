"""Construct the fixed Docker isolation policy and pytest invocation."""

from importlib.resources import files
from pathlib import Path, PurePosixPath
from typing import Literal

from backport_harness.execution.snapshot import MAX_SNAPSHOT_BYTES
from backport_harness.models import OracleConfig, RunnerConfig


def _suite_paths(paths: tuple[str, ...]) -> list[str]:
    result = []
    for value in paths:
        filename, *selectors = value.split("::")
        path = PurePosixPath(filename)
        if value.startswith("-") or path.is_absolute() or ".." in path.parts:
            raise ValueError(
                "Suite entries must be relative paths within the workspace"
            )
        if "\\" in filename or ":" in filename or not filename:
            raise ValueError("Suite entries must be paths, without pytest options")
        if any(not selector for selector in selectors):
            raise ValueError("Pytest node selectors must not be empty")
        result.append(value)
    return result


def build_container_arguments(
    config: RunnerConfig,
    name: str,
    image_id: str,
    snapshot: Path,
    oracle_dir: Path,
    report: Path,
    oracle: OracleConfig,
    kind: Literal["security", "suite"],
) -> list[str]:
    """Build the fixed isolation policy and explicitly selected pytest command."""
    pytest_args = [
        "-q",
        "--tb=short",
        "--import-mode=importlib",
        "-p",
        "no:cacheprovider",
        "--junitxml=/report.xml",
    ]
    if kind == "security":
        pytest_args.extend(["-c", "/dev/null", "--noconftest", "--rootdir=/oracle"])
        pytest_args.extend(
            f"/oracle/oracle.py::{test}"
            for test in (oracle.security_test, *oracle.controls)
        )
    else:
        pytest_args.extend(_suite_paths(config.suite))
    return [
        "create",
        "--name",
        name,
        "--network",
        "none",
        "--read-only",
        "--user",
        "65534:65534",
        "--cap-drop",
        "ALL",
        "--security-opt",
        "no-new-privileges",
        "--memory",
        f"{config.memory_mb}m",
        "--memory-swap",
        f"{config.memory_mb}m",
        "--cpus",
        str(config.cpus),
        "--pids-limit",
        str(config.pids),
        "--ulimit",
        f"fsize={MAX_SNAPSHOT_BYTES}:{MAX_SNAPSHOT_BYTES}",
        "--log-driver",
        "none",
        "--tmpfs",
        "/work:rw,nosuid,nodev,size=256m,mode=1777",
        "--tmpfs",
        "/tmp:rw,nosuid,nodev,noexec,size=64m,mode=1777",
        "--mount",
        f"type=bind,src={snapshot},dst=/source,readonly",
        "--mount",
        f"type=bind,src={oracle_dir},dst=/oracle,readonly",
        "--mount",
        f"type=bind,src={report},dst=/report.xml",
        "--workdir",
        "/work",
        "--env",
        "PYTEST_DISABLE_PLUGIN_AUTOLOAD=1",
        "--env",
        "PYTEST_ADDOPTS=",
        "--env",
        "PYTEST_PLUGINS=",
        "--env",
        "PYTHONDONTWRITEBYTECODE=1",
        "--env",
        "PYTHONPATH=/work/repo/src:/work/repo",
        "--env",
        "HOME=/tmp",
        "--entrypoint",
        "python",
        image_id,
        "-I",
        "-B",
        "-c",
        files("backport_harness.execution.resources")
        .joinpath("bootstrap.py.txt")
        .read_text(encoding="utf-8"),
        *pytest_args,
    ]
