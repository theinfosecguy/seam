"""Stage bounded source snapshots without credentials, unsafe links, or devices."""

import os
import stat
from pathlib import Path

from seam.constants import (
    MAX_SNAPSHOT_BYTES,
    MAX_SNAPSHOT_DEPTH,
    MAX_SNAPSHOT_FILES,
    MAX_SNAPSHOT_LINKS,
    MAX_SNAPSHOT_PATH_CHARACTERS,
    SNAPSHOT_EXCLUDED_NAMES,
)


def _excluded(name: str) -> bool:
    return (
        name in SNAPSHOT_EXCLUDED_NAMES
        or name == ".env"
        or name.startswith(".env.")
        or name.endswith((".pem", ".key", ".p12", ".pfx"))
    )


def _read_regular_file(descriptor: int, limit: int) -> tuple[bytes, int]:
    with os.fdopen(descriptor, "rb") as stream:
        metadata = os.fstat(stream.fileno())
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1:
            raise ValueError("Only ordinary files without hard links are supported")
        if metadata.st_size > limit:
            raise ValueError("Source exceeds the snapshot size limit")
        data = stream.read(limit + 1)
        if len(data) > limit:
            raise ValueError("Source exceeds the snapshot size limit")
    return data, 0o755 if metadata.st_mode & 0o111 else 0o644


def copy_regular_file(
    source: Path, destination: Path, limit: int, *, directory_fd: int | None = None
) -> int:
    """Copy one ordinary file within a byte limit and reject linked files."""
    descriptor = os.open(
        source,
        os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
        dir_fd=directory_fd,
    )
    data, mode = _read_regular_file(descriptor, limit)
    destination.write_bytes(data)
    destination.chmod(mode)
    return len(data)


def _open_parent(root_fd: int, parts: tuple[str, ...]) -> int:
    """Resolve target ancestors under the root without following directory links."""
    descriptor = os.dup(root_fd)
    try:
        for part in parts:
            child = os.open(
                part,
                os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                dir_fd=descriptor,
            )
            os.close(descriptor)
            descriptor = child
        return descriptor
    except BaseException:
        os.close(descriptor)
        raise


def _link_target_parts(
    root_fd: int, parent: tuple[str, ...], target: str
) -> tuple[str, ...]:
    if target.startswith("/"):
        raise ValueError("Absolute symbolic link targets are unsupported")
    components = target.split("/")
    if any(_excluded(part) for part in components):
        raise ValueError("Symbolic link target enters an excluded path")
    normalized = list(parent)
    descriptor = _open_parent(root_fd, parent)
    try:
        for index, part in enumerate(components):
            if part in {"", "."}:
                continue
            if part == "..":
                if not normalized:
                    raise ValueError("Symbolic link target escapes the workspace")
                normalized.pop()
                child = _open_parent(root_fd, tuple(normalized))
            elif index < len(components) - 1:
                # A/.. is valid only after A was opened as a real directory.
                child = os.open(
                    part,
                    os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                    dir_fd=descriptor,
                )
                normalized.append(part)
            else:
                normalized.append(part)
                break
            os.close(descriptor)
            descriptor = child
    finally:
        os.close(descriptor)
    if not normalized:
        raise ValueError("Symbolic link target must be an ordinary file")
    return tuple(normalized)


def _open_link_target(root_fd: int, relative: Path) -> int:
    """Open a contained ordinary file, resolving only relative file-link chains."""
    parts = relative.parts
    visited = set()
    for index in range(MAX_SNAPSHOT_LINKS + 1):
        if parts in visited:
            raise ValueError("Symbolic link cycle is unsupported")
        visited.add(parts)
        parent_fd = _open_parent(root_fd, parts[:-1])
        try:
            metadata = os.stat(parts[-1], dir_fd=parent_fd, follow_symlinks=False)
            if not stat.S_ISLNK(metadata.st_mode):
                if not stat.S_ISREG(metadata.st_mode):
                    raise ValueError("Symbolic link target must be an ordinary file")
                return os.open(
                    parts[-1],
                    os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                    dir_fd=parent_fd,
                )
            if index == MAX_SNAPSHOT_LINKS:
                raise ValueError("Symbolic link chain exceeds the supported limit")
            target = os.readlink(parts[-1], dir_fd=parent_fd)
        finally:
            os.close(parent_fd)
        parts = _link_target_parts(root_fd, parts[:-1], target)
    raise ValueError("Symbolic link chain exceeds the supported limit")


