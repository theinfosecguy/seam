"""Keep public evaluation assets bounded, portable, and faithful in exports."""

import compileall
import hashlib
import json
import shutil
from pathlib import Path

import pytest
from typer.testing import CliRunner

from seam.cli import app
from seam.constants.evals import DATASET_VERSION
from seam.evals import catalogue
from seam.verification.config import load_config

SOURCE_DATASET = Path(__file__).resolve().parents[2] / "evals/python"


@pytest.fixture
def dataset(tmp_path: Path) -> Path:
    destination = tmp_path / "dataset"
    shutil.copytree(SOURCE_DATASET, destination)
    return destination


def write_metadata(directory: Path, value: dict) -> None:
    (directory / "case.json").write_text(json.dumps(value))


def test_public_source_cases_and_default_resources_are_runnable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    expected = [
        "authlib",
        "flask",
        "h11",
        "jinja2",
        "python-multipart",
        "requests",
        "sqlparse",
        "urllib3",
    ]
    monkeypatch.chdir(tmp_path)
    assert [case.instance_id for case, _ in catalogue.cases(SOURCE_DATASET)] == expected
    assert [
        case.instance_id for case, _ in catalogue.cases(catalogue.default_dataset())
    ] == expected


def test_installed_resources_take_precedence_and_ignore_current_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    package = tmp_path / "package"
    bundled = package / "data/python"
    shutil.copytree(SOURCE_DATASET, bundled)
    monkeypatch.setattr(catalogue, "files", lambda name: package)
    monkeypatch.chdir(tmp_path)
    assert catalogue.default_dataset() == bundled
    assert len(catalogue.cases(catalogue.default_dataset())) == 8


def test_asset_content_must_match_the_frozen_hash(dataset: Path) -> None:
    oracle = dataset / "cases/h11/oracle.py"
    oracle.write_text(oracle.read_text() + "\n# changed after review\n")
    with pytest.raises(ValueError, match="SHA-256"):
        catalogue.load_case(dataset, "h11")


def test_installer_bytecode_keeps_the_catalogue_and_cli_check_valid(
    dataset: Path,
) -> None:
    before = catalogue.export_catalogue(dataset)
    oracle = dataset / "cases/h11/oracle.py"
    assert compileall.compile_file(str(oracle), quiet=1)
    assert list(oracle.parent.glob("__pycache__/*.pyc"))
    assert catalogue.load_case(dataset, "h11")[0].instance_id == "h11"
    assert catalogue.export_catalogue(dataset) == before
    result = CliRunner().invoke(app, ["eval", "check", "--dataset", str(dataset)])
    assert result.exit_code == 0, result.output
    assert "Validated 8 cases" in result.output
    oracle.write_text(
        oracle.read_text() + "\n# source changed despite cached bytecode\n"
    )
    with pytest.raises(ValueError, match="SHA-256"):
        catalogue.load_case(dataset, "h11")


@pytest.mark.parametrize("kind", ["directory", "bytecode"])
def test_installer_cache_exception_still_rejects_symlinks(
    dataset: Path, tmp_path: Path, kind: str
) -> None:
    oracle = dataset / "cases/h11/oracle.py"
    assert compileall.compile_file(str(oracle), quiet=1)
    path = oracle.parent / "__pycache__"
    if kind == "bytecode":
        path = next(path.glob("*.pyc"))
    outside = tmp_path / "outside"
    path.rename(outside)
    path.symlink_to(outside, target_is_directory=kind == "directory")
    with pytest.raises(ValueError, match="symbolic links"):
        catalogue.load_case(dataset, "h11")


@pytest.mark.parametrize("name", ["README.md", "helper.py", "case.json"])
def test_installer_cache_rejects_unlisted_non_bytecode_files(
    dataset: Path, name: str
) -> None:
    cache = dataset / "cases/h11/__pycache__"
    cache.mkdir()
    (cache / name).write_text("unreviewed file\n")
    with pytest.raises(ValueError, match="unlisted or missing"):
        catalogue.load_case(dataset, "h11")


def test_bytecode_outside_the_installer_cache_is_still_unlisted(dataset: Path) -> None:
    (dataset / "cases/h11/oracle.pyc").write_bytes(b"unexpected bytecode")
    with pytest.raises(ValueError, match="unlisted or missing"):
        catalogue.load_case(dataset, "h11")


def test_declared_cache_assets_still_require_their_pinned_hash(dataset: Path) -> None:
    directory = dataset / "cases/h11"
    cache = directory / "__pycache__"
    cache.mkdir()
    (cache / "declared.pyc").write_text("operator-declared input\n")
    metadata = json.loads((directory / "case.json").read_text())
    metadata["asset_sha256"]["__pycache__/declared.pyc"] = "a" * 64
    write_metadata(directory, metadata)
    with pytest.raises(ValueError, match="SHA-256"):
        catalogue.load_case(dataset, "h11")


@pytest.mark.parametrize("name", ["extra.py", "README.md", "nested/extra.py"])
def test_unlisted_files_are_rejected(dataset: Path, name: str) -> None:
    extra = dataset / "cases/h11" / name
    extra.parent.mkdir(exist_ok=True)
    extra.write_text("unreviewed execution input\n")
    with pytest.raises(ValueError):
        catalogue.load_case(dataset, "h11")


