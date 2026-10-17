"""Inspect local Git revisions and change disposable clones only."""

import re
from pathlib import Path, PurePosixPath

from backport_harness.processes import run_process


class RepositoryError(RuntimeError):
    """Describe an invalid repository operation without changing the caller's tree."""


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
        timeout=120,
        max_output=1048576,
    )
    if result.returncode or result.timed_out or result.truncated:
        raise RepositoryError(
            f"Git {arguments[0]} failed or exceeded limits: {result.stderr[:2000]}"
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
    if any(
        line.startswith("160000 ")
        for line in git(destination, "ls-files", "--stage").splitlines()
    ):
        raise RepositoryError("submodules are unsupported in the first version")


def validate_source_path(name: str) -> None:
    """Allow ordinary implementation Python files, excluding tests and setup code."""

    path = PurePosixPath(name)
    forbidden = {"tests", "test", "conftest.py", "setup.py", "sitecustomize.py"}
    if (
        path.is_absolute()
        or ".." in path.parts
        or any(part.startswith(".") or part in forbidden for part in path.parts)
        or path.suffix != ".py"
        or path.name.startswith("test_")
        or path.name.endswith("_test.py")
        or "\\" in name
    ):
        raise RepositoryError(
            f"patch path is outside supported implementation files: {name}"
        )


def validate_patch(workspace: Path, patch: str) -> tuple[str, ...]:
    """Reject non-source changes, binary patches, mode changes, and empty diffs."""

    if not patch or len(patch.encode()) > 262144:
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

    Recounting repairs generated hunk lengths, while Git still requires matching
    context and the same path and whitespace checks. Exported diffs come from
    Git, so reviewers do not need a special flag to apply them.
    """

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
        try:
            validate_source_path(name)
        except RepositoryError as error:
            path = PurePosixPath(name)
            documentation = path.suffix.lower() in {".md", ".rst"} or any(
                path.name.casefold().startswith(prefix)
                for prefix in (
                    "readme",
                    "changes",
                    "changelog",
                    "license",
                    "copying",
                    "authors",
                    "news",
                )
            )
            test_or_docs = any(
                part in {"tests", "test", "docs", "doc", ".github"}
                for part in path.parts
            )
            if documentation or test_or_docs or path.name in {"pytest.ini", "tox.ini"}:
                continue
            raise RepositoryError(
                f"fix includes unsupported runtime changes: {name}"
            ) from error
        allowed.append(name)
    if not allowed:
        raise RepositoryError("fix has no supported Python implementation changes")
    return git(
        repo, "diff", "--no-ext-diff", "--no-textconv", before, after, "--", *allowed
    )
