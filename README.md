# Seam

A security backport harness for Python libraries.

An upstream security fix does not always fit an older release. Files move, APIs
change, and a clean-looking adaptation can silently break legitimate behavior.

This local CLI takes a fix commit and a maintained branch, prepares a backport in
disposable clones, and runs independent checks before calling it verified. An
optional AI agent can adapt a conflicting patch. The test results decide whether
the patch works.

Start with **Python libraries tested by pytest** and one ordinary fix commit.
This is useful for maintainers supporting multiple release lines and security
engineers reviewing a proposed backport.

The supported patch scope is Python implementation files. Fixes that also need
dependency, build, or other runtime changes are rejected rather than partially
ported. All selected commits and their history must be available in a full local
clone; fetch missing history before starting a run.

Use this with reviewed repositories and review the resulting patch. Executable
target code runs inside pytest and can interfere with its process or forge test
reports; this is not a tamper-resistant verifier for adversarial patches.

## Try it without an API key

Requirements: Linux, Python 3.12+, Git, Docker, and
[uv](https://docs.astral.sh/uv/getting-started/installation/).

```bash
uv sync --frozen
uv run backport doctor
uv run backport demo --output /tmp/backport-demo
uv run backport inspect --report /tmp/backport-demo/verification/report.json
```

The demo builds a Python + pytest image, then performs test execution with the
network disabled. If your Docker daemon requires a command prefix, pass
`--docker 'sudo -n docker'` to `doctor` and `demo`. To reuse an image that already
contains Python and pytest, pass `demo --image YOUR_IMAGE`.

The synthetic library has an archive path traversal bug. Its upstream fix uses a
new API; the maintained branch still uses the old API and a different source
file, so the fix requires adaptation. The demo supplies a reference adaptation
and verifies it without contacting a model. It is **not a published CVE** and
does not demonstrate AI patch generation.

## What verification establishes

The same trusted external pytest oracle is run against four revisions:

| Revision | Security regression | Legitimate controls and project suite |
| --- | --- | --- |
| Upstream fix's parent | Fails with the expected assertion marker | Pass |
| Upstream fix | Passes | Pass |
| Maintained branch before adaptation | Fails with the expected marker | Pass |
| Maintained branch with backport | Passes | Pass |

The oracle lives outside the target repository. Its hash and the runner
configuration hash are frozen before adaptation. The model cannot replace the
mounted oracle or set the report status directly. These checks assume reviewed
target code cooperates with pytest, as described above. A patch that rejects
every request fails legitimate-behavior controls.

- `verified` means the recorded matrix and compatibility checks passed.
- `failed` means collected checks rejected the proposed fix or its behavior.
- `inconclusive` means evidence is missing or unsuitable: an unavailable image,
  setup error, timeout, skipped test, or a regression that did not reproduce for
  the expected reason.

Verification covers the recorded checks; it is not a claim that a release has no
other vulnerabilities. `run` and `demo` exit codes are `0`, `1`, and `2`,
respectively. `inspect` succeeds when it can read a valid report, regardless of
the recorded verification status.

## Use your own repository

First prepare a trusted image containing the target release's Python runtime,
pytest, and dependencies. The harness does not install repository dependencies
or fetch anything during tests. Choose an image compatible with **both** the
upstream and maintained revisions.

Write a trusted external oracle with one security test and one or more normal
behavior controls. The security test must fail on vulnerable revisions with a
distinct assertion marker. See [the oracle guide](docs/oracles.md).

Create an explicit `harness.toml` outside the target checkout:

```toml
schema_version = 1
max_attempts = 3

[oracle]
path = "oracle.py" # relative to this configuration file
security_test = "test_security_regression"
controls = ["test_ordinary_request"]
failure_marker = "EXPECTED_SECURITY_REGRESSION"

[runner]
image = "my-project-tests:local"
docker = ["docker"]
suite = ["tests"]
timeout_seconds = 120
memory_mb = 512
cpus = 1
pids = 128
```

Then try the original fix, or supply an adapted patch:

```bash
uv run backport run \
  --repo /path/to/library --fix FIX_COMMIT --target release/1.x \
  --config /path/to/harness.toml --output /tmp/backport-result

uv run backport run \
  --repo /path/to/library --fix FIX_COMMIT --target release/1.x \
  --config /path/to/harness.toml --output /tmp/backport-candidate \
  --candidate-patch /path/to/adapted.patch
```

Use a new output directory for every run. The original checkout is preserved.
An incompatible fix without a candidate or configured agent produces an
inconclusive report.

## Enable AI adaptation explicitly

The agent uses the official OpenAI Python SDK and Responses API. Ordinary runs
and the demo do not construct a model client. A paid run requires `--model`:

```bash
# Store the key locally; do not paste it into chat or commit it.
# .env contains only: OPENAI_API_KEY=your-value
chmod 600 .env

uv run backport run \
  --repo /path/to/library --fix FIX_COMMIT --target release/1.x \
  --config /path/to/harness.toml --output /tmp/backport-ai \
  --model gpt-5.4-mini-2026-03-17 --api-budget-usd 1 --env-file .env
```

`OPENAI_API_KEY` in the controller environment also works. Credential files are
read only when explicitly selected; the harness never discovers a repository's
`.env`. The key stays in the controller and is not forwarded into test containers.

The local budget accounts for known model prices and reserves the model's full
input context plus the permitted output before each request. Unknown models are
rejected. The CLI
allows a maximum of US$10 per run. This is separate from the provider dashboard's
spend alerts, which do not stop requests. Keep a dedicated project key and
monitor account usage. See [API operation](docs/api.md) for limits.

## Review the output

The run directory contains a structured `report.json`, a readable `report.md`,
frozen verification inputs, and the candidate patch when available. The JSON
records immutable revision IDs,
image identity, input hashes, each test outcome, the adaptation method, and any
model usage. Inspect those results and the patch before applying it to your
maintained branch. Nothing is pushed or merged.

```bash
uv run backport inspect --report /tmp/backport-result/report.json --json
```

## Engineering and boundaries

The implementation uses typed Python, Pydantic input validation, Typer, direct
Git subprocesses, and a small explicit verification state machine. Model tools
can list and read permitted source files and submit a unified diff. They cannot
execute host shell commands. Target tests run in restricted disposable Docker
containers with no network, API keys, host Docker socket, or writable original
checkout.

Docker shares the host kernel. Run truly hostile repositories on a dedicated
machine or VM; container restrictions do not provide a complete hostile-code
sandbox. An oracle and the selected image are trusted operator inputs. The
harness does not prove that an oracle is comprehensive or prevent a deliberately
malicious patch from detecting its test environment or falsifying pytest output.
See the
[threat model](docs/security.md) and [architecture](docs/architecture.md).

```bash
uv run ruff check .
uv run ruff format --check .
uv run mypy
uv run pytest
uv build
```

After the demo builds its image, exercise the complete SDK protocol, Git
adaptation, and container lifecycle without contacting an API:

```bash
BACKPORT_TEST_IMAGE=security-backport-demo:local \
  uv run pytest -q tests/test_integration.py tests/test_runner.py
```

For a prefixed Docker command, also set `BACKPORT_TEST_DOCKER='sudo -n docker'`.
An optional privileged-client cleanup test is enabled by `BACKPORT_TEST_SUDO=1`;
the ordinary tests need no sudo access.

CI runs these checks, validates the installed wheel, and executes the keyless
Docker demo. Coding conventions and primary references are in
[AGENTS.md](AGENTS.md). Licensed under [MIT](LICENSE).

For a public vulnerability rather than the synthetic exercise, see the
[Jinja xmlattr example](examples/jinja-xmlattr/README.md), which reproduces
CVE-2024-22195 and verifies a backport to an older release.
