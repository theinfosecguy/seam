"""Proposed helper-level regression using only inert local plaintext values."""
from pathlib import Path

import pytest
from litellm.proxy import proxy_server
from litellm.proxy.common_utils import encrypt_decrypt_utils as crypto

SALT = "local-test-key-for-context-separation"
PREFIX = "litellm_login_"
OTHER_PREFIX = "ordinary_other_context_"

assert Path(crypto.__file__).resolve().is_relative_to(Path('/work/repo/litellm').resolve())


@pytest.fixture(autouse=True)
def local_configuration(monkeypatch):
    monkeypatch.setenv("LITELLM_SALT_KEY", SALT)
    monkeypatch.setattr(proxy_server, "general_settings", {})


def decode_session(value, prefix=PREFIX):
    if hasattr(crypto, "decrypt_bearer_token"):
        return crypto.decrypt_bearer_token(value, prefix=prefix)
    return crypto.decrypt_value_helper(
        value.removeprefix(prefix), key="ui_hash_key", exception_type="debug"
    )


def encode_session(value, prefix=PREFIX):
    if hasattr(crypto, "encrypt_bearer_token"):
        return crypto.encrypt_bearer_token(value, prefix=prefix)
    return prefix + crypto.encrypt_value_helper(value)


def test_security_regression():
    stored = crypto.encrypt_value_helper("ordinary-inert-value")
    assert decode_session(PREFIX + stored) is None, (
        "CONTEXT_DOMAIN_BOUNDARY_ORACLE: stored ciphertext accepted as session data"
    )
    if hasattr(crypto, "encrypt_bearer_token"):
        valid = encode_session("ordinary-session-data")
        retagged = OTHER_PREFIX + valid.removeprefix(PREFIX)
        assert decode_session(retagged, prefix=OTHER_PREFIX) is None, (
            "CONTEXT_DOMAIN_BOUNDARY_ORACLE: token accepted under another context"
        )


def test_stored_value_roundtrip():
    value = crypto.encrypt_value_helper("ordinary-inert-value")
    assert crypto.decrypt_value_helper(value, key="ordinary", exception_type="debug") == "ordinary-inert-value"


def test_session_value_roundtrip():
    assert decode_session(encode_session("ordinary-session-data")) == "ordinary-session-data"


def test_aes_stored_value_roundtrip(monkeypatch):
    monkeypatch.setattr(proxy_server, "general_settings", {"encryption_algorithm": "aes-256-gcm"})
    value = crypto.encrypt_value_helper("ordinary-aes-value")
    assert value.startswith("v2:gcm:")
    assert crypto.decrypt_value_helper(value, key="ordinary", exception_type="debug") == "ordinary-aes-value"
