"""Check explicit model selection, provider cleanup, and truthful reports."""

from pathlib import Path

import pytest
from typer.testing import CliRunner

import seam.agent
from seam import cli
from seam.cli import application, credentials, providers
from seam.constants.agent import CLI_MODEL_CALLS, MAX_API_CALLS
from seam.models import ModelProvider, ProcessResult, RunReport

# Rich forces terminal styling in CI even when CliRunner disables color.
runner = CliRunner(env={"TERM": "dumb"})


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
            "patch_sha256": "1" * 64 if status == "verified" else None,
            "phases": [
                {
                    "name": name,
                    "revision": revision,
                    "security": {
                        "returncode": 1
                        if name in {"upstream_parent", "target_baseline"}
                        else 0,
                        "tests": [
                            {
                                "name": "test_security",
                                "outcome": "failed"
                                if name in {"upstream_parent", "target_baseline"}
                                else "passed",
                                "message": "AssertionError: SECURITY_REGRESSION",
                            },
                            {"name": "test_control", "outcome": "passed"},
                        ],
                    },
                    "suite": {
                        "returncode": 0,
                        "tests": [{"name": "test_existing", "outcome": "passed"}],
                    },
                }
                for name, revision in (
                    ("upstream_parent", "b" * 40),
                    ("upstream_fix", "a" * 40),
                    ("target_baseline", "c" * 40),
                    ("backport", "c" * 40),
                )
            ],
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
@pytest.mark.parametrize("offline_mode", ["direct", "candidate"])
def test_explicit_offline_modes_report_status_without_a_model(
    tmp_path, monkeypatch, status, exit_code, provider_args, offline_mode
):
    candidate = tmp_path / "candidate.patch"
    candidate.write_text("explicit supplied patch\n")

    def fake_run(*args, **kwargs):
        assert kwargs["proposer"] is None
        assert kwargs["direct"] is (offline_mode == "direct")
        assert kwargs["candidate_patch"] == (
            candidate if offline_mode == "candidate" else None
        )
        return report(status)

    def forbidden(*args, **kwargs):
        pytest.fail("Offline verification unexpectedly constructed a model provider")

    monkeypatch.setattr(application, "run_backport", fake_run)
    monkeypatch.setattr(application, "make_proposer", forbidden)
    mode_args = (
        ["--direct"]
        if offline_mode == "direct"
        else ["--candidate-patch", str(candidate)]
    )
    result = runner.invoke(cli.app, [*arguments(tmp_path), *provider_args, *mode_args])
    assert result.exit_code == exit_code, result.output
    assert status.upper() in result.output
    assert "recorded oracle" in result.output
    if status == "verified":
        assert f"Patch: {tmp_path / 'evidence' / 'backport.patch'}" in result.output


@pytest.mark.parametrize(
    "mode_args",
    [
        [],
        ["--provider", "deepseek"],
        ["--model", ""],
        ["--model", " "],
        ["--model", "some-model", "--direct"],
        ["--candidate-patch", "candidate.patch", "--direct"],
        ["--candidate-patch", "candidate.patch", "--model", "some-model"],
    ],
)
def test_missing_or_conflicting_modes_fail_before_provider_or_output(
    tmp_path, monkeypatch, mode_args
):
    def forbidden(*args, **kwargs):
        pytest.fail("Invalid mode must fail before provider construction or execution")

    monkeypatch.setattr(application, "make_proposer", forbidden)
    monkeypatch.setattr(application, "run_backport", forbidden)
    result = runner.invoke(cli.app, [*arguments(tmp_path), *mode_args])
    assert result.exit_code == 2, result.output
    assert "--model" in result.output
    assert not (tmp_path / "evidence").exists()


def test_explicit_model_passes_budget_and_explicit_key_file(tmp_path, monkeypatch):
    closed = []

    class Provider:
        def close(self):
            closed.append(True)

    sentinel = Provider()
    key_file = tmp_path / "credentials"
    key_file.write_text("OPENAI_API_KEY=test-only-value\n")

    def factory(provider, model, budget, path, **options):
        assert provider == ModelProvider.OPENAI
        assert (model, budget, path) == ("approved-model", 0.25, key_file)
        assert options.pop("max_model_calls") == CLI_MODEL_CALLS
        assert all(value is None for value in options.values())
        return sentinel

    def fake_run(*args, **kwargs):
        assert kwargs["proposer"] is sentinel
        assert kwargs["direct"] is False
        return report()

    monkeypatch.setattr(application, "make_proposer", factory)
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


