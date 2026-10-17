"""Expose preparation, verification, and report inspection commands."""

import math
from pathlib import Path
from typing import Annotated

import typer
from pydantic import ValidationError

from seam.cli.credentials import (
    make_deepseek_proposer,
    make_openai_proposer,
)
from seam.cli.presentation import exit_for_report, render_report
from seam.constants import DEFAULT_IMAGE
from seam.demo import (
    build_demo_image,
    create_demo,
    docker_arguments,
)
from seam.execution.processes import run_process
from seam.models import ModelProvider, RunReport
from seam.verification.workflow import run_backport

app = typer.Typer(
    help="Adapt a security fix to an older release and verify the execution evidence.",
    no_args_is_help=True,
    pretty_exceptions_enable=False,
)


@app.command()
def run(
    repo: Annotated[Path, typer.Option(file_okay=False)],
    fix: Annotated[str, typer.Option(help="One upstream security-fix commit.")],
    target: Annotated[str, typer.Option(help="Maintained release ref or commit.")],
    config: Annotated[Path, typer.Option(dir_okay=False)],
    output: Annotated[Path, typer.Option(help="New directory for patch and evidence.")],
    candidate_patch: Annotated[
        Path | None,
        typer.Option(dir_okay=False, help="Verify a supplied patch offline."),
    ] = None,
    model: Annotated[
        str | None,
        typer.Option(help="Explicitly enable paid adaptation with this model."),
    ] = None,
    provider: Annotated[
        ModelProvider, typer.Option(help="Model service used only with --model.")
    ] = ModelProvider.OPENAI,
    api_budget_usd: Annotated[
        float,
        typer.Option(min=0.01, help="Local maximum API reservation in USD."),
    ] = 10,
    no_api_budget_cap: Annotated[
        bool,
        typer.Option(
            "--no-api-budget-cap",
            help="Disable the dollar cap; call, token, and execution limits remain.",
        ),
    ] = False,
    env_file: Annotated[
        Path | None,
        typer.Option(exists=True, dir_okay=False, help="Explicit controller key file."),
    ] = None,
) -> None:
    """Verify an existing fix against its parent and an older maintained release."""
    if candidate_patch is not None and model is not None:
        raise typer.BadParameter("Use either --candidate-patch or --model")
    if env_file is not None and model is None:
        raise typer.BadParameter("--env-file requires an explicit --model")
    if no_api_budget_cap and model is None:
        raise typer.BadParameter("--no-api-budget-cap requires an explicit --model")
    if not math.isfinite(api_budget_usd):
        raise typer.BadParameter("--api-budget-usd must be finite")
    proposer = None
    try:
        factory = (
            make_deepseek_proposer
            if provider == ModelProvider.DEEPSEEK
            else make_openai_proposer
        )
        proposer = (
            factory(model, None if no_api_budget_cap else api_budget_usd, env_file)
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
    render_report(report)
    typer.echo(f"Evidence: {output.resolve() / 'report.json'}")
    if report.status == "verified":
        typer.echo(f"Patch: {output.resolve() / 'backport.patch'}")
    exit_for_report(report)


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
        render_report(record)


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
    render_report(report)
    typer.echo(f"Evidence: {evidence / 'report.json'}")
    if report.status == "verified":
        typer.echo(f"Patch: {evidence / 'backport.patch'}")
    typer.echo(
        "Synthetic fixture; the reference adaptation is supplied offline. "
        "No AI model or published CVE is involved."
    )
    exit_for_report(report)
