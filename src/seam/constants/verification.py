"""Bound trusted verification inputs, pytest settings, and reports."""

from typing import Final

MAX_CONFIG_BYTES: Final = 65536

MAX_ORACLE_BYTES: Final = 131072

MAX_REPORT_BYTES: Final = 1_048_576

MAX_PYTEST_PLUGINS: Final = 32

MAX_PYTEST_PLUGIN_NAME: Final = 200

MAX_PYTEST_MARKER_EXPRESSION: Final = 1024

MAX_DIAGNOSTIC_CHARACTERS: Final = 2000

MAX_DIAGNOSTIC_LINES: Final = 12

MAX_REVIEW_REASON_CHARACTERS: Final = 1000
