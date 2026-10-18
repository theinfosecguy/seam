"""Apply separately reviewed, hash-pinned assertion changes to existing tests."""

import ast
import hashlib
import re
from pathlib import Path

from seam import repository
from seam.constants.repository import MAX_PATCH_BYTES, SOURCE_FORBIDDEN_NAMES
from seam.exceptions import RepositoryError
from seam.security.files import read_controller_text


def load_reviewed_test_patch(path: Path, sha256: str) -> str:
    """Freeze one explicitly selected UTF-8 patch after checking its byte hash."""
    if not re.fullmatch(r"[0-9a-f]{64}", sha256):
        raise ValueError("reviewed test patch SHA-256 must be 64 lowercase hex digits")
    if path.is_symlink():
        raise ValueError("reviewed test patch must be a regular file")
    patch = read_controller_text(path, MAX_PATCH_BYTES)
    if not patch:
        raise ValueError("reviewed test patch is empty or exceeds 256 KiB")
    if hashlib.sha256(patch.encode("utf-8")).hexdigest() != sha256:
        raise ValueError("reviewed test patch SHA-256 does not match")
    return patch


class _AssertionMask(ast.NodeTransformer):
    """Mask assertions only within existing test functions, retaining their shape."""

    def __init__(self, pytest_names: set[str], mark_names: set[str]) -> None:
        self.pytest_names = pytest_names
        self.mark_names = mark_names
        self.in_function = False
        self.in_test = False
        self.assertions: list[ast.Assert] = []

    def _ordinary_mark(self, decorator: ast.expr) -> bool:
        function = decorator.func if isinstance(decorator, ast.Call) else decorator
        if not isinstance(function, ast.Attribute):
            return False
        owner = function.value
        return (isinstance(owner, ast.Name) and owner.id in self.mark_names) or (
            isinstance(owner, ast.Attribute)
            and owner.attr == "mark"
            and isinstance(owner.value, ast.Name)
            and owner.value.id in self.pytest_names
        )

    def visit_FunctionDef(
        self, node: ast.FunctionDef | ast.AsyncFunctionDef
    ) -> ast.FunctionDef | ast.AsyncFunctionDef:
        previous = self.in_function, self.in_test
        self.in_test = (
            not self.in_function
            and node.name.startswith("test")
            and all(self._ordinary_mark(decorator) for decorator in node.decorator_list)
        )
        self.in_function = True
        self.generic_visit(node)
        self.in_function, self.in_test = previous
        return node

    visit_AsyncFunctionDef = visit_FunctionDef

    def visit_Assert(self, node: ast.Assert) -> ast.Assert:
        if not self.in_test:
            return node
        self.assertions.append(node)
        return ast.Assert(test=ast.Constant(value=None), msg=None)


def _restricted_aliases(tree: ast.Module, names: set[str]) -> set[str]:
    return names | {
        alias.asname or alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
        and node.module is not None
        and node.module.split(".", 1)[0] in {"pytest", "_pytest", "unittest"}
        for alias in node.names
        if alias.name in names
    }


def _validate_assertion_changes(before: bytes, after: bytes) -> None:
    try:
        original, updated = ast.parse(before), ast.parse(after)
    except (SyntaxError, ValueError) as error:
        raise RepositoryError("reviewed test files must be valid Python") from error
    assigned_names = {
        node.id
        for node in ast.walk(original)
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store)
    }
    pytest_names = {
        alias.asname or alias.name
        for node in ast.walk(original)
        if isinstance(node, ast.Import)
        for alias in node.names
        if alias.name == "pytest"
    } - assigned_names
    mark_names = {
        alias.asname or alias.name
        for node in ast.walk(original)
        if isinstance(node, ast.ImportFrom) and node.module == "pytest"
        for alias in node.names
        if alias.name == "mark"
    } - assigned_names
    excluded_names = _restricted_aliases(
        original, {"skip", "skipif", "xfail", "importorskip"}
    )
    old_mask = _AssertionMask(pytest_names, mark_names)
    new_mask = _AssertionMask(pytest_names, mark_names)
    if ast.dump(old_mask.visit(original)) != ast.dump(new_mask.visit(updated)):
        raise RepositoryError(
            "reviewed tests may change only existing test assertion expressions; "
            "collection, decorators, fixtures, hooks, and test bodies must stay fixed"
        )
    changed = False
    for old, new in zip(old_mask.assertions, new_mask.assertions, strict=True):
        if ast.dump(old) == ast.dump(new):
            continue
        changed = True
        if any(
            isinstance(node, (ast.NamedExpr, ast.Yield, ast.YieldFrom))
            or (isinstance(node, ast.Name) and node.id in excluded_names)
            or (isinstance(node, ast.Attribute) and node.attr in excluded_names)
            for node in ast.walk(new)
        ):
            raise RepositoryError(
                "reviewed assertions cannot add skip, xfail, or assignment/yield flow"
            )
    if not changed:
        raise RepositoryError("reviewed test patch must change assertion expectations")


