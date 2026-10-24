"""Exercise native Node JUnit identities and incomplete execution evidence."""

import pytest

from seam.verification.junit import parse_junit


def test_node_identities_include_the_source_file() -> None:
    report = b"""<testsuites>
    <testcase classname="test" name="same" file="/work/repo/first.cjs"/>
    <testcase classname="test" name="same" file="/work/repo/second.cjs"/>
    </testsuites>"""
    cases = parse_junit(report, runner="node")
    assert len({(case.classname, case.name) for case in cases}) == 2
    with pytest.raises(ValueError, match="distinct"):
        parse_junit(report.replace(b"second.cjs", b"first.cjs"), runner="node")


@pytest.mark.parametrize("failure", [b"", b'<failure type="testCodeFailure"/>'])
def test_node_file_wrappers_are_incomplete_even_when_the_file_exits_zero(
    failure: bytes,
) -> None:
    cases = parse_junit(
        b'<testsuites><testcase name="/work/repo/empty.cjs" '
        b'file="/work/repo/empty.cjs">' + failure + b"</testcase></testsuites>",
        runner="node",
    )
    assert cases[0].outcome == "error"


def test_node_missing_source_identity_is_rejected() -> None:
    with pytest.raises(ValueError, match="source file"):
        parse_junit(b'<testsuites><testcase name="same"/></testsuites>', runner="node")


@pytest.mark.parametrize("state", ["skipped", "todo"])
def test_node_skips_and_todos_remain_incomplete(state: str) -> None:
    cases = parse_junit(
        f'<testsuites><testcase name="pending" file="/work/repo/check.cjs">'
        f'<skipped type="{state}"/></testcase></testsuites>'.encode(),
        runner="node",
    )
    assert cases[0].outcome == "skipped"
    assert not cases[0].expected_failure


def test_node_nested_counts_preserve_pytest_validation() -> None:
    report = b"""<testsuites>
    <testsuite name="outer" tests="1" failures="1" errors="0" skipped="1">
      <testsuite name="inner" tests="2" failures="1" errors="0" skipped="1">
        <testcase name="first" classname="outer.inner" file="/work/repo/test.cjs">
          <failure type="testCodeFailure">AssertionError: SECURITY_MARKER</failure>
        </testcase>
        <testcase name="second" classname="outer.inner" file="/work/repo/test.cjs">
          <skipped type="todo"/>
        </testcase>
      </testsuite>
    </testsuite></testsuites>"""
    cases = parse_junit(report, runner="node")
    assert [case.outcome for case in cases] == ["failed", "skipped"]
    assert "AssertionError: SECURITY_MARKER" in cases[0].message
    with pytest.raises(ValueError, match="count contradicts"):
        parse_junit(report)
    with pytest.raises(ValueError, match="count contradicts"):
        parse_junit(report.replace(b'tests="2"', b'tests="3"'), runner="node")


def test_mocha_xunit_error_count_preserves_assertion_failures() -> None:
    report = b"""<testsuite tests="1" failures="0" errors="1" skipped="0">
    <testcase classname="suite" name="first" file="/work/repo/test.cjs">
      <failure>AssertionError: assertion failed</failure>
    </testcase></testsuite>"""
    cases = parse_junit(report, runner="mocha")
    assert cases[0].outcome == "failed"
    with pytest.raises(ValueError, match="count contradicts"):
        parse_junit(report)
