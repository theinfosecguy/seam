# Seam

A security backport harness for Python libraries tested with pytest.

Maintainers often need an upstream security fix on an older release where APIs
or files have changed. Seam prepares the backport in disposable clones, then
checks the vulnerability and existing behavior before calling the patch verified.
It can apply a fix directly, check your patch, or ask an AI model to adapt it.
Fixes must change Python implementation files; package data, dependency updates,
build scripts, and native-code changes are outside the current scope.

## Contents

- [Try it without an API key](#try-it-without-an-api-key)
- [Use your own repository](#use-your-own-repository)
- [Optional AI adaptation](#optional-ai-adaptation)
- [What verification means](#what-verification-means)
- [Development](#development)
- [Documentation](#documentation)

## Try it without an API key

You need Linux, Python 3.12+, Git, Docker, and
[uv](https://docs.astral.sh/uv/getting-started/installation/).

```bash
uv sync --frozen
uv run seam doctor
uv run seam demo --output /tmp/seam-demo
uv run seam inspect --report /tmp/seam-demo/verification/report.json
```

The demo verifies a supplied reference patch for a synthetic archive traversal
bug; it does not generate a patch with AI or reproduce a published CVE.
The image build needs network access; test execution has networking disabled.
For Docker command prefixes or an existing image, see [usage](docs/usage.md#demo).
If you prefer pip, use the [virtualenv installation](docs/usage.md#installation).

## Use your own repository

Prepare a trusted test image and an external pytest regression test, then write a
small configuration file. The [setup guide](docs/usage.md#prepare-a-repository)
shows the complete configuration and requirements.

```bash
uv run seam run \
  --repo /path/to/library --fix FIX_COMMIT --target release/1.x \
  --config /path/to/harness.toml --output /tmp/seam-result
```

Use a new output directory for each run. Review its `report.md` and
`backport.patch` before applying it. Seam preserves your checkout and never
pushes or merges.
To check an existing adaptation, add `--candidate-patch /path/to/adapted.patch`.

## Optional AI adaptation

Store `DEEPSEEK_API_KEY=your-value` in an ignored local `.env.deepseek` file, then:

```bash
chmod 600 .env.deepseek
uv run seam run \
  --repo /path/to/library --fix FIX_COMMIT --target release/1.x \
  --config /path/to/harness.toml --output /tmp/seam-ai \
  --provider deepseek --model deepseek-flash \
  --api-budget-usd 1 --env-file .env.deepseek
```

A paid client is created only when you supply `--model`. OpenAI and DeepSeek are
supported; keys stay in the controller, outside test containers. See
[API setup](docs/api.md) for models, credentials, and spending limits.

## What verification means

The same external security test runs against four revisions:

| Revision | Security regression | Normal behavior and project suite |
| --- | --- | --- |
| Upstream fix's parent | Expected failure | Pass |
| Upstream fix | Pass | Pass |
| Maintained branch | Expected failure | Pass |
| Maintained branch with backport | Pass | Pass |

`verified` means these checks passed, with the target's existing suite cases
preserved. `failed` means the checks rejected the candidate. `inconclusive` means
usable evidence is missing, such as a setup failure, timeout, or skipped test.

Use reviewed Python code, a trusted oracle, and a trusted image. Target code runs
inside pytest and can forge test output; this is not a tamper-proof verifier.
Passing checks cover the recorded behavior, not every possible vulnerability.
Read the [security boundaries](docs/security.md) before testing unfamiliar code.

A [recorded live Flash run](docs/live-testing.md) backported Jinja's
CVE-2024-22195 fix while preserving all 120 target filter tests. That record also
includes unsuccessful Pro runs and the limits of the evidence.

## Development

```bash
uv run ruff check .
uv run ruff format --check .
uv run mypy
uv run pytest
uv build
```

See [coding conventions](AGENTS.md), the [package map](docs/architecture.md), and
[Docker integration checks](docs/usage.md#development-checks).

## Documentation

- [Usage and configuration](docs/usage.md)
- [Writing the security test and controls](docs/oracles.md)
- [API-backed adaptation](docs/api.md)
- [Real Jinja backport example](examples/jinja-xmlattr/README.md)
- [Live validation results](docs/live-testing.md)
- [Multi-library evaluation and gaps](docs/evaluations.md)

Licensed under [MIT](LICENSE).
