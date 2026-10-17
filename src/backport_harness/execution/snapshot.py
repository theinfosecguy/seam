"""Stage bounded source snapshots without credentials, links, or special files."""

import os
import stat
from pathlib import Path

MAX_SNAPSHOT_BYTES = 256 * 1_048_576
MAX_SNAPSHOT_FILES = 20_000

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


def _excluded(name: str) -> bool:
    return (
        name in _EXCLUDED_NAMES
        or name == ".env"
        or name.startswith(".env.")
        or name.endswith((".pem", ".key", ".p12", ".pfx"))
    )


def copy_regular_file(
    source: Path, destination: Path, limit: int, *, directory_fd: int | None = None
) -> int:
    """Copy one ordinary file within a byte limit and reject linked files."""
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


def stage_snapshot(workspace: Path, destination: Path) -> None:
    """Copy an ordinary source tree into a fresh, bounded bind-mount directory."""
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
        if total_entries > MAX_SNAPSHOT_FILES:
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
            total_bytes += copy_regular_file(
                Path(name),
                target / name,
                MAX_SNAPSHOT_BYTES - total_bytes,
                directory_fd=directory_fd,
            )