@pytest.mark.parametrize("name", ["oracle.py", "case.json"])
def test_linked_asset_or_metadata_cannot_escape_the_case(
    dataset: Path, tmp_path: Path, name: str
) -> None:
    path = dataset / "cases/h11" / name
    outside = tmp_path / name
    outside.write_bytes(path.read_bytes())
    path.unlink()
    path.symlink_to(outside)
    with pytest.raises(ValueError):
        catalogue.load_case(dataset, "h11")


@pytest.mark.parametrize("parent", ["cases", "cases/h11"])
def test_linked_case_directories_are_rejected(
    dataset: Path, tmp_path: Path, parent: str
) -> None:
    path = dataset / parent
    outside = tmp_path / "linked-directory"
    path.rename(outside)
    path.symlink_to(outside, target_is_directory=True)
    with pytest.raises(ValueError):
        catalogue.load_case(dataset, "h11")


def test_nested_asset_cannot_traverse_a_linked_directory(
    dataset: Path, tmp_path: Path
) -> None:
    directory = dataset / "cases/h11"
    outside = tmp_path / "outside"
    outside.mkdir()
    helper = outside / "helper.py"
    helper.write_text("pass\n")
    (directory / "nested").symlink_to(outside, target_is_directory=True)
    metadata = json.loads((directory / "case.json").read_text())
    metadata["asset_sha256"]["nested/helper.py"] = hashlib.sha256(
        helper.read_bytes()
    ).hexdigest()
    write_metadata(directory, metadata)
    with pytest.raises(ValueError):
        catalogue.load_case(dataset, "h11")


@pytest.mark.parametrize(
    "instance_id", ["", ".", "..", "../h11", "/h11", "h11/../sqlparse", "h11\\x"]
)
def test_case_selection_cannot_traverse_directories(
    dataset: Path, instance_id: str
) -> None:
    with pytest.raises(ValueError):
        catalogue.load_case(dataset, instance_id)


@pytest.mark.parametrize(
    "field,value",
    [
        ("instance_id", "UPPER_CASE"),
        ("instance_id", "h11/child"),
        ("instance_id", "h11\n"),
        ("repo", "https://github.com/python-hyper/h11"),
        ("repo", "../h11"),
        ("base_commit", "a" * 39),
        ("upstream_fix_commit", "A" * 40),
        ("advisory_ids", [""]),
        ("advisory_ids", ["CVE-2025"]),
        ("advisory_ids", ["GHSA-not-an-id"]),
        ("advisory_ids", ["CVE-2025-43859\n"]),
        ("advisory_ids", ["CVE-2025-43859", "CVE-2025-43859"]),
        ("schema_version", 2),
        ("platform", "linux/arm64"),
        ("expected_suite_cases", 0),
    ],
)
def test_metadata_rejects_invalid_ids_and_contract_values(
    dataset: Path, field: str, value: object
) -> None:
    directory = dataset / "cases/h11"
    metadata = json.loads((directory / "case.json").read_text())
    metadata[field] = value
    write_metadata(directory, metadata)
    with pytest.raises(ValueError):
        catalogue.load_case(dataset, "h11")


@pytest.mark.parametrize(
    "name", ["../outside.py", "/outside.py", "nested/../outside.py", ".hidden", "x\\y"]
)
def test_metadata_cannot_name_escaping_or_hidden_assets(
    dataset: Path, name: str
) -> None:
    directory = dataset / "cases/h11"
    metadata = json.loads((directory / "case.json").read_text())
    metadata["asset_sha256"][name] = "a" * 64
    write_metadata(directory, metadata)
    with pytest.raises(ValueError):
        catalogue.load_case(dataset, "h11")


def test_export_has_stable_keys_order_and_explicit_check_scope(dataset: Path) -> None:
    exported = catalogue.export_catalogue(dataset)
    assert exported == catalogue.export_catalogue(dataset)
    assert exported.endswith("\n") and not exported.endswith("\n\n")
    lines = exported.splitlines()
    rows = [json.loads(line) for line in lines]
    assert [row["instance_id"] for row in rows] == sorted(
        row["instance_id"] for row in rows
    )
    assert all(
        line == json.dumps(row, sort_keys=True)
        for line, row in zip(lines, rows, strict=True)
    )
    for row in rows:
        assert set(row) == {
            "instance_id",
            "repo",
            "base_commit",
            "problem_statement",
            "patch",
            "FAIL_TO_PASS",
            "PASS_TO_PASS",
            "seam",
        }
        case, directory = catalogue.load_case(dataset, row["instance_id"])
        config = load_config(directory / "harness.toml")
        assert row["repo"] == case.repo
        assert row["base_commit"] == case.base_commit
        assert row["problem_statement"] == case.problem_statement
        assert row["patch"] == (directory / "reference.patch").read_text()
        assert json.loads(row["FAIL_TO_PASS"]) == [
            f"oracle.py::{config.oracle.security_test}"
        ]
        assert json.loads(row["PASS_TO_PASS"]) == [
            f"oracle.py::{name}" for name in config.oracle.controls
        ]
        extension = row["seam"]
        assert extension["dataset_version"] == DATASET_VERSION
        assert extension["upstream_fix_commit"] == case.upstream_fix_commit
        assert extension["upstream_parent_commit"] == case.upstream_parent_commit
        assert extension["expected_suite_cases"] == case.expected_suite_cases
        assert extension["project_suite"] == list(config.runner.suite)
        assert extension["project_suite_markers"] == config.runner.suite_markers
        assert extension["asset_sha256"] == case.asset_sha256
        assert not {"status", "verified", "qualified"}.intersection(extension)
