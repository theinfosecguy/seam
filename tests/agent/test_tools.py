"""Keep every source revision behind the same bounded read-only policy."""

import json
import os
from pathlib import Path

import pytest
from pydantic_ai.messages import (
    ModelRequest,
    ModelResponse,
    ToolCallPart,
    ToolReturnPart,
    UserPromptPart,
)
from pydantic_ai.models.function import FunctionModel
from pydantic_ai.usage import RequestUsage

from seam.agent import PatchAgent
from seam.agent.prompts import initial_conversation
from seam.agent.schemas import TOOL_SCHEMAS
from seam.agent.tools import WorkspaceTools
from seam.constants.agent import MAX_CONTEXT_BYTES, MAX_TEXT_BYTES
from seam.constants.repository import MAX_PATCH_BYTES
from seam.exceptions import AgentError
from seam.models import AgentContext

REVISIONS = ("target", "upstream_parent", "upstream_fix")


def _tools(workspace: Path) -> WorkspaceTools:
    for revision in REVISIONS:
        (workspace / revision).mkdir()
    return WorkspaceTools(*(workspace / revision for revision in REVISIONS))


@pytest.mark.parametrize("revision", REVISIONS)
def test_tools_select_revision_and_filter_unsafe_entries(
    tmp_path: Path, revision: str
) -> None:
    tools = _tools(tmp_path)
    for name in REVISIONS:
        (tmp_path / name / "source.py").write_text(name)
    root = tmp_path / revision
    for name in (".env", "credentials.json", "data.bin"):
        (root / name).write_text("PRIVATE")
    (root / "linked.py").symlink_to(root / "source.py")
    assert tools.execute(
        "list_files", json.dumps({"directory": ".", "revision": revision})
    ) == {"entries": ["source.py"], "truncated": False}
    result = tools.execute(
        "read_file",
        json.dumps(
            {
                "path": "source.py",
                "start_line": 1,
                "line_count": 1,
                "revision": revision,
            }
        ),
    )
    assert isinstance(result, dict)
    assert result["content"] == revision
    assert result["revision"] == revision
    assert tools.inspected_target is (revision == "target")


@pytest.mark.parametrize("revision", REVISIONS)
@pytest.mark.parametrize(
    "path", ["../outside.py", "/outside.py", ".env", "credentials.json", "linked.py"]
)
def test_all_revisions_deny_escape_and_sensitive_paths(
    tmp_path: Path, revision: str, path: str
) -> None:
    tools = _tools(tmp_path)
    (tmp_path / "outside.py").write_text("PRIVATE")
    (tmp_path / revision / "linked.py").symlink_to(tmp_path / "outside.py")
    assert tools.execute(
        "read_file",
        json.dumps(
            {"path": path, "start_line": 1, "line_count": 1, "revision": revision}
        ),
    ) == {"error": "requested path is unavailable or not permitted"}
    assert not tools.inspected_target


@pytest.mark.parametrize("revision", REVISIONS)
@pytest.mark.parametrize("kind", ["secret", "hardlink", "fifo", "binary"])
def test_all_revisions_scan_and_reject_unsafe_file_contents(
    tmp_path: Path, revision: str, kind: str
) -> None:
    tools = _tools(tmp_path)
    path = tmp_path / revision / "source.py"
    if kind == "secret":
        path.write_text('ordinary first line\npassword = "synthetic-private-value"')
    elif kind == "hardlink":
        (tmp_path / "outside.py").write_text("PRIVATE")
        os.link(tmp_path / "outside.py", path)
    elif kind == "fifo":
        os.mkfifo(path)
    else:
        path.write_bytes(b"\x00PRIVATE")
    assert tools.execute(
        "read_file",
        json.dumps(
            {
                "path": "source.py",
                "start_line": 1,
                "line_count": 1,
                "revision": revision,
            }
        ),
    ) == {"error": "requested path is unavailable or not permitted"}
    assert not tools.inspected_target


@pytest.mark.parametrize("revision", REVISIONS)
def test_all_revision_reads_remain_bounded(tmp_path: Path, revision: str) -> None:
    tools = _tools(tmp_path)
    (tmp_path / revision / "source.py").write_text("x" * (MAX_TEXT_BYTES + 1))
    result = tools.execute(
        "read_file",
        json.dumps(
            {
                "path": "source.py",
                "start_line": 1,
                "line_count": 1,
                "revision": revision,
            }
        ),
    )
    assert isinstance(result, dict)
    assert result["truncated"] is True
    assert len(str(result["content"])) == MAX_TEXT_BYTES


@pytest.mark.parametrize("name", ["list_files", "read_file"])
def test_revision_schema_and_local_validation(tmp_path: Path, name: str) -> None:
    schema = next(tool["parameters"] for tool in TOOL_SCHEMAS if tool["name"] == name)
    assert schema["properties"]["revision"]["enum"] == list(REVISIONS)
    assert schema["properties"]["revision"]["default"] == "target"
    arguments: dict[str, object] = (
        {"directory": "."}
        if name == "list_files"
        else {"path": "source.py", "start_line": 1, "line_count": 1}
    )
    tools = WorkspaceTools(tmp_path)
    for revision in ("../outside", "TARGET", None, 42):
        result = tools.execute(name, json.dumps(arguments | {"revision": revision}))
        assert isinstance(result, dict)
        assert result["parameters"] == schema
    assert tools.execute(
        name, json.dumps(arguments | {"revision": "upstream_fix"})
    ) == {"error": "requested path is unavailable or not permitted"}


