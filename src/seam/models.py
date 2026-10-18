"""Define validated inputs and serializable evidence shared by the harness."""

import re
from dataclasses import dataclass, field
from decimal import Decimal
from enum import StrEnum
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from seam.constants.verification import (
    MAX_PYTEST_MARKER_EXPRESSION,
    MAX_PYTEST_PLUGIN_NAME,
    MAX_PYTEST_PLUGINS,
)


class ModelProvider(StrEnum):
    """Limit paid adaptation to explicitly supported provider endpoints."""

    OPENAI = "openai"
    DEEPSEEK = "deepseek"
    ANTHROPIC = "anthropic"
    GOOGLE = "google"
    XAI = "xai"
    MISTRAL = "mistral"
    GROQ = "groq"
    OPENROUTER = "openrouter"
    TOGETHER = "together"
    AZURE = "azure"
    BEDROCK = "bedrock"
    VERTEX = "vertex"


@dataclass(frozen=True)
class ModelPrice:
    """Standard text rates and the full documented model context ceiling."""

    input_per_million: Decimal
    output_per_million: Decimal
    context_tokens: int


@dataclass(frozen=True, kw_only=True)
class ProviderOptions:
    """Explicit cloud routing and authentication supplied only by the operator."""

    azure_endpoint: str | None = None
    azure_api_version: str | None = None
    aws_region: str | None = None
    aws_access_key_id: str | None = field(default=None, repr=False)
    aws_secret_access_key: str | None = field(default=None, repr=False)
    aws_session_token: str | None = field(default=None, repr=False)
    google_project: str | None = None
    google_location: str | None = None
    google_credentials_path: Path | None = None


class Record(BaseModel):
    """Reject unknown fields instead of silently ignoring configuration mistakes."""

    model_config = ConfigDict(extra="forbid")


class OracleConfig(Record):
    """Identify a trusted external pytest file and its expected regression."""

    path: Path
    security_test: str = Field(pattern=r"^test_[A-Za-z0-9_]+$")
    controls: tuple[str, ...] = Field(min_length=1)
    failure_marker: str = Field(min_length=8, max_length=200)

    @field_validator("controls")
    @classmethod
    def valid_controls(cls, names: tuple[str, ...]) -> tuple[str, ...]:
        if len(set(names)) != len(names) or any(
            not re.fullmatch(r"test_[A-Za-z0-9_]+", name) for name in names
        ):
            raise ValueError("controls must be unique pytest function names")
        return names


class RunnerConfig(Record):
    """Bound container execution using an operator-selected image."""

    image: str = Field(min_length=1)
    docker: tuple[str, ...] = ("docker",)
    timeout_seconds: float = Field(default=120, gt=0, le=3600)
    memory_mb: int = Field(default=512, ge=64, le=16384)
    cpus: float = Field(default=1, gt=0, le=8)
    pids: int = Field(default=128, ge=16, le=1024)
    max_output_bytes: int = Field(default=131072, ge=1024, le=1048576)
    suite: tuple[str, ...] = ("tests",)
    plugins: tuple[str, ...] = ()
    import_mode: Literal["importlib", "prepend", "append"] = "importlib"
    suite_markers: str | None = None

    @field_validator("plugins")
    @classmethod
    def valid_plugins(cls, modules: tuple[str, ...]) -> tuple[str, ...]:
        if (
            len(modules) > MAX_PYTEST_PLUGINS
            or len(set(modules)) != len(modules)
            or any(
                len(module) > MAX_PYTEST_PLUGIN_NAME
                or not re.fullmatch(
                    r"[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*", module
                )
                for module in modules
            )
        ):
            raise ValueError("plugins must be unique dotted Python module names")
        return modules

    @field_validator("suite_markers")
    @classmethod
    def valid_suite_markers(cls, expression: str | None) -> str | None:
        if expression is not None and (
            not expression.strip()
            or len(expression) > MAX_PYTEST_MARKER_EXPRESSION
            or not re.fullmatch(r"[A-Za-z0-9_(). \t]+", expression)
        ):
            raise ValueError("suite_markers must be a pytest boolean marker expression")
        return expression

    @field_validator("docker", "suite")
    @classmethod
    def nonempty_arguments(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        if not values or any(not value or "\x00" in value for value in values):
            raise ValueError("command arguments must be nonempty")
        return values


class HarnessConfig(Record):
    """Load explicit trusted configuration; repository config is never discovered."""

    schema_version: Literal[1] = 1
    oracle: OracleConfig
    runner: RunnerConfig
    max_attempts: int = Field(default=3, ge=1, le=5)


class ProcessResult(Record):
    """Record bounded process output and termination conditions."""

    returncode: int
    command: list[str] = Field(default_factory=list)
    stdout: str = ""
    stderr: str = ""
    timed_out: bool = False
    truncated: bool = False
    duration_seconds: float = 0


class TestCaseResult(Record):
    """Record one pytest result from a JUnit report."""

    name: str
    classname: str = ""
    outcome: Literal["passed", "failed", "error", "skipped"]
    message: str = ""
    expected_failure: bool = False

    @model_validator(mode="after")
    def valid_expected_failure(self) -> "TestCaseResult":
        """Keep pytest expected failures classified as incomplete evidence."""
        if self.expected_failure and self.outcome != "skipped":
            raise ValueError("expected failures must have a skipped outcome")
        return self


class ExecutionResult(ProcessResult):
    """Add parsed test evidence to a container execution result."""

    tests: list[TestCaseResult] = Field(default_factory=list)
    evidence_error: str | None = None


PhaseName = Literal["upstream_parent", "upstream_fix", "target_baseline", "backport"]


class PhaseResult(Record):
    """Preserve independent security and compatibility checks for a revision."""

    name: PhaseName
    revision: str
    security: ExecutionResult
    suite: ExecutionResult


class AgentContext(Record):
    """Give a patch proposer read access to a disposable target checkout."""

    workspace: Path
    upstream_diff: str
    feedback: str = ""


class AgentProposal(Record):
    """Return a candidate diff; the model cannot execute host commands."""

    patch: str = Field(min_length=1, max_length=262144)
    explanation: str = Field(max_length=4000)


class RunReport(Record):
    """Describe exactly what a backport run established and where it stopped."""

    schema_version: Literal[1, 2] = 2
    status: Literal["verified", "failed", "inconclusive"]
    reason: str
    fix_commit: str | None = None
    parent_commit: str | None = None
    target_commit: str | None = None
    image_id: str | None = None
    oracle_sha256: str | None = None
    config_sha256: str | None = None
    patch_sha256: str | None = None
    phases: list[PhaseResult] = Field(default_factory=list)
    attempts: int = 0
    adaptation: str = "none"
    model_usage: dict[str, int | float | str] = Field(default_factory=dict)

    @model_validator(mode="after")
    def verified_evidence_complete(self) -> "RunReport":
        """Reject a verified verdict without the completed evidence matrix."""
        if self.status == "verified" and (
            not all(
                (
                    self.fix_commit,
                    self.parent_commit,
                    self.target_commit,
                    self.image_id,
                    self.oracle_sha256,
                    self.config_sha256,
                    self.patch_sha256,
                )
            )
            or {phase.name for phase in self.phases}
            != {"upstream_parent", "upstream_fix", "target_baseline", "backport"}
            or self.phases[-1].name != "backport"
        ):
            raise ValueError(
                "verified reports require provenance, patch, and four phases"
            )
        return self
