"""Check explicit provider authentication, cloud configuration, and price forwarding."""

import os

import pytest

import seam.agent
from seam.cli import credentials, providers
from seam.constants.agent import MAX_API_CALLS
from seam.constants.providers import API_KEY_NAMES
from seam.models import ModelProvider
from seam.security.files import read_controller_text


@pytest.mark.parametrize("provider,key_name", list(API_KEY_NAMES.items()))
def test_selected_provider_uses_its_own_key(monkeypatch, provider, key_name):
    monkeypatch.setenv(key_name, "selected-test-value")
    assert credentials.load_api_key(None, provider) == "selected-test-value"
    monkeypatch.delenv(key_name)
    with pytest.raises(ValueError, match=key_name):
        credentials.load_api_key(None, provider)


@pytest.mark.parametrize("calls", [1, MAX_API_CALLS])
def test_provider_factory_keeps_model_and_credentials_separate(
    tmp_path, monkeypatch, calls
):
    key_file = tmp_path / "controller-key"
    key_file.write_text("ANTHROPIC_API_KEY=selected-anthropic-key\n")
    arguments = {}
    sentinel = object()

    def construct(**options):
        arguments.update(options)
        return sentinel

    monkeypatch.setattr(seam.agent, "PatchAgent", construct)
    result = providers.make_proposer(
        ModelProvider.ANTHROPIC,
        "new-model-id",
        None,
        key_file,
        max_model_calls=calls,
        input_price_per_million=1.0,
        output_price_per_million=5.0,
        context_tokens=200000,
    )
    assert result is sentinel
    assert arguments["provider"] == ModelProvider.ANTHROPIC
    assert arguments["model"] == "new-model-id"
    assert arguments["api_key"] == "selected-anthropic-key"
    assert arguments["budget_usd"] is None
    assert arguments["context_tokens"] == 200000
    assert arguments["max_calls"] == calls
    assert arguments["max_output_tokens"] == 16384
    assert arguments["timeout_seconds"] == 120


@pytest.mark.parametrize("calls", [0, -1, MAX_API_CALLS + 1, 1.5, True, "16"])
def test_invalid_call_limit_is_rejected_before_credentials_or_provider(
    monkeypatch, calls
):
    def forbidden(*args, **kwargs):
        pytest.fail("Invalid call limits must fail before settings or credentials")

    monkeypatch.setattr(providers, "load_provider_options", forbidden)
    monkeypatch.setattr(providers, "load_api_key", forbidden)
    monkeypatch.setattr(providers, "load_credentials", forbidden)
    monkeypatch.setattr(seam.agent, "PatchAgent", forbidden)
    with pytest.raises(ValueError, match="model call limit"):
        providers.make_proposer(
            ModelProvider.OPENAI, "some-model", None, None, max_model_calls=calls
        )


def test_cloud_file_cannot_contain_keys_or_foreign_provider_settings(tmp_path):
    config = tmp_path / "provider.toml"
    config.write_text('api_key = "must-never-be-displayed"\n')
    with pytest.raises(ValueError) as error:
        providers.load_provider_options(config, ModelProvider.AZURE)
    assert "must-never-be-displayed" not in str(error.value)
    config.write_text('aws_region = "us-east-1"\n')
    with pytest.raises(ValueError, match="another service"):
        providers.load_provider_options(config, ModelProvider.AZURE)
    config.write_text("aws_region = 123\n")
    with pytest.raises(ValueError, match="Invalid provider configuration"):
        providers.load_provider_options(config, ModelProvider.BEDROCK)


def test_provider_file_never_evaluates_interpolation(tmp_path, monkeypatch):
    config = tmp_path / "provider.toml"
    config.write_text('azure_endpoint = "https://$RESOURCE.openai.azure.com"\n')
    monkeypatch.setenv("RESOURCE", "should-not-expand")
    options = providers.load_provider_options(config, ModelProvider.AZURE)
    assert options.azure_endpoint == "https://$RESOURCE.openai.azure.com"


def test_bedrock_requires_and_selects_only_explicit_controller_pair(
    tmp_path, monkeypatch
):
    config = tmp_path / "bedrock.toml"
    config.write_text('aws_region = "us-east-1"\n')
    key_file = tmp_path / "key"
    key_file.write_text(
        "AWS_ACCESS_KEY_ID=controller-access\n"
        "AWS_SECRET_ACCESS_KEY=controller-secret\n"
        "AWS_SESSION_TOKEN=controller-session\n"
        "OPENAI_API_KEY=other-service-key\n"
    )
    arguments = {}
    monkeypatch.setattr(
        seam.agent, "PatchAgent", lambda **kwargs: arguments.update(kwargs)
    )
    providers.make_proposer(
        ModelProvider.BEDROCK, "opaque-model", None, key_file, provider_config=config
    )
    options = arguments["provider_options"]
    assert options.aws_region == "us-east-1"
    assert options.aws_access_key_id == "controller-access"
    assert options.aws_secret_access_key == "controller-secret"
    assert options.aws_session_token == "controller-session"
    assert arguments["api_key"] is None
    assert "controller-secret" not in repr(options)
    key_file.write_text("AWS_ACCESS_KEY_ID=controller-access\n")
    with pytest.raises(ValueError, match="AWS_SECRET_ACCESS_KEY"):
        providers.make_proposer(
            ModelProvider.BEDROCK,
            "opaque-model",
            None,
            key_file,
            provider_config=config,
        )


def test_vertex_resolves_explicit_account_path_relative_to_config(tmp_path):
    folder = tmp_path / "config"
    folder.mkdir()
    path = folder / "vertex.toml"
    path.write_text(
        'google_project = "review-project"\n'
        'google_location = "us-central1"\n'
        'google_credentials_path = "account.json"\n'
    )
    options = providers.load_provider_options(path, ModelProvider.VERTEX)
    assert options.google_credentials_path == folder / "account.json"
    with pytest.raises(ValueError, match="google_credentials_path"):
        providers.make_proposer(
            ModelProvider.VERTEX,
            "model",
            None,
            tmp_path / "unread-key-file",
            provider_config=path,
        )


@pytest.mark.parametrize("provider", [ModelProvider.BEDROCK, ModelProvider.VERTEX])
def test_cloud_auth_cannot_silently_fall_back_to_api_key(tmp_path, provider):
    with pytest.raises(ValueError, match="explicit cloud credentials"):
        credentials.load_api_key(tmp_path / "never-read", provider)


def test_controller_reads_are_bounded_and_never_block_on_fifo(tmp_path):
    path = tmp_path / "settings"
    path.write_bytes(b"x" * 101)
    with pytest.raises(ValueError, match="size limit"):
        read_controller_text(path, 100)
    path.write_bytes(b"\xff")
    with pytest.raises(ValueError, match="UTF-8"):
        read_controller_text(path, 100)
    path.unlink()
    os.mkfifo(path)
    with pytest.raises(ValueError, match="regular file"):
        read_controller_text(path, 100)
