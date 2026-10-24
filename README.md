# Seam

Backport security fixes to older releases, with test evidence you can review.

An upstream security patch does not always apply cleanly to a maintained release.
Seam helps adapt it, checks that it fixes the vulnerability, and runs the relevant
existing tests to catch regressions. You get a patch and a report explaining what
passed, failed, or could not be checked.

Seam currently supports **Python libraries tested with pytest**. You can ask an
AI model to adapt a fix, apply the upstream patch unchanged, or check a patch you
have already written. It works in disposable copies of your repository and never
pushes or merges changes.

## Try it without an API key

You need Linux, Python 3.12+, Git 2.38+, Docker, and
[uv](https://docs.astral.sh/uv/getting-started/installation/).
From a checkout of this repository:

```bash
uv sync --frozen
uv run --frozen seam doctor
uv run seam demo --output /tmp/seam-demo
uv run seam inspect --report /tmp/seam-demo/verification/report.json
```

The demo checks a supplied patch for a small synthetic vulnerability. It builds
a test image, then runs the tests without network access or model API calls.
Use a fresh output directory each time. For pip installation or Docker setup,
see the [setup guide](docs/usage.md#installation).

## Backport a fix

Start with an upstream fix commit, the older release you maintain, and a test
that reproduces the security issue. The [setup guide](docs/usage.md#prepare-a-repository)
walks through preparing that test, the test environment, and `harness.toml`.

To try the upstream patch unchanged:

```bash
uv run seam run \
  --repo /path/to/library --fix FIX_COMMIT --target release/1.x \
  --config /path/to/harness.toml --output /tmp/seam-result \
  --direct
```

To check your own adaptation, replace `--direct` with
`--candidate-patch /path/to/adapted.patch`. For AI-assisted adaptation, follow
the [API setup guide](docs/api.md) to choose a model, supply a key, and set a
spending limit.

Review `report.md` and `backport.patch` in the output directory before applying
the change. Seam handles Python implementation changes; fixes to dependencies,
build scripts, package data, or native code are outside its current scope.

## What does “verified” mean?

Seam checks the same security test before and after the upstream fix, then
before and after the proposed backport. The test must expose the vulnerability
on both unfixed revisions and pass on both fixed revisions. Normal-behavior
checks and the selected existing project tests must also pass.

- **Verified:** the patch passed these recorded checks.
- **Failed:** the checks rejected the proposed patch.
- **Inconclusive:** setup problems, skipped tests, timeouts, or missing evidence
  prevented a decision.

A verified result covers the tests you chose, not every possible security issue.
Use reviewed source, a trusted test environment, and an independently reviewed
security test. See the [security boundaries](docs/security.md) before running
unfamiliar code.

## Evaluations

The [public evaluation collection](evals/README.md) contains reproducible cases
with pinned revisions, security tests, selected project tests, and reference
patches. Try one without an API key:

```bash
uv run seam eval qualify jinja2 --build-image --output /tmp/seam-jinja2-eval
```

This checks the supplied reference patch and a deliberately ineffective patch;
it does not measure an AI model. See the [case catalogue](evals/python/README.md),
[recent backport comparison](docs/recent-backports.md), and
[earlier evaluations](docs/evaluations.md) for results and their limits.

## More information

- [Next: JavaScript and npm](docs/roadmap.md)
- [Usage and configuration](docs/usage.md)
- [Writing security tests and controls](docs/oracles.md)
- [Models, API keys, and spending limits](docs/api.md)
- [Real Jinja backport example](examples/jinja-xmlattr/README.md)
- [Development checks](docs/usage.md#development-checks) and
  [project architecture](docs/architecture.md)

Licensed under [MIT](LICENSE).