@pytest.mark.parametrize(
    "path,content,start_line",
    [
        ("tests/example.py", "unsafe()", 1),
        ("test_example.py", "unsafe()", 1),
        ("conftest.py", "unsafe()", 1),
        ("setup.py", "unsafe()", 1),
        ("README.md", "unsafe()", 1),
        ("example.py", "  \n", 1),
        ("example.py", "unsafe()", 2),
    ],
)
def test_inspection_requires_nonempty_target_implementation(
    tmp_path: Path, path: str, content: str, start_line: int
) -> None:
    selected = tmp_path / path
    selected.parent.mkdir(parents=True, exist_ok=True)
    selected.write_text(content)
    tools = WorkspaceTools(tmp_path)
    tools.execute(
        "read_file",
        json.dumps({"path": path, "start_line": start_line, "line_count": 1}),
    )
    assert not tools.inspected_target


def test_retry_context_preserves_diff_feedback_and_available_sources(
    tmp_path: Path,
) -> None:
    context = AgentContext(
        workspace=tmp_path,
        upstream_diff="upstream change",
        previous_patch="previous full candidate",
        feedback="regression failed",
        upstream_parent_workspace=tmp_path,
        upstream_fix_workspace=tmp_path,
    )
    part = initial_conversation(context)[0].parts[1]
    assert isinstance(part, UserPromptPart)
    assert isinstance(part.content, str)
    assert json.loads(part.content) == {
        "upstream_diff": context.upstream_diff,
        "previous_patch": context.previous_patch,
        "feedback": context.feedback,
        "available_revisions": list(REVISIONS),
    }
    assert str(tmp_path) not in part.content


def test_both_maximum_diff_contexts_fit_without_truncation(tmp_path: Path) -> None:
    patch = ("+ordinary_code()\n" * MAX_PATCH_BYTES)[:MAX_PATCH_BYTES]
    context = AgentContext(
        workspace=tmp_path, upstream_diff=patch, previous_patch=patch
    )
    part = initial_conversation(context)[0].parts[1]
    assert isinstance(part, UserPromptPart)
    assert isinstance(part.content, str)
    payload = json.loads(part.content)
    assert payload["upstream_diff"] == patch
    assert payload["previous_patch"] == patch
    assert len(part.content.encode("utf-8")) < MAX_CONTEXT_BYTES


def test_submission_requires_a_target_read_in_each_proposal(tmp_path: Path) -> None:
    (tmp_path / "source.py").write_text("unsafe()\n")
    read = {"path": "source.py", "start_line": 1, "line_count": 1}
    submit = {"patch": "candidate diff", "explanation": "Preserve the release API."}
    calls = [
        ("submit_patch", submit),
        ("read_file", read | {"revision": "upstream_fix"}),
        ("submit_patch", submit),
        ("read_file", read),
        ("submit_patch", submit),
        ("submit_patch", submit),
        ("read_file", read),
        ("submit_patch", submit),
    ]
    rejections = []
    call_count = 0

    def model(messages: list[object], info: object) -> ModelResponse:
        nonlocal call_count
        latest = messages[-1]
        if isinstance(latest, ModelRequest):
            rejections.extend(
                part.content
                for part in latest.parts
                if isinstance(part, ToolReturnPart) and part.tool_name == "submit_patch"
            )
        name, arguments = calls.pop(0)
        call_count += 1
        return ModelResponse(
            parts=[ToolCallPart(name, arguments, f"call_{call_count}")],
            usage=RequestUsage(input_tokens=100, output_tokens=50),
            finish_reason="tool_call",
        )

    agent = PatchAgent(
        provider="openai",
        model="gpt-5.4-mini",
        model_instance=FunctionModel(model),
        budget_usd=None,
    )
    context = AgentContext(
        workspace=tmp_path,
        upstream_diff="upstream diff",
        upstream_fix_workspace=tmp_path,
    )
    try:
        assert agent.propose(context).patch == "candidate diff"
        assert agent.propose(context).patch == "candidate diff"
    finally:
        agent.close()
    assert call_count == 8
    assert len(rejections) == 3
    assert all(
        "Read at least one nonempty target implementation" in str(r) for r in rejections
    )


@pytest.mark.parametrize("field", ["upstream_diff", "previous_patch"])
def test_context_diff_limit_counts_utf8_bytes(tmp_path: Path, field: str) -> None:
    context = AgentContext(workspace=tmp_path, upstream_diff="ordinary source")
    setattr(context, field, "é" * (MAX_PATCH_BYTES // 2 + 1))
    with pytest.raises(AgentError, match="diff exceeds"):
        initial_conversation(context)


def test_previous_patch_secrets_are_rejected(tmp_path: Path) -> None:
    context = AgentContext(
        workspace=tmp_path,
        upstream_diff="ordinary source",
        previous_patch='password = "synthetic-private-value"',
    )
    with pytest.raises(AgentError, match="may contain credentials"):
        initial_conversation(context)


def test_aggregate_context_limit_rejects_without_truncation(tmp_path: Path) -> None:
    context = AgentContext(
        workspace=tmp_path,
        upstream_diff="ordinary source",
        feedback="x" * MAX_CONTEXT_BYTES,
    )
    with pytest.raises(AgentError, match="prompt size"):
        initial_conversation(context)
