"""Bounded, read-only workspace access and locally validated tool arguments."""

import os
import re
import stat
from pathlib import Path, PurePosixPath

from openai.types.responses import FunctionToolParam
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from backport_harness.agent.errors import AgentError
from backport_harness.models import AgentProposal

MAX_ARGUMENT_BYTES = 262144 + 8192
MAX_TEXT_BYTES = 65536
MAX_ENTRIES = 1000
ALLOWED_SUFFIXES = {".py", ".md", ".rst", ".txt", ".toml", ".cfg", ".ini"}
SENSITIVE_NAME = re.compile(
    r"(?:secret|credential|password|private[_-]?key|access[_-]?token|id_rsa)", re.I
)
SENSITIVE_CONTENT = re.compile(
    r"sk-[A-Za-z0-9_-]{16,}|-----BEGIN [A-Z ]*PRIVATE KEY-----"
)


class Arguments(BaseModel):
    """Reject unknown fields and implicit coercions in every tool call."""

    model_config = ConfigDict(extra="forbid", strict=True)


class ListFiles(Arguments):
    """Select one project directory for a bounded listing."""

    directory: str = Field(min_length=1, max_length=500)


class ReadFile(Arguments):
    """Select a bounded line range from an allowed project file."""

    path: str = Field(min_length=1, max_length=500)
    start_line: int = Field(ge=1, le=100000)
    line_count: int = Field(ge=1, le=200)


class SubmitPatch(Arguments):
    """Carry one candidate diff and its compatibility explanation."""

    patch: str = Field(min_length=1, max_length=262144)
    explanation: str = Field(max_length=4000)


def _tool(name: str, description: str, schema: type[Arguments]) -> FunctionToolParam:
    return {
        "type": "function",
        "name": name,
        "description": description,
        "strict": True,
        "parameters": schema.model_json_schema(),
    }


TOOL_SCHEMAS: list[FunctionToolParam] = [
    _tool("list_files", "List one project directory; use '.' for root.", ListFiles),
    _tool("read_file", "Read a bounded range of a safe UTF-8 project file.", ReadFile),
    _tool("submit_patch", "Submit the candidate implementation diff.", SubmitPatch),
]


def _safe_parts(value: str, *, root_allowed: bool = False) -> tuple[str, ...]:
    if root_allowed and value == ".":
        return ()
    parts = PurePosixPath(value).parts
    if (
        not parts
        or PurePosixPath(value).is_absolute()
        or "\\" in value
        or any(ord(char) < 32 or ord(char) == 127 for char in value)
        or any(part.startswith(".") or SENSITIVE_NAME.search(part) for part in parts)
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

    def __init__(self, root: Path) -> None:
        self.root = root.absolute()
        if self.root.is_symlink() or not self.root.is_dir():
            raise AgentError("agent workspace must be a real directory")

    def execute(self, name: str, arguments: str) -> AgentProposal | dict[str, object]:
        """Validate every call locally, including providers without strict schemas."""
        if not isinstance(arguments, str):
            raise AgentError("provider returned invalid tool arguments")
        if len(arguments.encode("utf-8")) > MAX_ARGUMENT_BYTES:
            raise AgentError("provider tool arguments exceeded the size limit")
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
            raise AgentError("provider returned invalid tool arguments") from None
        except (OSError, UnicodeError, ValueError):
            return {"error": "requested path is unavailable or not permitted"}

    def list_files(self, argument: ListFiles) -> dict[str, object]:
        """List safe immediate entries without following symbolic links."""
        parts = _safe_parts(argument.directory, root_allowed=True)
        descriptor = _open_directory(self.root, parts)
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
        directory = _open_directory(self.root, parts[:-1])
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
        if "\x00" in text or SENSITIVE_CONTENT.search(text):
            raise ValueError("file may contain binary data or credentials")
        lines = text.splitlines()
        start = argument.start_line - 1
        end = start + argument.line_count
        return {
            "path": argument.path,
            "start_line": argument.start_line,
            "content": "\n".join(lines[start:end]),
            "truncated": truncated or end < len(lines),
            "readable_lines": len(lines),
        }