def _test_paths(workspace: Path, patch: str) -> tuple[str, ...]:
    if not patch or len(patch.encode("utf-8")) > MAX_PATCH_BYTES:
        raise RepositoryError("reviewed test patch is empty or exceeds 256 KiB")
    if repository.git(
        workspace, "apply", "--recount", "--summary", "-", input_text=patch
    ):
        raise RepositoryError(
            "reviewed test patches cannot add, delete, rename, or change file modes"
        )
    stats = repository.git(
        workspace, "apply", "--recount", "--numstat", "-z", "-", input_text=patch
    )
    names = []
    for record in filter(None, stats.split("\x00")):
        fields = record.split("\t", 2)
        if len(fields) != 3 or not all(value.isdigit() for value in fields[:2]):
            raise RepositoryError("reviewed tests require an ordinary text patch")
        name = fields[2]
        if "\ufffd" in name or name in names:
            raise RepositoryError(
                "reviewed test paths must be unique and contain "
                "no replacement characters"
            )
        destination = workspace / name
        if (
            repository._source_path_role(name) != "test"
            or destination.suffix != ".py"
            or destination.name.casefold() == "conftest.py"
            or any(
                part.startswith(".") or part.casefold() in SOURCE_FORBIDDEN_NAMES
                for part in Path(name).parts
            )
            or not destination.is_file()
        ):
            raise RepositoryError(
                "reviewed test patches require existing ordinary Python test files"
            )
        current = workspace
        for part in Path(name).parts:
            current /= part
            if current.is_symlink():
                raise RepositoryError("reviewed test path traverses a symlink")
        entries = repository.git(
            workspace, "ls-files", "--stage", "-z", "--", name
        ).split("\x00")
        if len(entries) != 2 or not entries[0].startswith(("100644 ", "100755 ")):
            raise RepositoryError("reviewed tests must be tracked ordinary files")
        names.append(name)
    if not names:
        raise RepositoryError("reviewed test patch contains no test changes")
    if repository.git(
        workspace, "diff", "--no-ext-diff", "--no-textconv", "HEAD", "--", *names
    ):
        raise RepositoryError("reviewed test files must match the target baseline")
    return tuple(names)


def apply_reviewed_test_patch(workspace: Path, patch: str) -> tuple[str, ...]:
    """Apply reviewed assertions; semantic strength remains the human's judgment.

    This narrow structural check supplements the required operator review. It
    cannot establish that a changed expectation still tests the right behavior.
    """
    names = _test_paths(workspace, patch)
    repository.git(
        workspace,
        "apply",
        "--recount",
        "--check",
        "--whitespace=error",
        "-",
        input_text=patch,
    )
    originals = {name: (workspace / name).read_bytes() for name in names}
    accepted = False
    try:
        repository.git(
            workspace, "apply", "--recount", "--whitespace=error", "-", input_text=patch
        )
        for name, before in originals.items():
            _validate_assertion_changes(before, (workspace / name).read_bytes())
        accepted = True
    finally:
        if not accepted:
            for name, before in originals.items():
                (workspace / name).write_bytes(before)
    return names
