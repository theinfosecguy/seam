"""Bounded, read-only workspace access and locally validated tool arguments."""

import os
import stat
from pathlib import Path, PurePosixPath

from pydantic import ValidationError

from seam.agent.schemas import TOOL_SCHEMAS, ListFiles, ReadFile, SubmitPatch
from seam.constants.agent import (
    MAX_ARGUMENT_BYTES,
    MAX_ENTRIES,
    MAX_TEXT_BYTES,
)
from seam.constants.security import ALLOWED_SUFFIXES
from seam.exceptions import AgentError, RepositoryError
from seam.models import AgentProposal
from seam.repository import validate_source_path
from seam.security import contains_secret, is_sensitive_path


def _safe_parts(value: str, *, root_allowed: bool = False) -> tuple[str, ...]:
    if root_allowed and value == ".":
        return ()
    parts = PurePosixPath(value).parts
    if (
        not parts
        or PurePosixPath(value).is_absolute()
        or "\\" in value
        or any(ord(char) < 32 or ord(char) == 127 for char in value)
        or any(part.startswith(".") for part in parts)
        or is_sensitive_path(value)
        or contains_secret(value)
    ):
        raise ValueError("path is outside the allowed project files")
    return parts


def _open_directory(root: Path, parts: tuple[str, ...]) -> int:
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    descriptor = os.open(root, flags)
    try:
        for part in parts:
            next_descriptor = os.open(part, flags, dir_fd=descriptor)
            os.close(descriptor)
            descriptor = next_descriptor
        return descriptor
    except OSError:
        os.close(descriptor)
        raise


class WorkspaceTools:
    """Expose only safe directory listings, bounded reads, and patch submission."""

    def __init__(
        self,
        root: Path,
        upstream_parent: Path | None = None,
        upstream_fix: Path | None = None,
    ) -> None:
        self.root = root.absolute()
        self.inspected_target = False
        self._roots = {
            "target": self.root,
            "upstream_parent": upstream_parent,
            "upstream_fix": upstream_fix,
        }
        for workspace in self._roots.values():
            if workspace is not None and (
                workspace.is_symlink() or not workspace.is_dir()
            ):
                raise AgentError("agent workspace must be a real directory")

    def _root(self, revision: str) -> Path:
        root = self._roots[revision]
        if root is None:
            raise ValueError("requested revision is unavailable")
        return root

    def execute(self, name: str, arguments: str) -> AgentProposal | dict[str, object]:
        """Validate every call locally, including providers without strict schemas."""
        if not isinstance(arguments, str):
            raise AgentError("provider returned invalid tool arguments")
        if len(arguments.encode("utf-8")) > MAX_ARGUMENT_BYTES:
            raise AgentError("provider tool arguments exceeded the size limit")
        if contains_secret(arguments):
            raise AgentError("provider tool arguments may contain credentials")
        try:
            if name == "submit_patch":
                submission = SubmitPatch.model_validate_json(arguments)
                return AgentProposal(**submission.model_dump())
            if name == "list_files":
                return self.list_files(ListFiles.model_validate_json(arguments))
            if name == "read_file":
                return self.read_file(ReadFile.model_validate_json(arguments))
            raise AgentError("provider requested an unknown tool")
        except ValidationError:
            return {
                "error": "invalid tool arguments; retry using the declared parameters",
                "parameters": next(
                    tool["parameters"] for tool in TOOL_SCHEMAS if tool["name"] == name
                ),
            }
        except (OSError, UnicodeError, ValueError):
            return {"error": "requested path is unavailable or not permitted"}

    def list_files(self, argument: ListFiles) -> dict[str, object]:
        """List safe immediate entries without following symbolic links."""
        parts = _safe_parts(argument.directory, root_allowed=True)
        descriptor = _open_directory(self._root(argument.revision), parts)
        try:
            result: list[str] = []
            scanned = 0
            truncated = False
            with os.scandir(descriptor) as entries:
                for entry in entries:
                    scanned += 1
                    if scanned > MAX_ENTRIES:
                        truncated = True
                        break
                    try:
                        _safe_parts(entry.name)
                    except ValueError:
                        continue
                    if entry.is_dir(follow_symlinks=False):
                        result.append(entry.name + "/")
                    elif (
                        entry.is_file(follow_symlinks=False)
                        and Path(entry.name).suffix.lower() in ALLOWED_SUFFIXES
                    ):
                        result.append(entry.name)
            return {"entries": sorted(result), "truncated": truncated}
        finally:
            os.close(descriptor)

    def read_file(self, argument: ReadFile) -> dict[str, object]:
        """Read bounded UTF-8 text from one independent regular file."""
        parts = _safe_parts(argument.path)
        if Path(parts[-1]).suffix.lower() not in ALLOWED_SUFFIXES:
            raise ValueError("file type is not allowed")
        directory = _open_directory(self._root(argument.revision), parts[:-1])
        try:
            descriptor = os.open(
                parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory
            )
        finally:
            os.close(directory)
        with os.fdopen(descriptor, "rb") as stream:
            metadata = os.fstat(stream.fileno())
            if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1:
                raise ValueError("only independent regular files can be read")
            content = stream.read(MAX_TEXT_BYTES + 1)
        truncated = len(content) > MAX_TEXT_BYTES
        text = content[:MAX_TEXT_BYTES].decode("utf-8")
        if "\x00" in text or contains_secret(text):
            raise ValueError("file may contain binary data or credentials")
        lines = text.splitlines()
        start = argument.start_line - 1
        end = start + argument.line_count
        selected = "\n".join(lines[start:end])
        if argument.revision == "target" and selected.strip():
            try:
                validate_source_path(argument.path)
            except RepositoryError:
                pass
            else:
                self.inspected_target = True
        return {
            "revision": argument.revision,
            "path": argument.path,
            "start_line": argument.start_line,
            "content": selected,
            "truncated": truncated or end < len(lines),
            "readable_lines": len(lines),
        }
