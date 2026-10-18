"""Confine explicitly reviewed assertion updates without weakening source policy."""

import difflib
import hashlib
import os
from pathlib import Path

import pytest

from seam import repository
from seam.constants.repository import MAX_PATCH_BYTES
from seam.demo import create_demo
from seam.demo.fixture import _commit
from seam.exceptions import RepositoryError
from seam.verification.reviewed_tests import (
    _validate_assertion_changes,
    apply_reviewed_test_patch,
    load_reviewed_test_patch,
)


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    return create_demo(tmp_path / "project").repo


def patch_for(name: str, before: str, after: str) -> str:
    return "".join(
        difflib.unified_diff(
            before.splitlines(keepends=True),
            after.splitlines(keepends=True),
            fromfile=f"a/{name}",
            tofile=f"b/{name}",
        )
    )


def test_freezes_exact_hash_pinned_bytes(tmp_path: Path) -> None:
    path = tmp_path / "reviewed.patch"
    content = b"reviewed UTF-8 content: \xc3\xa9\r\n"
    path.write_bytes(content)
    frozen = load_reviewed_test_patch(path, hashlib.sha256(content).hexdigest())
    path.write_bytes(b"operator file changed after freezing\n")
    assert frozen.encode("utf-8") == content


@pytest.mark.parametrize("content", [b"", b"x" * (MAX_PATCH_BYTES + 1), b"\xff"])
def test_rejects_empty_oversized_and_non_utf8_patch(
    tmp_path: Path, content: bytes
) -> None:
    path = tmp_path / "reviewed.patch"
    path.write_bytes(content)
    with pytest.raises(ValueError):
        load_reviewed_test_patch(path, hashlib.sha256(content).hexdigest())


@pytest.mark.parametrize("digest", ["0" * 64, "A" * 64, "bad", ""])
def test_rejects_changed_or_malformed_hash(tmp_path: Path, digest: str) -> None:
    path = tmp_path / "reviewed.patch"
    path.write_text("patch\n")
    with pytest.raises(ValueError, match="SHA-256"):
        load_reviewed_test_patch(path, digest)


def test_rejects_symlink_and_directory_patch_inputs(tmp_path: Path) -> None:
    path = tmp_path / "reviewed.patch"
    path.write_bytes(b"patch\n")
    link = tmp_path / "link.patch"
    link.symlink_to(path)
    for candidate in (link, tmp_path):
        with pytest.raises(ValueError, match="regular file"):
            load_reviewed_test_patch(candidate, hashlib.sha256(b"patch\n").hexdigest())


def test_rejects_fifo_and_device_patch_inputs_without_reading(tmp_path: Path) -> None:
    fifo = tmp_path / "reviewed.fifo"
    os.mkfifo(fifo)
    for candidate in (fifo, Path("/dev/null")):
        with pytest.raises(ValueError, match="regular file"):
            load_reviewed_test_patch(candidate, hashlib.sha256(b"").hexdigest())


