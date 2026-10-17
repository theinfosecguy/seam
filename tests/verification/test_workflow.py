"""Cover failures that otherwise look like completed execution or verification."""

from pathlib import Path

from seam.models import ExecutionResult
from seam.models import TestCaseResult as Case
from seam.verification import workflow


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
    monkeypatch.setattr(
        workflow.repository, "resolve", lambda _repo, ref: revisions[ref]
    )
    monkeypatch.setattr(workflow.repository, "parent", lambda *_: "a" * 40)
    monkeypatch.setattr(
        workflow.repository, "upstream_patch", lambda *_: "source patch"
    )
    monkeypatch.setattr(
        workflow.repository, "clone_at", lambda _r, _c, dst: dst.mkdir()
    )
    monkeypatch.setattr(
        workflow.repository, "apply_patch", lambda _workspace, patch: patch
    )

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

    monkeypatch.setattr(workflow, "DockerRunner", Runner)
    report = workflow.run_backport(repo, "fix", "target", config, tmp_path / "output")
    assert report.status == "inconclusive"
    assert "collect" in report.reason.lower() or "missing" in report.reason.lower()
