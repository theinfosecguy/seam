"""Validated model tool arguments and their generated provider schemas."""

from typing import Any, Final, TypedDict

from pydantic import BaseModel, ConfigDict, Field

from seam.constants.agent import MAX_PATCH_CHARACTERS


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

    patch: str = Field(min_length=1, max_length=MAX_PATCH_CHARACTERS)
    explanation: str = Field(max_length=4000)


class ToolSchema(TypedDict):
    """Provider-independent metadata generated from locally validated arguments."""

    name: str
    description: str
    parameters: dict[str, Any]


def _tool(name: str, description: str, schema: type[Arguments]) -> ToolSchema:
    return {
        "name": name,
        "description": description,
        "parameters": schema.model_json_schema(),
    }


TOOL_SCHEMAS: Final[list[ToolSchema]] = [
    _tool("list_files", "List one project directory; use '.' for root.", ListFiles),
    _tool("read_file", "Read a bounded range of a safe UTF-8 project file.", ReadFile),
    _tool("submit_patch", "Submit the candidate implementation diff.", SubmitPatch),
]
