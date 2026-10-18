"""Exercise local credential detection with synthetic values and ordinary source."""

import json
from pathlib import Path

import pytest
import requests

from seam.security import contains_secret, content, is_sensitive_path

_AWS = "AKIA" + "A" * 16
_GITHUB = "ghp_" + "A" * 36
_OPENAI = "sk-" + "A" * 20 + "T3BlbkFJ" + "B" * 20


@pytest.mark.parametrize(
    "text",
    [
        _AWS,
        _GITHUB,
        _OPENAI,
        "-----BEGIN RSA PRIVATE KEY-----\nsynthetic\n-----END RSA PRIVATE KEY-----",
        "-----BEGIN ENCRYPTED PRIVATE KEY-----\nsynthetic\n"
        "-----END ENCRYPTED PRIVATE KEY-----",
        "@@ -1 +1 @@\n+-----BEGIN ENCRYPTED PRIVATE KEY-----\n+synthetic\n"
        "+-----END ENCRYPTED PRIVATE KEY-----",
        'password = "synthetic password"',
        'password = "!synthetic-password"',
        "DEEPSEEK_API_KEY=synthetic-only-value",
        "export API_KEY=synthetic-only-value",
        "password: synthetic-only-value",
        'access_token = "synthetic-only-value"',
        'client_secret = "synthetic-only-value"',
        'api_key =\n"synthetic-only-value"',
        'password = (\n    "synthetic-only-value"\n)',
        'password = """\nsynthetic-only-value\n"""',
        'password: str = "synthetic-only-value"',
        'config["password"] = "synthetic-only-value"',
        'config = {"password": "synthetic-only-value"}',
        '@@ -1 +1 @@\n+client.api_key = "synthetic-only-value"',
        '@@ -1 +1 @@\n+config["password"] = "synthetic-only-value"',
        json.dumps({"metadata": {"api_key": "synthetic-only-value"}}),
        json.dumps({"feedback": json.dumps({"access_token": "synthetic-only-value"})}),
        json.dumps({"patch": '+PASSWORD = "synthetic-only-value"'}),
        'password = "synthetic-only-value" # pragma: allowlist secret',
        '# pragma: allowlist nextline secret\npassword = "synthetic-only-value"',
    ],
)
def test_detects_credential_formats_and_contextual_assignments(text: str) -> None:
    assert contains_secret(text)


@pytest.mark.parametrize(
    "text",
    [
        "flask-" + "a" * 24,
        "ordinary_identifier_with_secret_and_credential_substrings",
        'password_algorithm = "pbkdf2_sha256"',
        'SECRET_KIND = "public"',
        'credential_format = "json"',
        'token = "StartTag"',
        'current_token = "EndTag"',
        'commit = "7d9ea8dd3b1274be542384d5f79c1b9892bba972"',
        'digest = "59d484678610db33ed451b364f2872c5c531c622d66543ff392b129d9702f70f"',
        'example = "VGhpcyBpcyBvcmRpbmFyeSBwdWJsaWMgZXhhbXBsZSB0ZXh0Lg=="',
        'password = os.environ.get("PASSWORD")',
        'client_secret = get_secret("client")',
        "api_key = None",
        'password = ""',
        "api_key: str | None = None",
        'password: str = ""',
        "api_key = DEFAULT_API_KEY",
        "api_key: str",
        "api_key: str,",
        "password: str | None",
        "-----BEGIN PUBLIC KEY-----\npublic-material\n-----END PUBLIC KEY-----",
        json.dumps({"secret_kind": "public", "credential_format": "json"}),
        "A public IP address is 192.0.2.1",
    ],
)
def test_allows_source_metadata_and_public_noncredential_values(text: str) -> None:
    assert not contains_secret(text)


def test_never_verifies_loads_repository_plugins_or_logs_findings(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    tmp_path: Path,
) -> None:
    def forbidden(*args: object, **kwargs: object) -> None:
        pytest.fail("secret detection invoked verification or outbound HTTP")

    monkeypatch.setattr(requests.sessions.Session, "request", forbidden)
    for detector in content._DETECTORS:
        monkeypatch.setattr(type(detector), "verify", forbidden)
    (tmp_path / ".secrets.baseline").write_text(
        json.dumps({"plugins_used": [{"name": "Custom", "path": "file://bad.py"}]})
    )
    (tmp_path / "bad.py").write_text("raise RuntimeError('must never execute')")
    monkeypatch.chdir(tmp_path)
    caplog.clear()
    for value in (_AWS, _GITHUB, _OPENAI):
        assert contains_secret(value + " # pragma: allowlist secret")
        assert value not in caplog.text
    assert not caplog.records


def test_literal_normalization_is_bounded_without_skipping_detection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(content, "MAX_SECRET_PARSE_BYTES", 128)
    original_parse = content.ast.parse
    original_literal_eval = content.ast.literal_eval

    def bounded_parse(source: str, *args: object, **kwargs: object) -> object:
        assert len(source.encode("utf-8")) <= 128
        return original_parse(source, *args, **kwargs)

    def bounded_literal_eval(source: str) -> object:
        assert len(source.encode("utf-8")) <= 128
        return original_literal_eval(source)

    monkeypatch.setattr(content.ast, "parse", bounded_parse)
    monkeypatch.setattr(content.ast, "literal_eval", bounded_literal_eval)
    assert contains_secret('password: str = "' + "synthetic" * 100 + '"')
    assert contains_secret("ordinary " * 100 + _AWS)


@pytest.mark.parametrize(
    "path",
    [
        ".env",
        "src/.env.production",
        "src/.ENV.PRODUCTION",
        "credentials.json",
        "config/secrets.toml",
        ".aws/config",
        ".config/gcloud/application_default_credentials.json",
        "config/.config/gcloud/configurations/config_default",
        "keys/id_ed25519",
        "keys/server.PEM",
        "keys/client.p12",
    ],
)
def test_sensitive_path_policy_names_credential_stores(path: str) -> None:
    assert is_sensitive_path(path)


@pytest.mark.parametrize(
    "path",
    [
        "src/secret_detection.py",
        "src/credentials_manager.py",
        "src/credentials.py",
        "src/secret.py",
        "src/secrets.py",
        "tests/test_passwords.py",
        "src/private_key_format.py",
        "docs/access_tokens.md",
        "credential_metadata.toml",
    ],
)
def test_sensitive_path_policy_allows_ordinary_source_names(path: str) -> None:
    assert not is_sensitive_path(path)
