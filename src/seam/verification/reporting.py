"""Persist machine-readable and human-readable verification reports."""

from pathlib import Path

from seam.constants.verification import MAX_DIAGNOSTIC_CHARACTERS, MAX_DIAGNOSTIC_LINES
from seam.models import ExecutionResult, RunReport


def display_text(value: str) -> str:
    """Keep bounded untrusted text on one line without terminal controls."""
    clean = "".join(
        character if character.isprintable() else " " for character in value
    )
    if len(clean) > MAX_DIAGNOSTIC_CHARACTERS:
        return clean[: MAX_DIAGNOSTIC_CHARACTERS - 1] + "…"
    return clean


def diagnostic_excerpt(
    execution: ExecutionResult, *, include_failures: bool = True
) -> str:
    """Surface bounded root-error context without treating logs as test evidence."""
    outcomes = {"error", "skipped"}
    if include_failures:
        outcomes.add("failed")
    messages = [
        case.message
        for case in execution.tests
        if case.outcome in outcomes and case.message
    ]
    unresolved = (
        execution.evidence_error
        or execution.timed_out
        or execution.truncated
        or execution.returncode not in {0, 1}
        or any(case.outcome in {"error", "skipped"} for case in execution.tests)
    )
    if not messages and not unresolved:
        return ""
    lines = "\n".join([*messages, execution.stdout, execution.stderr]).splitlines()
    # Pytest may report an unusable JUnit wrapper while stdout names the import
    # or fixture error. Keep that root cause ahead of generic capture details.
    useful = [
        index
        for index, line in enumerate(lines)
        if any(
            marker in line.lower()
            for marker in ("error:", "exception:", "not found", "traceback", "failed")
        )
    ]
    selected = [lines[index] for index in useful]
    for index in useful:
        selected.extend(lines[max(0, index - 1) : index + 2])
    selected.extend(lines[-MAX_DIAGNOSTIC_LINES:])
    if execution.evidence_error:
        selected.insert(0, execution.evidence_error)
    unique = list(dict.fromkeys(line.strip() for line in selected if line.strip()))
    excerpt = "\n".join(unique[:MAX_DIAGNOSTIC_LINES])
    excerpt = "\n".join(display_text(line) for line in excerpt.splitlines())
    if len(excerpt) > MAX_DIAGNOSTIC_CHARACTERS:
        excerpt = excerpt[: MAX_DIAGNOSTIC_CHARACTERS - 1] + "…"
    return excerpt


def write_report(output: Path, report: RunReport) -> RunReport:
    """Write both report formats and return the recorded result."""
    RunReport.model_validate(report.model_dump())
    (output / "report.json").write_text(
        report.model_dump_json(indent=2) + "\n", "utf-8"
    )
    rows = [
        "# Security backport evidence",
        "",
        f"Status: **{report.status}**",
        "",
        f"    {display_text(report.reason)}",
        "",
        "Verification is limited to the recorded tests, revisions, "
        "and execution image.",
        "",
        f"- Fix: `{report.fix_commit or 'unresolved'}`",
        f"- Target: `{report.target_commit or 'unresolved'}`",
        f"- Image: `{report.image_id or 'unresolved'}`",
        f"- Oracle SHA-256: `{report.oracle_sha256 or 'unavailable'}`",
        f"- Patch SHA-256: `{report.patch_sha256 or 'none'}`",
    ]
    if report.status == "verified":
        rows.append("- Canonical patch: `backport.patch`")
    if report.reviewed_tests is not None:
        rows.extend(
            [
                f"- Reviewed assertion patch SHA-256: `{report.reviewed_tests.sha256}`",
                f"- Review reason: {display_text(report.reviewed_tests.reason)}",
                "- Frozen assertion input: `reviewed-tests.patch`; "
                "a verified `backport.patch` includes these changes.",
                "- Assertion strength depends on the operator's review; "
                "the independent security oracle is unchanged.",
            ]
        )
    if report.reviewed_fixtures:
        rows.append(
            f"- Reviewed cryptographic fixture paths: {len(report.reviewed_fixtures)} "
            "(SHA-256 pinned in report.json and config.json)"
        )
    rows.extend(
        [
            "",
            "| Revision | Oracle exit | Oracle cases | Suite exit | Suite cases |",
            "| --- | ---: | ---: | ---: | ---: |",
        ]
    )
    for phase in report.phases:
        counts: list[str] = []
        for execution in (phase.security, phase.suite):
            count = str(len(execution.tests))
            xfailed = sum(test.expected_failure for test in execution.tests)
            skipped = sum(
                test.outcome == "skipped" and not test.expected_failure
                for test in execution.tests
            )
            if xfailed or skipped:
                count += f" ({xfailed} xfailed, {skipped} skipped)"
            counts.append(count)
        rows.append(
            f"| {phase.name} | {phase.security.returncode} "
            f"| {counts[0]} | {phase.suite.returncode} | {counts[1]} |"
        )
    for phase in report.phases:
        for label, execution in (("oracle", phase.security), ("suite", phase.suite)):
            excerpt = diagnostic_excerpt(
                execution,
                include_failures=(
                    label == "suite"
                    or phase.name == "backport"
                    or (report.status != "verified" and phase.name in report.reason)
                ),
            )
            if excerpt:
                rows.extend(
                    [
                        "",
                        f"### {phase.name} {label} diagnostics",
                        "",
                        *(f"    {line}" for line in excerpt.splitlines()),
                    ]
                )
    rows.extend(
        ["", "See report.json for individual outcomes and bounded execution logs.", ""]
    )
    (output / "report.md").write_text("\n".join(rows), "utf-8")
    return report
