"""Build a synthetic, reproducible security backport exercise."""

import json
import os
import re
import shlex
import tempfile
from dataclasses import dataclass
from pathlib import Path

from .models import HarnessConfig, OracleConfig, RunnerConfig
from .processes import run_process

DEFAULT_IMAGE = "security-backport-demo:local"
FAILURE_MARKER = "TRAVERSAL_SECURITY_ORACLE"

_LEGACY = '''"""Resolve archive member names for the 1.x public API."""

from pathlib import Path


def member_path(destination: str, member: str) -> str:
    """Return the extraction path for an archive member."""
    return str(Path(destination) / member)
'''

_MODERN = '''"""Resolve archive member names for the 2.x public API."""

from pathlib import Path


def resolve_member(root: Path, name: str) -> Path:
    """Return the extraction path for an archive member."""
    return root / name
'''

_FIXED = '''"""Resolve archive member names for the 2.x public API."""

from pathlib import Path


def resolve_member(root: Path, name: str) -> Path:
    """Reject archive members that escape the extraction directory."""
    root = root.resolve()
    candidate = (root / name).resolve()
    if not candidate.is_relative_to(root):
        raise ValueError("archive member escapes extraction directory")
    return candidate
'''

_BACKPORTED = '''"""Resolve archive member names for the 1.x public API."""

from pathlib import Path


def member_path(destination: str, member: str) -> str:
    """Reject archive members that escape the extraction directory."""
    root = Path(destination).resolve()
    candidate = (root / member).resolve()
    if not candidate.is_relative_to(root):
        raise ValueError("archive member escapes extraction directory")
    return str(candidate)
'''

_TESTS = '''"""Compatibility checks shared by the maintained releases."""

from pathlib import Path

import parcel_paths


def resolve(root: Path, name: str) -> Path:
    if hasattr(parcel_paths, "resolve_member"):
        return parcel_paths.resolve_member(root, name)
    return Path(parcel_paths.member_path(str(root), name))


def test_nested_member(tmp_path):
    assert resolve(tmp_path, "docs/readme.txt") == tmp_path / "docs/readme.txt"


def test_repeated_dots_in_filename(tmp_path):
    assert resolve(tmp_path, "release..notes.txt") == tmp_path / "release..notes.txt"
'''

_ORACLE = '''"""Independent path containment and compatibility checks.

This synthetic fixture is not a reproduction of a published vulnerability.
"""

from pathlib import Path

import parcel_paths


def resolve(root: Path, name: str) -> Path:
    if hasattr(parcel_paths, "resolve_member"):
        return parcel_paths.resolve_member(root, name)
    return Path(parcel_paths.member_path(str(root), name))


def test_security_traversal(tmp_path):
    root = tmp_path / "extraction"
    root.mkdir()
    for name in ("../outside.txt", str(tmp_path / "absolute.txt")):
        try:
            candidate = resolve(root, name)
        except ValueError:
            continue
        assert candidate.resolve().is_relative_to(root.resolve()), (
            "TRAVERSAL_SECURITY_ORACLE: member escaped extraction directory"
        )


def test_control_nested_path(tmp_path):
    assert resolve(tmp_path, "docs/readme.txt") == tmp_path / "docs/readme.txt"


def test_control_repeated_dots(tmp_path):
    assert resolve(tmp_path, "release..notes.txt") == tmp_path / "release..notes.txt"


def test_control_unicode_filename(tmp_path):
    assert resolve(tmp_path, "résumé.txt") == tmp_path / "résumé.txt"
'''


@dataclass(frozen=True)
class DemoProject:
    """Identify the generated repository and its trusted external inputs."""

    repo: Path
    config_path: Path
    candidate_patch: Path
    fix: str
    target: str = "release/1.x"


def docker_arguments(value: str) -> tuple[str, ...]:
    """Parse an operator-selected Docker command without invoking a shell."""
    arguments = tuple(shlex.split(value))
    if not arguments or any("\x00" in argument for argument in arguments):
        raise ValueError("Docker command must contain nonempty arguments")
    return arguments


def _execute(
    command: list[str],
    cwd: Path,
    *,
    timeout: float = 30,
    env: dict[str, str] | None = None,
) -> str:
    result = run_process(command, cwd=cwd, timeout=timeout, env=env)
    if result.returncode or result.timed_out or result.truncated:
        # Commands and output here contain only the generated, public fixture.
        detail = (result.stderr or result.stdout).strip()[-4000:]
        raise RuntimeError(f"Demo setup failed: {command[0]}: {detail}")
    return result.stdout.strip()


def _git(repo: Path, *arguments: str) -> str:
    return _execute(
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
    _write(repo / "src/parcel_paths/legacy.py", _LEGACY)
    _write(
        repo / "src/parcel_paths/__init__.py",
        '"""Synthetic archive path library."""\n'
        'from .legacy import member_path\n\n__all__ = ["member_path"]\n',
    )
    _write(repo / "tests/test_paths.py", _TESTS)
    _write(
        repo / "README.md",
        "# Synthetic archive path fixture\n\n"
        "This repository demonstrates backport verification. "
        "It does not describe a published CVE.\n",
    )
    _git(repo, "add", "README.md", "src", "tests")
    _commit(repo, "Add archive path API for the maintained release")
    _git(repo, "branch", "release/1.x")
    (repo / "src/parcel_paths/legacy.py").unlink()
    _write(repo / "src/parcel_paths/paths.py", _MODERN)
    _write(
        repo / "src/parcel_paths/__init__.py",
        '"""Synthetic archive path library."""\n'
        'from .paths import resolve_member\n\n__all__ = ["resolve_member"]\n',
    )
    _git(repo, "add", "src")
    _commit(repo, "Refactor path resolution for the next major release")
    _write(repo / "src/parcel_paths/paths.py", _FIXED)
    _git(repo, "add", "src/parcel_paths/paths.py")
    _commit(repo, "Reject archive paths outside the extraction directory")
    fix = _git(repo, "rev-parse", "HEAD")
    _git(repo, "checkout", "release/1.x")
    _write(repo / "src/parcel_paths/legacy.py", _BACKPORTED)
    patch = _git(repo, "diff", "--no-ext-diff", "--no-color") + "\n"
    _git(repo, "checkout", "--", "src/parcel_paths/legacy.py")

    oracle = directory / "oracle.py"
    _write(oracle, _ORACLE)
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


def build_demo_image(
    directory: Path,
    *,
    docker: tuple[str, ...] = ("docker",),
    image: str = DEFAULT_IMAGE,
) -> None:
    """Build a trusted pytest environment before network-isolated verification."""
    context = directory / "container"
    context.mkdir()
    _write(
        context / "Dockerfile",
        "FROM python:3.12.12-slim\n"
        "RUN python -m pip install --no-cache-dir pytest==8.4.2\n"
        'ENV PYTHONDONTWRITEBYTECODE="1"\n',
    )
    _execute([*docker, "build", "--tag", image, str(context)], directory, timeout=600)
