"""Evaluate model adaptations or explicit offline patches with the verifier."""

import hashlib
import json
import platform
import re
import tempfile
import time
from collections.abc import Callable
from importlib.metadata import distribution, version
from pathlib import Path
from typing import Literal

from seam import repository
from seam.constants.evals import (
    DATASET_VERSION,
    EVAL_BUILD_TIMEOUT_SECONDS,
    MAX_EVAL_ASSET_BYTES,
)
from seam.constants.repository import MAX_PATCH_BYTES
from seam.evals.catalogue import load_case, read_asset
from seam.execution.processes import run_process
from seam.models import RunnerConfig, RunReport
from seam.security.files import read_controller_text
from seam.verification.config import load_config
from seam.verification.reporting import write_report
from seam.verification.workflow import PatchProposer, run_backport


def _package_source_hash(package: Path) -> str:
    """Hash installed code and resources independently of location and caches."""
    digest = hashlib.sha256()
    for path in sorted(package.rglob("*")):
        relative = path.relative_to(package)
        if (
            not path.is_file()
            or "__pycache__" in relative.parts
            or path.suffix in {".pyc", ".pyo"}
            or relative.parts[:2] == ("evals", "data")
        ):
            continue
        data = path.read_bytes()
        digest.update(relative.as_posix().encode() + b"\0")
        digest.update(str(len(data)).encode() + b"\0" + data)
    return digest.hexdigest()


def _distribution_provenance() -> dict[str, str]:
    """Retain immutable installation IDs without exposing local paths or URLs."""
    raw = distribution("seam").read_text("direct_url.json")
    if raw is None:
        return {}
    try:
        record = json.loads(raw)
    except ValueError:
        return {}
    if not isinstance(record, dict):
        return {}
    result = {}
    archive = record.get("archive_info")
    if isinstance(archive, dict):
        hashes = archive.get("hashes", {})
        sha256 = hashes.get("sha256") if isinstance(hashes, dict) else None
        if sha256 is None and isinstance(archive.get("hash"), str):
            sha256 = archive["hash"].removeprefix("sha256=")
        if isinstance(sha256, str) and re.fullmatch(r"[0-9a-f]{64}", sha256):
            result["archive_sha256"] = sha256
    vcs = record.get("vcs_info")
    if isinstance(vcs, dict):
        commit = vcs.get("commit_id")
        if isinstance(commit, str) and re.fullmatch(r"[0-9a-f]{40,64}", commit):
            result["vcs_commit"] = commit
    return result


def _base_images(dockerfile: str) -> list[str]:
    images = []
    for line in dockerfile.splitlines():
        words = line.split()
        if words and words[0].upper() == "FROM":
            names = [word for word in words[1:] if not word.startswith("--")]
            if (
                not names
                or re.fullmatch(r"[^\s@]+@sha256:[0-9a-f]{64}", names[0]) is None
            ):
                raise ValueError("evaluation base images require manifest SHA-256 pins")
            images.append(names[0])
    if not images:
        raise ValueError("evaluation recipe must declare a pinned base image")
    return images


