# Usage and configuration

Seam handles one ordinary upstream fix commit and one maintained release at a
time. The initial scope is Python libraries tested by pytest, with patches to
Python implementation files. A fix requiring dependency, build, or other runtime
changes is rejected rather than partially ported.

## Demo

The keyless demo creates a synthetic archive traversal vulnerability, divergent
release history, a trusted oracle, and a reference adaptation. It verifies that
adaptation without contacting a model.

```bash
uv sync --frozen
uv run seam doctor
uv run seam demo --output /tmp/seam-demo
uv run seam inspect --report /tmp/seam-demo/verification/report.json
```

The demo builds a Python + pytest image, then runs tests with networking disabled.
If your Docker daemon requires a command prefix, pass
`--docker 'sudo -n docker'` to `doctor` and `demo`. To reuse an image containing
Python and pytest, pass `demo --image YOUR_IMAGE`.

## Prepare a repository

1. Use a full local Git clone. Fetch all selected commits and their history
   before running Seam.
2. Build or select a trusted image containing Python, pytest, and the target's
   dependencies. It must support both upstream and maintained revisions. Seam
   does not install dependencies or fetch anything during test execution.
3. Write an external oracle with one security regression and one or more
   normal-behavior controls. The regression must fail on vulnerable revisions
   with a distinct assertion marker. Follow the [oracle guide](oracles.md).
4. Keep the oracle and explicit `harness.toml` outside the target checkout.

A minimal configuration:

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

The suite should cover the relevant existing behavior. Baseline and backport
must collect the same suite case identities. The oracle, runner configuration,
and image are trusted operator inputs; they are frozen before adaptation.

## Run a backport

Try the upstream fix directly:

```bash
uv run seam run \
  --repo /path/to/library --fix FIX_COMMIT --target release/1.x \
  --config /path/to/harness.toml --output /tmp/seam-result
```

If the fix does not fit the maintained release, provide your adaptation:

```bash
uv run seam run \
  --repo /path/to/library --fix FIX_COMMIT --target release/1.x \
  --config /path/to/harness.toml --output /tmp/seam-candidate \
  --candidate-patch /path/to/adapted.patch
```

An incompatible fix without a supplied candidate or configured agent produces an
inconclusive report. For model adaptation, select `--model` instead of
`--candidate-patch`; see [API operation](api.md). The two options cannot be combined.
Use a new output directory for every run. The original checkout is preserved.

## Read the results

The output directory contains `report.json`, `report.md`, frozen verification
inputs, raw candidate attempts, and a canonical candidate patch when available.
The JSON records immutable revision IDs, image identity, input hashes, test
outcomes, adaptation method, and any model usage. Review the patch and evidence
before applying it to the maintained branch.

```bash
uv run seam inspect --report /tmp/seam-result/report.json
uv run seam inspect --report /tmp/seam-result/report.json --json
```

| `run` and `demo` status | Exit code | Meaning |
| --- | --- | --- |
| `verified` | `0` | The recorded security, control, and compatibility checks passed. |
| `failed` | `1` | Collected checks rejected the proposed fix or its behavior. |
| `inconclusive` | `2` | Evidence is missing or unsuitable. |

Setup errors also exit with `2`. `inspect` exits successfully when it reads a
valid report, regardless of the recorded verification status. Timeouts, skipped
tests, malformed reports, missing checks, or a baseline that does not reproduce
the expected failure cannot establish a verified backport. Passing checks do not
establish that a release has no other vulnerabilities.

## Development checks

```bash
uv run ruff check .
uv run ruff format --check .
uv run mypy
uv run pytest
uv build
```

After the demo builds its image, exercise the SDK protocol, Git adaptation, and
container lifecycle without contacting an API:

```bash
BACKPORT_TEST_IMAGE=security-backport-demo:local \
  uv run pytest -q tests/test_integration.py tests/execution tests/verification/test_junit.py
```

For a prefixed Docker command, also set `BACKPORT_TEST_DOCKER='sudo -n docker'`.
An optional privileged-client cleanup test uses `BACKPORT_TEST_SUDO=1`; ordinary
tests need no sudo access. CI also validates the installed wheel and executes the
keyless Docker demo. The [architecture guide](architecture.md) maps package
responsibilities and the [coding conventions](../AGENTS.md) describe required
checks.
