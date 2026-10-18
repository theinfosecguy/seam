"""Check Git isolation and patch boundaries using real local repositories."""

import subprocess
from pathlib import Path

import pytest

from seam import repository
from seam.exceptions import RepositoryError
from seam.execution.processes import safe_environment


def make_repository(path: Path, content: str = "def answer():\n    return 1\n") -> Path:
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
    (path / "library.py").write_text(content, "utf-8")
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


def test_clone_destination_is_relative_to_callers_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    original = make_repository(tmp_path / "original")
    revision = repository.resolve(original, "HEAD")
    monkeypatch.chdir(tmp_path)
    repository.clone_at(original, revision, Path("clone"))
    assert (tmp_path / "clone/library.py").read_text() == (
        original / "library.py"
    ).read_text()
    assert not (original / "clone").exists()


@pytest.mark.parametrize("ref", ["--help", "", "--output=/tmp/unsafe"])
def test_revision_options_are_rejected(tmp_path: Path, ref: str) -> None:
    with pytest.raises(RepositoryError):
        repository.resolve(tmp_path, ref)


@pytest.mark.parametrize(
    "path",
    [
        "../outside.py",
        "/absolute.py",
        ".git/config.py",
        "tests/test_check.py",
        "Tests/helper.py",
        "TESTS/helpers/check.py",
        "src/Test/helper.py",
        "src/CONFTEST.py",
        "src/Test_check.py",
        "src/check_TEST.py",
        "Docs/helper.py",
        "setup.py",
        "src/conftest.py",
        "src/.env",
        "src/code.txt",
    ],
)
def test_patch_paths_are_confined(path: str) -> None:
    with pytest.raises(RepositoryError):
        repository.validate_source_path(path)


@pytest.mark.parametrize("final_newline", ["\n", ""])
def test_apply_patch_and_reject_test_change(tmp_path: Path, final_newline: str) -> None:
    repo = make_repository(tmp_path / "repo")
    patch = (
        "--- a/library.py\n"
        "+++ b/library.py\n"
        "@@ -1,2 +1,2 @@\n"
        " def answer():\n"
        "-    return 1\n"
        "+    return 2" + final_newline
    )
    repository.apply_patch(repo, patch)
    assert "return 2" in (repo / "library.py").read_text()
    with pytest.raises(RepositoryError, match="outside supported implementation"):
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


def test_captured_unterminated_hunk_exports_an_ordinary_applicable_diff(
    tmp_path: Path,
) -> None:
    source = "\n" * 1890 + (
        "def parse_form(headers):\n"
        "    content_length: int | float | bytes | None = "
        'headers.get("Content-Length")\n'
        "    if content_length is not None:\n"
        "        content_length = int(content_length)\n"
        "    else:\n"
        '        content_length = float("inf")\n'
        "    bytes_read = 0\n"
    )
    repo = make_repository(tmp_path / "repo", source)
    revision = repository.resolve(repo, "HEAD")
    patch = (
        "diff --git a/library.py b/library.py\n"
        "--- a/library.py\n"
        "+++ b/library.py\n"
        "@@ -1900,6 +1900,8 @@ def parse_form(\n"
        "     content_length: int | float | bytes | None = "
        'headers.get("Content-Length")\n'
        "     if content_length is not None:\n"
        "         content_length = int(content_length)\n"
        "+        if content_length < 0:\n"
        '+            raise ValueError("Content-Length must be non-negative")\n'
        "     else:\n"
        '         content_length = float("inf")\n'
        "     bytes_read = 0"
    )
    canonical = repository.apply_patch(repo, patch)
    expected = source.replace(
        "        content_length = int(content_length)\n",
        "        content_length = int(content_length)\n"
        "        if content_length < 0:\n"
        '            raise ValueError("Content-Length must be non-negative")\n',
    )
    assert (repo / "library.py").read_text() == expected
    assert canonical.endswith("\n")
    consumer = tmp_path / "consumer"
    repository.clone_at(repo, revision, consumer)
    repository.git(consumer, "apply", "--check", "-", input_text=canonical)
    repository.git(consumer, "apply", "-", input_text=canonical)
    assert (consumer / "library.py").read_text() == expected


def test_missing_patch_terminator_preserves_explicit_file_newline_marker(
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
        "\\ No newline at end of file"
    )
    canonical = repository.apply_patch(repo, patch)
    expected = "def answer():\n    return 2"
    assert (repo / "library.py").read_text() == expected
    assert "\\ No newline at end of file\n" in canonical
    consumer = tmp_path / "consumer"
    repository.clone_at(repo, revision, consumer)
    repository.git(consumer, "apply", "-", input_text=canonical)
    assert (consumer / "library.py").read_text() == expected


def test_canonical_patch_includes_new_implementation_files(tmp_path: Path) -> None:
    repo = make_repository(tmp_path / "repo")
    patch = "--- /dev/null\n+++ b/helper.py\n@@ -0,0 +1 @@\n+VALUE = 1\n"
    canonical = repository.apply_patch(repo, patch)
    assert "new file mode 100644" in canonical
    assert "+VALUE = 1" in canonical


@pytest.mark.parametrize("final_newline", ["\n", ""])
def test_recounting_does_not_accept_incorrect_context(
    tmp_path: Path, final_newline: str
) -> None:
    repo = make_repository(tmp_path / "repo")
    patch = (
        "--- a/library.py\n"
        "+++ b/library.py\n"
        "@@ -1,99 +1,777 @@\n"
        " def missing():\n"
        "-    return 1\n"
        "+    return 2" + final_newline
    )
    with pytest.raises(RepositoryError):
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
    with pytest.raises(RepositoryError, match="symlink"):
        repository.validate_patch(repo, patch)


def test_root_commit_is_not_an_ordinary_fix(tmp_path: Path) -> None:
    repo = make_repository(tmp_path / "repo")
    with pytest.raises(RepositoryError, match="one parent"):
        repository.parent(repo, repository.resolve(repo, "HEAD"))


def test_runtime_changes_are_not_silently_dropped(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        repository, "git", lambda *args, **kwargs: "library.py\x00requirements.txt\x00"
    )
    with pytest.raises(RepositoryError, match="unsupported changed file"):
        repository.upstream_patch(tmp_path, "a" * 40, "b" * 40)


@pytest.mark.parametrize(
    "path",
    [
        "Tests/helper.py",
        "TESTS/test_imagefont.py",
        "package/Test/helpers.py",
        "conftest.py",
        "Test_regression.py",
        "package/check_TEST.py",
        "Docs/config.py",
        "docs/README.rst",
    ],
)
def test_upstream_excludes_paths_that_candidate_must_not_change(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, path: str
) -> None:
    selected = []

    def git(*arguments: object) -> str:
        if "--name-only" in arguments:
            return f"library.py\x00{path}\x00"
        selected.extend(arguments)
        return "implementation diff"

    monkeypatch.setattr(repository, "git", git)
    assert repository.upstream_patch(tmp_path, "a" * 40, "b" * 40) == (
        "implementation diff"
    )
    assert selected[-1] == "library.py"
    assert path not in selected
    with pytest.raises(RepositoryError):
        repository.validate_source_path(path)


@pytest.mark.parametrize(
    "path", ["library.py", "src/news.py", "package/tests_support.py"]
)
def test_source_policy_keeps_ordinary_python_modules(path: str) -> None:
    repository.validate_source_path(path)
