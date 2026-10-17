"""Cover failures that otherwise look like completed execution or verification."""

import sys
from pathlib import Path

from backport_harness import core
from backport_harness.models import ExecutionResult
from backport_harness.models import TestCaseResult as Case
from backport_harness.processes import run_process


def test_timeout_still_applies_after_child_closes_output_pipes() -> None:
    result = run_process(
        [
            sys.executable,
            "-c",
            "import os,time; os.close(1); os.close(2); time.sleep(.4)",
        ],
        timeout=0.05,
    )
    assert result.timed_out
    assert result.duration_seconds < 0.3


def test_backport_cannot_drop_previously_collected_suite_tests(
    tmp_path: Path, monkeypatch
) -> None:
    repo = tmp_path / "source"
    repo.mkdir()
    oracle = tmp_path / "oracle.py"
    oracle.write_text("# trusted regression fixture\n")
    config = tmp_path / "run.toml"
    config.write_text(
        """[oracle]
path = "oracle.py"
security_test = "test_security"
controls = ["test_control"]
failure_marker = "SECURITY_REGRESSION"
[runner]
image = "test-image"
"""
    )
    revisions = {"fix": "f" * 40, "target": "b" * 40}
    monkeypatch.setattr(core.repository, "resolve", lambda _repo, ref: revisions[ref])
    monkeypatch.setattr(core.repository, "parent", lambda *_: "a" * 40)
    monkeypatch.setattr(core.repository, "upstream_patch", lambda *_: "source patch")
    monkeypatch.setattr(core.repository, "clone_at", lambda _r, _c, dst: dst.mkdir())
    monkeypatch.setattr(core.repository, "apply_patch", lambda _workspace, patch: patch)

    class Runner:
        def __init__(self, _config) -> None:
            pass

        def resolve_image(self) -> str:
            return "sha256:" + "a" * 64

        def run(self, workspace, _oracle, _image, kind) -> ExecutionResult:
            if kind == "suite":
                names = ["test_existing"]
                if not workspace.name.startswith("candidate-"):
                    names.append("test_previously_collected")
                return ExecutionResult(
                    returncode=0,
                    tests=[Case(name=name, outcome="passed") for name in names],
                )
            vulnerable = workspace.name in {"upstream_parent", "target_baseline"}
            return ExecutionResult(
                returncode=1 if vulnerable else 0,
                tests=[
                    Case(
                        name="test_security",
                        outcome="failed" if vulnerable else "passed",
                        message="AssertionError: SECURITY_REGRESSION"
                        if vulnerable
                        else "",
                    ),
                    Case(name="test_control", outcome="passed"),
                ],
            )

    monkeypatch.setattr(core, "DockerRunner", Runner)
    report = core.run_backport(repo, "fix", "target", config, tmp_path / "output")
    assert report.status == "inconclusive"
    assert "collect" in report.reason.lower() or "missing" in report.reason.lower()
