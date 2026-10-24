"""Keep validated directory aliases intact in the container's writable copy."""

import os
import sys
from importlib.resources import files
from pathlib import Path

import pytest

from seam.execution.snapshot import stage_snapshot


def test_bootstrap_preserves_directory_alias_semantics(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace = tmp_path / "workspace"
    (workspace / "enterprise").mkdir(parents=True)
    (workspace / "enterprise/source.py").write_text("ordinary")
    (workspace / "litellm/proxy").mkdir(parents=True)
    (workspace / "litellm/proxy/enterprise").symlink_to(
        "../../enterprise", target_is_directory=True
    )
    source = tmp_path / "source"
    destination = tmp_path / "runtime"
    stage_snapshot(workspace, source)
    bootstrap = (
        files("seam.execution.resources")
        .joinpath("bootstrap.py.txt")
        .read_text(encoding="utf-8")
    )
    bootstrap = bootstrap.replace("'/source'", repr(str(source)))
    bootstrap = bootstrap.replace("'/work/repo'", repr(str(destination)))

    def check_runtime(arguments: list[str]) -> int:
        alias = destination / "litellm/proxy/enterprise"
        assert alias.is_symlink()
        assert os.readlink(alias) == "../../enterprise"
        assert (alias / "source.py").samefile(destination / "enterprise/source.py")
        return 0

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sys, "path", list(sys.path))
    monkeypatch.setattr(pytest, "main", check_runtime)
    with pytest.raises(SystemExit) as stopped:
        exec(compile(bootstrap, "container-bootstrap", "exec"), {})
    assert stopped.value.code == 0
