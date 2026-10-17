"""Generate divergent release history and trusted verification inputs."""

import json
import os
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path

from seam.constants import DEFAULT_IMAGE, FAILURE_MARKER
from seam.demo.commands import execute_setup
from seam.demo.templates import write_template
from seam.models import HarnessConfig, OracleConfig, RunnerConfig


@dataclass(frozen=True)
class DemoProject:
    """Identify the generated repository and its trusted external inputs."""

    repo: Path
    config_path: Path
    candidate_patch: Path
    fix: str
    target: str = "release/1.x"


def _git(repo: Path, *arguments: str) -> str:
    return execute_setup(
        [
            "git",
            "-c",
            "core.hooksPath=/dev/null",
            "-c",
            "commit.gpgsign=false",
            *arguments,
        ],
        repo,
        env={
            "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
            "HOME": str(repo),
            "LANG": "C.UTF-8",
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_CONFIG_GLOBAL": "/dev/null",
            "GIT_AUTHOR_NAME": "Project Maintainer",
            "GIT_AUTHOR_EMAIL": "maintainer@example.invalid",
            "GIT_COMMITTER_NAME": "Project Maintainer",
            "GIT_COMMITTER_EMAIL": "maintainer@example.invalid",
        },
    )


def _commit(repo: Path, message: str) -> None:
    """Inspect the exact synthetic history metadata before each commit."""
    metadata = "\n".join(
        (
            message,
            _git(repo, "symbolic-ref", "--short", "HEAD"),
            _git(repo, "var", "GIT_AUTHOR_IDENT"),
            _git(repo, "var", "GIT_COMMITTER_IDENT"),
        )
    )
    forbidden = "".join(map(chr, (99, 111, 100, 101, 120)))
    if forbidden in metadata.casefold():
        raise ValueError("Synthetic Git metadata violates submission restrictions")
    if re.search(r"co-authored-by|generated.by|assistant", metadata, re.IGNORECASE):
        raise ValueError("Synthetic Git metadata must not contain attribution")
    _git(repo, "commit", "--no-verify", "-m", message)


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def create_demo(
    directory: Path,
    *,
    image: str = DEFAULT_IMAGE,
    docker: tuple[str, ...] = ("docker",),
) -> DemoProject:
    """Create divergent release history, an oracle, and a reference patch."""
    directory = directory.resolve()
    directory.mkdir(parents=True, exist_ok=True)
    if any(directory.iterdir()):
        raise ValueError("Demo output directory must be empty")
    repo = directory / "fixture"
    repo.mkdir()
    with tempfile.TemporaryDirectory(prefix="backport-empty-template-") as empty:
        _git(repo, "init", "--initial-branch=main", f"--template={empty}")
    _git(repo, "config", "user.name", "Project Maintainer")
    _git(repo, "config", "user.email", "maintainer@example.invalid")
    write_template(repo / "src/parcel_paths/legacy.py", "legacy.py.txt")
    write_template(repo / "src/parcel_paths/__init__.py", "legacy_init.py.txt")
    write_template(repo / "tests/test_paths.py", "tests.py.txt")
    write_template(repo / "README.md", "README.md.txt")
    _git(repo, "add", "README.md", "src", "tests")
    _commit(repo, "Add archive path API for the maintained release")
    _git(repo, "branch", "release/1.x")
    (repo / "src/parcel_paths/legacy.py").unlink()
    write_template(repo / "src/parcel_paths/paths.py", "modern.py.txt")
    write_template(repo / "src/parcel_paths/__init__.py", "modern_init.py.txt")
    _git(repo, "add", "src")
    _commit(repo, "Refactor path resolution for the next major release")
    write_template(repo / "src/parcel_paths/paths.py", "fixed.py.txt")
    _git(repo, "add", "src/parcel_paths/paths.py")
    _commit(repo, "Reject archive paths outside the extraction directory")
    fix = _git(repo, "rev-parse", "HEAD")
    _git(repo, "checkout", "release/1.x")
    write_template(repo / "src/parcel_paths/legacy.py", "backported.py.txt")
    patch = _git(repo, "diff", "--no-ext-diff", "--no-color") + "\n"
    _git(repo, "checkout", "--", "src/parcel_paths/legacy.py")

    oracle = directory / "oracle.py"
    write_template(oracle, "oracle.py.txt")
    candidate_patch = directory / "reference.patch"
    _write(candidate_patch, patch)
    config = HarnessConfig(
        oracle=OracleConfig(
            path=oracle,
            security_test="test_security_traversal",
            controls=(
                "test_control_nested_path",
                "test_control_repeated_dots",
                "test_control_unicode_filename",
            ),
            failure_marker=FAILURE_MARKER,
        ),
        runner=RunnerConfig(image=image, docker=docker),
    )
    config_path = directory / "harness.toml"
    _write(
        config_path,
        "schema_version = 1\nmax_attempts = 3\n\n[oracle]\n"
        f"path = {json.dumps(str(oracle))}\n"
        f"security_test = {json.dumps(config.oracle.security_test)}\n"
        f"controls = {json.dumps(config.oracle.controls)}\n"
        f"failure_marker = {json.dumps(FAILURE_MARKER)}\n\n[runner]\n"
        f"image = {json.dumps(image)}\n"
        f"docker = {json.dumps(docker)}\n"
        'suite = ["tests"]\ntimeout_seconds = 120\n',
    )
    return DemoProject(repo, config_path, candidate_patch, fix)
