"""Check bounded nesting rejection and legitimate SQL parsing."""

import sys

import sqlparse
from sqlparse.exceptions import SQLParseError


def test_security_regression() -> None:
    previous = sys.getrecursionlimit()
    try:
        sys.setrecursionlimit(200)
        try:
            sqlparse.parse("[" * 300 + "]" * 300)
        except SQLParseError:
            return
        except RecursionError as error:
            raise AssertionError(
                "SECURITY_REGRESSION: unhandled recursion error"
            ) from error
        raise AssertionError("SECURITY_REGRESSION: nested input was not rejected")
    finally:
        sys.setrecursionlimit(previous)


def test_control_ordinary() -> None:
    assert (
        str(sqlparse.parse("SELECT value FROM records")[0])
        == "SELECT value FROM records"
    )


def test_control_boundary() -> None:
    assert (
        str(sqlparse.parse("SELECT [column] FROM records")[0])
        == "SELECT [column] FROM records"
    )
