"""Constrain candidate patches and classify supported source paths."""

from typing import Final

MAX_PATCH_BYTES: Final = 262144

SOURCE_TEST_NAMES: Final = frozenset({"test", "tests", "conftest.py"})

SOURCE_DOCUMENTATION_DIRECTORIES: Final = frozenset({"docs", "doc", ".github"})

SOURCE_DOCUMENTATION_SUFFIXES: Final = frozenset({".md", ".rst"})

SOURCE_DOCUMENTATION_PREFIXES: Final = (
    "readme",
    "changes",
    "changelog",
    "license",
    "copying",
    "authors",
    "news",
)

SOURCE_IGNORED_CONFIG_NAMES: Final = frozenset({"pytest.ini", "tox.ini"})

SOURCE_FORBIDDEN_NAMES: Final = frozenset({"setup.py", "sitecustomize.py"})
