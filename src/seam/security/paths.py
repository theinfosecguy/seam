"""Keep credential stores out without excluding ordinary source identifiers."""

from pathlib import Path, PurePosixPath

from seam.constants.security import SENSITIVE_PATH_NAMES, SENSITIVE_PATH_SUFFIXES


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