def _display_path(path: str | bytes | Path | None) -> str:
    displayed = repr(os.fsdecode(path)) if path is not None else "'.'"
    if len(displayed) > MAX_SNAPSHOT_PATH_CHARACTERS:
        return displayed[:MAX_SNAPSHOT_PATH_CHARACTERS] + "..."
    return displayed


def _walk_error(error: OSError) -> None:
    raise ValueError(
        f"Snapshot directory cannot be read: {_display_path(error.filename)}"
    ) from error


def _snapshot(workspace: Path, destination: Path | None) -> None:
    try:
        root_fd = os.open(workspace, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    except OSError as error:
        raise ValueError(
            "Snapshot path '.': workspace must be an ordinary directory"
        ) from error
    try:
        total_bytes = 0
        total_entries = 0
        for source, directories, files, directory_fd in os.fwalk(
            ".",
            topdown=True,
            onerror=_walk_error,
            follow_symlinks=False,
            dir_fd=root_fd,
        ):
            relative = Path(source)
            if len(relative.parts) > MAX_SNAPSHOT_DEPTH:
                raise ValueError(
                    f"Snapshot path {_display_path(relative)}: "
                    "directory nesting exceeds the limit"
                )
            directories[:] = [name for name in directories if not _excluded(name)]
            files = [name for name in files if not _excluded(name)]
            total_entries += len(directories) + len(files)
            if total_entries > MAX_SNAPSHOT_FILES:
                raise ValueError(
                    f"Snapshot path {_display_path(relative)}: "
                    "too many files or directories"
                )
            for name in directories:
                path = relative / name
                try:
                    metadata = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
                    if not stat.S_ISDIR(metadata.st_mode):
                        raise ValueError("Directory symbolic links are unsupported")
                    if destination is not None:
                        copied = destination / path
                        copied.mkdir(mode=0o755)
                        copied.chmod(0o755)
                except (OSError, ValueError) as error:
                    raise ValueError(
                        f"Snapshot path {_display_path(path)}: {error}"
                    ) from error
            for name in files:
                path = relative / name
                try:
                    metadata = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
                    if stat.S_ISLNK(metadata.st_mode):
                        descriptor = _open_link_target(root_fd, path)
                    else:
                        if not stat.S_ISREG(metadata.st_mode):
                            raise ValueError("Only ordinary files are supported")
                        descriptor = os.open(
                            name,
                            os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                            dir_fd=directory_fd,
                        )
                    data, mode = _read_regular_file(
                        descriptor, MAX_SNAPSHOT_BYTES - total_bytes
                    )
                    total_bytes += len(data)
                    if destination is not None:
                        copied = destination / path
                        copied.write_bytes(data)
                        copied.chmod(mode)
                except (OSError, ValueError) as error:
                    raise ValueError(
                        f"Snapshot path {_display_path(path)}: {error}"
                    ) from error
    finally:
        os.close(root_fd)


def preflight_snapshot(workspace: Path) -> None:
    """Check snapshot compatibility without writing; staging repeats every check."""
    _snapshot(workspace, None)


def stage_snapshot(workspace: Path, destination: Path) -> None:
    """Copy a bounded source tree, materializing contained regular file links."""
    destination.mkdir(mode=0o755)
    destination.chmod(0o755)
    _snapshot(workspace, destination)
