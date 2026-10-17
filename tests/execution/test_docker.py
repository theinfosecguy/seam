"""Exercise sandbox boundaries and incomplete pytest evidence handling."""

import os
import shlex
from collections.abc import Mapping, Sequence
from pathlib import Path

import pytest

import backport_harness.execution.docker as runner_module
from backport_harness.execution.docker import DockerRunner, RunnerError
from backport_harness.models import OracleConfig, ProcessResult, RunnerConfig

IMAGE_ID = "sha256:" + "a" * 64
PASSING_REPORT = (
    b"<testsuites>"
    b'<testsuite tests="2" failures="0" errors="0" skipped="0">\n'
    b'<testcase classname="oracle" name="test_security"/>\n'
    b'<testcase classname="oracle" name="test_control"/>\n'
    b"</testsuite></testsuites>"
)


@pytest.fixture
def target(tmp_path: Path) -> tuple[Path, OracleConfig]:
    workspace = tmp_path / "target"
    workspace.mkdir()
    (workspace / "src").mkdir()
    (workspace / "src" / "library.py").write_text("VALUE = 1\n")
    oracle_path = tmp_path / "oracle.py"
    oracle_path.write_text("def test_security():\n    assert True\n")
    return workspace, OracleConfig(
        path=oracle_path,
        security_test="test_security",
        controls=("test_control",),
        failure_marker="unsafe-security-regression",
    )


class DockerStub:
    """Model Docker lifecycle commands while inspecting the staged bind mounts."""

    def __init__(self) -> None:
        self.calls: list[list[str]] = []
        self.report: Path | None = None
        self.source: Path | None = None
        self.oracle: Path | None = None
        self.report_bytes = PASSING_REPORT
        self.execution = ProcessResult(returncode=0, stdout="2 passed")
        self.creation = ProcessResult(returncode=0, stdout="container-id")
        self.cleanup = ProcessResult(returncode=0)
        self.interrupt = False
        self.replace_report_with_symlink: Path | None = None
        self.staged_paths: set[str] = set()
        self.oracle_mode = 0
        self.snapshot_content = ""

    def __call__(
        self,
        command: Sequence[str],
        *,
        cwd: Path | None = None,
        timeout: float = 120,
        max_output: int = 131072,
        input_text: str | None = None,
        env: Mapping[str, str] | None = None,
    ) -> ProcessResult:
        args = list(command)
        self.calls.append(args)
        if "create" in args:
            for argument in args:
                if argument.startswith("type=bind,src="):
                    parts = dict(
                        part.split("=", 1)
                        for part in argument.split(",")
                        if "=" in part
                    )
                    if parts["dst"] == "/report.xml":
                        self.report = Path(parts["src"])
                    elif parts["dst"] == "/source":
                        self.source = Path(parts["src"])
                        self.staged_paths = {
                            str(path.relative_to(self.source))
                            for path in self.source.rglob("*")
                        }
                        self.snapshot_content = (
                            self.source / "src" / "library.py"
                        ).read_text()
                    elif parts["dst"] == "/oracle":
                        self.oracle = Path(parts["src"])
                        self.oracle_mode = (
                            self.oracle / "oracle.py"
                        ).stat().st_mode & 0o777
            return self.creation
        if "start" in args:
            if self.interrupt:
                raise KeyboardInterrupt
            assert self.report is not None
            if self.replace_report_with_symlink is not None:
                self.report.unlink()
                self.report.symlink_to(self.replace_report_with_symlink)
            else:
                self.report.write_bytes(self.report_bytes)
            return self.execution
        if "rm" in args:
            return self.cleanup
        raise AssertionError(f"Unexpected Docker command: {args}")


