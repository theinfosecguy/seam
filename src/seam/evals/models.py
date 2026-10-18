"""Validate immutable revisions and assets in public evaluation cases."""

import re
from pathlib import PurePosixPath
from typing import Literal

from pydantic import Field, field_validator

from seam.constants.evals import REQUIRED_EVAL_ASSETS
from seam.models import Record


def valid_asset_path(name: str) -> bool:
    """Accept exact portable paths, allowing the recipe's explicit ignore file."""
    path = PurePosixPath(name)
    return bool(name) and not (
        path.is_absolute()
        or path.as_posix() != name
        or ".." in path.parts
        or (
            name != ".dockerignore" and any(part.startswith(".") for part in path.parts)
        )
        or "\\" in name
        or "\ufffd" in name
        or any(ord(character) < 32 or ord(character) == 127 for character in name)
    )


class EvalCase(Record):
    """Describe a backport task independently of a method's observed results."""

    schema_version: Literal[1] = 1
    instance_id: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{0,79}$")
    repo: str = Field(
        pattern=r"^[A-Za-z0-9_-][A-Za-z0-9_.-]*/[A-Za-z0-9_-][A-Za-z0-9_.-]*$",
        max_length=200,
    )
    base_commit: str = Field(pattern=r"^[a-f0-9]{40}$")
    upstream_parent_commit: str = Field(pattern=r"^[a-f0-9]{40}$")
    upstream_fix_commit: str = Field(pattern=r"^[a-f0-9]{40}$")
    advisory_ids: list[str] = Field(min_length=1, max_length=16)
    problem_statement: str = Field(min_length=10, max_length=8000)
    target_version: str = Field(min_length=1, max_length=100)
    platform: Literal["linux/amd64"] = "linux/amd64"
    expected_suite_cases: int = Field(ge=1, le=100_000)
    upstream_license: str = Field(min_length=1, max_length=100)
    notes: list[str] = Field(default_factory=list, max_length=32)
    asset_sha256: dict[str, str] = Field(max_length=64)

    @field_validator("advisory_ids")
    @classmethod
    def valid_advisories(cls, values: list[str]) -> list[str]:
        if len(set(values)) != len(values) or any(
            re.fullmatch(
                r"CVE-[0-9]{4}-[0-9]{4,}|GHSA-[a-z0-9]{4}-[a-z0-9]{4}-[a-z0-9]{4}",
                value,
            )
            is None
            for value in values
        ):
            raise ValueError("advisories must be unique CVE or GHSA identifiers")
        return values

    @field_validator("asset_sha256")
    @classmethod
    def valid_assets(cls, assets: dict[str, str]) -> dict[str, str]:
        if not REQUIRED_EVAL_ASSETS.issubset(assets):
            raise ValueError("evaluation case is missing required assets")
        for name, digest in assets.items():
            if (
                not valid_asset_path(name)
                or name == "case.json"
                or re.fullmatch(r"[a-f0-9]{64}", digest) is None
            ):
                raise ValueError(
                    "evaluation assets require exact relative paths and SHA-256 hashes"
                )
        return assets
