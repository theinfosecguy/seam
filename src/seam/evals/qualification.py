"""Qualify reference replays and an executed negative control before release."""

import difflib
import hashlib
import json
from collections.abc import Callable
from pathlib import Path

from seam import repository
from seam.evals.catalogue import load_case, read_asset
from seam.evals.runner import run_case
from seam.models import RunReport
from seam.verification.assessment import assess_phase
from seam.verification.config import load_config


def _suite_identities(report: RunReport) -> set[tuple[str, str]]:
    return {(test.classname, test.name) for test in report.phases[-1].suite.tests}


def _same_inputs(output: Path, reports: tuple[RunReport, ...]) -> None:
    """Require the same case, harness build, image and effective verification inputs."""
    manifests = [
        json.loads((output / name / "run-manifest.json").read_text())
        for name in ("reference", "repeat", "negative")
    ]
    keys = (
        "case_sha256",
        "asset_sha256",
        "harness_source_sha256",
        "harness_version",
        "harness_distribution",
        "image_id",
        "base_image_manifest_digests",
        "repo",
        "base_commit",
        "upstream_parent_commit",
        "upstream_fix_commit",
    )
    if any(
        any(record.get(key) != manifests[0].get(key) for key in keys)
        for record in manifests[1:]
    ):
        raise ValueError("qualification inputs changed between runs")
    configurations = []
    for name, manifest, report in zip(
        ("reference", "repeat", "negative"), manifests, reports, strict=True
    ):
        config_bytes = (output / name / "evidence/config.json").read_bytes()
        if report.config_sha256 != hashlib.sha256(config_bytes).hexdigest():
            raise ValueError("qualification configuration hash contradicts its report")
        report_bytes = (output / name / "evidence/report.json").read_bytes()
        if (
            manifest.get("report_sha256") != hashlib.sha256(report_bytes).hexdigest()
            or RunReport.model_validate_json(report_bytes) != report
        ):
            raise ValueError("qualification stored report contradicts its manifest")
        config = json.loads(config_bytes)
        config["runner"]["image"] = manifest["image_id"]
        configurations.append(config)
    if any(value != configurations[0] for value in configurations[1:]):
        raise ValueError("qualification verification configuration changed")


