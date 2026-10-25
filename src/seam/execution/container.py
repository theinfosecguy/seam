"""Construct the fixed Docker isolation policy and explicit test invocation."""

from importlib.resources import files
from pathlib import Path, PurePosixPath
from typing import Literal

from seam.constants.execution import MAX_SNAPSHOT_BYTES
from seam.models import OracleConfig, RunnerConfig


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
    *,
    node_modules: str = "",
    mocha_ui: Literal["bdd", "tdd"] | None = None,
) -> list[str]:
    """Build the fixed isolation policy and explicitly selected test command."""
    if config.kind != "pytest":
        if kind == "security":
            arguments = [*_node_test_arguments(), f"/oracle/oracle{oracle.path.suffix}"]
        else:
            if any(
                PurePosixPath(path).suffix not in {".js", ".mjs", ".cjs"}
                or "::" in path
                or any(character in path for character in "*?[]{}")
                for path in config.suite
            ):
                raise ValueError("Node suite entries must be explicit JavaScript files")
            if config.kind == "tape":
                arguments = [
                    "--eval",
                    files("seam.execution.resources")
                    .joinpath("tape.cjs.txt")
                    .read_text(encoding="utf-8"),
                    "--",
                ]
            elif config.kind == "mocha":
                arguments = [
                    "/opt/seam/node_modules/mocha/bin/mocha.js",
                    "--no-config",
                    "--no-package",
                    f"--ui={mocha_ui or config.mocha_ui}",
                    "--posix-exit-codes",
                    "--forbid-only",
                    "--timeout",
                    "0",
                    "--reporter",
                    "xunit",
                    "--reporter-options",
                    "output=/report.xml",
                ]
            else:
                arguments = _node_test_arguments()
            if config.mocha_grep is not None:
                arguments.append(f"--grep={config.mocha_grep}")
            arguments.extend(
                f"/work/repo/{path}" for path in _suite_paths(config.suite)
            )
        command = [
            "node",
            image_id,
            "--eval",
            files("seam.execution.resources")
            .joinpath("bootstrap.cjs.txt")
            .read_text(encoding="utf-8"),
            "--",
            node_modules,
            *arguments,
        ]
        environment = ["NODE_OPTIONS=", "NODE_PATH="]
    else:
        command = _pytest_command(config, image_id, oracle, kind)
        environment = [
            "PYTEST_DISABLE_PLUGIN_AUTOLOAD=1",
            "PYTEST_ADDOPTS=",
            "PYTEST_PLUGINS=",
            "PYTHONDONTWRITEBYTECODE=1",
            "PYTHONPATH=/work/repo/src:/work/repo",
        ]
    environment_arguments = []
    for value in [*environment, "HOME=/tmp"]:
        environment_arguments.extend(["--env", value])
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
        *environment_arguments,
        "--entrypoint",
        *command,
    ]


def _node_test_arguments() -> list[str]:
    return [
        "--test",
        "--test-reporter=junit",
        "--test-reporter-destination=/report.xml",
        "--test-reporter=spec",
        "--test-reporter-destination=stderr",
    ]


def _pytest_command(
    config: RunnerConfig,
    image_id: str,
    oracle: OracleConfig,
    kind: Literal["security", "suite"],
) -> list[str]:
    arguments = [
        "-q",
        "--tb=short",
        f"--import-mode={config.import_mode}",
        "-p",
        "no:cacheprovider",
        "--junitxml=/report.xml",
    ]
    for module in config.plugins:
        arguments.extend(["-p", module])
    if kind == "security":
        arguments.extend(["-c", "/dev/null", "--noconftest", "--rootdir=/oracle"])
        arguments.extend(
            f"/oracle/oracle.py::{test}"
            for test in (oracle.security_test, *oracle.controls)
        )
    else:
        if config.suite_markers is not None:
            arguments.extend(["-m", config.suite_markers])
        arguments.extend(_suite_paths(config.suite))
    return [
        "python",
        image_id,
        "-I",
        "-B",
        "-c",
        files("seam.execution.resources")
        .joinpath("bootstrap.py.txt")
        .read_text(encoding="utf-8"),
        *arguments,
    ]
