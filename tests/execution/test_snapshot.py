"""Exercise the shared preflight and staging boundary on real filesystem entries."""

import os
from pathlib import Path

import pytest

from seam.execution import snapshot


def check_snapshot(workspace: Path, destination: Path, stage: bool) -> None:
    if stage:
        snapshot.stage_snapshot(workspace, destination)
    else:
        snapshot.preflight_snapshot(workspace)
        assert not destination.exists()


def test_materializes_contained_file_links_without_copying_excluded_entries(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    (workspace / "assets").mkdir(parents=True)
    (workspace / "docs").mkdir()
    (workspace / "assets/icon.png").write_bytes(b"image")
    (workspace / "docs/icon.png").symlink_to("../assets/icon.png")
    (workspace / "alias.png").symlink_to("docs/icon.png")
    (workspace / ".env.deepseek").write_text("private")
    (workspace / ".git").mkdir()
    (workspace / ".git/config").write_text("private")
    (workspace / "run.py").write_text("print('source')\n")
    (workspace / "run.py").chmod(0o755)
    destination = tmp_path / "snapshot"

    snapshot.preflight_snapshot(workspace)
    assert not destination.exists()
    snapshot.stage_snapshot(workspace, destination)

    assert (destination / "docs/icon.png").read_bytes() == b"image"
    assert (destination / "alias.png").read_bytes() == b"image"
    assert not (destination / "docs/icon.png").is_symlink()
    assert not (destination / "alias.png").is_symlink()
    assert not (destination / ".env.deepseek").exists()
    assert not (destination / ".git").exists()
    assert (destination / "run.py").stat().st_mode & 0o777 == 0o755
    assert (workspace / "docs/icon.png").is_symlink()


@pytest.mark.parametrize("stage", [False, True])
@pytest.mark.parametrize(
    ("target", "expected"),
    [
        ("../outside", "escapes"),
        ("/etc/passwd", "Absolute"),
        ("missing", "No such file"),
        (".env", "excluded"),
        (".env.deepseek", "excluded"),
        (".aws/credentials", "excluded"),
        ("credentials/config", "excluded"),
        ("secret.pem", "excluded"),
        (".git/../ordinary.py", "excluded"),
        ("cache/../.env", "excluded"),
    ],
)
def test_rejects_unsafe_aliases_with_the_offending_relative_path(
    tmp_path: Path, stage: bool, target: str, expected: str
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "ordinary.py").write_text("source")
    (workspace / "visible.py").symlink_to(target)
    with pytest.raises(ValueError, match=rf"'visible.py': .*{expected}"):
        check_snapshot(workspace, tmp_path / "snapshot", stage)


@pytest.mark.parametrize("stage", [False, True])
def test_cannot_hide_an_excluded_target_behind_a_file_link_chain(
    tmp_path: Path, stage: bool
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / ".env").write_text("private")
    (workspace / "second.py").symlink_to(".env")
    (workspace / "first.py").symlink_to("second.py")
    with pytest.raises(ValueError, match=r"Snapshot path .*: .*excluded"):
        check_snapshot(workspace, tmp_path / "snapshot", stage)


@pytest.mark.parametrize("stage", [False, True])
def test_rejects_directory_links_even_when_contained(
    tmp_path: Path, stage: bool
) -> None:
    workspace = tmp_path / "workspace"
    (workspace / "ordinary").mkdir(parents=True)
    (workspace / "linked").symlink_to("ordinary", target_is_directory=True)
    with pytest.raises(ValueError, match=r"'linked': .*symbolic link"):
        check_snapshot(workspace, tmp_path / "snapshot", stage)


@pytest.mark.parametrize("stage", [False, True])
def test_file_alias_cannot_traverse_linked_target_ancestors(
    tmp_path: Path, stage: bool
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "private.py").write_text("private")
    (workspace / ".git").symlink_to(outside, target_is_directory=True)
    (workspace / "visible.py").symlink_to(".git/private.py")
    with pytest.raises(ValueError, match=r"'visible.py': .*excluded"):
        check_snapshot(workspace, tmp_path / "snapshot", stage)


@pytest.mark.parametrize("stage", [False, True])
def test_file_alias_does_not_follow_a_linked_ancestor_before_its_directory_is_walked(
    tmp_path: Path, stage: bool
) -> None:
    workspace = tmp_path / "workspace"
    (workspace / "ordinary").mkdir(parents=True)
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "private.py").write_text("private")
    (workspace / "ordinary/inside").symlink_to(outside, target_is_directory=True)
    (workspace / "visible.py").symlink_to("ordinary/inside/private.py")
    with pytest.raises(ValueError, match=r"'visible.py':"):
        check_snapshot(workspace, tmp_path / "snapshot", stage)


