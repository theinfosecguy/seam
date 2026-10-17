# Usage and configuration

Seam handles one ordinary upstream fix commit and one maintained release at a
time. The initial scope is Python libraries tested by pytest, with patches to
Python implementation files. A fix changing package data (including certificate
bundles), dependencies, native code, build files, or extensionless scripts is
rejected. Test and documentation changes are excluded from the upstream patch;
candidate patches may not change tests or documentation.

## Installation

The controller needs Linux, Python 3.12+, Git, and Docker. From this checkout:

```bash
uv sync --frozen
uv run seam doctor
```

Or install in a virtual environment without uv:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install .
.venv/bin/seam doctor
```

Target interpreters and test dependencies live in the trusted Docker image and
can differ from the controller. If your Docker socket needs a command prefix,
use `seam doctor --docker 'sudo -n docker'` and the equivalent runner configuration.

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
   before running Seam. Inspect the fix before preparing its environment:

   ```bash
   git -C /path/to/library show --no-patch --format='%H %P' FIX_COMMIT
   git -C /path/to/library diff --name-status FIX_COMMIT^ FIX_COMMIT
   ```

   The fix must have one parent. An advisory may link a merge commit; inspect its
   parents and select the ordinary implementation commit. Unsupported changed
   files stop the run even when a supplied candidate omits them.
2. Build or select a trusted image containing Python, pytest, and the target's
   dependencies. It must support both upstream and maintained revisions. Seam
   does not install dependencies or fetch anything during test execution. See
   [test images](#test-images) for an example and plugin configuration.
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
plugins = []
import_mode = "importlib"
timeout_seconds = 120
memory_mb = 512
cpus = 1
pids = 128
```

The suite should cover the relevant existing behavior. Baseline and backport
must collect the same suite case identities. The oracle, runner configuration,
and image are trusted operator inputs; they are frozen before adaptation.

Seam preflights all three clean revisions before preparing the image or running
tests. Relative file symlinks are materialized when their final target is a
contained ordinary file. Directory links, absolute or escaping links, cycles,
hard links, and links into excluded paths are rejected with the offending path.
Snapshots retain file, byte, nesting, and link-chain limits. Credential-like
paths and certificate/key files are excluded; keep secrets outside the checkout.

## Test images

The smallest image has Python, pytest, and every dependency imported by the
selected tests or their `conftest.py`. For example:

```dockerfile
FROM python:3.11-slim
RUN python -m pip install --no-cache-dir pytest==7.4.4
# Install this library's runtime and test dependencies here.
```

```bash
docker build -t my-project-tests:local /path/to/image-context
```

Choose versions supported by both revisions. Pytest 7.4.4 worked for several
historical evaluation cases; it is not a universal requirement. Existing suites
can depend on old interpreter behavior, warning filters, optional native
extensions, and framework initialization. Supply those in the image without
replacing the implementation under test with an installed library release.
Native extensions must be available from executable image storage rather than
copied onto the source tmpfs. The image identity is recorded in the evidence.

Plugin autoload is disabled and inherited `PYTEST_PLUGINS` and `PYTEST_ADDOPTS`
are cleared. Install needed plugins in the image and select their importable
module names explicitly:

```toml
[runner]
image = "my-project-tests:local"
plugins = ["anyio.pytest_plugin"] # or pytest_django.plugin, pytest_asyncio.plugin
suite = ["tests/test_staticfiles.py"]
```

Do not register the same plugin again through image/project `addopts`. The list
is trusted configuration, applied to every phase and included in the frozen
configuration hash. Framework settings still belong in the trusted image or
project's normal pytest configuration. See
[pytest plugin loading](https://docs.pytest.org/en/stable/how-to/plugins.html).

If package downloads inside Docker fail, download wheels on the host and build
offline. Pin the complete dependency set for the chosen target interpreter:

```bash
python3 -m pip download --dest image/wheels --python-version 3.11 \
  --only-binary=:all: pytest==7.4.4 YOUR_PINNED_DEPENDENCIES
docker build --network none -t my-project-tests:local image
```

The corresponding Dockerfile replaces its network install with:

```dockerfile
COPY wheels /wheels
RUN python -m pip install --no-index --find-links=/wheels \
    pytest==7.4.4 YOUR_PINNED_DEPENDENCIES
```

Replace `YOUR_PINNED_DEPENDENCIES` with the actual pinned packages. Wheels must
match the image's Python version, ABI and platform. Image construction can use
networking; verification containers always run with networking disabled.

## Select the existing suite

`runner.suite` accepts relative paths and pytest node IDs, such as
`tests/test_http.py::TestHeaders`. It does not accept pytest command-line options.
For an older suite whose package-relative imports need pytest's traditional
behavior, set `import_mode = "prepend"` (or `"append"`). The default is
`"importlib"`; it applies consistently to oracle and suite runs. See
[pytest import modes](https://docs.pytest.org/en/stable/explanation/pythonpath.html).

A trusted marker expression can narrow only the existing suite:

```toml
[runner]
image = "my-project-tests:local"
suite = ["tests"]
suite_markers = "not xfail"
```

This replaces long positive selector lists for suites with marked expected
failures. It excludes every matching marked case, including any that might pass;
review the selection and coverage loss. The same filter applies to all four
revisions and is frozen before adaptation. The external security regression and
controls are always selected explicitly and are unaffected by suite markers.

Selected skips and expected failures remain inconclusive evidence. Reports label
pytest xfails separately without treating them as passes. Baseline and backport
must collect the same selected suite identities, and every selected case must
pass. Marker filtering does not authorize missing or skipped security tests.

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
The canonical patch is `backport.patch`; the command prints its absolute path.
CLI and Markdown summaries separate oracle and suite counts and include bounded
error excerpts when checks fail.

```bash
uv run seam inspect --report /tmp/seam-result/report.json
uv run seam inspect --report /tmp/seam-result/report.json --json
```

| `run` and `demo` status | Exit code | Meaning |
| --- | --- | --- |
| `verified` | `0` | The recorded security, control, and compatibility checks passed. |
| `failed` | `1` | Collected checks rejected the proposed fix or its behavior. |
| `inconclusive` | `2` | Evidence is missing or unsuitable. |

Repository, fix, configuration, candidate, image, and test setup failures also
exit with `2` and leave an inconclusive report once a usable output directory
has been selected. Unavailable provenance fields are `null`. CLI usage and
credential errors, unsafe output paths, and nonempty output directories are
rejected before verification and may not create a report. Reports use schema
version 2; `inspect` also accepts historical version 1 reports.

`inspect` exits successfully when it reads a
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