def test_normal_run_defaults_to_32_model_requests_without_changing_budget(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen: dict[str, object] = {}
    closed = []

    class Provider:
        def close(self) -> None:
            closed.append(True)

    proposer = Provider()

    def construct(**options: object) -> Provider:
        seen.update(options)
        return proposer

    def execute(*args: object, **options: object) -> RunReport:
        assert options["proposer"] is proposer
        return report()

    monkeypatch.setattr(seam.agent, "PatchAgent", construct)
    monkeypatch.setattr(providers, "load_api_key", lambda *_: "offline-test-key")
    monkeypatch.setattr(application, "run_backport", execute)
    result = runner.invoke(cli.app, [*arguments(tmp_path), "--model", "explicit-model"])

    assert result.exit_code == 0, result.output
    assert seen["max_calls"] == 32
    assert seen["budget_usd"] == 10
    assert closed == [True]


def test_provider_is_closed_when_verification_raises(tmp_path, monkeypatch):
    closed = []

    class Provider:
        def close(self):
            closed.append(True)

    def fail(*args, **kwargs):
        raise RuntimeError("verification stopped")

    monkeypatch.setattr(
        application, "make_proposer", lambda *args, **kwargs: Provider()
    )
    monkeypatch.setattr(application, "run_backport", fail)
    result = runner.invoke(cli.app, [*arguments(tmp_path), "--model", "approved-model"])
    assert result.exit_code == 2
    assert closed == [True]


def test_provider_failure_never_falls_back_to_offline_verification(
    tmp_path, monkeypatch
):
    def fail(*args, **kwargs):
        raise RuntimeError("provider unavailable")

    def forbidden(*args, **kwargs):
        pytest.fail("Provider failure must not start offline verification")

    monkeypatch.setattr(application, "make_proposer", fail)
    monkeypatch.setattr(application, "run_backport", forbidden)
    result = runner.invoke(cli.app, [*arguments(tmp_path), "--model", "some-model"])
    assert result.exit_code == 2, result.output
    assert "provider unavailable" in result.output
    assert not (tmp_path / "evidence").exists()


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

    monkeypatch.setattr(application, "make_proposer", forbidden)
    result = runner.invoke(
        cli.app,
        [*arguments(tmp_path), "--model", "some-model", "--api-budget-usd", budget],
    )
    assert result.exit_code == 2


@pytest.mark.parametrize("calls", [1, MAX_API_CALLS])
def test_explicit_model_call_limit_reaches_provider(tmp_path, monkeypatch, calls):
    class Provider:
        def close(self):
            pass

    def factory(*args, **options):
        assert options["max_model_calls"] == calls
        return Provider()

    monkeypatch.setattr(application, "make_proposer", factory)
    monkeypatch.setattr(application, "run_backport", lambda *args, **kwargs: report())
    result = runner.invoke(
        cli.app,
        [
            *arguments(tmp_path),
            "--model",
            "some-model",
            "--max-model-calls",
            str(calls),
        ],
    )
    assert result.exit_code == 0, result.output


@pytest.mark.parametrize("calls", ["0", "-1", str(MAX_API_CALLS + 1), "1.5", "inf"])
def test_invalid_model_call_limit_is_rejected_before_provider(
    tmp_path, monkeypatch, calls
):
    def forbidden(*args, **kwargs):
        pytest.fail("Invalid call limits must not construct a provider")

    monkeypatch.setattr(application, "make_proposer", forbidden)
    result = runner.invoke(
        cli.app,
        [
            *arguments(tmp_path),
            "--model",
            "some-model",
            "--max-model-calls",
            calls,
        ],
    )
    assert result.exit_code == 2
    assert "max-model-calls" in result.output


def test_run_help_exposes_model_call_limit():
    result = runner.invoke(cli.app, ["run", "--help"], color=False)
    assert result.exit_code == 0, result.output
    assert "--max-model-calls" in result.output
    assert "default: 32" in result.output
    assert "--direct" in result.output
    assert "explicit model" in result.output


def test_custom_model_call_limit_requires_model(tmp_path, monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("Call limits without a model must fail before verification")

    monkeypatch.setattr(application, "make_proposer", forbidden)
    monkeypatch.setattr(application, "run_backport", forbidden)
    result = runner.invoke(cli.app, [*arguments(tmp_path), "--max-model-calls", "1"])
    assert result.exit_code == 2
    assert "--max-model-calls requires an explicit --model" in result.output


def test_doctor_identifies_installed_version_and_package_without_provider(
    tmp_path, monkeypatch
):
    def forbidden(*args, **kwargs):
        pytest.fail("Environment diagnostics must not construct a provider")

    monkeypatch.setattr(application, "version", lambda name: "0.2.0")
    monkeypatch.setattr(application, "files", lambda name: tmp_path / "seam")
    monkeypatch.setattr(application, "make_proposer", forbidden)
    monkeypatch.setattr(
        application,
        "run_process",
        lambda *args, **kwargs: ProcessResult(returncode=0, stdout="available"),
    )
    result = runner.invoke(cli.app, ["doctor"])
    assert result.exit_code == 0, result.output
    assert f"Seam: 0.2.0 ({tmp_path / 'seam'})" in result.output
    assert "Git: OK" in result.output
    assert "Docker: OK" in result.output


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

    def factory(provider, model, actual_budget, path, **options):
        assert provider == ModelProvider.DEEPSEEK
        assert (model, actual_budget, path) == ("deepseek-flash", budget, None)
        return sentinel

    def fake_run(*args, **kwargs):
        assert kwargs["proposer"] is sentinel
        return report()

    monkeypatch.setattr(application, "make_proposer", factory)
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


@pytest.mark.parametrize("provider", list(ModelProvider))
def test_model_identifiers_pass_unchanged_through_one_factory(
    tmp_path, monkeypatch, provider
):
    calls = []

    class Provider:
        def close(self):
            calls.append("closed")

    def factory(selected, model, budget, path, **options):
        assert selected == provider
        assert model == "new-model-id-without-a-code-change"
        assert budget is None
        return Provider()

    monkeypatch.setattr(application, "make_proposer", factory)
    monkeypatch.setattr(application, "run_backport", lambda *args, **kwargs: report())
    result = runner.invoke(
        cli.app,
        [
            *arguments(tmp_path),
            "--provider",
            provider.value,
            "--model",
            "new-model-id-without-a-code-change",
            "--no-api-budget-cap",
        ],
    )
    assert result.exit_code == 0, result.output
    assert calls == ["closed"]


def test_no_api_budget_cap_requires_explicit_model(tmp_path):
    result = runner.invoke(cli.app, [*arguments(tmp_path), "--no-api-budget-cap"])
    assert result.exit_code == 2
    assert "requires an explicit --model" in result.output


def test_real_config_rejection_has_report_and_inconclusive_exit(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    config = tmp_path / "bad.toml"
    config.write_text('unexpected = "private-value"\n')
    output = tmp_path / "evidence"
    result = runner.invoke(
        cli.app,
        [
            "run",
            "--repo",
            str(source),
            "--fix",
            "main",
            "--target",
            "release",
            "--config",
            str(config),
            "--output",
            str(output),
            "--direct",
        ],
    )
    assert result.exit_code == 2, result.output
    assert "INCONCLUSIVE" in result.output
    assert str(output / "report.json") in result.output
    assert "private-value" not in result.output
    saved = RunReport.model_validate_json((output / "report.json").read_bytes())
    assert saved.status == "inconclusive" and saved.phases == []


def test_missing_repository_and_config_paths_reach_structured_report(tmp_path):
    output = tmp_path / "evidence"
    result = runner.invoke(
        cli.app,
        [
            "run",
            "--repo",
            str(tmp_path / "missing-repository"),
            "--fix",
            "main",
            "--target",
            "release",
            "--config",
            str(tmp_path / "missing.toml"),
            "--output",
            str(output),
            "--direct",
        ],
    )
    assert result.exit_code == 2
    assert "INCONCLUSIVE" in result.output
    assert (
        RunReport.model_validate_json((output / "report.json").read_bytes()).status
        == "inconclusive"
    )


@pytest.mark.parametrize(
    "option,value",
    [
        ("--input-price-per-million", "nan"),
        ("--output-price-per-million", "inf"),
        ("--context-tokens", "0"),
    ],
)
def test_invalid_pricing_is_rejected_before_provider(
    tmp_path, monkeypatch, option, value
):
    def forbidden(*args, **kwargs):
        pytest.fail("Invalid price or context must not construct a provider")

    monkeypatch.setattr(application, "make_proposer", forbidden)
    result = runner.invoke(
        cli.app, [*arguments(tmp_path), "--model", "custom", option, value]
    )
    assert result.exit_code == 2


def test_cloud_and_pricing_options_reach_provider_factory(tmp_path, monkeypatch):
    settings = tmp_path / "azure.toml"
    settings.write_text('azure_endpoint = "https://review.openai.azure.com"\n')
    seen = {}

    class Provider:
        def close(self):
            pass

    def factory(provider, model, budget, env_file, **options):
        assert provider == ModelProvider.AZURE
        seen.update(options)
        return Provider()

    monkeypatch.setattr(application, "make_proposer", factory)
    monkeypatch.setattr(application, "run_backport", lambda *args, **kwargs: report())
    result = runner.invoke(
        cli.app,
        [
            *arguments(tmp_path),
            "--provider",
            "azure",
            "--model",
            "deployment-name",
            "--provider-config",
            str(settings),
            "--input-price-per-million",
            "0.5",
            "--output-price-per-million",
            "2",
            "--context-tokens",
            "100000",
        ],
    )
    assert result.exit_code == 0, result.output
    assert seen == {
        "max_model_calls": CLI_MODEL_CALLS,
        "provider_config": settings,
        "input_price_per_million": 0.5,
        "output_price_per_million": 2.0,
        "context_tokens": 100000,
    }
