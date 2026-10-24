"""Allow only operator-reviewed fixture bytes through the snapshot boundary."""

import hashlib
import os
from pathlib import Path

import pytest

from seam.agent.tools import WorkspaceTools
from seam.execution import snapshot
from seam.security.paths import validate_reviewed_fixtures

FIXTURE = (
    b"-----BEGIN PRIVATE KEY-----\npublic-test-fixture\n-----END PRIVATE KEY-----\n"
)
FIXTURE_PATH = "tests/fixtures/example.pem"
DIGEST = hashlib.sha256(FIXTURE).hexdigest()
MANIFEST = {FIXTURE_PATH: (DIGEST,)}


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    root = tmp_path / "workspace"
    (root / "tests/fixtures").mkdir(parents=True)
    (root / FIXTURE_PATH).write_bytes(FIXTURE)
    return root


def check_snapshot(
    workspace: Path,
    destination: Path,
    stage: bool,
    manifest: dict[str, tuple[str, ...]] = MANIFEST,
) -> None:
    if stage:
        snapshot.stage_snapshot(workspace, destination, reviewed_fixtures=manifest)
    else:
        snapshot.preflight_snapshot(workspace, reviewed_fixtures=manifest)
        assert not destination.exists()


def test_only_exact_reviewed_fixture_is_staged_and_model_access_stays_blocked(
    workspace: Path, tmp_path: Path
) -> None:
    (workspace / "tests/fixtures/unreviewed.pem").write_bytes(FIXTURE)
    snapshot.preflight_snapshot(workspace, reviewed_fixtures=MANIFEST)
    destination = tmp_path / "snapshot"
    snapshot.stage_snapshot(workspace, destination, reviewed_fixtures=MANIFEST)

    assert (destination / FIXTURE_PATH).read_bytes() == FIXTURE
    assert not (destination / "tests/fixtures/unreviewed.pem").exists()
    assert (workspace / FIXTURE_PATH).read_bytes() == FIXTURE
    assert WorkspaceTools(workspace).execute(
        "read_file",
        '{"path":"tests/fixtures/example.pem","start_line":1,"line_count":10}',
    ) == {"error": "requested path is unavailable or not permitted"}


def test_default_snapshot_still_excludes_reviewed_fixture_bytes(
    workspace: Path, tmp_path: Path
) -> None:
    snapshot.preflight_snapshot(workspace)
    destination = tmp_path / "snapshot"
    snapshot.stage_snapshot(workspace, destination)
    assert not (destination / FIXTURE_PATH).exists()


@pytest.mark.parametrize("stage", [False, True])
def test_explicit_revision_hash_variants_are_accepted(
    workspace: Path, tmp_path: Path, stage: bool
) -> None:
    manifest = {FIXTURE_PATH: ("0" * 64, DIGEST)}
    check_snapshot(workspace, tmp_path / "snapshot", stage, manifest)


@pytest.mark.parametrize("stage", [False, True])
@pytest.mark.parametrize("change", ["missing", "changed"])
def test_missing_or_changed_reviewed_fixture_fails_closed(
    workspace: Path, tmp_path: Path, stage: bool, change: str
) -> None:
    fixture = workspace / FIXTURE_PATH
    fixture.unlink()
    if change == "changed":
        fixture.write_bytes(b"unreviewed-value")
    destination = tmp_path / "snapshot"
    with pytest.raises(ValueError, match=r"missing|SHA-256") as caught:
        check_snapshot(workspace, destination, stage)
    assert "unreviewed-value" not in str(caught.value)
    assert not (destination / FIXTURE_PATH).exists()


def test_staging_rechecks_fixture_after_successful_preflight(
    workspace: Path, tmp_path: Path
) -> None:
    snapshot.preflight_snapshot(workspace, reviewed_fixtures=MANIFEST)
    (workspace / FIXTURE_PATH).write_bytes(FIXTURE + b"changed")
    destination = tmp_path / "snapshot"
    with pytest.raises(ValueError, match="SHA-256"):
        snapshot.stage_snapshot(workspace, destination, reviewed_fixtures=MANIFEST)
    assert not (destination / FIXTURE_PATH).exists()


@pytest.mark.parametrize("stage", [False, True])
@pytest.mark.parametrize("kind", ["symlink", "hardlink", "fifo", "directory"])
def test_review_never_allows_linked_or_special_files(
    workspace: Path, tmp_path: Path, stage: bool, kind: str
) -> None:
    fixture = workspace / FIXTURE_PATH
    fixture.unlink()
    ordinary = workspace / "ordinary.txt"
    ordinary.write_bytes(FIXTURE)
    if kind == "symlink":
        fixture.symlink_to("../../ordinary.txt")
    elif kind == "hardlink":
        os.link(ordinary, fixture)
    elif kind == "fifo":
        os.mkfifo(fixture)
    else:
        fixture.mkdir()
    with pytest.raises(ValueError, match=r"symbolic|hard links|ordinary|missing"):
        check_snapshot(workspace, tmp_path / "snapshot", stage)


