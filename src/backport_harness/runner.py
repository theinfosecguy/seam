"""Run target pytest checks in constrained, disposable Docker containers."""

import os
import re
import stat
import tempfile
import threading
import uuid
from contextlib import suppress
from pathlib import Path, PurePosixPath
from typing import Literal
from xml.etree import ElementTree

from backport_harness.models import (
    ExecutionResult,
    OracleConfig,
    ProcessResult,
    RunnerConfig,
    TestCaseResult,
)
from backport_harness.processes import run_process

_MAX_REPORT_BYTES = 1_048_576
_MAX_SNAPSHOT_BYTES = 256 * 1_048_576
_MAX_SNAPSHOT_FILES = 20_000
_IMAGE_ID = re.compile(r"sha256:[a-f0-9]{64}")
_EXCLUDED_NAMES = frozenset(
    {
        ".git",
        ".hg",
        ".svn",
        ".venv",
        "venv",
        "__pycache__",
        ".pytest_cache",
        ".mypy_cache",
        ".ruff_cache",
        ".ssh",
        ".aws",
        ".azure",
        ".netrc",
        ".pypirc",
        "id_rsa",
        "id_ed25519",
        "credentials",
        "credentials.json",
        "secrets.json",
    }
)
_BOOTSTRAP = """
import os
import shutil
import sys

# Import the image's pytest before target imports can shadow its installation.
import pytest

shutil.copytree('/source', '/work/repo')
os.chdir('/work/repo')
sys.path[:0] = ['/work/repo/src', '/work/repo']
raise SystemExit(pytest.main(sys.argv[1:]))
"""


class RunnerError(RuntimeError):
    """Explain an execution environment that could not be prepared."""


def parse_junit(report: bytes) -> list[TestCaseResult]:
    """Parse bounded pytest JUnit evidence, rejecting ambiguous test identities."""
    if not report or len(report) > _MAX_REPORT_BYTES:
        raise ValueError("JUnit report is empty or exceeds the evidence limit")
    try:
        document = report.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ValueError("JUnit reports must use UTF-8 encoding") from exc
    if "<!DOCTYPE" in document.upper() or "<!ENTITY" in document.upper():
        raise ValueError("JUnit reports must not contain document declarations")
    try:
        root = ElementTree.fromstring(document)
    except ElementTree.ParseError as exc:
        raise ValueError("JUnit report is malformed XML") from exc
    if root.tag not in {"testsuites", "testsuite"}:
        raise ValueError("JUnit report has an unsupported root element")

    elements = list(root.iter("testcase"))
    if not elements:
        raise ValueError("JUnit report contains no test cases")
    identities: set[tuple[str, str]] = set()
    results: list[TestCaseResult] = []
    for element in elements:
        name = element.get("name", "")
        classname = element.get("classname", "")
        identity = (classname, name)
        if not name or identity in identities:
            raise ValueError("JUnit test case names must identify distinct tests")
        identities.add(identity)
        states = [
            child for child in element if child.tag in {"failure", "error", "skipped"}
        ]
        if len(states) > 1:
            raise ValueError("JUnit test case has conflicting outcomes")
        outcome: Literal["passed", "failed", "error", "skipped"] = "passed"
        message = ""
        if states:
            state = states[0]
            if state.tag == "failure":
                outcome = "failed"
            elif state.tag == "error":
                outcome = "error"
            else:
                outcome = "skipped"
            message = "\n".join(
                value
                for value in (state.get("message", ""), "".join(state.itertext()))
                if value
            )[:16_384]
        results.append(
            TestCaseResult(
                name=name,
                classname=classname,
                outcome=outcome,
                message=message,
            )
        )

    for suite in root.iter("testsuite"):
        cases = list(suite.iter("testcase"))
        expected = {
            "tests": len(cases),
            "failures": sum(case.find("failure") is not None for case in cases),
            "errors": sum(case.find("error") is not None for case in cases),
            "skipped": sum(case.find("skipped") is not None for case in cases),
        }
        for attribute, actual in expected.items():
            declared = suite.get(attribute)
            if declared is not None and (
                not declared.isascii()
                or not declared.isdecimal()
                or int(declared) != actual
            ):
                raise ValueError(f"JUnit {attribute} count contradicts test cases")
    return results


