"""Keep evaluation commands explicit, keyless by default, and truthful on failure."""

import json
import shutil
from pathlib import Path

import pytest
from typer.testing import CliRunner

from seam import cli
from seam.cli import evals
from seam.constants.agent import CLI_MODEL_CALLS
from seam.constants.repository import MAX_PATCH_BYTES
from seam.evals import catalogue
from seam.evals import runner as eval_runner
from seam.models import ModelProvider, ProcessResult, RunReport

DATASET = Path(__file__).resolve().parents[2] / "evals/python"
runner = CliRunner()


def forbidden(*args: object, **kwargs: object) -> None:
    pytest.fail("This command must fail before provider construction or execution")


@pytest.fixture
def dataset(tmp_path: Path) -> Path:
    selected = tmp_path / "dataset"
    shutil.copytree(DATASET / "cases/h11", selected / "cases/h11")
    (selected / "tasks.jsonl").write_text(catalogue.export_catalogue(selected))
    return selected


@pytest.fixture
def no_execution(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(evals, "make_proposer", forbidden)
    monkeypatch.setattr(evals, "run_case", forbidden)
    monkeypatch.setattr(evals, "qualify_case", forbidden)


def arguments(dataset: Path, output: Path) -> list[str]:
    return ["eval", "run", "h11", "--dataset", str(dataset), "--output", str(output)]


def report(status: str, usage: dict[str, int | float | str] | None = None) -> RunReport:
    if status != "verified":
        return RunReport.model_validate(
            {"status": status, "reason": "recorded result", "model_usage": usage or {}}
        )
    phases = []
    for name, revision in (
        ("upstream_parent", "b" * 40),
        ("upstream_fix", "a" * 40),
        ("target_baseline", "c" * 40),
        ("backport", "c" * 40),
    ):
        vulnerable = name in {"upstream_parent", "target_baseline"}
        phases.append(
            {
                "name": name,
                "revision": revision,
                "security": {
                    "returncode": 1 if vulnerable else 0,
                    "tests": [
                        {
                            "name": "test_security",
                            "outcome": "failed" if vulnerable else "passed",
                            "message": "AssertionError: intended regression",
                        },
                        {"name": "test_control", "outcome": "passed"},
                    ],
                },
                "suite": {
                    "returncode": 0,
                    "tests": [{"name": "test_existing", "outcome": "passed"}],
                },
            }
        )
    return RunReport.model_validate(
        {
            "status": status,
            "reason": "recorded result",
            "fix_commit": "a" * 40,
            "parent_commit": "b" * 40,
            "target_commit": "c" * 40,
            "image_id": "sha256:" + "d" * 64,
            "oracle_sha256": "e" * 64,
            "config_sha256": "f" * 64,
            "patch_sha256": "1" * 64,
            "phases": phases,
            "model_usage": usage or {},
        }
    )


@pytest.mark.parametrize("command", ["list", "check", "export"])
def test_catalogue_commands_are_keyless_and_do_not_execute(
    tmp_path: Path, dataset: Path, no_execution: None, command: str
) -> None:
    output = tmp_path / "catalogue.jsonl"
    options = ["--output", str(output)] if command == "export" else []
    result = runner.invoke(
        cli.app, ["eval", command, "--dataset", str(dataset), *options]
    )
    assert result.exit_code == 0, result.output
    if command == "export":
        row = json.loads(output.read_text())
        assert row["instance_id"] == "h11"
        assert row["base_commit"]
        assert row["patch"]
    elif command == "list":
        assert "h11: python-hyper/h11" in result.output
    else:
        assert "Validated 1 cases" in result.output


@pytest.mark.parametrize(
    "status,expected_exit", [("verified", 0), ("failed", 1), ("inconclusive", 2)]
)
@pytest.mark.parametrize(
    "mode_options,mode", [([], "reference"), (["--mode", "direct"], "direct")]
)
def test_reference_and_direct_modes_never_construct_a_provider(
    tmp_path: Path,
    dataset: Path,
    monkeypatch: pytest.MonkeyPatch,
    status: str,
    expected_exit: int,
    mode_options: list[str],
    mode: str,
) -> None:
    def execute(
        selected: Path, instance_id: str, output: Path, **options: object
    ) -> RunReport:
        assert (selected, instance_id, output) == (dataset, "h11", tmp_path / "run")
        assert options["mode"] == mode
        assert options["proposer"] is None
        assert options["candidate_patch"] is None
        assert options["docker"] == ("sudo", "-n", "docker")
        return report(status)

    monkeypatch.setattr(evals, "make_proposer", forbidden)
    monkeypatch.setattr(evals, "run_case", execute)
    result = runner.invoke(
        cli.app,
        [
            *arguments(dataset, tmp_path / "run"),
            *mode_options,
            "--provider",
            "deepseek",
            "--docker",
            "sudo -n docker",
        ],
    )
    assert result.exit_code == expected_exit, result.output
    assert status.upper() in result.output


@pytest.mark.parametrize("failure", ["build", "clone"])
def test_setup_failure_points_to_existing_manifest_without_a_report(
    tmp_path: Path,
    dataset: Path,
    monkeypatch: pytest.MonkeyPatch,
    failure: str,
) -> None:
    def failed_clone(*args: object, **kwargs: object) -> str:
        raise RuntimeError("simulated source clone failure")

    monkeypatch.setattr(evals, "make_proposer", forbidden)
    monkeypatch.setattr(eval_runner, "run_backport", forbidden)
    monkeypatch.setattr(
        eval_runner,
        "run_process",
        lambda *args, **kwargs: ProcessResult(
            returncode=1, stderr="simulated image build failure"
        ),
    )
    monkeypatch.setattr(eval_runner.repository, "git", failed_clone)
    output = tmp_path / "run"
    result = runner.invoke(
        cli.app,
        [
            *arguments(dataset, output),
            *(["--build-image"] if failure == "build" else []),
        ],
    )
    assert result.exit_code == 2, result.output
    manifest = output / "run-manifest.json"
    assert manifest.is_file()
    assert not (output / "evidence/report.json").exists()
    assert f"Manifest: {manifest}" in result.output
    assert "Evidence:" not in result.output


@pytest.mark.parametrize(
    "options",
    [
        ["--mode", "unknown"],
        ["--mode", "candidate"],
        ["--mode", "agent"],
        ["--model", "explicit-model"],
        ["--max-model-calls", str(CLI_MODEL_CALLS + 1)],
        ["--no-api-budget-cap"],
        ["--api-budget-usd", "nan"],
        ["--api-budget-usd", "inf"],
        ["--api-budget-usd", "0"],
        ["--docker", ""],
    ],
)
def test_invalid_modes_and_settings_fail_before_provider_or_runner(
    tmp_path: Path, dataset: Path, no_execution: None, options: list[str]
) -> None:
    result = runner.invoke(cli.app, [*arguments(dataset, tmp_path / "run"), *options])
    assert result.exit_code == 2, result.output
    assert not (tmp_path / "run").exists()


@pytest.mark.parametrize("kind", ["missing", "empty", "oversized", "non_utf8"])
def test_invalid_candidate_fails_before_provider_or_execution(
    tmp_path: Path,
    dataset: Path,
    monkeypatch: pytest.MonkeyPatch,
    kind: str,
) -> None:
    monkeypatch.setattr(evals, "make_proposer", forbidden)
    monkeypatch.setattr(eval_runner, "run_process", forbidden)
    monkeypatch.setattr(eval_runner.repository, "git", forbidden)
    monkeypatch.setattr(eval_runner, "run_backport", forbidden)
    candidate = tmp_path / "candidate.patch"
    if kind != "missing":
        candidate.write_bytes(
            b"x" * (MAX_PATCH_BYTES + 1)
            if kind == "oversized"
            else b"\xff"
            if kind == "non_utf8"
            else b""
        )
    result = runner.invoke(
        cli.app,
        [
            *arguments(dataset, tmp_path / "run"),
            "--mode",
            "candidate",
            "--candidate-patch",
            str(candidate),
        ],
    )
    assert result.exit_code == 2, result.output
    assert not (tmp_path / "run").exists()


@pytest.mark.parametrize("command", ["list", "check", "run"])
def test_invalid_metadata_does_not_print_pydantic_input(
    tmp_path: Path, dataset: Path, no_execution: None, command: str
) -> None:
    path = dataset / "cases/h11/case.json"
    value = json.loads(path.read_text())
    marker = "invalid-private-controller-value"
    value["repo"] = marker
    path.write_text(json.dumps(value))
    options = (
        [
            *arguments(dataset, tmp_path / "run"),
            "--mode",
            "agent",
            "--model",
            "explicit-model",
        ]
        if command == "run"
        else ["eval", command, "--dataset", str(dataset)]
    )
    result = runner.invoke(cli.app, options)
    assert result.exit_code == 2, result.output
    assert marker not in result.output


@pytest.mark.parametrize("command", ["check", "run"])
def test_mutated_case_asset_never_reaches_provider_or_runner(
    tmp_path: Path, dataset: Path, no_execution: None, command: str
) -> None:
    with (dataset / "cases/h11/oracle.py").open("a") as stream:
        stream.write("\n# modified after review\n")
    options = (
        [
            *arguments(dataset, tmp_path / "run"),
            "--mode",
            "agent",
            "--model",
            "explicit-model",
        ]
        if command == "run"
        else ["eval", "check", "--dataset", str(dataset)]
    )
    result = runner.invoke(cli.app, options)
    assert result.exit_code == 2, result.output
    assert "SHA-256 mismatch" in result.output


@pytest.mark.parametrize("setting", ["--env-file", "--provider-config"])
def test_controller_files_require_explicit_agent_mode(
    tmp_path: Path, dataset: Path, no_execution: None, setting: str
) -> None:
    path = tmp_path / "controller.toml"
    path.write_text("# explicit controller input\n")
    result = runner.invoke(
        cli.app, [*arguments(dataset, tmp_path / "run"), setting, str(path)]
    )
    assert result.exit_code == 2, result.output


def test_stale_catalogue_fails_and_can_be_regenerated_without_execution(
    dataset: Path, no_execution: None
) -> None:
    path = dataset / "tasks.jsonl"
    path.write_text("stale\n")
    result = runner.invoke(cli.app, ["eval", "check", "--dataset", str(dataset)])
    assert result.exit_code == 2
    assert "stale" in result.output
    result = runner.invoke(
        cli.app, ["eval", "export", "--dataset", str(dataset), "--output", str(path)]
    )
    assert result.exit_code == 0, result.output
    result = runner.invoke(cli.app, ["eval", "check", "--dataset", str(dataset)])
    assert result.exit_code == 0, result.output


def test_source_default_works_from_an_unrelated_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, no_execution: None
) -> None:
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(cli.app, ["eval", "list"])
    assert result.exit_code == 0, result.output
    assert "h11: python-hyper/h11" in result.output
    assert "authlib: authlib/authlib" in result.output


