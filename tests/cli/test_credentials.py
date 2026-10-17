"""Keep controller credentials explicit, restricted, and provider specific."""

import pytest

from seam.cli import credentials
from seam.models import ModelProvider


def test_credential_file_is_not_discovered(tmp_path, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env").write_text("OPENAI_API_KEY=never-discover-me\n")
    with pytest.raises(ValueError, match="Set OPENAI_API_KEY"):
        credentials.load_api_key(None)


def test_explicit_credential_file_is_restricted_and_never_echoed(tmp_path):
    path = tmp_path / "key"
    path.write_text("# controller only\nOPENAI_API_KEY='local-test-key'\n")
    assert credentials.load_api_key(path) == "local-test-key"
    path.write_text("OPENAI_API_KEY=local-test-key\nUNRELATED=unsafe\n")
    with pytest.raises(ValueError) as caught:
        credentials.load_api_key(path)
    assert "local-test-key" not in str(caught.value)


def test_environment_credentials_are_selected_by_provider(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "openai-only-key")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "deepseek-only-key")
    assert credentials.load_api_key(None) == "openai-only-key"
    assert credentials.load_api_key(None, ModelProvider.DEEPSEEK) == "deepseek-only-key"
    monkeypatch.delenv("DEEPSEEK_API_KEY")
    with pytest.raises(ValueError, match="Set DEEPSEEK_API_KEY"):
        credentials.load_api_key(None, ModelProvider.DEEPSEEK)


def test_explicit_credentials_select_one_service_and_reject_duplicate_keys(tmp_path):
    key_file = tmp_path / "key"
    key_file.write_text(
        "OPENAI_API_KEY=openai-only-key\nDEEPSEEK_API_KEY='deepseek-only-key'\n"
    )
    assert credentials.load_api_key(key_file) == "openai-only-key"
    assert (
        credentials.load_api_key(key_file, ModelProvider.DEEPSEEK)
        == "deepseek-only-key"
    )
    key_file.write_text("OPENAI_API_KEY=openai-only-key\n")
    with pytest.raises(ValueError, match="Set DEEPSEEK_API_KEY"):
        credentials.load_api_key(key_file, ModelProvider.DEEPSEEK)
    key_file.write_text("DEEPSEEK_API_KEY=first\nDEEPSEEK_API_KEY=second\n")
    with pytest.raises(ValueError) as caught:
        credentials.load_api_key(key_file, ModelProvider.DEEPSEEK)
    assert "first" not in str(caught.value)
    assert "second" not in str(caught.value)
