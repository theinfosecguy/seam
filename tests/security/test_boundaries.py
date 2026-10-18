"""Screen model egress while preserving ordinary local source snapshots."""

import json
from pathlib import Path

import pytest
from pydantic_ai.messages import (
    ModelRequest,
    ModelResponse,
    TextPart,
    ThinkingPart,
    ToolReturnPart,
    UserPromptPart,
)

from seam.agent.prompts import check_conversation_size, initial_conversation
from seam.agent.tools import WorkspaceTools
from seam.exceptions import AgentError
from seam.execution.snapshot import (
    copy_regular_file,
    preflight_snapshot,
    stage_snapshot,
)
from seam.models import AgentContext

_CREDENTIAL = 'password = "synthetic-private-value"'


@pytest.mark.parametrize("field", ["upstream_diff", "feedback"])
def test_context_credentials_are_rejected_without_source_in_error(
    tmp_path: Path, field: str
) -> None:
    context = AgentContext(
        workspace=tmp_path,
        upstream_diff=_CREDENTIAL if field == "upstream_diff" else "ordinary source",
        feedback=_CREDENTIAL if field == "feedback" else "",
    )
    with pytest.raises(AgentError, match="may contain credentials") as caught:
        initial_conversation(context)
    assert "synthetic-private-value" not in str(caught.value)


@pytest.mark.parametrize(
    "message",
    [
        ModelRequest(parts=[UserPromptPart(_CREDENTIAL)]),
        ModelRequest(parts=[ToolReturnPart("read_file", _CREDENTIAL, "call")]),
        ModelResponse(parts=[TextPart(_CREDENTIAL)]),
        ModelResponse(parts=[ThinkingPart(_CREDENTIAL)]),
    ],
)
def test_every_outbound_history_part_is_scanned(message: object) -> None:
    assert isinstance(message, ModelRequest | ModelResponse)
    with pytest.raises(AgentError, match="may contain credentials") as caught:
        check_conversation_size([message])
    assert "synthetic-private-value" not in str(caught.value)


@pytest.mark.parametrize("name", ["source.py", "credential.py", "credentials.py"])
def test_workspace_reads_scan_entire_bounded_file_before_selecting_lines(
    tmp_path: Path, name: str
) -> None:
    (tmp_path / name).write_text("ordinary first line\n" + _CREDENTIAL)
    result = WorkspaceTools(tmp_path).execute(
        "read_file",
        json.dumps({"path": name, "start_line": 1, "line_count": 1}),
    )
    assert result == {"error": "requested path is unavailable or not permitted"}


def test_model_submissions_are_scanned_before_the_patch_can_be_used(
    tmp_path: Path,
) -> None:
    with pytest.raises(AgentError, match="may contain credentials"):
        WorkspaceTools(tmp_path).execute(
            "submit_patch", json.dumps({"patch": _CREDENTIAL, "explanation": "change"})
        )


@pytest.mark.parametrize(
    "name", ["secret_detection.py", "credentials.py", "secret.py", "secrets.py"]
)
def test_ordinary_security_source_names_remain_readable_and_listed(
    tmp_path: Path, name: str
) -> None:
    (tmp_path / name).write_text("def detect_secret():\n    pass\n")
    tools = WorkspaceTools(tmp_path)
    result = tools.execute(
        "read_file",
        json.dumps({"path": name, "start_line": 1, "line_count": 1}),
    )
    assert isinstance(result, dict)
    assert result["content"] == "def detect_secret():"
    assert tools.execute("list_files", '{"directory": "."}') == {
        "entries": [name],
        "truncated": False,
    }


@pytest.mark.parametrize("name", ["credentials.py", "secret.py", "secrets.py"])
def test_snapshots_preserve_ordinary_credential_named_source_modules(
    tmp_path: Path, name: str
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / name).write_text("def read_credentials():\n    pass\n")
    destination = tmp_path / "snapshot"
    preflight_snapshot(workspace)
    stage_snapshot(workspace, destination)
    assert (destination / name).read_text() == (workspace / name).read_text()


@pytest.mark.parametrize("stage", [False, True])
def test_offline_snapshot_copies_fixtures_with_literal_passwords(
    tmp_path: Path, stage: bool
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "source.py").write_text(_CREDENTIAL)
    if stage:
        stage_snapshot(workspace, tmp_path / "snapshot")
        assert (tmp_path / "snapshot/source.py").read_text() == _CREDENTIAL
    else:
        preflight_snapshot(workspace)
        assert not (tmp_path / "snapshot").exists()


def test_offline_oracle_copy_allows_literal_password_fixtures(tmp_path: Path) -> None:
    source = tmp_path / "oracle.py"
    source.write_text(_CREDENTIAL)
    destination = tmp_path / "copied.py"
    assert copy_regular_file(source, destination, 65536) == len(_CREDENTIAL)
    assert destination.read_text() == _CREDENTIAL


def test_snapshot_excludes_nested_credential_stores_without_reading_them(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    store = workspace / "package/.config/gcloud"
    store.mkdir(parents=True)
    (store / "private.json").write_text(_CREDENTIAL)
    (workspace / "package/.git").mkdir()
    (workspace / "package/.git/config").write_text(_CREDENTIAL)
    (workspace / "package/source.py").write_text("ordinary source")
    destination = tmp_path / "snapshot"
    stage_snapshot(workspace, destination)
    assert not (destination / "package/.config/gcloud").exists()
    assert not (destination / "package/.git").exists()
    assert (destination / "package/source.py").read_text() == "ordinary source"
