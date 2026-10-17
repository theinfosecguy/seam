"""Reject incomplete and ambiguous pytest JUnit evidence."""

import pytest

from backport_harness.verification.junit import parse_junit


def test_junit_preserves_failure_reason_and_other_outcomes() -> None:
    cases = parse_junit(
        b"""<testsuite tests="4" failures="1" errors="1" skipped="1">
        <testcase name="test_regression"><failure message="unsafe-marker">
        assertion details</failure></testcase>
        <testcase name="test_control"/>
        <testcase name="test_setup"><error message="dependency missing"/></testcase>
        <testcase name="test_skip"><skipped message="unsupported"/></testcase>
        </testsuite>"""
    )
    assert [case.outcome for case in cases] == ["failed", "passed", "error", "skipped"]
    assert "unsafe-marker" in cases[0].message
    assert "assertion details" in cases[0].message


@pytest.mark.parametrize(
    "report",
    [
        b"",
        b"not xml",
        b"<something><testcase name='a'/></something>",
        b"<testsuite/>",
        b"<testsuite><testcase/></testsuite>",
        b"<testsuite><testcase name='a'/><testcase name='a'/></testsuite>",
        b"<testsuite><testcase name='a'><failure/><skipped/></testcase></testsuite>",
        b"<testsuite tests='2'><testcase name='a'/></testsuite>",
        b"<testsuite failures='1'><testcase name='a'/></testsuite>",
        b"<!DOCTYPE testsuite><testsuite><testcase name='a'/></testsuite>",
        (
            '<?xml version="1.0" encoding="utf-16"?>'
            '<!DOCTYPE testsuite [<!ENTITY marker "expanded">]>'
            '<testsuite><testcase name="&marker;"/></testsuite>'
        ).encode("utf-16"),
        b"x" * (1_048_576 + 1),
    ],
)
def test_invalid_or_ambiguous_junit_is_rejected(report: bytes) -> None:
    with pytest.raises(ValueError):
        parse_junit(report)


def test_same_function_names_in_different_modules_are_distinct() -> None:
    cases = parse_junit(
        b"""<testsuite><testcase classname="first" name="test_value"/>
        <testcase classname="second" name="test_value"/></testsuite>"""
    )
    assert [(case.classname, case.name) for case in cases] == [
        ("first", "test_value"),
        ("second", "test_value"),
    ]
