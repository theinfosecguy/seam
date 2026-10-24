"""Keep credential stores out without excluding ordinary source identifiers."""

import re
from collections.abc import Mapping
from pathlib import Path, PurePosixPath

from seam.constants.security import (
    SENSITIVE_PATH_NAMES,
    SENSITIVE_PATH_SUFFIXES,
    SNAPSHOT_EXCLUDED_NAMES,
)


def is_sensitive_path(path: str | Path) -> bool:
    """Match reserved credential basenames and extensions, case insensitively."""
    normalized = PurePosixPath(path).as_posix().lower()
    if "/.config/gcloud/" in f"/{normalized}/":
        return True
    return any(
        part in SENSITIVE_PATH_NAMES
        or part == ".env"
        or part.startswith(".env.")
        or part.endswith(SENSITIVE_PATH_SUFFIXES)
        for part in normalized.split("/")
    )


def is_reviewable_fixture_path(path: str) -> bool:
    """Limit fixture exceptions to exact key-file paths outside credential stores."""
    relative = PurePosixPath(path)
    if (
        not path
        or relative.is_absolute()
        or relative.as_posix() != path
        or ".." in relative.parts
        or "\\" in path
        or any(ord(character) < 32 or ord(character) == 127 for character in path)
        or relative.suffix.lower() not in SENSITIVE_PATH_SUFFIXES
    ):
        return False
    without_suffix = relative.with_suffix("")
    return not is_sensitive_path(without_suffix.as_posix()) and not any(
        part in SNAPSHOT_EXCLUDED_NAMES
        for part in without_suffix.as_posix().lower().split("/")
    )


def validate_reviewed_fixtures(fixtures: Mapping[str, tuple[str, ...]]) -> None:
    """Validate operator-reviewed key fixtures without weakening store exclusions."""
    for path, digests in fixtures.items():
        if (
            not isinstance(path, str)
            or not is_reviewable_fixture_path(path)
            or not isinstance(digests, tuple)
            or not digests
            or any(
                not isinstance(digest, str)
                or re.fullmatch(r"[0-9a-f]{64}", digest) is None
                for digest in digests
            )
            or len(set(digests)) != len(digests)
        ):
            raise ValueError(
                "Reviewed fixtures require exact key-file paths and unique "
                "SHA-256 hashes outside credential stores"
            )


def validate_reviewed_submodules(modules: Mapping[str, tuple[str, ...]]) -> None:
    """Limit exceptions to exact, uninitialized Git links reviewed by an operator."""
    if len(modules) > 16:
        raise ValueError("at most 16 reviewed submodule paths are supported")
    for path, objects in modules.items():
        relative = PurePosixPath(path)
        if (
            not path
            or not relative.parts
            or relative.is_absolute()
            or relative.as_posix() != path
            or any(part.startswith(".") for part in relative.parts)
            or "\\" in path
            or any(ord(character) < 32 or ord(character) == 127 for character in path)
            or not 1 <= len(objects) <= 16
            or len(set(objects)) != len(objects)
            or any(
                re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", oid) is None
                for oid in objects
            )
        ):
            raise ValueError(
                "reviewed submodules require relative paths and exact object IDs"
            )
