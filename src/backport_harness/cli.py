"""Expose backport preparation and verification through a small CLI."""

import os
from collections import Counter
from pathlib import Path
from typing import TYPE_CHECKING, Annotated

import typer
from pydantic import ValidationError

from .demo import DEFAULT_IMAGE, build_demo_image, create_demo, docker_arguments
from .models import RunReport, TestCaseResult
from .processes import run_process

if TYPE_CHECKING:
    from .agent import OpenAIPatchAgent

app = typer.Typer(
    help="Adapt a security fix to an older release and verify the execution evidence.",
    no_args_is_help=True,
    pretty_exceptions_enable=False,
)


def _local_api_key(env_file: Path | None) -> str:
    """Read only explicitly selected local credentials, never target config."""
    if env_file is None:
        value = os.environ.get("OPENAI_API_KEY", "").strip()
    else:
        value = ""
        found = False
        for line in env_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            name, separator, candidate = line.partition("=")
            if name.strip() != "OPENAI_API_KEY" or not separator or found:
                raise ValueError(
                    "Credential file must contain one OPENAI_API_KEY assignment "
                    "and optional comments"
                )
            found = True
            value = candidate.strip()
            if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
                value = value[1:-1]
    if not value or "\n" in value or "\r" in value:
        raise ValueError(
            "Set OPENAI_API_KEY in the controller environment or use --env-file"
        )
    return value


def make_openai_proposer(
    model: str, api_budget_usd: float, env_file: Path | None
) -> "OpenAIPatchAgent":
    """Create a paid proposer only when the operator explicitly selects a model."""
    from .agent import OpenAIPatchAgent

    return OpenAIPatchAgent(
        api_key=_local_api_key(env_file), model=model, budget_usd=api_budget_usd
    )


def _test_summary(cases: list[TestCaseResult]) -> str:
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


def _render(report: RunReport) -> None:
    typer.echo(f"{report.status.upper()}: {report.reason}")
    if report.phases:
        typer.echo("Checks:")
    for phase in report.phases:
        typer.echo(f"  {phase.name}: {_test_summary(phase.security.tests)}")
        typer.echo(f"    suite: {_test_summary(phase.suite.tests)}")
    typer.echo("Verification covers the recorded oracle, controls, and suite only.")


def _exit_for(report: RunReport) -> None:
    if report.status != "verified":
        raise typer.Exit(1 if report.status == "failed" else 2)


@app.command()
def run(
    repo: Annotated[Path, typer.Option(exists=True, file_okay=False)],
    fix: Annotated[str, typer.Option(help="One upstream security-fix commit.")],
    target: Annotated[str, typer.Option(help="Maintained release ref or commit.")],
    config: Annotated[Path, typer.Option(exists=True, dir_okay=False)],
    output: Annotated[Path, typer.Option(help="New directory for patch and evidence.")],
    candidate_patch: Annotated[
        Path | None,
        typer.Option(
            exists=True, dir_okay=False, help="Verify a supplied patch offline."
        ),
    ] = None,
    model: Annotated[
        str | None,
        typer.Option(help="Explicitly enable paid adaptation with this OpenAI model."),
    ] = None,
    api_budget_usd: Annotated[
        float,
        typer.Option(min=0.01, max=10, help="Local maximum API reservation in USD."),
    ] = 10,
    env_file: Annotated[
        Path | None,
        typer.Option(exists=True, dir_okay=False, help="Explicit controller key file."),
    ] = None,
) -> None:
    """Verify an existing fix against its parent and an older maintained release."""
    from .core import run_backport

    if candidate_patch is not None and model is not None:
        raise typer.BadParameter("Use either --candidate-patch or --model")
    if env_file is not None and model is None:
        raise typer.BadParameter("--env-file requires an explicit --model")
    proposer = None
    try:
        proposer = (
            make_openai_proposer(model, api_budget_usd, env_file)
            if model is not None
            else None
        )
        report = run_backport(
            repo,
            fix,
            target,
            config,
            output,
            proposer=proposer,
            candidate_patch=candidate_patch,
            progress=typer.echo,
        )
    except (OSError, ValueError, RuntimeError) as error:
        typer.echo(f"Error: {error}", err=True)
        raise typer.Exit(2) from error
    finally:
        if proposer is not None:
            proposer.close()
    _render(report)
    typer.echo(f"Evidence: {output.resolve() / 'report.json'}")
    _exit_for(report)


@app.command()
def inspect(
    report: Annotated[Path, typer.Option(exists=True, dir_okay=False)],
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Print the validated machine-readable report."),
    ] = False,
) -> None:
    """Read a completed report without running commands or contacting a model."""
    try:
        record = RunReport.model_validate_json(report.read_bytes())
    except (OSError, ValidationError) as error:
        typer.echo(f"Invalid report: {error}", err=True)
        raise typer.Exit(2) from error
    if json_output:
        typer.echo(record.model_dump_json(indent=2))
    else:
        _render(record)


@app.command()
def doctor(
    docker: Annotated[
        str, typer.Option(help="Trusted Docker command, e.g. 'sudo -n docker'.")
    ] = "docker",
) -> None:
    """Check local Git and Docker prerequisites without API credentials."""
    try:
        docker_command = docker_arguments(docker)
    except ValueError as error:
        raise typer.BadParameter(str(error)) from error
    checks = (
        ("Git", ["git", "--version"]),
        ("Docker", [*docker_command, "info", "--format", "{{.ServerVersion}}"]),
    )
    ready = True
    for name, command in checks:
        try:
            result = run_process(command, timeout=15, max_output=8192)
            passed = result.returncode == 0 and not result.timed_out
            detail = (
                result.stdout.strip() if passed else "unavailable or not accessible"
            )
        except OSError:
            passed, detail = False, "executable not found"
        ready = ready and passed
        typer.echo(f"{name}: {'OK' if passed else 'FAIL'} {detail}")
    typer.echo("No API key is required for offline verification or the demo.")
    if not ready:
        raise typer.Exit(2)


@app.command()
def demo(
    output: Annotated[
        Path, typer.Option(help="Empty directory for the fixture and verification.")
    ],
    docker: Annotated[
        str, typer.Option(help="Trusted Docker command, e.g. 'sudo -n docker'.")
    ] = "docker",
    image: Annotated[
        str | None,
        typer.Option(help="Use an existing Python+pytest image; skip the demo build."),
    ] = None,
) -> None:
    """Run a complete synthetic backport exercise without an API key."""
    from .core import run_backport

    try:
        command = docker_arguments(docker)
        project = create_demo(output, docker=command, image=image or DEFAULT_IMAGE)
        if image is None:
            typer.echo("Building the trusted Python+pytest image (network required).")
            build_demo_image(output.resolve(), docker=command)
        typer.echo("Running the independent before/after verification matrix.")
        evidence = output.resolve() / "verification"
        report = run_backport(
            project.repo,
            project.fix,
            project.target,
            project.config_path,
            evidence,
            candidate_patch=project.candidate_patch,
            progress=typer.echo,
        )
    except (OSError, ValueError, RuntimeError) as error:
        typer.echo(f"Demo error: {error}", err=True)
        raise typer.Exit(2) from error
    _render(report)
    typer.echo(f"Evidence: {evidence / 'report.json'}")
    typer.echo(
        "Synthetic fixture; the reference adaptation is supplied offline. "
        "No AI model or published CVE is involved."
    )
    _exit_for(report)


if __name__ == "__main__":
    app()
