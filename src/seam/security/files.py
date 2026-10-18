"""Bound reads of explicitly selected controller configuration and credentials."""

import os
import stat
from pathlib import Path


def read_controller_text(path: Path, limit: int) -> str:
    """Bound reads of an explicitly selected regular controller file."""
    descriptor = os.open(path, os.O_RDONLY | os.O_NONBLOCK)
    try:
        if not stat.S_ISREG(os.fstat(descriptor).st_mode):
            raise ValueError("Controller configuration must be a regular file")
        with os.fdopen(descriptor, "rb", closefd=False) as stream:
            content = stream.read(limit + 1)
    finally:
        os.close(descriptor)
    if len(content) > limit:
        raise ValueError("Controller configuration exceeds its size limit")
    try:
        return content.decode("utf-8")
    except UnicodeError:
        raise ValueError("Controller configuration must contain UTF-8 text") from None
