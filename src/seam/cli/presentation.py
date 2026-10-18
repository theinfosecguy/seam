"""Render bounded, truthful command-line verification summaries."""

from collections import Counter

import typer

from seam.models import RunReport, TestCaseResult
from seam.verification.reporting import diagnostic_excerpt, display_text


def test_summary(cases: list[TestCaseResult]) -> str:
    """Summarize outcomes and a bounded list of unsuccessful test names."""
    if not cases:
        return "no test evidence"
    counts = Counter(
        "xfailed" if case.expected_failure else case.outcome for case in cases
    )
    summary = ", ".join(
        f"{count} {outcome}" for outcome, count in sorted(counts.items())
    )
    rejected = [repr(case.name) for case in cases if case.outcome != "passed"]
    if rejected:
        summary += "; " + ", ".join(rejected[:5])
        if len(rejected) > 5:
            summary += f"; and {len(rejected) - 5} more (see report)"
    return display_text(summary)


def render_report(report: RunReport) -> None:
    """Display the verification result and the scope of its evidence."""
    typer.echo(f"{report.status.upper()}: {display_text(report.reason)}")
    if report.reviewed_tests is not None:
        typer.echo(
            "Reviewed test expectations: "
            f"{display_text(report.reviewed_tests.reason)} "
            f"(SHA-256 {report.reviewed_tests.sha256})"
        )
    if report.reviewed_fixtures:
        typer.echo(
            f"Reviewed cryptographic fixtures: {len(report.reviewed_fixtures)} "
            "exact paths with pinned SHA-256 hashes."
        )
    if report.phases:
        typer.echo("Checks:")
    for phase in report.phases:
        typer.echo(f"  {phase.name} oracle: {test_summary(phase.security.tests)}")
        typer.echo(f"    suite: {test_summary(phase.suite.tests)}")
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
                typer.echo(
                    f"    {label} diagnostics (see report.json for full capture):"
                )
                for line in excerpt.splitlines():
                    typer.echo(f"      {line}")
    typer.echo("Verification covers the recorded oracle, controls, and suite only.")


def exit_for_report(report: RunReport) -> None:
    """Return distinct shell statuses for failed and inconclusive verification."""
    if report.status != "verified":
        raise typer.Exit(1 if report.status == "failed" else 2)
