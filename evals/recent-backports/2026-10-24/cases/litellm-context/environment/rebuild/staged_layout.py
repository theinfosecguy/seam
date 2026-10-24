"""Expose staged workspaces and select exact real MCP for each release line."""
import importlib
import importlib.metadata
from pathlib import Path
import sys
import tomllib

from packaging.requirements import Requirement

ROOT = Path("/work/repo")
PACKAGE_ROOTS = [ROOT / "enterprise", ROOT / "litellm-proxy-extras"]
assert all(root.is_dir() for root in PACKAGE_ROOTS), "Expected staged workspace roots"
project = tomllib.loads((ROOT / "pyproject.toml").read_text())
requirement = next(Requirement(value) for value in project["project"]["optional-dependencies"]["proxy"] if Requirement(value).name == "mcp")
expected_mcp = "1.28.1"
if "2.2.0" in requirement.specifier:
    expected_mcp = "2.2.0"
    assert "1.28.1" not in requirement.specifier, "Ambiguous MCP release selection"
    PACKAGE_ROOTS.insert(0, Path("/opt/source-mcp"))
else:
    assert "1.28.1" in requirement.specifier, "Unknown MCP release requirement"
sys.path[:0] = [str(root) for root in PACKAGE_ROOTS]
importlib.invalidate_caches()

assert importlib.metadata.version("mcp") == expected_mcp, "Incorrect real MCP SDK selected"
import mcp
expected_root = Path("/opt/source-mcp") if expected_mcp == "2.2.0" else Path("/usr/local/lib/python3.12/site-packages")
assert Path(mcp.__file__).resolve().is_relative_to(expected_root), "Unexpected MCP package source"