def qualify_case(
    dataset: Path,
    instance_id: str,
    output: Path,
    *,
    docker: tuple[str, ...] = ("docker",),
    build_image: bool = False,
    progress: Callable[[str], None] | None = None,
) -> dict[str, object]:
    """Require two successful references and rejection of unchanged implementation."""
    case, directory = load_case(dataset.resolve(), instance_id)
    output = output.resolve()
    if output == dataset.resolve() or dataset.resolve() in output.parents:
        raise ValueError("qualification output must be outside the dataset")
    if output.exists() and any(output.iterdir()):
        raise ValueError("qualification output directory must be new or empty")
    output.mkdir(parents=True, exist_ok=True, mode=0o700)
    summary: dict[str, object] = {
        "schema_version": 1,
        "instance_id": instance_id,
        "qualified": False,
    }
    try:
        config = load_config(directory / "harness.toml")
        first = run_case(
            dataset,
            instance_id,
            output / "reference",
            mode="reference",
            docker=docker,
            build_image=build_image,
            progress=progress,
        )
        if first.status != "verified":
            raise ValueError("reference patch did not verify")
        second = run_case(
            dataset,
            instance_id,
            output / "repeat",
            mode="reference",
            docker=docker,
            image=first.image_id,
            progress=progress,
        )
        if (
            second.status != "verified"
            or first.patch_sha256 != second.patch_sha256
            or _suite_identities(first) != _suite_identities(second)
        ):
            raise ValueError("reference replay changed the verified patch or suite")
        revisions = (
            case.upstream_parent_commit,
            case.upstream_fix_commit,
            case.base_commit,
            case.base_commit,
        )
        names = ("upstream_parent", "upstream_fix", "target_baseline", "backport")
        for report in (first, second):
            RunReport.model_validate(report.model_dump())
            if (
                report.image_id != first.image_id
                or report.oracle_sha256 != case.asset_sha256["oracle.py"]
                or (report.parent_commit, report.fix_commit, report.target_commit)
                != (
                    case.upstream_parent_commit,
                    case.upstream_fix_commit,
                    case.base_commit,
                )
                or tuple(phase.name for phase in report.phases) != names
                or tuple(phase.revision for phase in report.phases) != revisions
                or len(report.phases[-1].suite.tests) != case.expected_suite_cases
            ):
                raise ValueError(
                    "reference replay changed image, oracle, or revision provenance"
                )
            for phase in report.phases:
                status, _ = assess_phase(
                    phase,
                    config,
                    vulnerable=phase.name in {"upstream_parent", "target_baseline"},
                )
                if status != "passed":
                    raise ValueError(
                        "reference evidence contradicts the declared oracle"
                    )
        source = output / "reference/source"
        source_names = repository.validate_patch(
            source, read_asset(directory, "reference.patch")
        )
        name = next(
            name
            for name in source_names
            if repository.git(
                source, "ls-tree", case.base_commit, "--", name
            ).startswith(("100644", "100755"))
        )
        before = repository.git(source, "show", f"{case.base_commit}:{name}")
        if not before.endswith("\n"):
            raise ValueError(
                "negative control requires a source file with a final newline"
            )
        after = (
            before + "\n# Negative control: implementation intentionally unchanged.\n"
        )
        patch = "".join(
            difflib.unified_diff(
                before.splitlines(keepends=True),
                after.splitlines(keepends=True),
                fromfile=f"a/{name}",
                tofile=f"b/{name}",
            )
        )
        negative_path = output / "negative.patch"
        negative_path.write_text(patch)
        negative = run_case(
            dataset,
            instance_id,
            output / "negative",
            docker=docker,
            image=first.image_id,
            mode="candidate",
            candidate_patch=negative_path,
            progress=progress,
        )
        if (
            negative.status != "failed"
            or negative.adaptation != "provided_patch"
            or negative.attempts != 1
            or tuple(phase.name for phase in negative.phases) != names
            or tuple(phase.revision for phase in negative.phases) != revisions
            or negative.image_id != first.image_id
            or negative.oracle_sha256 != first.oracle_sha256
            or (output / "negative/evidence/attempt-1.patch").read_bytes()
            != patch.encode()
        ):
            raise ValueError("negative candidate was not rejected by executed checks")
        _same_inputs(output, (first, second, negative))
        if negative.phases[-1].suite.evidence_issue() or _suite_identities(
            negative
        ) != _suite_identities(first):
            raise ValueError("negative candidate has incomplete project suite evidence")
        for phase in negative.phases[:3]:
            status, _ = assess_phase(
                phase, config, vulnerable=phase.name != "upstream_fix"
            )
            if status != "passed":
                raise ValueError("negative baseline prerequisites were not established")
        security = negative.phases[-1].security
        tests = {test.name: test for test in security.tests}
        regression = tests.get(config.oracle.security_test)
        if (
            security.evidence_issue()
            or security.returncode != 1
            or regression is None
            or regression.outcome != "failed"
            or config.oracle.failure_marker not in regression.message
            or "AssertionError" not in regression.message
            or any(
                name not in tests or tests[name].outcome != "passed"
                for name in config.oracle.controls
            )
        ):
            raise ValueError(
                "negative control requires the intended assertion and passing controls"
            )
        exported = (output / "reference/evidence/backport.patch").read_text()
        if hashlib.sha256(exported.encode()).hexdigest() != first.patch_sha256:
            raise ValueError("exported patch hash contradicts its verified report")
        application = output / "export-check"
        repository.clone_at(source, case.base_commit, application)
        repository.git(application, "apply", "--check", "-", input_text=exported)
        repository.git(application, "apply", "-", input_text=exported)
        tested_inputs = json.loads((output / "reference/run-manifest.json").read_text())
        current_case, _ = load_case(dataset.resolve(), instance_id)
        if (
            current_case != case
            or hashlib.sha256((directory / "case.json").read_bytes()).hexdigest()
            != tested_inputs["case_sha256"]
            or current_case.asset_sha256 != tested_inputs["asset_sha256"]
        ):
            raise ValueError("case inputs changed after qualification execution")
        summary.update(
            {
                "qualified": True,
                "reference_status": first.status,
                "repeat_status": second.status,
                "negative_status": negative.status,
                "target_suite_cases": case.expected_suite_cases,
                "backport_security_cases": len(first.phases[-1].security.tests),
                "suite_identities_preserved": True,
                "repeat_patch_identical": True,
                "ordinary_git_apply": True,
                "negative_intended_failure": True,
                "patch_sha256": hashlib.sha256(exported.encode()).hexdigest(),
                "case_sha256": tested_inputs["case_sha256"],
                "image_id": first.image_id,
                "reports": [
                    "reference/evidence/report.json",
                    "repeat/evidence/report.json",
                    "negative/evidence/report.json",
                ],
            }
        )
    except (OSError, ValueError, RuntimeError, StopIteration) as error:
        summary["reason"] = str(error)[:2000]
    finally:
        (output / "qualification.json").write_text(json.dumps(summary, indent=2) + "\n")
    return summary
