"""Persist machine-readable and human-readable verification reports."""

from pathlib import Path

from backport_harness.models import RunReport


def write_report(output: Path, report: RunReport) -> RunReport:
    """Write both report formats and return the recorded result."""
    (output / "report.json").write_text(
        report.model_dump_json(indent=2) + "\n", "utf-8"
    )
    rows = [
        "# Security backport evidence",
        "",
        f"Status: **{report.status}**",
        "",
        report.reason,
        "",
        "Verification is limited to the recorded tests, revisions, "
        "and execution image.",
        "",
        f"- Fix: `{report.fix_commit}`",
        f"- Target: `{report.target_commit}`",
        f"- Image: `{report.image_id}`",
        f"- Oracle SHA-256: `{report.oracle_sha256}`",
        f"- Patch SHA-256: `{report.patch_sha256 or 'none'}`",
        "",
        "| Revision | Security exit | Suite exit | Test cases |",
        "| --- | ---: | ---: | ---: |",
    ]
    for phase in report.phases:
        rows.append(
            f"| {phase.name} | {phase.security.returncode} | {phase.suite.returncode} "
            f"| {len(phase.security.tests) + len(phase.suite.tests)} |"
        )
    rows.extend(
        ["", "See report.json for individual outcomes and bounded execution logs.", ""]
    )
    (output / "report.md").write_text("\n".join(rows), "utf-8")
    return report
