"""Read and validate bounded pytest JUnit evidence."""

import os
import stat
from pathlib import Path
from typing import Literal
from xml.etree import ElementTree

from seam.constants import MAX_REPORT_BYTES
from seam.models import TestCaseResult


def parse_junit(report: bytes) -> list[TestCaseResult]:
    """Parse bounded pytest JUnit evidence, rejecting ambiguous test identities."""
    if not report or len(report) > MAX_REPORT_BYTES:
        raise ValueError("JUnit report is empty or exceeds the evidence limit")
    try:
        document = report.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ValueError("JUnit reports must use UTF-8 encoding") from exc
    if "<!DOCTYPE" in document.upper() or "<!ENTITY" in document.upper():
        raise ValueError("JUnit reports must not contain document declarations")
    try:
        root = ElementTree.fromstring(document)
    except ElementTree.ParseError as exc:
        raise ValueError("JUnit report is malformed XML") from exc
    if root.tag not in {"testsuites", "testsuite"}:
        raise ValueError("JUnit report has an unsupported root element")

    elements = list(root.iter("testcase"))
    if not elements:
        raise ValueError("JUnit report contains no test cases")
    identities: set[tuple[str, str]] = set()
    results: list[TestCaseResult] = []
    for element in elements:
        name = element.get("name", "")
        classname = element.get("classname", "")
        identity = (classname, name)
        if not name or identity in identities:
            raise ValueError("JUnit test case names must identify distinct tests")
        identities.add(identity)
        states = [
            child for child in element if child.tag in {"failure", "error", "skipped"}
        ]
        if len(states) > 1:
            raise ValueError("JUnit test case has conflicting outcomes")
        outcome: Literal["passed", "failed", "error", "skipped"] = "passed"
        message = ""
        if states:
            state = states[0]
            if state.tag == "failure":
                outcome = "failed"
            elif state.tag == "error":
                outcome = "error"
            else:
                outcome = "skipped"
            message = "\n".join(
                value
                for value in (state.get("message", ""), "".join(state.itertext()))
                if value
            )[:16_384]
        results.append(
            TestCaseResult(
                name=name,
                classname=classname,
                outcome=outcome,
                message=message,
            )
        )

    for suite in root.iter("testsuite"):
        cases = list(suite.iter("testcase"))
        expected = {
            "tests": len(cases),
            "failures": sum(case.find("failure") is not None for case in cases),
            "errors": sum(case.find("error") is not None for case in cases),
            "skipped": sum(case.find("skipped") is not None for case in cases),
        }
        for attribute, actual in expected.items():
            declared = suite.get(attribute)
            if declared is not None and (
                not declared.isascii()
                or not declared.isdecimal()
                or int(declared) != actual
            ):
                raise ValueError(f"JUnit {attribute} count contradicts test cases")
    return results


def read_junit_report(path: Path) -> bytes:
    """Read bounded evidence without following symbolic or hard links."""
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(descriptor, "rb") as stream:
        metadata = os.fstat(stream.fileno())
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1:
            raise ValueError("JUnit evidence must be a regular file without hard links")
        if metadata.st_size > MAX_REPORT_BYTES:
            raise ValueError("JUnit report exceeds the evidence limit")
        return stream.read(MAX_REPORT_BYTES + 1)
