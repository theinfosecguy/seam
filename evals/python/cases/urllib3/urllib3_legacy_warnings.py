"""Keep a deprecated helper in the historical pytest plugin usable."""

import pytest


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "filterwarnings",
        "ignore:distutils Version classes are deprecated.*:DeprecationWarning",
    )