@pytest.mark.parametrize("stage", [False, True])
def test_reviewed_fixture_cannot_use_a_directory_symlink(
    workspace: Path, tmp_path: Path, stage: bool
) -> None:
    (workspace / FIXTURE_PATH).unlink()
    (workspace / "tests/fixtures").rmdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "example.pem").write_bytes(FIXTURE)
    (workspace / "tests/fixtures").symlink_to(outside, target_is_directory=True)
    with pytest.raises(ValueError, match="Absolute symbolic link"):
        check_snapshot(workspace, tmp_path / "snapshot", stage)


@pytest.mark.parametrize("stage", [False, True])
def test_reviewed_fixture_path_cannot_traverse_a_contained_directory_link(
    workspace: Path, tmp_path: Path, stage: bool
) -> None:
    (workspace / FIXTURE_PATH).unlink()
    (workspace / "tests/fixtures").rmdir()
    (workspace / "ordinary").mkdir()
    (workspace / "ordinary/example.pem").write_bytes(FIXTURE)
    (workspace / "tests/fixtures").symlink_to("../ordinary", target_is_directory=True)
    with pytest.raises(ValueError, match="reviewed fixture is missing or excluded"):
        check_snapshot(workspace, tmp_path / "snapshot", stage)
    assert not (tmp_path / "snapshot/ordinary/example.pem").exists()


@pytest.mark.parametrize("stage", [False, True])
def test_review_does_not_allow_aliases_to_a_sensitive_fixture(
    workspace: Path, tmp_path: Path, stage: bool
) -> None:
    (workspace / "alias.txt").symlink_to(FIXTURE_PATH)
    with pytest.raises(ValueError, match="excluded"):
        check_snapshot(workspace, tmp_path / "snapshot", stage)


@pytest.mark.parametrize(
    "path",
    [
        "/tmp/example.pem",
        "./example.pem",
        "tests//example.pem",
        "tests/../example.pem",
        "tests\\example.pem",
        "tests/example.pem\n",
        "tests/example.txt",
        ".env.pem",
        "id_rsa.pem",
        "credentials.key",
        ".git/example.pem",
        ".venv/example.pem",
        ".aws/example.pem",
        ".config/gcloud/example.pem",
        "tests/.env.local/example.pem",
        "tests/secret.key/example.pem",
    ],
)
def test_invalid_review_cannot_bypass_excluded_ancestors_or_credential_stores(
    workspace: Path, tmp_path: Path, path: str
) -> None:
    manifest = {path: (DIGEST,)}
    with pytest.raises(ValueError, match="exact key-file paths"):
        snapshot.preflight_snapshot(workspace, reviewed_fixtures=manifest)
    with pytest.raises(ValueError, match="exact key-file paths"):
        snapshot.stage_snapshot(
            workspace, tmp_path / "snapshot", reviewed_fixtures=manifest
        )


@pytest.mark.parametrize(
    "digests",
    [(), ("a",), ("A" * 64,), ("z" * 64,), (DIGEST, DIGEST)],
)
def test_manifest_rejects_invalid_hash_declarations(digests: tuple[str, ...]) -> None:
    with pytest.raises(ValueError, match="SHA-256"):
        validate_reviewed_fixtures({FIXTURE_PATH: digests})


@pytest.mark.parametrize("stage", [False, True])
def test_reviewed_fixture_bytes_still_count_toward_snapshot_limit(
    workspace: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, stage: bool
) -> None:
    monkeypatch.setattr(snapshot, "MAX_SNAPSHOT_BYTES", len(FIXTURE) - 1)
    with pytest.raises(ValueError, match="size limit"):
        check_snapshot(workspace, tmp_path / "snapshot", stage)


@pytest.mark.parametrize("stage", [False, True])
def test_fixture_replacement_before_open_cannot_copy_unreviewed_data(
    workspace: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, stage: bool
) -> None:
    original_open = os.open

    def replace_before_open(
        path: str | Path,
        flags: int,
        mode: int = 0o777,
        *,
        dir_fd: int | None = None,
    ) -> int:
        if path == "example.pem":
            (workspace / FIXTURE_PATH).write_bytes(b"unreviewed-replacement")
        return original_open(path, flags, mode, dir_fd=dir_fd)

    monkeypatch.setattr(os, "open", replace_before_open)
    destination = tmp_path / "snapshot"
    with pytest.raises(ValueError, match="SHA-256"):
        check_snapshot(workspace, destination, stage)
    assert not (destination / FIXTURE_PATH).exists()