def _excluded(name: str) -> bool:
    return (
        name in _EXCLUDED_NAMES
        or name == ".env"
        or name.startswith(".env.")
        or name.endswith((".pem", ".key", ".p12", ".pfx"))
    )


def _copy_regular(
    source: Path, destination: Path, limit: int, *, directory_fd: int | None = None
) -> int:
    descriptor = os.open(
        source,
        os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
        dir_fd=directory_fd,
    )
    with os.fdopen(descriptor, "rb") as stream:
        metadata = os.fstat(stream.fileno())
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1:
            raise ValueError("Only ordinary files without hard links are supported")
        if metadata.st_size > limit:
            raise ValueError("Source exceeds the snapshot size limit")
        data = stream.read(limit + 1)
        if len(data) > limit:
            raise ValueError("Source exceeds the snapshot size limit")
    destination.write_bytes(data)
    destination.chmod(0o755 if metadata.st_mode & 0o111 else 0o644)
    return len(data)


def _snapshot(workspace: Path, destination: Path) -> None:
    if not workspace.is_dir():
        raise ValueError("The target workspace is not a directory")
    destination.mkdir(mode=0o755)
    destination.chmod(0o755)
    total_bytes = 0
    total_entries = 0
    workspace = workspace.resolve()
    for source, directories, files, directory_fd in os.fwalk(
        workspace, topdown=True, follow_symlinks=False
    ):
        relative = Path(source).relative_to(workspace)
        if len(relative.parts) > 100:
            raise ValueError("Snapshot directory nesting exceeds the supported limit")
        target = destination / relative
        directories[:] = [name for name in directories if not _excluded(name)]
        files = [name for name in files if not _excluded(name)]
        total_entries += len(directories) + len(files)
        if total_entries > _MAX_SNAPSHOT_FILES:
            raise ValueError("Snapshot contains too many files or directories")
        for name in directories:
            metadata = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
            if stat.S_ISLNK(metadata.st_mode):
                raise ValueError("Snapshot contains an unsupported symbolic link")
            copied = target / name
            copied.mkdir(mode=0o755)
            copied.chmod(0o755)
        for name in files:
            metadata = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
            if stat.S_ISLNK(metadata.st_mode):
                raise ValueError("Snapshot contains an unsupported symbolic link")
            total_bytes += _copy_regular(
                Path(name),
                target / name,
                _MAX_SNAPSHOT_BYTES - total_bytes,
                directory_fd=directory_fd,
            )


def _read_report(path: Path) -> bytes:
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(descriptor, "rb") as stream:
        metadata = os.fstat(stream.fileno())
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1:
            raise ValueError("JUnit evidence must be a regular file without hard links")
        if metadata.st_size > _MAX_REPORT_BYTES:
            raise ValueError("JUnit report exceeds the evidence limit")
        return stream.read(_MAX_REPORT_BYTES + 1)


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


