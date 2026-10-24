"""Manage immutable Docker images and disposable test-container lifecycles."""

import tempfile
import threading
import uuid
from contextlib import suppress
from pathlib import Path
from typing import Literal

from seam import repository
from seam.constants.execution import IMAGE_ID_PATTERN
from seam.constants.verification import MAX_REPORT_BYTES
from seam.exceptions import RepositoryError, RunnerError
from seam.execution.container import build_container_arguments
from seam.execution.processes import run_process
from seam.execution.snapshot import copy_regular_file, stage_snapshot
from seam.models import (
    ExecutionResult,
    OracleConfig,
    ProcessResult,
    RunnerConfig,
    TestCaseResult,
)
from seam.verification.junit import (
    parse_junit,
    read_junit_report,
)


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
            or not IMAGE_ID_PATTERN.fullmatch(image_id)
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

    def run(
        self,
        workspace: Path,
        oracle: OracleConfig,
        image_id: str,
        kind: Literal["security", "suite"],
    ) -> ExecutionResult:
        """Return bounded evidence; unresolved container teardown raises RunnerError."""
        if not IMAGE_ID_PATTERN.fullmatch(image_id):
            return ExecutionResult(
                returncode=125, evidence_error="Tests require an immutable image ID"
            )
        try:
            return self._run(workspace, oracle, image_id, kind)
        except (OSError, RepositoryError, ValueError) as exc:
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
        node_modules = ""
        mocha_ui = self.config.mocha_ui
        if self.config.node_dependencies or self.config.mocha_interfaces:
            revision = repository.resolve(workspace, "HEAD")
        if self.config.node_dependencies:
            if revision not in self.config.node_dependencies:
                raise ValueError(f"No Node dependencies are configured for {revision}")
            node_modules = self.config.node_dependencies[revision]
        if self.config.mocha_interfaces:
            if revision not in self.config.mocha_interfaces:
                raise ValueError(f"No Mocha interface is configured for {revision}")
            mocha_ui = self.config.mocha_interfaces[revision]
        with tempfile.TemporaryDirectory(prefix="backport-run-") as directory:
            root = Path(directory)
            snapshot = root / "source"
            stage_snapshot(
                workspace, snapshot, reviewed_fixtures=self.config.reviewed_fixtures
            )
            oracle_dir = root / "oracle"
            oracle_dir.mkdir(mode=0o755)
            oracle_dir.chmod(0o755)
            oracle_name = (
                "oracle.py"
                if self.config.kind == "pytest"
                else f"oracle{oracle.path.suffix}"
            )
            copy_regular_file(oracle.path, oracle_dir / oracle_name, MAX_REPORT_BYTES)
            (oracle_dir / oracle_name).chmod(0o444)
            report = root / "report.xml"
            report.touch(mode=0o666)
            report.chmod(0o666)
            name = f"backport-check-{uuid.uuid4().hex}"
            arguments = build_container_arguments(
                self.config,
                name,
                image_id,
                snapshot,
                oracle_dir,
                report,
                oracle,
                kind,
                node_modules=node_modules,
                mocha_ui=mocha_ui,
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
                raise RunnerError(
                    "Docker could not confirm removal of the test container"
                )
            elif result.timed_out:
                error = "Test execution exceeded its time limit"
            elif result.truncated:
                error = "Test output exceeded its capture limit"
            else:
                try:
                    tests = parse_junit(
                        read_junit_report(report),
                        runner="node"
                        if kind == "security" and self.config.kind == "mocha"
                        else self.config.kind,
                    )
                except (OSError, ValueError) as exc:
                    error = str(exc)
            details = result.model_dump()
            entrypoint_index = arguments.index("--entrypoint")
            details["command"] = [
                arguments[entrypoint_index + 1],
                *arguments[entrypoint_index + 3 :],
            ]
            return ExecutionResult(**details, tests=tests, evidence_error=error)
