"""Expose copied workspace source with authentic frozen build metadata."""
import hashlib
import importlib
import json
from pathlib import Path
import shutil
import sys

ROOT = Path("/work/repo")
PACKAGE_ROOTS = [ROOT / "pydantic_ai_slim", ROOT / "pydantic_graph"]
assert all(root.is_dir() for root in PACKAGE_ROOTS), "Expected staged monorepo roots"
METADATA_ROOT = Path("/opt/staged-metadata")
RECORDS = json.loads((METADATA_ROOT / "manifest.json").read_text())["revisions"]
sha = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
init_sha = sha(ROOT / "pydantic_ai_slim/pydantic_ai/__init__.py")
if init_sha == RECORDS["target"]["source_init_sha256"]:
    label = "target"
else:
    assert init_sha == RECORDS["upstream_parent"]["source_init_sha256"], "Unknown source revision metadata"
    hosts = ROOT / "pydantic_ai_slim/pydantic_ai/ui/_web/_hosts.py"
    label = "upstream_fix" if hosts.is_file() else "upstream_parent"
    if hosts.is_file():
        assert sha(hosts) == RECORDS[label]["source_hosts_sha256"], "Unknown upstream fix source"
for name in RECORDS[label]["metadata_directories"]:
    package = "pydantic_ai_slim" if name.startswith("pydantic_ai_slim-") else "pydantic_graph"
    shutil.copytree(METADATA_ROOT / label / name, ROOT / package / name)
sys.path[:0] = [str(root) for root in PACKAGE_ROOTS]
importlib.invalidate_caches()