@pytest.mark.parametrize("stage", [False, True])
def test_rejects_file_link_cycles(tmp_path: Path, stage: bool) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "first.py").symlink_to("second.py")
    (workspace / "second.py").symlink_to("first.py")
    with pytest.raises(ValueError, match=r"Snapshot path .*: .*cycle"):
        check_snapshot(workspace, tmp_path / "snapshot", stage)


@pytest.mark.parametrize("stage", [False, True])
@pytest.mark.parametrize("alias", [False, True])
def test_rejects_hard_linked_files_and_aliases_to_them(
    tmp_path: Path, stage: bool, alias: bool
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    outside = tmp_path / "outside"
    outside.write_text("private")
    os.link(outside, workspace / "ordinary.py")
    if alias:
        (workspace / "visible.py").symlink_to("ordinary.py")
    with pytest.raises(ValueError, match="hard links"):
        check_snapshot(workspace, tmp_path / "snapshot", stage)


@pytest.mark.parametrize("stage", [False, True])
def test_rejects_special_files_without_blocking(tmp_path: Path, stage: bool) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    os.mkfifo(workspace / "pipe")
    with pytest.raises(ValueError, match=r"'pipe': .*ordinary files"):
        check_snapshot(workspace, tmp_path / "snapshot", stage)


@pytest.mark.parametrize("stage", [False, True])
@pytest.mark.parametrize(
    ("limit", "value", "expected"),
    [
        ("MAX_SNAPSHOT_BYTES", 6, "size limit"),
        ("MAX_SNAPSHOT_FILES", 1, "too many"),
        ("MAX_SNAPSHOT_DEPTH", 0, "nesting"),
        ("MAX_SNAPSHOT_LINKS", 0, "chain"),
    ],
)
def test_preflight_and_staging_share_materialized_size_and_entry_limits(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    stage: bool,
    limit: str,
    value: int,
    expected: str,
) -> None:
    workspace = tmp_path / "workspace"
    (workspace / "package").mkdir(parents=True)
    (workspace / "package/source.py").write_bytes(b"data")
    (workspace / "alias.py").symlink_to("package/source.py")
    monkeypatch.setattr(snapshot, limit, value)
    with pytest.raises(ValueError, match=expected):
        check_snapshot(workspace, tmp_path / "snapshot", stage)


def test_regular_file_copy_still_rejects_a_direct_symlink(tmp_path: Path) -> None:
    (tmp_path / "source").write_text("source")
    (tmp_path / "link").symlink_to("source")
    with pytest.raises(OSError):
        snapshot.copy_regular_file(tmp_path / "link", tmp_path / "copied", 100)
    assert not (tmp_path / "copied").exists()


@pytest.mark.parametrize("stage", [False, True])
@pytest.mark.parametrize("alias", [False, True])
def test_file_replacement_with_a_symlink_cannot_expose_outside_data(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, stage: bool, alias: bool
) -> None:
    workspace = tmp_path / "workspace"
    (workspace / "ordinary").mkdir(parents=True)
    (workspace / "ordinary/source.py").write_text("source")
    if alias:
        (workspace / "visible.py").symlink_to("ordinary/source.py")
    outside = tmp_path / "private"
    outside.write_text("private")
    original_open = os.open

    def replace_before_open(
        path: str | Path,
        flags: int,
        mode: int = 0o777,
        *,
        dir_fd: int | None = None,
    ) -> int:
        if path == "source.py":
            (workspace / "ordinary/source.py").unlink()
            (workspace / "ordinary/source.py").symlink_to(outside)
        return original_open(path, flags, mode, dir_fd=dir_fd)

    monkeypatch.setattr(os, "open", replace_before_open)
    destination = tmp_path / "snapshot"
    with pytest.raises(ValueError, match="symbolic links"):
        check_snapshot(workspace, destination, stage)
    assert not (destination / "ordinary/source.py").exists()
    assert not (destination / "visible.py").exists()


def test_file_link_chain_limit_accepts_the_exact_boundary(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "first.py").symlink_to("second.py")
    (workspace / "second.py").symlink_to("source.py")
    (workspace / "source.py").write_text("source")
    monkeypatch.setattr(snapshot, "MAX_SNAPSHOT_LINKS", 2)
    snapshot.preflight_snapshot(workspace)
    destination = tmp_path / "snapshot"
    snapshot.stage_snapshot(workspace, destination)
    assert (destination / "first.py").read_text() == "source"


def test_snapshot_error_escapes_terminal_control_characters(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    name = "visible\n\x1b[31m.py"
    (workspace / name).symlink_to("../outside")
    with pytest.raises(ValueError) as caught:
        snapshot.preflight_snapshot(workspace)
    assert repr(name) in str(caught.value)
    assert "\n" not in str(caught.value)
    assert "\x1b" not in str(caught.value)


def test_directory_walk_errors_have_bounded_escaped_paths(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    def unreadable_walk(*args: object, **kwargs: object) -> None:
        callback = kwargs["onerror"]
        assert callable(callback)
        callback(OSError(13, "Permission denied", "bad\n\x1b" + "x" * 2000))

    monkeypatch.setattr(os, "fwalk", unreadable_walk)
    with pytest.raises(ValueError) as caught:
        snapshot.preflight_snapshot(workspace)
    message = str(caught.value)
    assert "\\n\\x1b" in message
    assert "\n" not in message
    assert "\x1b" not in message
    assert len(message) < snapshot.MAX_SNAPSHOT_PATH_CHARACTERS + 100


def test_snapshot_root_must_be_an_ordinary_directory(tmp_path: Path) -> None:
    root = tmp_path / "linked"
    root.symlink_to(tmp_path, target_is_directory=True)
    with pytest.raises(ValueError, match=r"Snapshot path '.': .*ordinary directory"):
        snapshot.preflight_snapshot(root)


@pytest.mark.parametrize("stage", [False, True])
@pytest.mark.parametrize(
    "target",
    [
        "missing/../implementation.py",
        "missing/./../implementation.py",
        "implementation.py/../implementation.py",
        "implementation.py/.",
        "implementation.py/",
    ],
)
def test_broken_native_file_links_cannot_become_importable_in_a_snapshot(
    tmp_path: Path, stage: bool, target: str
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "implementation.py").write_text("source")
    alias = workspace / "alias.py"
    alias.symlink_to(target)
    with pytest.raises((FileNotFoundError, NotADirectoryError)):
        alias.read_bytes()
    destination = tmp_path / "snapshot"
    with pytest.raises(ValueError, match=r"'alias.py':"):
        check_snapshot(workspace, destination, stage)
    assert not (destination / "alias.py").exists()


@pytest.mark.parametrize(
    ("directory", "target"),
    [
        ("", "existing_dir/../implementation.py"),
        ("", "existing_dir/./../implementation.py"),
        ("", "./implementation.py"),
        ("package", "../implementation.py"),
    ],
)
def test_native_contained_parent_traversal_preserves_file_contents(
    tmp_path: Path, directory: str, target: str
) -> None:
    workspace = tmp_path / "workspace"
    (workspace / "existing_dir").mkdir(parents=True)
    (workspace / "package").mkdir()
    (workspace / "implementation.py").write_text("source")
    alias = workspace / directory / "alias.py"
    alias.symlink_to(target)
    expected = alias.read_bytes()
    snapshot.preflight_snapshot(workspace)
    destination = tmp_path / "snapshot"
    snapshot.stage_snapshot(workspace, destination)
    materialized = destination / directory / "alias.py"
    assert not materialized.is_symlink()
    assert materialized.read_bytes() == expected
