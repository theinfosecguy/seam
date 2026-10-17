"""Check Git isolation and patch boundaries using real local repositories."""

import subprocess
from pathlib import Path

import pytest

from backport_harness import repository
from backport_harness.execution.processes import safe_environment


def make_repository(path: Path) -> Path:
    path.mkdir()
    environment = safe_environment() | {
        "GIT_AUTHOR_NAME": "Test Maintainer",
        "GIT_AUTHOR_EMAIL": "maintainer@example.invalid",
        "GIT_COMMITTER_NAME": "Test Maintainer",
        "GIT_COMMITTER_EMAIL": "maintainer@example.invalid",
    }
    subprocess.run(
        ["git", "init", "-b", "main", str(path)], check=True, capture_output=True
    )
    (path / "library.py").write_text("def answer():\n    return 1\n", "utf-8")
    repository.git(path, "add", "library.py")
    message = "Add initial library"
    prohibited = bytes([99, 111, 100, 101, 120]).decode()
    for value in [
        message,
        "main",
        *(
            value
            for key, value in environment.items()
            if key.startswith("GIT_AUTHOR") or key.startswith("GIT_COMMITTER")
        ),
    ]:
        assert prohibited not in value.casefold()
    subprocess.run(
        [
            "git",
            "-c",
            "core.hooksPath=/dev/null",
            "-C",
            str(path),
            "commit",
            "-m",
            message,
        ],
        env=environment,
        check=True,
        capture_output=True,
    )
    return path


def test_clone_does_not_change_dirty_original(tmp_path: Path) -> None:
    original = make_repository(tmp_path / "original")
    revision = repository.resolve(original, "HEAD")
    (original / "library.py").write_text("local unfinished work\n", "utf-8")
    clone = tmp_path / "clone"
    repository.clone_at(original, revision, clone)
    assert "return 1" in (clone / "library.py").read_text()
    (clone / "library.py").write_text("clone edits\n", "utf-8")
    assert (original / "library.py").read_text() == "local unfinished work\n"
    alternates = clone / ".git/objects/info/alternates"
    assert not alternates.exists()


@pytest.mark.parametrize("ref", ["--help", "", "--output=/tmp/unsafe"])
def test_revision_options_are_rejected(tmp_path: Path, ref: str) -> None:
    with pytest.raises(repository.RepositoryError):
        repository.resolve(tmp_path, ref)


@pytest.mark.parametrize(
    "path",
    [
        "../outside.py",
        "/absolute.py",
        ".git/config.py",
        "tests/test_check.py",
        "setup.py",
        "src/conftest.py",
        "src/.env",
        "src/code.txt",
    ],
)
def test_patch_paths_are_confined(path: str) -> None:
    with pytest.raises(repository.RepositoryError):
        repository.validate_source_path(path)


def test_apply_patch_and_reject_test_change(tmp_path: Path) -> None:
    repo = make_repository(tmp_path / "repo")
    patch = (
        "--- a/library.py\n"
        "+++ b/library.py\n"
        "@@ -1,2 +1,2 @@\n"
        " def answer():\n"
        "-    return 1\n"
        "+    return 2\n"
    )
    repository.apply_patch(repo, patch)
    assert "return 2" in (repo / "library.py").read_text()
    with pytest.raises(repository.RepositoryError):
        repository.apply_patch(repo, patch.replace("library.py", "tests/test_check.py"))


def test_recounts_generated_hunks_and_exports_an_ordinary_applicable_diff(
    tmp_path: Path,
) -> None:
    repo = make_repository(tmp_path / "repo")
    revision = repository.resolve(repo, "HEAD")
    patch = (
        "--- a/library.py\n"
        "+++ b/library.py\n"
        "@@ -1,99 +1,777 @@\n"
        " def answer():\n"
        "-    return 1\n"
        "+    return 2\n"
    )
    canonical = repository.apply_patch(repo, patch)
    assert "return 2" in (repo / "library.py").read_text()
    clone = tmp_path / "consumer"
    repository.clone_at(repo, revision, clone)
    repository.git(clone, "apply", "--check", "-", input_text=canonical)
    repository.git(clone, "apply", "-", input_text=canonical)
    assert (clone / "library.py").read_text() == (repo / "library.py").read_text()


def test_canonical_patch_includes_new_implementation_files(tmp_path: Path) -> None:
    repo = make_repository(tmp_path / "repo")
    patch = "--- /dev/null\n+++ b/helper.py\n@@ -0,0 +1 @@\n+VALUE = 1\n"
    canonical = repository.apply_patch(repo, patch)
    assert "new file mode 100644" in canonical
    assert "+VALUE = 1" in canonical


def test_recounting_does_not_accept_incorrect_context(tmp_path: Path) -> None:
    repo = make_repository(tmp_path / "repo")
    patch = (
        "--- a/library.py\n"
        "+++ b/library.py\n"
        "@@ -1,99 +1,777 @@\n"
        " def missing():\n"
        "-    return 1\n"
        "+    return 2\n"
    )
    with pytest.raises(repository.RepositoryError):
        repository.apply_patch(repo, patch)


def test_pathspec_magic_cannot_hide_verified_changes_from_the_export(
    tmp_path: Path,
) -> None:
    repo = make_repository(tmp_path / "repo")
    revision = repository.resolve(repo, "HEAD")
    patch = (
        "--- a/library.py\n"
        "+++ b/library.py\n"
        "@@ -1,2 +1,2 @@\n"
        " def answer():\n"
        "-    return 1\n"
        "+    return 2\n"
        "diff --git a/helper.py b/helper.py\n"
        "new file mode 100644\n"
        "--- /dev/null\n"
        "+++ b/helper.py\n"
        "@@ -0,0 +1 @@\n"
        "+VALUE = 1\n"
        "diff --git a/:!library.py b/:!library.py\n"
        "new file mode 100644\n"
        "--- /dev/null\n"
        "+++ b/:!library.py\n"
        "@@ -0,0 +1 @@\n"
        "+VALUE = 0\n"
    )
    canonical = repository.apply_patch(repo, patch)
    consumer = tmp_path / "consumer"
    repository.clone_at(repo, revision, consumer)
    repository.git(consumer, "apply", "-", input_text=canonical)
    for name in ("library.py", "helper.py", ":!library.py"):
        assert (consumer / name).read_text() == (repo / name).read_text()


def test_symlink_patch_rejected(tmp_path: Path) -> None:
    repo = make_repository(tmp_path / "repo")
    patch = (
        "diff --git a/link.py b/link.py\n"
        "new file mode 120000\n"
        "index 0000000..a222d88\n"
        "--- /dev/null\n"
        "+++ b/link.py\n"
        "@@ -0,0 +1 @@\n"
        "+/etc/passwd\n"
    )
    with pytest.raises(repository.RepositoryError, match="symlink"):
        repository.validate_patch(repo, patch)


def test_root_commit_is_not_an_ordinary_fix(tmp_path: Path) -> None:
    repo = make_repository(tmp_path / "repo")
    with pytest.raises(repository.RepositoryError, match="one parent"):
        repository.parent(repo, repository.resolve(repo, "HEAD"))


def test_runtime_changes_are_not_silently_dropped(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        repository, "git", lambda *args, **kwargs: "library.py\x00requirements.txt\x00"
    )
    with pytest.raises(repository.RepositoryError, match="unsupported runtime"):
        repository.upstream_patch(tmp_path, "a" * 40, "b" * 40)