def test_security_execution_isolated_and_source_is_filtered(
    target: tuple[Path, OracleConfig], monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace, oracle = target
    (workspace / ".git").mkdir()
    (workspace / ".git" / "config").write_text("sensitive origin")
    (workspace / ".env").write_text("sensitive value")
    (workspace / "private.pem").write_text("private material")
    docker = DockerStub()
    monkeypatch.setattr(runner_module, "run_process", docker)
    result = DockerRunner(RunnerConfig(image="operator-image")).run(
        workspace, oracle, IMAGE_ID, "security"
    )
    assert result.returncode == 0
    assert result.evidence_error is None
    assert len(result.tests) == 2
    assert result.command[:3] == ["python", "-I", "-B"]
    assert "--noconftest" in result.command
    assert "/oracle/oracle.py::test_security" in result.command
    assert docker.staged_paths == {"src", "src/library.py"}
    assert docker.snapshot_content == "VALUE = 1\n"
    assert docker.oracle_mode == 0o444
    assert docker.source is not None and not docker.source.exists()
    create = docker.calls[0]
    for option, value in (
        ("--network", "none"),
        ("--user", "65534:65534"),
        ("--cap-drop", "ALL"),
        ("--security-opt", "no-new-privileges"),
        ("--log-driver", "none"),
    ):
        assert create[create.index(option) + 1] == value
    assert "--read-only" in create
    assert create[create.index("--ulimit") + 1] == "fsize=268435456:268435456"
    assert not any("docker.sock" in argument for argument in create)
    assert len([item for item in create if item.startswith("type=bind")]) == 3
    assert create[create.index("--mount") + 1].endswith(",readonly")
    assert docker.calls[-1][1:4] == ["rm", "--force", "--volumes"]
    assert (workspace / "src" / "library.py").read_text() == "VALUE = 1\n"


def test_suite_uses_explicit_paths_and_prefix(
    target: tuple[Path, OracleConfig], monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace, oracle = target
    docker = DockerStub()
    monkeypatch.setattr(runner_module, "run_process", docker)
    result = DockerRunner(
        RunnerConfig(
            image="operator-image",
            docker=("sudo", "-n", "docker"),
            suite=("tests/unit.py::TestThing::test_works", "tests/compatibility"),
        )
    ).run(workspace, oracle, IMAGE_ID, "suite")
    assert result.evidence_error is None
    assert docker.calls[0][:4] == ["sudo", "-n", "docker", "create"]
    assert result.command[-2:] == [
        "tests/unit.py::TestThing::test_works",
        "tests/compatibility",
    ]
    assert "--noconftest" not in result.command


@pytest.mark.parametrize("suite", ["../outside", "/tmp", "--help", "tests::"])
def test_suite_cannot_add_flags_or_escape_workspace(
    target: tuple[Path, OracleConfig],
    monkeypatch: pytest.MonkeyPatch,
    suite: str,
) -> None:
    workspace, oracle = target
    docker = DockerStub()
    monkeypatch.setattr(runner_module, "run_process", docker)
    result = DockerRunner(RunnerConfig(image="operator-image", suite=(suite,))).run(
        workspace, oracle, IMAGE_ID, "suite"
    )
    assert result.evidence_error is not None
    assert docker.calls == []


@pytest.mark.parametrize(
    "execution",
    [
        ProcessResult(returncode=-9, timed_out=True),
        ProcessResult(returncode=0, truncated=True),
    ],
)
def test_incomplete_execution_is_not_green_even_with_passing_report(
    target: tuple[Path, OracleConfig],
    monkeypatch: pytest.MonkeyPatch,
    execution: ProcessResult,
) -> None:
    workspace, oracle = target
    docker = DockerStub()
    docker.execution = execution
    monkeypatch.setattr(runner_module, "run_process", docker)
    result = DockerRunner(RunnerConfig(image="operator-image")).run(
        workspace, oracle, IMAGE_ID, "security"
    )
    assert result.evidence_error is not None
    assert not result.tests
    assert "rm" in docker.calls[-1]


def test_container_is_removed_on_interrupt(
    target: tuple[Path, OracleConfig], monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace, oracle = target
    docker = DockerStub()
    docker.interrupt = True
    monkeypatch.setattr(runner_module, "run_process", docker)
    with pytest.raises(KeyboardInterrupt):
        DockerRunner(RunnerConfig(image="operator-image")).run(
            workspace, oracle, IMAGE_ID, "security"
        )
    assert "rm" in docker.calls[-1]
    assert docker.source is not None and not docker.source.exists()


def test_creation_failure_is_reported_and_removal_still_attempted(
    target: tuple[Path, OracleConfig], monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace, oracle = target
    docker = DockerStub()
    docker.creation = ProcessResult(returncode=125, stderr="invalid configuration")
    monkeypatch.setattr(runner_module, "run_process", docker)
    result = DockerRunner(RunnerConfig(image="operator-image")).run(
        workspace, oracle, IMAGE_ID, "security"
    )
    assert result.returncode == 125
    assert "create" in (result.evidence_error or "")
    assert "rm" in docker.calls[-1]


def test_failed_cleanup_prevents_verified_evidence(
    target: tuple[Path, OracleConfig], monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace, oracle = target
    docker = DockerStub()
    docker.cleanup = ProcessResult(returncode=1)
    monkeypatch.setattr(runner_module, "run_process", docker)
    result = DockerRunner(RunnerConfig(image="operator-image")).run(
        workspace, oracle, IMAGE_ID, "security"
    )
    assert "removal" in (result.evidence_error or "")


def test_symlink_report_cannot_read_host_file(
    target: tuple[Path, OracleConfig], monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    workspace, oracle = target
    outside = tmp_path / "outside.xml"
    outside.write_bytes(PASSING_REPORT)
    docker = DockerStub()
    docker.replace_report_with_symlink = outside
    monkeypatch.setattr(runner_module, "run_process", docker)
    result = DockerRunner(RunnerConfig(image="operator-image")).run(
        workspace, oracle, IMAGE_ID, "security"
    )
    assert result.evidence_error is not None
    assert not result.tests
    assert outside.read_bytes() == PASSING_REPORT


def test_workspace_symlinks_cannot_expose_host_files(
    target: tuple[Path, OracleConfig], monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    workspace, oracle = target
    (workspace / "linked").symlink_to(tmp_path)
    docker = DockerStub()
    monkeypatch.setattr(runner_module, "run_process", docker)
    result = DockerRunner(RunnerConfig(image="operator-image")).run(
        workspace, oracle, IMAGE_ID, "security"
    )
    assert "symbolic link" in (result.evidence_error or "")
    assert not docker.calls


def test_workspace_hard_links_cannot_expose_host_files(
    target: tuple[Path, OracleConfig], monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    workspace, oracle = target
    outside = tmp_path / "outside"
    outside.write_text("private")
    os.link(outside, workspace / "linked")
    docker = DockerStub()
    monkeypatch.setattr(runner_module, "run_process", docker)
    result = DockerRunner(RunnerConfig(image="operator-image")).run(
        workspace, oracle, IMAGE_ID, "security"
    )
    assert "hard links" in (result.evidence_error or "")
    assert not docker.calls


def test_missing_or_malformed_report_is_unresolved(
    target: tuple[Path, OracleConfig], monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace, oracle = target
    docker = DockerStub()
    docker.report_bytes = b""
    monkeypatch.setattr(runner_module, "run_process", docker)
    result = DockerRunner(RunnerConfig(image="operator-image")).run(
        workspace, oracle, IMAGE_ID, "security"
    )
    assert result.evidence_error is not None
    assert not result.tests


def test_unpinned_image_cannot_run_target(
    target: tuple[Path, OracleConfig], monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace, oracle = target
    docker = DockerStub()
    monkeypatch.setattr(runner_module, "run_process", docker)
    result = DockerRunner(RunnerConfig(image="operator-image")).run(
        workspace, oracle, "python:latest", "security"
    )
    assert "immutable" in (result.evidence_error or "")
    assert not docker.calls


def test_resolve_image_reuses_local_immutable_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[list[str]] = []

    def fake(command: Sequence[str], **kwargs: object) -> ProcessResult:
        calls.append(list(command))
        return ProcessResult(returncode=0, stdout=IMAGE_ID + "\n")

    monkeypatch.setattr(runner_module, "run_process", fake)
    assert (
        DockerRunner(RunnerConfig(image="operator-image")).resolve_image() == IMAGE_ID
    )
    assert len(calls) == 1
    assert calls[0][1:3] == ["image", "inspect"]


def test_resolve_image_pulls_missing_selected_image(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[list[str]] = []
    replies = iter(
        [
            ProcessResult(returncode=1, stderr="No such image"),
            ProcessResult(returncode=0),
            ProcessResult(returncode=0, stdout=IMAGE_ID),
        ]
    )

    def fake(command: Sequence[str], **kwargs: object) -> ProcessResult:
        calls.append(list(command))
        return next(replies)

    monkeypatch.setattr(runner_module, "run_process", fake)
    assert (
        DockerRunner(RunnerConfig(image="operator-image")).resolve_image() == IMAGE_ID
    )
    assert calls[1] == ["docker", "pull", "--", "operator-image"]


def test_invalid_image_inspection_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake(command: Sequence[str], **kwargs: object) -> ProcessResult:
        return ProcessResult(returncode=0, stdout="python:latest")

    monkeypatch.setattr(runner_module, "run_process", fake)
    with pytest.raises(RunnerError, match="immutable"):
        DockerRunner(RunnerConfig(image="operator-image")).resolve_image()


def test_docker_integration_runs_src_layout_with_readonly_inputs(
    target: tuple[Path, OracleConfig], monkeypatch: pytest.MonkeyPatch
) -> None:
    image = os.environ.get("BACKPORT_TEST_IMAGE")
    if not image:
        pytest.skip("Set BACKPORT_TEST_IMAGE to run the real Docker isolation check")
    workspace, oracle = target
    (workspace / ".env").write_text("PRIVATE_VALUE=must-not-enter-container\n")
    (workspace / ".git").mkdir()
    (workspace / "large-fixture.bin").write_bytes(b"x" * (1_048_576 + 1))
    oracle.path.write_text(
        """import os
from pathlib import Path
import pytest
from library import VALUE

def test_security():
    assert VALUE == 1

def test_control():
    assert os.getuid() != 0
    assert 'OPENAI_API_KEY' not in os.environ
    assert not Path('/source/.env').exists()
    assert not Path('/source/.git').exists()
    assert not Path('/var/run/docker.sock').exists()
    assert Path('/work/repo/large-fixture.bin').stat().st_size > 1_048_576
    with pytest.raises(OSError):
        Path('/oracle/oracle.py').write_text('modified')
    with pytest.raises(OSError):
        Path('/source/src/library.py').write_text('modified')
    with pytest.raises(OSError):
        Path('/rootfs-write-probe').write_text('modified')
    capabilities = next(
        line for line in Path('/proc/self/status').read_text().splitlines()
        if line.startswith('CapEff:')
    )
    assert int(capabilities.split()[1], 16) == 0
"""
    )
    monkeypatch.setenv("OPENAI_API_KEY", "must-stay-on-host")
    docker = tuple(shlex.split(os.environ.get("BACKPORT_TEST_DOCKER", "docker")))
    runner = DockerRunner(RunnerConfig(image=image, docker=docker))
    result = runner.run(workspace, oracle, runner.resolve_image(), "security")
    assert result.evidence_error is None, result.model_dump()
    assert result.returncode == 0, result.model_dump()
    assert [case.outcome for case in result.tests] == ["passed", "passed"]
    assert (workspace / "src" / "library.py").read_text() == "VALUE = 1\n"


def test_docker_integration_preserves_skips_and_removes_timed_out_container(
    target: tuple[Path, OracleConfig], monkeypatch: pytest.MonkeyPatch
) -> None:
    image = os.environ.get("BACKPORT_TEST_IMAGE")
    if not image:
        pytest.skip("Set BACKPORT_TEST_IMAGE to run the real Docker lifecycle check")
    workspace, oracle = target
    oracle.path.write_text(
        "import pytest\n"
        "def test_security():\n    pytest.skip('unsupported fixture')\n"
        "def test_control():\n    assert True\n"
    )
    docker = tuple(shlex.split(os.environ.get("BACKPORT_TEST_DOCKER", "docker")))
    runner = DockerRunner(RunnerConfig(image=image, docker=docker))
    image_id = runner.resolve_image()
    skipped = runner.run(workspace, oracle, image_id, "security")
    assert skipped.evidence_error is None, skipped.model_dump()
    assert [case.outcome for case in skipped.tests] == ["skipped", "passed"]

    oracle.path.write_text(
        "import time\n"
        "def test_security():\n    time.sleep(10)\n"
        "def test_control():\n    assert True\n"
    )
    timed_runner = DockerRunner(
        RunnerConfig(image=image, docker=docker, timeout_seconds=0.25)
    )
    original = timed_runner._docker
    commands: list[list[str]] = []

    def capture(arguments: list[str], *, timeout: float = 30) -> ProcessResult:
        commands.append(arguments)
        return original(arguments, timeout=timeout)

    monkeypatch.setattr(timed_runner, "_docker", capture)
    timed_out = timed_runner.run(workspace, oracle, image_id, "security")
    assert timed_out.timed_out, timed_out.model_dump()
    assert "time limit" in (timed_out.evidence_error or "")
    assert commands[-1][:3] == ["rm", "--force", "--volumes"]
    removed_name = commands[-1][-1]
    assert original(["container", "inspect", removed_name]).returncode != 0
