"""Check explicit model selection, provider cleanup, and truthful reports."""

from pathlib import Path

import pytest
from typer.testing import CliRunner

from seam import cli
from seam.cli import application, credentials
from seam.models import RunReport

runner = CliRunner()


def report(status: str = "verified") -> RunReport:
    return RunReport.model_validate(
        {
            "status": status,
            "reason": "Recorded checks complete",
            "fix_commit": "a" * 40,
            "parent_commit": "b" * 40,
            "target_commit": "c" * 40,
            "image_id": "sha256:" + "d" * 64,
            "oracle_sha256": "e" * 64,
            "config_sha256": "f" * 64,
        }
    )


def arguments(tmp_path: Path) -> list[str]:
    config = tmp_path / "harness.toml"
    config.write_text("schema_version = 1\n")
    return [
        "run",
        "--repo",
        str(tmp_path),
        "--fix",
        "main",
        "--target",
        "release/1.x",
        "--config",
        str(config),
        "--output",
        str(tmp_path / "evidence"),
    ]


@pytest.mark.parametrize(
    "status,exit_code", [("verified", 0), ("failed", 1), ("inconclusive", 2)]
)
@pytest.mark.parametrize("provider_args", [[], ["--provider", "deepseek"]])
def test_run_reports_status_and_never_enables_model_implicitly(
    tmp_path, monkeypatch, status, exit_code, provider_args
):
    def fake_run(*args, **kwargs):
        assert kwargs["proposer"] is None
        return report(status)

    def forbidden(*args, **kwargs):
        pytest.fail("Default CLI unexpectedly constructed a model provider")

    monkeypatch.setattr(application, "run_backport", fake_run)
    monkeypatch.setattr(application, "make_openai_proposer", forbidden)
    monkeypatch.setattr(application, "make_deepseek_proposer", forbidden)
    result = runner.invoke(cli.app, [*arguments(tmp_path), *provider_args])
    assert result.exit_code == exit_code, result.output
    assert status.upper() in result.output
    assert "recorded oracle" in result.output


def test_explicit_model_passes_budget_and_explicit_key_file(tmp_path, monkeypatch):
    closed = []

    class Provider:
        def close(self):
            closed.append(True)

    sentinel = Provider()
    key_file = tmp_path / "credentials"
    key_file.write_text("OPENAI_API_KEY=test-only-value\n")

    def factory(model, budget, path):
        assert (model, budget, path) == ("approved-model", 0.25, key_file)
        return sentinel

    def fake_run(*args, **kwargs):
        assert kwargs["proposer"] is sentinel
        return report()

    monkeypatch.setattr(application, "make_openai_proposer", factory)
    monkeypatch.setattr(application, "run_backport", fake_run)
    result = runner.invoke(
        cli.app,
        [
            *arguments(tmp_path),
            "--model",
            "approved-model",
            "--api-budget-usd",
            "0.25",
            "--env-file",
            str(key_file),
        ],
    )
    assert result.exit_code == 0, result.output
    assert "test-only-value" not in result.output
    assert closed == [True]


def test_provider_is_closed_when_verification_raises(tmp_path, monkeypatch):
    closed = []

    class Provider:
        def close(self):
            closed.append(True)

    def fail(*args, **kwargs):
        raise RuntimeError("verification stopped")

    monkeypatch.setattr(application, "make_openai_proposer", lambda *args: Provider())
    monkeypatch.setattr(application, "run_backport", fail)
    result = runner.invoke(cli.app, [*arguments(tmp_path), "--model", "approved-model"])
    assert result.exit_code == 2
    assert closed == [True]


def test_key_file_requires_model_and_candidate_cannot_enable_model(tmp_path):
    patch = tmp_path / "candidate.patch"
    patch.write_text("not used")
    credentials = tmp_path / "key"
    credentials.write_text("OPENAI_API_KEY=test\n")
    result = runner.invoke(
        cli.app, [*arguments(tmp_path), "--env-file", str(credentials)]
    )
    assert result.exit_code == 2
    result = runner.invoke(
        cli.app,
        [
            *arguments(tmp_path),
            "--candidate-patch",
            str(patch),
            "--model",
            "some-model",
        ],
    )
    assert result.exit_code == 2


def test_inspect_validates_and_returns_json(tmp_path):
    path = tmp_path / "report.json"
    path.write_text(report("inconclusive").model_dump_json())
    result = runner.invoke(cli.app, ["inspect", "--report", str(path), "--json"])
    assert result.exit_code == 0
    assert RunReport.model_validate_json(result.output).status == "inconclusive"
    path.write_text('{"status":"verified"}')
    result = runner.invoke(cli.app, ["inspect", "--report", str(path)])
    assert result.exit_code == 2


@pytest.mark.parametrize("budget", ["0", "nan", "inf", "-1"])
def test_invalid_budget_is_validated_before_provider(tmp_path, monkeypatch, budget):
    def forbidden(*args, **kwargs):
        pytest.fail("Provider must not be constructed for an invalid budget")

    monkeypatch.setattr(application, "make_openai_proposer", forbidden)
    result = runner.invoke(
        cli.app,
        [*arguments(tmp_path), "--model", "some-model", "--api-budget-usd", budget],
    )
    assert result.exit_code == 2


@pytest.mark.parametrize(
    "budget_args,budget",
    [([], 10), (["--api-budget-usd", "25"], 25), (["--no-api-budget-cap"], None)],
)
def test_deepseek_provider_receives_selected_model_and_budget(
    tmp_path, monkeypatch, budget_args, budget
):
    closed = []

    class Provider:
        def close(self):
            closed.append(True)

    sentinel = Provider()

    def factory(model, actual_budget, path):
        assert (model, actual_budget, path) == ("deepseek-flash", budget, None)
        return sentinel

    def forbidden(*args, **kwargs):
        pytest.fail("DeepSeek selection must not construct the OpenAI provider")

    def fake_run(*args, **kwargs):
        assert kwargs["proposer"] is sentinel
        return report()

    monkeypatch.setattr(application, "make_openai_proposer", forbidden)
    monkeypatch.setattr(application, "make_deepseek_proposer", factory)
    monkeypatch.setattr(application, "run_backport", fake_run)
    result = runner.invoke(
        cli.app,
        [
            *arguments(tmp_path),
            "--provider",
            "deepseek",
            "--model",
            "deepseek-flash",
            *budget_args,
        ],
    )
    assert result.exit_code == 0, result.output
    assert closed == [True]


def test_unknown_provider_is_rejected_before_key_read(tmp_path, monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("Unknown provider must not read any credentials")

    monkeypatch.setattr(credentials, "load_api_key", forbidden)
    result = runner.invoke(
        cli.app,
        [*arguments(tmp_path), "--provider", "untrusted", "--model", "some-model"],
    )
    assert result.exit_code == 2


def test_unknown_deepseek_model_is_rejected_before_key_read(tmp_path, monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("Unknown DeepSeek model must not read any credentials")

    monkeypatch.setattr(credentials, "load_api_key", forbidden)
    result = runner.invoke(
        cli.app,
        [
            *arguments(tmp_path),
            "--provider",
            "deepseek",
            "--model",
            "unknown-deepseek-model",
        ],
    )
    assert result.exit_code == 2
    assert "Unsupported DeepSeek model" in result.output


def test_no_api_budget_cap_requires_explicit_model(tmp_path):
    result = runner.invoke(cli.app, [*arguments(tmp_path), "--no-api-budget-cap"])
    assert result.exit_code == 2
    assert "requires an explicit --model" in result.output