def test_installed_default_prefers_bundled_data(
    tmp_path: Path, dataset: Path, monkeypatch: pytest.MonkeyPatch, no_execution: None
) -> None:
    package = tmp_path / "installed/seam/evals"
    bundled = package / "data/python"
    shutil.copytree(dataset, bundled)
    monkeypatch.setattr(catalogue, "files", lambda _package: package)
    monkeypatch.chdir(tmp_path)
    assert catalogue.default_dataset() == bundled
    result = runner.invoke(cli.app, ["eval", "list"])
    assert result.exit_code == 0, result.output
    assert result.output.count("suite cases") == 1


@pytest.mark.parametrize(
    "outcome", ["verified", "failed", "inconclusive", "setup_error"]
)
@pytest.mark.parametrize("uncapped", [False, True])
def test_explicit_agent_settings_usage_and_cleanup(
    tmp_path: Path,
    dataset: Path,
    monkeypatch: pytest.MonkeyPatch,
    outcome: str,
    uncapped: bool,
) -> None:
    usage = {"calls": 3, "input_tokens": 123, "estimated_cost_usd": 0.01}
    closed = []
    displayed = []
    key_file = tmp_path / "controller.env"
    provider_file = tmp_path / "provider.toml"
    key_file.write_text("# factory is mocked; no credentials needed\n")
    provider_file.write_text("# explicit provider configuration\n")

    class Provider:
        def __init__(self) -> None:
            self.usage = usage

        def close(self) -> None:
            closed.append(True)

    proposer = Provider()

    def factory(
        provider: ModelProvider,
        model: str,
        budget: float | None,
        env_file: Path | None,
        **options: object,
    ) -> Provider:
        assert provider == ModelProvider.DEEPSEEK
        assert (model, budget, env_file) == (
            "explicit-model",
            None if uncapped else 0.25,
            key_file,
        )
        assert options["provider_config"] == provider_file
        assert options["max_model_calls"] == 7
        return proposer

    def execute(*args: object, **options: object) -> RunReport:
        assert options["mode"] == "agent"
        assert options["proposer"] is proposer
        assert proposer.usage == usage
        if outcome == "setup_error":
            raise RuntimeError("clone setup failed")
        return report(outcome, usage)

    monkeypatch.setattr(evals, "make_proposer", factory)
    monkeypatch.setattr(evals, "run_case", execute)
    monkeypatch.setattr(evals, "render_report", displayed.append)
    result = runner.invoke(
        cli.app,
        [
            *arguments(dataset, tmp_path / "run"),
            "--mode",
            "agent",
            "--model",
            "explicit-model",
            "--provider",
            "deepseek",
            "--env-file",
            str(key_file),
            "--provider-config",
            str(provider_file),
            "--max-model-calls",
            "7",
            "--api-budget-usd",
            "0.25",
            *(["--no-api-budget-cap"] if uncapped else []),
        ],
    )
    assert (
        result.exit_code
        == {"verified": 0, "failed": 1, "inconclusive": 2, "setup_error": 2}[outcome]
    ), result.output
    assert closed == [True]
    if outcome == "setup_error":
        assert not displayed
        assert "clone setup failed" in result.output
    else:
        assert displayed[0].model_usage == usage


