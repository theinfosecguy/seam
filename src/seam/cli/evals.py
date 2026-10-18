"""List, replay, and qualify the published Python evaluation cases."""

import math
from pathlib import Path
from typing import Annotated, Literal

import typer
from pydantic import ValidationError

from seam.cli.presentation import exit_for_report, render_report
from seam.cli.providers import make_proposer
from seam.constants.agent import CLI_MODEL_CALLS, MAX_API_CALLS
from seam.demo import docker_arguments
from seam.evals.catalogue import cases, default_dataset, export_catalogue, load_case
from seam.evals.qualification import qualify_case
from seam.evals.runner import run_case
from seam.models import ModelProvider
from seam.verification.reporting import display_text

app = typer.Typer(
    help="Replay the public Python backport evaluation cases.", no_args_is_help=True
)


def _error_detail(error: Exception) -> str:
    if isinstance(error, ValidationError):
        return display_text(
            "; ".join(item["msg"] for item in error.errors(include_input=False))
        )
    return display_text(str(error))


@app.command("list")
def list_cases(
    dataset: Annotated[Path | None, typer.Option(file_okay=False)] = None,
) -> None:
    """List case IDs and their selected target suite sizes; make no model requests."""
    try:
        for case, _ in cases(dataset or default_dataset()):
            typer.echo(
                f"{case.instance_id}: {case.repo} {case.target_version}; "
                f"{case.expected_suite_cases} suite cases"
            )
    except (OSError, ValueError) as error:
        raise typer.BadParameter(_error_detail(error)) from error


@app.command()
def check(
    dataset: Annotated[Path | None, typer.Option(file_okay=False)] = None,
) -> None:
    """Validate case assets and the generated catalogue without execution."""
    selected = dataset or default_dataset()
    try:
        expected = export_catalogue(selected)
        if (selected / "tasks.jsonl").read_text() != expected:
            raise ValueError(
                "tasks.jsonl is stale; regenerate it with seam eval export"
            )
        typer.echo(f"Validated {len(cases(selected))} cases and their asset hashes.")
    except (OSError, ValueError) as error:
        raise typer.BadParameter(_error_detail(error)) from error


@app.command()
def export(
    output: Annotated[Path, typer.Option()],
    dataset: Annotated[Path | None, typer.Option(file_okay=False)] = None,
) -> None:
    """Generate JSONL from reviewed metadata, configuration, and reference patches."""
    try:
        selected = (dataset or default_dataset()).resolve()
        destination = output.resolve()
        if destination != selected / "tasks.jsonl" and (
            destination == selected or selected in destination.parents
        ):
            raise ValueError("catalogue export cannot overwrite evaluation case assets")
        if output.is_symlink():
            raise ValueError("catalogue export cannot follow a symbolic link")
        if output.exists() and destination != selected / "tasks.jsonl":
            raise ValueError("catalogue export requires a new output file")
        value = export_catalogue(selected)
        output.write_text(value)
        typer.echo(f"Catalogue: {output.resolve()}")
    except (OSError, ValueError) as error:
        raise typer.BadParameter(_error_detail(error)) from error


@app.command()
def run(
    instance_id: str,
    output: Annotated[Path, typer.Option()],
    dataset: Annotated[Path | None, typer.Option(file_okay=False)] = None,
    docker: str = "docker",
    build_image: bool = False,
    mode: Literal["reference", "direct", "candidate", "agent"] = "reference",
    candidate_patch: Annotated[
        Path | None, typer.Option(exists=True, dir_okay=False)
    ] = None,
    model: str | None = None,
    provider: ModelProvider = ModelProvider.OPENAI,
    env_file: Annotated[Path | None, typer.Option(exists=True, dir_okay=False)] = None,
    provider_config: Annotated[
        Path | None, typer.Option(exists=True, dir_okay=False)
    ] = None,
    max_model_calls: Annotated[
        int, typer.Option(min=1, max=MAX_API_CALLS)
    ] = CLI_MODEL_CALLS,
    api_budget_usd: Annotated[float, typer.Option(min=0.01)] = 10,
    no_api_budget_cap: bool = False,
) -> None:
    """Run a reference by default; paid adaptation requires agent mode and a model."""
    selected = dataset or default_dataset()
    proposer = None
    try:
        load_case(selected.resolve(), instance_id)
        if (mode == "agent") != (model is not None) or (mode == "candidate") != (
            candidate_patch is not None
        ):
            raise ValueError(
                "select reference/direct, candidate with a patch, "
                "or agent with an explicit model"
            )
        if model is None and (
            env_file is not None
            or provider_config is not None
            or no_api_budget_cap
            or max_model_calls != CLI_MODEL_CALLS
        ):
            raise ValueError("model settings require agent mode and an explicit model")
        if not math.isfinite(api_budget_usd):
            raise ValueError("API budget must be finite")
        command = docker_arguments(docker)
        if model is not None:
            proposer = make_proposer(
                provider,
                model,
                None if no_api_budget_cap else api_budget_usd,
                env_file,
                max_model_calls=max_model_calls,
                provider_config=provider_config,
            )
        report = run_case(
            selected,
            instance_id,
            output,
            docker=command,
            build_image=build_image,
            mode=mode,
            candidate_patch=candidate_patch,
            proposer=proposer,
            progress=typer.echo,
        )
    except (OSError, ValueError, RuntimeError) as error:
        typer.echo(f"Evaluation error: {_error_detail(error)}", err=True)
        raise typer.Exit(2) from error
    finally:
        if proposer is not None:
            proposer.close()
    render_report(report)
    typer.echo(f"Manifest: {output.resolve() / 'run-manifest.json'}")
    report_path = output.resolve() / "evidence/report.json"
    if report_path.is_file():
        typer.echo(f"Evidence: {report_path}")
    exit_for_report(report)


@app.command()
def qualify(
    instance_id: str,
    output: Annotated[Path, typer.Option()],
    dataset: Annotated[Path | None, typer.Option(file_okay=False)] = None,
    docker: str = "docker",
    build_image: bool = False,
) -> None:
    """Repeat reference verification and require an executed negative control."""
    try:
        result = qualify_case(
            dataset or default_dataset(),
            instance_id,
            output,
            docker=docker_arguments(docker),
            build_image=build_image,
            progress=typer.echo,
        )
    except (OSError, ValueError, RuntimeError) as error:
        typer.echo(f"Qualification error: {_error_detail(error)}", err=True)
        raise typer.Exit(2) from error
    typer.echo(f"Qualification: {output.resolve() / 'qualification.json'}")
    if not result["qualified"]:
        reason = display_text(str(result.get("reason", "checks failed")))
        typer.echo(
            f"Not qualified: {reason}",
            err=True,
        )
        raise typer.Exit(2)