class DockerRunner:
    """Execute an explicit image without target access to host credentials."""

    def __init__(self, config: RunnerConfig) -> None:
        self.config = config

    def _docker(self, arguments: list[str], *, timeout: float = 30) -> ProcessResult:
        return run_process(
            [*self.config.docker, *arguments],
            timeout=timeout,
            max_output=self.config.max_output_bytes,
        )

    def resolve_image(self) -> str:
        """Inspect or explicitly pull the selected image, then pin its local ID."""
        inspect = ["image", "inspect", "--format", "{{.Id}}", "--", self.config.image]
        result = self._docker(inspect)
        if result.returncode != 0:
            pulled = self._docker(["pull", "--", self.config.image], timeout=300)
            if pulled.returncode != 0 or pulled.timed_out or pulled.truncated:
                raise RunnerError(f"Could not prepare Docker image: {pulled.stderr}")
            result = self._docker(inspect)
        image_id = result.stdout.strip()
        if (
            result.returncode != 0
            or result.timed_out
            or result.truncated
            or not _IMAGE_ID.fullmatch(image_id)
        ):
            raise RunnerError("Docker did not return one immutable image ID")
        return image_id

    def _execute(self, name: str) -> tuple[ProcessResult, bool]:
        """Stop the container at the deadline, including with a privileged CLI.

        A user process cannot signal a Docker client launched through sudo. Kill
        the container through the same configured Docker command first, allowing
        the attached client to finish before the host command's separate limit.
        """
        expired = threading.Event()
        removed = threading.Event()

        def stop() -> None:
            expired.set()
            # The main lifecycle retries removal if this watchdog cannot finish.
            with suppress(OSError):
                cleanup = self._docker(["rm", "--force", "--volumes", name], timeout=10)
                if not cleanup.returncode and not cleanup.timed_out:
                    removed.set()

        watchdog = threading.Timer(self.config.timeout_seconds, stop)
        watchdog.daemon = True
        watchdog.start()
        try:
            result = self._docker(
                ["start", "--attach", name],
                timeout=self.config.timeout_seconds + 15,
            )
        finally:
            watchdog.cancel()
            watchdog.join(timeout=11)
        if expired.is_set():
            result = result.model_copy(update={"timed_out": True})
        return result, removed.is_set()

    def _create_arguments(
        self,
        name: str,
        image_id: str,
        snapshot: Path,
        oracle_dir: Path,
        report: Path,
        oracle: OracleConfig,
        kind: Literal["security", "suite"],
    ) -> list[str]:
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
            pytest_args.extend(_suite_paths(self.config.suite))
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
            f"{self.config.memory_mb}m",
            "--memory-swap",
            f"{self.config.memory_mb}m",
            "--cpus",
            str(self.config.cpus),
            "--pids-limit",
            str(self.config.pids),
            "--ulimit",
            f"fsize={_MAX_SNAPSHOT_BYTES}:{_MAX_SNAPSHOT_BYTES}",
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
            _BOOTSTRAP,
            *pytest_args,
        ]

    def run(
        self,
        workspace: Path,
        oracle: OracleConfig,
        image_id: str,
        kind: Literal["security", "suite"],
    ) -> ExecutionResult:
        """Return execution evidence; incomplete reports never become passing checks."""
        if not _IMAGE_ID.fullmatch(image_id):
            return ExecutionResult(
                returncode=125, evidence_error="Tests require an immutable image ID"
            )
        try:
            return self._run(workspace, oracle, image_id, kind)
        except (OSError, ValueError) as exc:
            return ExecutionResult(
                returncode=125, evidence_error=f"Could not collect test evidence: {exc}"
            )

    def _run(
        self,
        workspace: Path,
        oracle: OracleConfig,
        image_id: str,
        kind: Literal["security", "suite"],
    ) -> ExecutionResult:
        with tempfile.TemporaryDirectory(prefix="backport-run-") as directory:
            root = Path(directory)
            snapshot = root / "source"
            _snapshot(workspace, snapshot)
            oracle_dir = root / "oracle"
            oracle_dir.mkdir(mode=0o755)
            oracle_dir.chmod(0o755)
            _copy_regular(oracle.path, oracle_dir / "oracle.py", _MAX_REPORT_BYTES)
            (oracle_dir / "oracle.py").chmod(0o444)
            report = root / "report.xml"
            report.touch(mode=0o666)
            report.chmod(0o666)
            name = f"backport-check-{uuid.uuid4().hex}"
            arguments = self._create_arguments(
                name, image_id, snapshot, oracle_dir, report, oracle, kind
            )
            result = ProcessResult(returncode=125)
            created = False
            removed = False
            cleanup = ProcessResult(returncode=0)
            try:
                creation = self._docker(arguments)
                if creation.returncode or creation.timed_out or creation.truncated:
                    return ExecutionResult(
                        **creation.model_dump(),
                        evidence_error="Docker could not create the test container",
                    )
                created = True
                result, removed = self._execute(name)
            finally:
                if not removed:
                    cleanup = self._docker(["rm", "--force", "--volumes", name])

            error: str | None = None
            tests: list[TestCaseResult] = []
            if created and (cleanup.returncode or cleanup.timed_out):
                error = "Docker could not confirm removal of the test container"
            elif result.timed_out:
                error = "Test execution exceeded its time limit"
            elif result.truncated:
                error = "Test output exceeded its capture limit"
            else:
                try:
                    tests = parse_junit(_read_report(report))
                except (OSError, ValueError) as exc:
                    error = str(exc)
            details = result.model_dump()
            entrypoint_index = arguments.index("--entrypoint")
            details["command"] = [
                arguments[entrypoint_index + 1],
                *arguments[entrypoint_index + 3 :],
            ]
            return ExecutionResult(**details, tests=tests, evidence_error=error)