@pytest.mark.parametrize("qualified,exit_code", [(True, 0), (False, 2)])
def test_qualification_reports_failure_as_nonzero(
    tmp_path: Path,
    dataset: Path,
    monkeypatch: pytest.MonkeyPatch,
    qualified: bool,
    exit_code: int,
) -> None:
    monkeypatch.setattr(evals, "make_proposer", forbidden)
    monkeypatch.setattr(
        evals,
        "qualify_case",
        lambda *args, **kwargs: {
            "qualified": qualified,
            "reason": "negative control was not rejected",
        },
    )
    result = runner.invoke(
        cli.app,
        [
            "eval",
            "qualify",
            "h11",
            "--dataset",
            str(dataset),
            "--output",
            str(tmp_path / "qualification"),
        ],
    )
    assert result.exit_code == exit_code, result.output
    if not qualified:
        assert "Not qualified" in result.output


def test_export_cannot_overwrite_a_pinned_case_asset(
    dataset: Path, no_execution: None
) -> None:
    oracle = dataset / "cases/h11/oracle.py"
    before = oracle.read_bytes()
    result = runner.invoke(
        cli.app, ["eval", "export", "--dataset", str(dataset), "--output", str(oracle)]
    )
    assert result.exit_code == 2, result.output
    assert oracle.read_bytes() == before


def test_export_preserves_an_existing_unrelated_output(
    tmp_path: Path, dataset: Path, no_execution: None
) -> None:
    output = tmp_path / "existing.jsonl"
    output.write_text("previous publication\n")
    result = runner.invoke(
        cli.app, ["eval", "export", "--dataset", str(dataset), "--output", str(output)]
    )
    assert result.exit_code == 2, result.output
    assert output.read_text() == "previous publication\n"


def test_export_cannot_follow_a_link_to_the_catalogue(
    tmp_path: Path, dataset: Path, no_execution: None
) -> None:
    catalogue_path = dataset / "tasks.jsonl"
    catalogue_path.write_text("previous catalogue\n")
    output = tmp_path / "catalogue-link.jsonl"
    output.symlink_to(catalogue_path)
    result = runner.invoke(
        cli.app, ["eval", "export", "--dataset", str(dataset), "--output", str(output)]
    )
    assert result.exit_code == 2, result.output
    assert catalogue_path.read_text() == "previous catalogue\n"
