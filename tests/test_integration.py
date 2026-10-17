"""Connect the real SDK protocol, Git adaptation, and real container verification."""

import hashlib
import json
import os
import shlex
from pathlib import Path

import httpx
import pytest
from openai import OpenAI

from seam.agent import DeepSeekPatchAgent, OpenAIPatchAgent
from seam.constants import DEFAULT_DEEPSEEK_MODEL, DEFAULT_MODEL
from seam.demo import DemoProject, create_demo
from seam.exceptions import AgentError
from seam.repository import git, parent
from seam.verification.workflow import run_backport


@pytest.fixture
def project(tmp_path: Path) -> DemoProject:
    image = os.environ.get("BACKPORT_TEST_IMAGE")
    if not image:
        pytest.skip("Set BACKPORT_TEST_IMAGE for the complete Docker backport flow")
    docker = tuple(shlex.split(os.environ.get("BACKPORT_TEST_DOCKER", "docker")))
    return create_demo(tmp_path / "project", image=image, docker=docker)


@pytest.mark.parametrize("provider", ["openai", "deepseek"])
def test_sdk_tools_adapt_conflict_and_real_verifier_accepts_patch(
    tmp_path: Path, project: DemoProject, provider: str
) -> None:
    base_url = (
        "https://api.deepseek.com"
        if provider == "deepseek"
        else "https://api.openai.com/v1"
    )
    model = DEFAULT_DEEPSEEK_MODEL if provider == "deepseek" else DEFAULT_MODEL
    patch = project.candidate_patch.read_text()
    calls = [
        ("list_files", {"directory": "src/parcel_paths"}),
        (
            "read_file",
            {"path": "src/parcel_paths/legacy.py", "start_line": 1, "line_count": 100},
        ),
        (
            "submit_patch",
            {"patch": patch, "explanation": "Preserve the old public API."},
        ),
    ]
    requests: list[dict[str, object]] = []

    def respond(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        requests.append(payload)
        assert str(request.url) == base_url + "/responses"
        assert "offline-test-credential" not in request.content.decode()
        name, arguments = calls[len(requests) - 1]
        return httpx.Response(
            200,
            json={
                "id": f"resp_{len(requests)}",
                "created_at": 1,
                "object": "response",
                "model": model,
                "status": "completed",
                "output": [
                    {
                        "type": "function_call",
                        "id": f"fc_{len(requests)}",
                        "call_id": f"call_{len(requests)}",
                        "name": name,
                        "arguments": json.dumps(arguments),
                        "status": "completed",
                    }
                ],
                "usage": {
                    "input_tokens": 200,
                    "output_tokens": 100,
                    "total_tokens": 300,
                },
            },
        )

    client = OpenAI(
        api_key="offline-test-credential",
        base_url=base_url,
        max_retries=0,
        http_client=httpx.Client(transport=httpx.MockTransport(respond)),
    )
    agent_type = DeepSeekPatchAgent if provider == "deepseek" else OpenAIPatchAgent
    agent = agent_type(api_key="offline-test-credential", client=client, budget_usd=1)
    original_status = git(project.repo, "status", "--porcelain")
    oracle = (project.config_path.parent / "oracle.py").read_bytes()
    try:
        report = run_backport(
            project.repo,
            project.fix,
            project.target,
            project.config_path,
            tmp_path / "result",
            proposer=agent,
        )
    finally:
        agent.close()
    assert report.status == "verified", report.model_dump()
    assert report.adaptation == "agent"
    assert report.attempts == 2
    assert report.model_usage["calls"] == 3
    assert report.patch_sha256 == hashlib.sha256(patch.encode()).hexdigest()
    assert report.oracle_sha256 == hashlib.sha256(oracle).hexdigest()
    assert git(project.repo, "status", "--porcelain") == original_status
    assert (project.config_path.parent / "oracle.py").read_bytes() == oracle
    assert "offline-test-credential" not in report.model_dump_json()
    assert [phase.name for phase in report.phases] == [
        "upstream_parent",
        "upstream_fix",
        "target_baseline",
        "backport",
    ]
    assert "legacy.py" in str(requests[1]["input"])


def test_clean_fix_is_applied_without_a_model(
    tmp_path: Path, project: DemoProject
) -> None:
    report = run_backport(
        project.repo,
        project.fix,
        parent(project.repo, project.fix),
        project.config_path,
        tmp_path / "direct",
    )
    assert report.status == "verified", report.model_dump()
    assert report.adaptation == "direct_application"
    assert report.attempts == 1
    assert report.model_usage == {}


def test_unavailable_provider_records_attempted_adaptation(
    tmp_path: Path, project: DemoProject
) -> None:
    class UnavailableAgent:
        @property
        def usage(self):
            return {"calls": 1}

        def propose(self, _context):
            raise AgentError("provider request failed")

    report = run_backport(
        project.repo,
        project.fix,
        project.target,
        project.config_path,
        tmp_path / "provider-failure",
        proposer=UnavailableAgent(),
    )
    assert report.status == "inconclusive"
    assert report.adaptation == "agent"
    assert report.attempts == 2
    assert report.model_usage == {"calls": 1}
    assert "provider request failed" in report.reason
    assert report.patch_sha256 is None
    assert not (tmp_path / "provider-failure" / "backport.patch").exists()
