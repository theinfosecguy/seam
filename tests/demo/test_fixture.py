"""Exercise real divergent Git history without executing repository code."""

from pathlib import Path

import pytest

from backport_harness.demo.commands import docker_arguments
from backport_harness.demo.fixture import create_demo
from backport_harness.execution.processes import run_process
from backport_harness.verification.config import load_config


def git(repo: Path, *arguments: str) -> str:
    result = run_process(["git", *arguments], cwd=repo)
    assert result.returncode == 0, result.stderr
    return result.stdout.strip()


def test_fixture_requires_real_adaptation_and_preserves_clean_checkout(tmp_path):
    project = create_demo(tmp_path / "demo", image="example:local")
    assert git(project.repo, "status", "--porcelain") == ""
    assert git(project.repo, "branch", "--show-current") == "release/1.x"
    assert len(git(project.repo, "rev-list", "--all").splitlines()) == 3
    fix_diff = git(project.repo, "show", "--format=", project.fix)
    assert "paths.py" in fix_diff
    assert "is_relative_to" in fix_diff
    result = run_process(
        ["git", "apply", "--check", "-"], cwd=project.repo, input_text=fix_diff
    )
    assert result.returncode != 0
    candidate = run_process(
        ["git", "apply", "--check", str(project.candidate_patch)], cwd=project.repo
    )
    assert candidate.returncode == 0, candidate.stderr
    assert "legacy.py" in project.candidate_patch.read_text()
    assert git(project.repo, "status", "--porcelain") == ""


def test_fixture_trusted_inputs_live_outside_the_target(tmp_path):
    project = create_demo(
        tmp_path / "demo", image="example:local", docker=("sudo", "-n", "docker")
    )
    config = load_config(project.config_path)
    assert not config.oracle.path.is_relative_to(project.repo)
    assert config.runner.docker == ("sudo", "-n", "docker")
    assert config.runner.image == "example:local"
    assert "release..notes.txt" in config.oracle.path.read_text()
    assert config.oracle.failure_marker in config.oracle.path.read_text()
    assert len(config.oracle.controls) == 3
    assert "published CVE" in (project.repo / "README.md").read_text()


def test_fixture_metadata_is_explicit_even_with_inherited_identity(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("GIT_AUTHOR_NAME", "Unwanted Identity")
    monkeypatch.setenv("GIT_COMMITTER_EMAIL", "unwanted@example.org")
    project = create_demo(tmp_path / "demo")
    history = git(project.repo, "log", "--all", "--format=%an|%ae|%cn|%ce")
    assert "Unwanted Identity" not in history
    assert "unwanted@example.org" not in history
    assert set(history.splitlines()) == {
        "Project Maintainer|maintainer@example.invalid|"
        "Project Maintainer|maintainer@example.invalid"
    }


def test_demo_refuses_nonempty_output(tmp_path):
    (tmp_path / "keep.txt").write_text("keep me")
    with pytest.raises(ValueError, match="empty"):
        create_demo(tmp_path)
    assert (tmp_path / "keep.txt").read_text() == "keep me"


def test_operator_docker_command_does_not_invoke_shell():
    assert docker_arguments("sudo -n docker") == ("sudo", "-n", "docker")
    assert docker_arguments("docker ';' false") == ("docker", ";", "false")
    with pytest.raises(ValueError):
        docker_arguments(" ")
