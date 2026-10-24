"""Expose the copied first-party workspace packages after runner staging."""
import importlib
from pathlib import Path
import sys

PACKAGE_ROOTS = ["/work/repo/enterprise", "/work/repo/litellm-proxy-extras"]
assert all(Path(root).is_dir() for root in PACKAGE_ROOTS), "Expected staged first-party workspace roots"
sys.path[:0] = PACKAGE_ROOTS
importlib.invalidate_caches()
