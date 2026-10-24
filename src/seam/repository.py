"""Inspect local Git revisions and change disposable clones only."""

import re
from pathlib import Path, PurePosixPath
from typing import Literal

from seam.constants.repository import (
    GIT_TIMEOUT_SECONDS,
    MAX_GIT_OUTPUT_BYTES,
    MAX_PATCH_BYTES,
    SOURCE_DOCUMENTATION_DIRECTORIES,
    SOURCE_DOCUMENTATION_PREFIXES,
    SOURCE_DOCUMENTATION_SUFFIXES,
    SOURCE_FORBIDDEN_NAMES,
    SOURCE_IGNORED_CONFIG_NAMES,
    SOURCE_TEST_NAMES,
)
from seam.exceptions import RepositoryError
from seam.execution.processes import run_process


def git(path: Path, *arguments: str, input_text: str | None = None) -> str:
    """Run a bounded Git builtin with global configuration and hooks disabled."""

    result = run_process(
        [
            "git",
            "--literal-pathspecs",
            "-c",
            "core.hooksPath=/dev/null",
            "-c",
            "protocol.ext.allow=never",
            "-c",
            "core.fsmonitor=false",
            "-C",
            str(path),
            *arguments,
        ],
        input_text=input_text,
        timeout=GIT_TIMEOUT_SECONDS,
        max_output=MAX_GIT_OUTPUT_BYTES,
    )
    if result.returncode or result.timed_out or result.truncated:
        reasons = [f"exit status {result.returncode}"]
        if result.timed_out:
            reasons.append(f"timeout after {GIT_TIMEOUT_SECONDS} seconds")
        if result.truncated:
            reasons.append(f"output exceeded {MAX_GIT_OUTPUT_BYTES} bytes")
        raise RepositoryError(
            f"Git {arguments[0]} failed ({'; '.join(reasons)}): {result.stderr[:2000]}"
        )
    return result.stdout


def resolve(repo: Path, ref: str) -> str:
    """Resolve a revision once, preventing refs from becoming Git options."""

    if not ref or ref.startswith("-") or "\x00" in ref:
        raise RepositoryError("revision must be a nonempty Git reference")
    commit = git(repo, "rev-parse", "--verify", "--end-of-options", f"{ref}^{{commit}}")
    if not re.fullmatch(r"[0-9a-f]{40,64}\n?", commit):
        raise RepositoryError("Git returned an invalid commit ID")
    return commit.strip()


def parent(repo: Path, commit: str) -> str:
    """Accept a single ordinary fix commit with exactly one parent."""

    parents = git(repo, "rev-list", "--parents", "-n", "1", commit).split()
    if len(parents) != 2:
        raise RepositoryError("the fix must be one ordinary commit with one parent")
    return parents[1]


def clone_at(repo: Path, commit: str, destination: Path) -> None:
    """Create an independent clone without shared objects or recursive submodules."""

    destination = destination.absolute()
    git(
        repo,
        "clone",
        "--no-local",
        "--no-hardlinks",
        "--no-checkout",
        "--no-recurse-submodules",
        "--",
        str(repo.resolve()),
        str(destination),
    )
    git(destination, "checkout", "--detach", "--force", commit)
    try:
        # Only modes are needed; long tracked paths must not consume this budget.
        modes = git(destination, "ls-files", "--format=%(objectmode)").splitlines()
    except RepositoryError as error:
        raise RepositoryError(
            f"Commit {commit} inventory (requires Git 2.38+): {error}"
        ) from error
    if "160000" in modes:
        raise RepositoryError("submodules are unsupported in the first version")


