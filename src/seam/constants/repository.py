"""Constrain candidate patches and classify supported source paths."""

from typing import Final, Literal

SourceLanguage = Literal["python", "javascript"]

SOURCE_SUFFIXES: Final = {
    "python": frozenset({".py"}),
    "javascript": frozenset({".js", ".mjs", ".cjs"}),
}

JAVASCRIPT_NON_SOURCE_DIRECTORIES: Final = frozenset(
    {"node_modules", "scripts", "build", "dist", "coverage", "vendor"}
)

JAVASCRIPT_CONFIG_STEMS: Final = frozenset({"gulpfile", "gruntfile", "jest.setup"})

JAVASCRIPT_ROOT_SCRIPT_STEMS: Final = frozenset(
    {"build", "install", "preinstall", "postinstall", "prepare", "setup"}
)

MAX_PATCH_BYTES: Final = 262144

MAX_GIT_OUTPUT_BYTES: Final = 1_048_576
GIT_TIMEOUT_SECONDS: Final = 120
MIN_GIT_VERSION: Final = (2, 38)

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
