"""Load reviewed case assets and export a reproducible JSONL catalogue."""

import hashlib
import json
import re
from importlib.resources import files
from pathlib import Path

from seam.constants.evals import DATASET_VERSION, MAX_EVAL_ASSET_BYTES, MAX_EVAL_CASES
from seam.constants.verification import MAX_CONFIG_BYTES
from seam.evals.models import EvalCase, valid_asset_path
from seam.security.files import read_controller_text
from seam.verification.config import load_config


def default_dataset() -> Path:
    """Locate bundled case data independently of the working directory."""
    bundled = Path(str(files("seam.evals").joinpath("data/python")))
    if (bundled / "cases").is_dir():
        return bundled
    source = Path(__file__).resolve().parents[3] / "evals/python"
    if (source / "cases").is_dir():
        return source
    raise ValueError("installed evaluation dataset is missing")


def read_asset(directory: Path, name: str) -> str:
    """Read bounded UTF-8 case data without accepting linked or escaping paths."""
    path = directory / name
    if not valid_asset_path(name) or any(
        parent.is_symlink()
        for parent in (path, *path.parents)
        if parent.is_relative_to(directory)
    ):
        raise ValueError("evaluation assets cannot traverse symbolic links")
    return read_controller_text(path, MAX_EVAL_ASSET_BYTES)


def load_case(dataset: Path, instance_id: str) -> tuple[EvalCase, Path]:
    """Validate case metadata, every declared asset, and the native harness config."""
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,79}", instance_id):
        raise ValueError("select an exact evaluation case ID")
    dataset = dataset.resolve()
    directory = dataset / "cases" / instance_id
    if directory.is_symlink() or (dataset / "cases").is_symlink():
        raise ValueError("evaluation case directories cannot be symbolic links")
    if (directory / "case.json").is_symlink():
        raise ValueError("evaluation metadata cannot be a symbolic link")
    case = EvalCase.model_validate_json(
        read_controller_text(directory / "case.json", MAX_CONFIG_BYTES)
    )
    if case.instance_id != instance_id:
        raise ValueError("evaluation case ID contradicts its directory")
    actual_assets = set()
    for path in directory.rglob("*"):
        if path.is_symlink():
            raise ValueError("evaluation assets cannot be symbolic links")
        if path.is_file() and path.name != "case.json":
            actual_assets.add(path.relative_to(directory).as_posix())
    if actual_assets != set(case.asset_sha256):
        raise ValueError("evaluation case has unlisted or missing assets")
    for name, digest in case.asset_sha256.items():
        if hashlib.sha256(read_asset(directory, name).encode()).hexdigest() != digest:
            raise ValueError(f"evaluation asset SHA-256 mismatch: {name}")
    config = load_config(directory / "harness.toml")
    if config.oracle.path != (directory / "oracle.py").resolve():
        raise ValueError("evaluation oracle must be the pinned oracle.py asset")
    if config.reviewed_tests is not None:
        reviewed = config.reviewed_tests
        if (
            not reviewed.path.is_relative_to(directory)
            or case.asset_sha256.get(str(reviewed.path.relative_to(directory)))
            != reviewed.sha256
        ):
            raise ValueError("reviewed test patch must be a pinned case asset")
    return case, directory


def cases(dataset: Path) -> list[tuple[EvalCase, Path]]:
    """Load a bounded catalogue in stable ID order."""
    paths = sorted((dataset / "cases").iterdir())
    if not paths or len(paths) > MAX_EVAL_CASES:
        raise ValueError("evaluation dataset has no cases or exceeds its case limit")
    return [load_case(dataset, path.name) for path in paths]


def export_catalogue(dataset: Path) -> str:
    """Export familiar patch-task fields with an explicit Seam backport extension."""
    rows = []
    for case, directory in cases(dataset):
        config = load_config(directory / "harness.toml")
        row = {
            "instance_id": case.instance_id,
            "repo": case.repo,
            "base_commit": case.base_commit,
            "problem_statement": case.problem_statement,
            "patch": read_asset(directory, "reference.patch"),
            "FAIL_TO_PASS": json.dumps([f"oracle.py::{config.oracle.security_test}"]),
            "PASS_TO_PASS": json.dumps(
                [f"oracle.py::{name}" for name in config.oracle.controls]
            ),
            "seam": {
                "dataset_version": DATASET_VERSION,
                "project_suite": list(config.runner.suite),
                "project_suite_markers": config.runner.suite_markers,
                **case.model_dump(
                    exclude={"instance_id", "repo", "base_commit", "problem_statement"}
                ),
            },
        }
        rows.append(json.dumps(row, sort_keys=True))
    return "\n".join(rows) + "\n"