def _source_path_role(
    name: str,
) -> Literal["implementation", "test", "documentation", "unsupported"]:
    """Classify paths once for both upstream extraction and candidate validation."""
    path = PurePosixPath(name)
    if (
        not path.parts
        or path.is_absolute()
        or ".." in path.parts
        or "\\" in name
        or "\x00" in name
    ):
        return "unsupported"
    parts = tuple(part.casefold() for part in path.parts)
    filename = path.name.casefold()
    if (
        any(part in SOURCE_TEST_NAMES for part in parts)
        or filename.startswith("test_")
        or filename.endswith("_test.py")
    ):
        return "test"
    if any(part in SOURCE_DOCUMENTATION_DIRECTORIES for part in parts):
        return "documentation"
    if path.suffix == ".py" and not any(
        part.startswith(".") or part in SOURCE_FORBIDDEN_NAMES for part in parts
    ):
        return "implementation"
    if (
        path.suffix.casefold() in SOURCE_DOCUMENTATION_SUFFIXES
        or filename.startswith(SOURCE_DOCUMENTATION_PREFIXES)
        or filename in SOURCE_IGNORED_CONFIG_NAMES
    ):
        return "documentation"
    return "unsupported"


def validate_source_path(name: str) -> None:
    """Allow ordinary implementation Python files, excluding tests and setup code."""
    if _source_path_role(name) != "implementation":
        raise RepositoryError(
            f"patch path is outside supported implementation files: {name}"
        )


def validate_patch(workspace: Path, patch: str) -> tuple[str, ...]:
    """Reject non-source changes, binary patches, mode changes, and empty diffs."""

    if not patch or len(patch.encode()) > MAX_PATCH_BYTES:
        raise RepositoryError("candidate patch is empty or exceeds 256 KiB")
    if any(
        marker in patch
        for marker in (
            "GIT binary patch",
            "Binary files ",
            "new file mode 120000",
            "new file mode 160000",
            "old mode ",
            "new mode ",
            "rename from ",
            "copy from ",
        )
    ):
        raise RepositoryError(
            "binary, symlink, submodule, rename, and mode changes unsupported"
        )
    stats = git(
        workspace, "apply", "--recount", "--numstat", "-z", "-", input_text=patch
    )
    names = []
    for record in stats.split("\x00"):
        if not record:
            continue
        fields = record.split("\t", 2)
        if len(fields) != 3 or not fields[0].isdigit() or not fields[1].isdigit():
            raise RepositoryError("candidate is not an ordinary text patch")
        name = fields[2]
        validate_source_path(name)
        destination = workspace / name
        if destination.is_symlink() or any(
            ancestor.is_symlink()
            for ancestor in destination.parents
            if ancestor != workspace
        ):
            raise RepositoryError("candidate path traverses a symlink")
        names.append(name)
    if not names:
        raise RepositoryError("candidate patch contains no implementation changes")
    return tuple(names)


def apply_patch(workspace: Path, patch: str) -> str:
    """Apply a confined patch and return a canonical diff from its actual changes.

    Restore a missing patch terminator and recount generated hunk lengths while
    retaining Git's context, path, and whitespace checks. Exported diffs come
    from Git, so reviewers do not need a special flag to apply them.
    """

    if patch and not patch.endswith("\n"):
        patch += "\n"
    names = validate_patch(workspace, patch)
    git(
        workspace,
        "apply",
        "--recount",
        "--check",
        "--whitespace=error",
        "-",
        input_text=patch,
    )
    git(workspace, "apply", "--recount", "--whitespace=error", "-", input_text=patch)
    git(workspace, "add", "--intent-to-add", "--", *names)
    canonical = git(
        workspace, "diff", "--no-ext-diff", "--no-textconv", "HEAD", "--", *names
    )
    validate_patch(workspace, canonical)
    return canonical


def upstream_patch(repo: Path, before: str, after: str) -> str:
    """Extract Python implementation changes from the original fix."""

    names = git(repo, "diff", "--name-only", "-z", before, after).split("\x00")
    allowed = []
    for name in filter(None, names):
        role = _source_path_role(name)
        if role in {"test", "documentation"}:
            continue
        if role == "unsupported":
            raise RepositoryError(
                f"fix includes unsupported changed file: {name}"
                "; only ordinary Python implementation changes can be backported"
            )
        allowed.append(name)
    if not allowed:
        raise RepositoryError("fix has no supported Python implementation changes")
    return git(
        repo, "diff", "--no-ext-diff", "--no-textconv", before, after, "--", *allowed
    )
