"""Expose backport preparation and verification through a small CLI."""

import math
import os
from collections import Counter
from enum import StrEnum
from pathlib import Path
from typing import TYPE_CHECKING, Annotated

import typer
from pydantic import ValidationError

from .demo import DEFAULT_IMAGE, build_demo_image, create_demo, docker_arguments
from .models import RunReport, TestCaseResult
from .processes import run_process

if TYPE_CHECKING:
    from .agent import DeepSeekPatchAgent, OpenAIPatchAgent

app = typer.Typer(
    help="Adapt a security fix to an older release and verify the execution evidence.",
    no_args_is_help=True,
    pretty_exceptions_enable=False,
)


class ModelProvider(StrEnum):
    """Limit paid adaptation to explicitly supported provider endpoints."""

    OPENAI = "openai"
    DEEPSEEK = "deepseek"


_KEY_NAMES = {
    ModelProvider.OPENAI: "OPENAI_API_KEY",
    ModelProvider.DEEPSEEK: "DEEPSEEK_API_KEY",
}


def _local_api_key(
    env_file: Path | None, provider: ModelProvider = ModelProvider.OPENAI
) -> str:
    """Read only explicitly selected local credentials, never target config."""
    key_name = _KEY_NAMES[provider]
    if env_file is None:
        value = os.environ.get(key_name, "").strip()
    else:
        value = ""
        found: set[str] = set()
        if env_file.stat().st_size > 65536:
            raise ValueError("Credential file exceeds 64 KiB")
        for line in env_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            name, separator, candidate = line.partition("=")
            name = name.strip()
            if name not in _KEY_NAMES.values() or not separator or name in found:
                raise ValueError(
                    "Credential file accepts only OPENAI_API_KEY and "
                    "DEEPSEEK_API_KEY assignments, once each, and optional comments"
                )
            found.add(name)
            if name == key_name:
                value = candidate.strip()
                if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
                    value = value[1:-1]
    if not value or "\n" in value or "\r" in value:
        raise ValueError(
            f"Set {key_name} in the controller environment or use --env-file"
        )
    return value


def make_openai_proposer(
    model: str, api_budget_usd: float | None, env_file: Path | None
) -> "OpenAIPatchAgent":
    """Create a paid proposer only when the operator explicitly selects a model."""
    from .agent import OpenAIPatchAgent

    return OpenAIPatchAgent(
        api_key=_local_api_key(env_file), model=model, budget_usd=api_budget_usd
    )


def make_deepseek_proposer(
    model: str, api_budget_usd: float | None, env_file: Path | None
) -> "DeepSeekPatchAgent":
    """Keep DeepSeek credentials separate from the OpenAI integration."""
    from .agent import DEEPSEEK_MODELS, DeepSeekPatchAgent

    if model not in DEEPSEEK_MODELS:
        raise ValueError("Unsupported DeepSeek model")
    return DeepSeekPatchAgent(
        api_key=_local_api_key(env_file, ModelProvider.DEEPSEEK),
        model=model,
        budget_usd=api_budget_usd,
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
    from .core import run_backport

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