def test_regular_patch_replaced_by_fifo_cannot_block(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "reviewed.patch"
    path.write_bytes(b"patch\n")
    original = Path.is_symlink

    def replace_after_check(candidate: Path) -> bool:
        result = original(candidate)
        if candidate == path:
            candidate.unlink()
            os.mkfifo(candidate)
        return result

    monkeypatch.setattr(Path, "is_symlink", replace_after_check)
    with pytest.raises(ValueError, match="regular file"):
        load_reviewed_test_patch(path, hashlib.sha256(b"patch\n").hexdigest())


def test_applies_assertion_reshaping_without_opening_candidate_policy(
    repo: Path,
) -> None:
    name = "tests/test_paths.py"
    before = (repo / name).read_text()
    after = before.replace(
        'assert resolve(tmp_path, "docs/readme.txt") == tmp_path / "docs/readme.txt"',
        'assert str(resolve(tmp_path, "docs/readme.txt")).endswith("docs/readme.txt")',
    )
    patch = patch_for(name, before, after)
    with pytest.raises(RepositoryError, match="implementation"):
        repository.apply_patch(repo, patch)
    assert apply_reviewed_test_patch(repo, patch) == (name,)
    assert (repo / name).read_text() == after


@pytest.mark.parametrize(
    ("old", "new"),
    [
        ("def test_nested_member(tmp_path):", "def test_renamed_member(tmp_path):"),
        ("def test_nested_member(tmp_path):", "def test_nested_member(other_fixture):"),
        (
            "def test_nested_member(tmp_path):",
            '@pytest.mark.skip(reason="reviewed")\ndef test_nested_member(tmp_path):',
        ),
        (
            "def test_nested_member(tmp_path):",
            '@pytest.mark.parametrize("extra", [1], ids=["new-id"])\n'
            "def test_nested_member(tmp_path):",
        ),
        ("import parcel_paths", "import parcel_paths\npytestmark = pytest.mark.xfail"),
        ("import parcel_paths", "import parcel_paths\npytest_plugins = ['custom']"),
        ("import parcel_paths", "import parcel_paths\n__test__ = False"),
        (
            "import parcel_paths",
            "import parcel_paths\ndef pytest_collection_modifyitems():\n    pass",
        ),
        (
            'assert resolve(tmp_path, "docs/readme.txt") == '
            'tmp_path / "docs/readme.txt"',
            "return",
        ),
        (
            'assert resolve(tmp_path, "docs/readme.txt") == '
            'tmp_path / "docs/readme.txt"',
            "pytest.skip('old policy')",
        ),
        (
            'assert resolve(tmp_path, "docs/readme.txt") == '
            'tmp_path / "docs/readme.txt"',
            "assert pytest.xfail('old policy')",
        ),
        (
            'assert resolve(tmp_path, "docs/readme.txt") == '
            'tmp_path / "docs/readme.txt"',
            "assert (disabled := True)",
        ),
        (
            'assert resolve(tmp_path, "docs/readme.txt") == '
            'tmp_path / "docs/readme.txt"',
            "assert (yield True)",
        ),
        (
            "return Path(parcel_paths.member_path(str(root), name))",
            "return Path('other')",
        ),
        ("def test_nested_member(tmp_path):", "def test_nested_member(tmp_path)"),
    ],
)
def test_rejects_test_control_and_collection_changes_and_restores_bytes(
    repo: Path, old: str, new: str
) -> None:
    name = "tests/test_paths.py"
    before = (repo / name).read_bytes()
    patch = patch_for(name, before.decode(), before.decode().replace(old, new))
    with pytest.raises(RepositoryError):
        apply_reviewed_test_patch(repo, patch)
    assert (repo / name).read_bytes() == before
    assert not repository.git(repo, "diff", "--", name)


@pytest.mark.parametrize(
    "name",
    [
        "src/parcel_paths/legacy.py",
        "conftest.py",
        "tests/conftest.py",
        "pytest.ini",
        "tests/new_test.py",
        "../test_escape.py",
    ],
)
def test_rejects_non_test_and_untracked_paths(repo: Path, name: str) -> None:
    patch = patch_for(
        name, "def test_old():\n    assert 1\n", "def test_old():\n    assert 2\n"
    )
    with pytest.raises(RepositoryError):
        apply_reviewed_test_patch(repo, patch)


@pytest.mark.parametrize(
    "patch",
    [
        "--- /dev/null\n+++ b/tests/test_new.py\n@@ -0,0 +1,2 @@\n"
        "+def test_added():\n+    assert True\n",
        "diff --git a/tests/test_paths.py b/tests/test_paths.py\n"
        "old mode 100644\nnew mode 100755\n",
        "diff --git a/tests/test_paths.py b/tests/test_renamed.py\n"
        "similarity index 100%\nrename from tests/test_paths.py\n"
        "rename to tests/test_renamed.py\n",
    ],
)
def test_rejects_additions_modes_and_renames(repo: Path, patch: str) -> None:
    with pytest.raises(RepositoryError):
        apply_reviewed_test_patch(repo, patch)


def test_rejects_test_deletion(repo: Path) -> None:
    name = "tests/test_paths.py"
    before = (repo / name).read_text()
    patch = "".join(
        difflib.unified_diff(
            before.splitlines(keepends=True),
            [],
            fromfile=f"a/{name}",
            tofile="/dev/null",
        )
    )
    with pytest.raises(RepositoryError):
        apply_reviewed_test_patch(repo, patch)
    assert (repo / name).read_text() == before


def test_rejects_symlink_test_path_without_changing_target(repo: Path) -> None:
    destination = repo / "tests/test_paths.py"
    before = destination.read_bytes()
    target = repo.parent / "test_outside.py"
    target.write_bytes(before)
    destination.unlink()
    destination.symlink_to(target)
    patch = patch_for(
        "tests/test_paths.py",
        before.decode(),
        before.decode().replace("assert ", "assert not "),
    )
    with pytest.raises(RepositoryError, match="symlink"):
        apply_reviewed_test_patch(repo, patch)
    assert target.read_bytes() == before


def test_preserves_existing_source_candidate_changes(repo: Path) -> None:
    source = repo / "src/parcel_paths/legacy.py"
    source.write_text(source.read_text() + "\nSOURCE_CANDIDATE = True\n")
    name = "tests/test_paths.py"
    before = (repo / name).read_text()
    after = before.replace('"docs/readme.txt"', '"docs/updated.txt"')
    apply_reviewed_test_patch(repo, patch_for(name, before, after))
    assert "SOURCE_CANDIDATE = True" in source.read_text()


def test_rejects_preexisting_test_modification(repo: Path) -> None:
    name = "tests/test_paths.py"
    before = (repo / name).read_text()
    (repo / name).write_text(before + "# changed before review application\n")
    with pytest.raises(RepositoryError, match="target baseline"):
        apply_reviewed_test_patch(
            repo, patch_for(name, before, before.replace("assert ", "assert not "))
        )


def test_rejects_mixed_source_and_test_patch_without_changes(repo: Path) -> None:
    name = "tests/test_paths.py"
    before = (repo / name).read_bytes()
    patch = patch_for(
        name, before.decode(), before.decode().replace("assert ", "assert not ")
    )
    patch += patch_for(
        "src/parcel_paths/legacy.py",
        (repo / "src/parcel_paths/legacy.py").read_text(),
        "unapproved source change\n",
    )
    with pytest.raises(RepositoryError):
        apply_reviewed_test_patch(repo, patch)
    assert (repo / name).read_bytes() == before


def test_lossy_git_metadata_cannot_validate_a_shadow_file(repo: Path) -> None:
    raw_path = Path(os.fsdecode(os.fsencode(repo / "tests") + b"/test_\xff.py"))
    shadow = repo / "tests/test_\ufffd.py"
    before = b"def test_existing():\n    assert 1\n"
    raw_path.write_bytes(before)
    shadow.write_bytes(before)
    repository.git(repo, "add", "--", "tests")
    _commit(repo, "Add parser boundary review fixtures")
    raw_path.write_bytes(b"def test_existing():\n    pass\n")
    shadow.write_bytes(b"def test_existing():\n    assert 2\n")
    patch = repository.git(repo, "diff", "--no-ext-diff", "--no-textconv", "HEAD")
    raw_path.write_bytes(before)
    shadow.write_bytes(before)

    with pytest.raises(RepositoryError, match="replacement characters"):
        apply_reviewed_test_patch(repo, patch)
    assert raw_path.read_bytes() == before
    assert shadow.read_bytes() == before


def test_rejects_duplicate_metadata_paths_before_applying(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    name = "tests/test_paths.py"
    before = (repo / name).read_text()
    patch = patch_for(name, before, before.replace("assert ", "assert not "))
    git = repository.git

    def duplicate_stats(workspace, *arguments, **kwargs):
        if "--numstat" in arguments:
            return f"1\t1\t{name}\x00" * 2
        return git(workspace, *arguments, **kwargs)

    monkeypatch.setattr(repository, "git", duplicate_stats)
    with pytest.raises(RepositoryError, match="unique"):
        apply_reviewed_test_patch(repo, patch)
    assert (repo / name).read_text() == before


@pytest.mark.parametrize(
    "before",
    [
        "import pytest\n@pytest.fixture\ndef test_fixture():\n    assert 1\n",
        "from pytest import fixture as fx\n@fx\ndef test_fixture():\n    assert 1\n",
        "from _pytest.fixtures import fixture as fx\n"
        "@fx\ndef test_fixture():\n    assert 1\n",
        "import pytest\nmake_fixture = pytest.fixture\n"
        "@make_fixture\ndef test_fixture():\n    assert 1\n",
        "import functools\nimport pytest\n"
        "make_fixture = functools.partial(pytest.fixture, scope='module')\n"
        "@make_fixture\ndef test_fixture():\n    assert 1\n",
        "from test_support import fixture_wrapper\n"
        "@fixture_wrapper\ndef test_fixture():\n    assert 1\n",
        "import pytest\nmark = pytest.mark\n"
        "@mark.parametrize('value', [1])\ndef test_fixture(value):\n    assert 1\n",
        "import pytest\nfrom pytest import mark\nfrom types import SimpleNamespace\n"
        "mark = SimpleNamespace(fixture=pytest.fixture)\n"
        "@mark.fixture\ndef test_fixture():\n    assert 1\n",
        "def helper():\n    assert 1\n",
        "def test_parent():\n    def helper():\n        assert 1\n",
    ],
)
def test_rejects_assertion_edits_in_fixtures_and_helpers(before: str) -> None:
    with pytest.raises(RepositoryError, match="only existing test assertion"):
        _validate_assertion_changes(
            before.encode(), before.replace("assert 1", "assert 2").encode()
        )


@pytest.mark.parametrize(
    ("imports", "expression"),
    [
        ("import pytest", "pytest.skip('old policy')"),
        ("import pytest", "pytest.xfail('old policy')"),
        ("import pytest", "pytest.importorskip('unavailable')"),
        ("from pytest import skip as omitted", "omitted('old policy')"),
        ("from _pytest.outcomes import xfail as ignored", "ignored('old policy')"),
    ],
)
def test_rejects_skip_calls_inside_assertion_expressions(
    imports: str, expression: str
) -> None:
    before = f"{imports}\ndef test_existing():\n    assert 1\n".encode()
    after = f"{imports}\ndef test_existing():\n    assert {expression}\n".encode()
    with pytest.raises(RepositoryError, match="skip, xfail"):
        _validate_assertion_changes(before, after)


@pytest.mark.parametrize(
    ("imports", "mark"),
    [
        ("import pytest", "pytest.mark"),
        ("import pytest as pt", "pt.mark"),
        ("from pytest import mark", "mark"),
        ("from pytest import mark as selected", "selected"),
    ],
)
def test_preserves_decorators_and_test_ids_while_updating_expectations(
    imports: str, mark: str
) -> None:
    before = (
        f"{imports}\n@{mark}.parametrize('value', [1], ids=['stable'])\n"
        "def test_expected(value):\n    assert value == 1\n"
    )
    _validate_assertion_changes(
        before.encode(), before.replace("value == 1", "value in {1, 2}").encode()
    )
    with pytest.raises(RepositoryError, match="collection"):
        _validate_assertion_changes(
            before.encode(), before.replace("'stable'", "'changed'").encode()
        )