def run_case(
    dataset: Path,
    instance_id: str,
    output: Path,
    *,
    docker: tuple[str, ...] = ("docker",),
    build_image: bool = False,
    image: str | None = None,
    mode: Literal["reference", "direct", "candidate", "agent"] = "agent",
    candidate_patch: Path | None = None,
    proposer: PatchProposer | None = None,
    progress: Callable[[str], None] | None = None,
) -> RunReport:
    """Validate inputs, adapt a case, and preserve bounded setup-failure evidence."""
    dataset = dataset.resolve()
    case, directory = load_case(dataset, instance_id)
    if mode not in {"reference", "direct", "candidate", "agent"} or (
        (mode == "candidate") != (candidate_patch is not None)
        or (mode == "agent") != (proposer is not None)
    ):
        raise ValueError(
            "candidate and agent modes require their explicit patch or model"
        )
    if build_image and image is not None:
        raise ValueError("select either a recipe build or an explicit execution image")
    if candidate_patch is not None and not read_controller_text(
        candidate_patch, MAX_PATCH_BYTES
    ):
        raise ValueError("candidate patch must be nonempty")
    config_path = directory / "harness.toml"
    config = load_config(config_path)
    declared_image = config.runner.image
    selected_image = declared_image if image is None else image
    if build_image:
        selected_image = f"seam-eval-{case.instance_id}:python-v1"
    runner_config = RunnerConfig.model_validate(
        {**config.runner.model_dump(), "docker": docker, "image": selected_image}
    )
    base_images = _base_images(read_asset(directory, "Dockerfile"))
    provenance = {
        "harness_version": version("seam"),
        "harness_distribution": _distribution_provenance(),
        "harness_source_sha256": _package_source_hash(
            Path(__file__).resolve().parents[1]
        ),
        "case_sha256": hashlib.sha256(
            (directory / "case.json").read_bytes()
        ).hexdigest(),
    }
    output = output.resolve()
    if output == dataset or dataset in output.parents:
        raise ValueError("evaluation output must be outside the dataset")
    if output.exists() and (not output.is_dir() or any(output.iterdir())):
        raise ValueError("evaluation output directory must be new or empty")
    output.mkdir(parents=True, exist_ok=True, mode=0o700)
    output.chmod(0o700)
    started = time.monotonic()
    report = RunReport(
        status="inconclusive", reason="evaluation setup did not complete"
    )
    try:
        if build_image:
            built = run_process(
                [
                    *docker,
                    "build",
                    "--pull",
                    "--no-cache",
                    "--platform",
                    case.platform,
                    "--tag",
                    selected_image,
                    "--label",
                    "org.opencontainers.image.source=https://github.com/theinfosecguy/seam",
                    str(directory),
                ],
                timeout=EVAL_BUILD_TIMEOUT_SECONDS,
                max_output=MAX_EVAL_ASSET_BYTES,
            )
            (output / "image-build.log").write_text(built.stdout + built.stderr)
            if built.returncode or built.timed_out or built.truncated:
                raise ValueError("evaluation image build failed; see image-build.log")
        source = output / "source"
        with tempfile.TemporaryDirectory(prefix="seam-eval-template-") as empty:
            repository.git(
                output,
                "clone",
                "--no-local",
                "--no-hardlinks",
                "--no-checkout",
                "--no-recurse-submodules",
                f"--template={empty}",
                "--",
                f"https://github.com/{case.repo}.git",
                str(source),
            )
        for revision in (
            case.base_commit,
            case.upstream_parent_commit,
            case.upstream_fix_commit,
        ):
            if repository.resolve(source, revision) != revision:
                raise ValueError("evaluation source revision did not resolve exactly")
        if (
            repository.parent(source, case.upstream_fix_commit)
            != case.upstream_parent_commit
        ):
            raise ValueError("evaluation upstream parent contradicts fix commit")
        report = run_backport(
            source,
            case.upstream_fix_commit,
            case.base_commit,
            config_path,
            output / "evidence",
            direct=mode == "direct",
            runner_config=runner_config,
            candidate_patch=(
                directory / "reference.patch"
                if mode == "reference"
                else candidate_patch
            ),
            proposer=proposer,
            progress=progress,
        )
        if report.status == "verified" and (
            not report.phases
            or len(report.phases[-1].suite.tests) != case.expected_suite_cases
        ):
            report.status = "inconclusive"
            report.reason = (
                "verified evaluation suite count differs from published case"
            )
            write_report(output / "evidence", report)
    except (OSError, ValueError, RuntimeError) as error:
        report.status = "inconclusive"
        report.reason = f"Evaluation setup could not complete: {str(error)[:2000]}"
    finally:
        report_path = output / "evidence/report.json"
        manifest = {
            "schema_version": 1,
            "dataset_version": DATASET_VERSION,
            "instance_id": case.instance_id,
            **provenance,
            "asset_sha256": case.asset_sha256,
            "platform": case.platform,
            "controller_python": platform.python_version(),
            "mode": mode,
            "repo": case.repo,
            "base_commit": case.base_commit,
            "upstream_parent_commit": case.upstream_parent_commit,
            "upstream_fix_commit": case.upstream_fix_commit,
            "case_image_reference": declared_image,
            "image_reference": selected_image,
            "base_image_references": base_images,
            "base_image_manifest_digests": [
                value.split("@", 1)[1] for value in base_images
            ],
            "image_id": report.image_id,
            "status": report.status,
            "reason": report.reason,
            "duration_seconds": round(time.monotonic() - started, 3),
            "report_sha256": (
                hashlib.sha256(report_path.read_bytes()).hexdigest()
                if report_path.is_file()
                else None
            ),
            "patch_sha256": report.patch_sha256,
            "model_usage": proposer.usage
            if proposer is not None
            else report.model_usage,
            "phases": [
                {
                    "name": phase.name,
                    "revision": phase.revision,
                    "security_returncode": phase.security.returncode,
                    "suite_returncode": phase.suite.returncode,
                    "security_cases": len(phase.security.tests),
                    "suite_cases": len(phase.suite.tests),
                    "security_outcomes": [
                        test.model_dump(exclude={"message"})
                        for test in phase.security.tests
                    ],
                    "suite_outcomes": [
                        test.model_dump(exclude={"message"})
                        for test in phase.suite.tests
                    ],
                }
                for phase in report.phases
            ],
            "test_scope": (
                "selected oracle, controls, and project suite; "
                "no universal security claim"
            ),
        }
        (output / "run-manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    return report
