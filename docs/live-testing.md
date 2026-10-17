# Recorded live DeepSeek validation

On 17 October 2026, Seam was exercised with real DeepSeek API requests and the
Docker verifier. These are individual executions, not a model benchmark or a
guarantee that another generation will succeed.

## Results

| Case | Model | Result |
| --- | --- | --- |
| Synthetic archive traversal backport | `deepseek-flash` | Verified live adaptation; 5 API calls |
| Jinja CVE-2024-22195 backport to 3.0.3 | `deepseek-flash` | Verified live adaptation; 3 API calls |
| Jinja backport, fresh Pro run | `deepseek-v4-pro` | Inconclusive; reached the 16-call ceiling |
| Earlier Pro-generated Jinja patch | `deepseek-v4-pro` | Verified in an offline replay after deterministic hunk recounting |

The successful Flash Jinja run used 6,635 input and 3,006 output tokens. Its local
peak, uncached cost estimate was US$0.0055977. This is a conservative estimate,
not an account invoice. The operator explicitly disabled the dollar cap; call,
token, execution, and patch-attempt limits remained active.

The successful Jinja execution established the complete frozen matrix:

| Revision | External security checks | Existing filter suite |
| --- | --- | --- |
| Upstream parent | Expected regression failure; 3 controls pass | 124 pass |
| Upstream fix | Regression and 3 controls pass | 125 pass |
| Target 3.0.3 | Expected regression failure; 3 controls pass | 120 pass |
| Flash-generated backport | Regression and 3 controls pass | Same 120 cases pass |

The fix is `7dd3680e6eea0d77fde024763657aa4d884ddb23`; the target is
`2a48dd898d72f1a119ee923996e70aa43da04ea4`. The canonical Flash patch's SHA-256 is
`92a0f0d8b415f165275235d49dfc42656a57c9254ddda6fe5172ba663d49bbb9`.
See the [Jinja example](../examples/jinja-xmlattr/README.md) for the oracle's
scope and the upstream advisory. The recorded target is a historical exercise.

## Issues exposed by live execution

- Thinking mode rejected forced tool selection. DeepSeek requests now use
  automatic selection; a valid local `submit_patch` call is still required.
- Generated hunk lengths were sometimes wrong. Git recounts them while retaining
  context, path, mode, and whitespace checks. The exported patch is a canonical
  diff of the actual tested changes and applies with ordinary `git apply`.
- A model sometimes combined reading and submission in one batch. The controller
  rejects that entire batch, returns errors for every call, and allows a retry
  within the same call ceiling. No tools in the rejected batch execute.

An independent review also found that literal filenames resembling Git pathspec
expressions could omit a tested edit from the export. Git operations now use
literal pathspecs. A regression replays the exported patch in a fresh checkout
and compares all affected files.

Earlier attempts that failed provider validation, patch application, or call
limits remain inconclusive. In particular, the Pro replay is not evidence of a
successful fresh Pro run. Its input is byte-identical to the earlier model's
recorded proposal; no manual source edits were made for that replay.

## Reproduce a live Jinja run

First follow the Jinja example's image-building and preparation steps. Put the
credential in an ignored local `.env.deepseek` file with mode `0600`, then run:

```bash
uv run seam run \
  --repo /tmp/jinja-backport/repo \
  --fix 7dd3680e6eea0d77fde024763657aa4d884ddb23 --target 3.0.3 \
  --config /tmp/jinja-backport/harness.toml \
  --output /tmp/jinja-deepseek-live \
  --provider deepseek --model deepseek-flash \
  --env-file .env.deepseek --api-budget-usd 1
```

The ordinary repository test suite makes no paid requests. At this revision,
181 tests passed with the Docker and privileged-cleanup integrations enabled;
Ruff, strict mypy, wheel/sdist builds, and an installed-wheel CLI demo also passed.

The downloadable export includes selected public evidence under
`.runs/deepseek-live/`, including raw proposals, canonical patches, frozen inputs,
usage, and reports for successful and unsuccessful runs. These artifacts remain
outside Git history. Credential files, provider conversations, dependency caches,
and upstream repository copies are excluded. Historical report paths identify
the VM execution; regenerate configuration paths for a new machine.
