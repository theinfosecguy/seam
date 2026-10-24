"""Constrain credential input and exclude sensitive files and content."""

from typing import Final

MAX_CREDENTIAL_BYTES: Final = 65536
MAX_SECRET_PARSE_BYTES: Final = 1_048_576

CREDENTIAL_FIELD_NAMES: Final = frozenset(
    {
        "api_key",
        "apikey",
        "auth_key",
        "auth_token",
        "access_token",
        "refresh_token",
        "client_secret",
        "password",
        "passwd",
        "pwd",
        "private_key",
        "secret",
        "credential",
        "credentials",
    }
)

ALLOWED_SUFFIXES: Final = frozenset(
    {".py", ".md", ".rst", ".txt", ".toml", ".cfg", ".ini"}
)

SENSITIVE_PATH_NAMES: Final = frozenset(
    {
        ".ssh",
        ".aws",
        ".azure",
        ".netrc",
        ".npmrc",
        ".pypirc",
        "id_rsa",
        "id_dsa",
        "id_ecdsa",
        "id_ed25519",
        "credentials",
        "secrets",
        "passwords",
        "credentials.json",
        "secrets.json",
        "passwords.json",
        "credentials.yaml",
        "credentials.yml",
        "secrets.yaml",
        "secrets.yml",
        "credentials.toml",
        "secrets.toml",
        "credentials.ini",
        "secrets.ini",
    }
)

SENSITIVE_PATH_SUFFIXES: Final = (".pem", ".key", ".p12", ".pfx", ".jks")

SNAPSHOT_EXCLUDED_NAMES: Final = frozenset(
    {
        ".git",
        ".hg",
        ".svn",
        ".venv",
        "venv",
        "__pycache__",
        ".pytest_cache",
        "node_modules",
        ".npm",
        ".mypy_cache",
        ".ruff_cache",
        ".ssh",
        ".aws",
        ".azure",
        ".netrc",
        ".pypirc",
        "id_rsa",
        "id_ed25519",
        "credentials",
        "credentials.json",
        "secrets.json",
    }
)
