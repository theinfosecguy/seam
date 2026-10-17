"""Render bounded, truthful command-line verification summaries."""

from collections import Counter

import typer

from seam.models import RunReport, TestCaseResult


def test_summary(cases: list[TestCaseResult]) -> str:
    """Summarize outcomes and a bounded list of unsuccessful test names."""
    if not cases:
        return "no test evidence"
    counts = Counter(case.outcome for case in cases)
    summary = ", ".join(
        f"{count} {outcome}" for outcome, count in sorted(counts.items())
    )
    rejected = [repr(case.name) for case in cases if case.outcome != "passed"]
    if rejected:
        summary += "; " + ", ".join(rejected[:5])
        if len(rejected) > 5:
            summary += f"; and {len(rejected) - 5} more (see report)"
    return summary


def render_report(report: RunReport) -> None:
    """Display the verification result and the scope of its evidence."""
    typer.echo(f"{report.status.upper()}: {report.reason}")
    if report.phases:
        typer.echo("Checks:")
    for phase in report.phases:
        typer.echo(f"  {phase.name}: {test_summary(phase.security.tests)}")
        typer.echo(f"    suite: {test_summary(phase.suite.tests)}")
    typer.echo("Verification covers the recorded oracle, controls, and suite only.")


def exit_for_report(report: RunReport) -> None:
    """Return distinct shell statuses for failed and inconclusive verification."""
    if report.status != "verified":
        raise typer.Exit(1 if report.status == "failed" else 2)
