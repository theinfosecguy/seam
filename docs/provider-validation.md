# Provider and credential-screening validation

Validated on 18 October 2026 in the `provider-security-refactor` worktree.
The original checkout and existing evaluation inputs were preserved.

## Implementation

- Constants live in seven focused modules under `seam.constants`, with direct
  absolute imports and no umbrella re-exports.
- One `PatchAgent` uses PydanticAI's maintained model/provider adapters. Seam
  retains its tool loop, local argument validation, independent verification,
  cumulative limits, and conservative offline price accounting.
- Local `detect-secrets` matchers replace the custom token regex. Small bounded
  literal normalization handles credential assignments; exact matching also
  protects the configured controller key and AWS credentials.
- Credential paths are excluded separately. Ordinary Python modules named
  `credentials.py`, `secrets.py`, or `secret.py` remain available. Content
  screening protects model transmission; offline verification accepts ordinary
  local test fixtures containing example passwords.

See [API setup](api.md) and [security boundaries](security.md) for supported
protocols, authentication, and limits.

## Automated checks

Ruff lint/import checks, Ruff formatting, strict mypy across 49 source modules,
and the frozen dependency lock check passed. A wheel and source distribution
were built, and every packaged source/resource file was compared with the
checkout.

The full test suite passed **502 tests**, with no skips, from a clean Python
3.12 wheel installation outside the checkout. Docker integration and privileged
process cleanup were explicitly enabled:

```bash
BACKPORT_TEST_IMAGE=backport-runner-test:local \
BACKPORT_TEST_DOCKER='sudo -n docker' BACKPORT_TEST_SUDO=1 \
/path/to/installed/python -m pytest -q \
  -c /path/to/seam/pyproject.toml /path/to/seam/tests
```

Native SDK protocol tests cover the ten HTTP provider configurations, Bedrock
Converse with an AWS SDK stub, and Vertex with a synthetic signed service
account. They check tool/result round trips, explicit routing and authentication,
malformed usage, retained budget reservations, hidden follow-up requests, SDK
logging, and cleanup. Vertex credential tests reject FIFOs, devices, oversized
files, and invalid JSON or private keys.

These tests use synthetic credentials and deterministic responses. They establish
serialization and local policy behavior, not live service availability.

## Library replay

A separate clean Python 3.13 wheel installation replayed the existing inputs.
Supplied adaptations were used where required; none of these runs called a model.
All 13 outcomes matched the expected results.

| Library / case | Result | Target suite preserved |
| --- | --- | ---: |
| Bleach | Verified | 335 |
| Flask | Verified | 132 |
| Idna | Verified | 32 |
| Pillow | Verified | 7 |
| Requests | Verified | 61 |
| Starlette | Verified | 51 |
| Tornado | Verified | 52 |
| Werkzeug | Verified | 65 |
| Django | Verified | 25 |
| Idna v3.3 supplementary target | Verified | 26 |
| Certifi | Inconclusive: unsupported certificate-bundle change | — |
| Bleach without marker filtering | Inconclusive: skipped / expected failures | — |
| Tornado with pytest 8 | Inconclusive: target suite collection error | — |

The nine primary positive library cases preserve 760 selected target tests.
These are the frozen case-specific suites, not every library's complete suite.
Input files, oracle and candidate hashes, and original repository HEAD/status
were checked before and after the runs.

The replay wheel SHA256 was
`adc0528e5bfc5600586f320789409f62ece23f53a0976b4ab86e7fe9e1cc78ee`.
Subsequent changes bounded Vertex credential reads, restored benign Python
basenames, and preserved the CLI's previous DeepSeek request envelope as shared
CLI defaults. They do not affect these offline inputs: all 31 unique selected
Git revisions were checked for the three basenames, with no matches. The final
wheel received the full installed test run described above.

One historical manifest had an incorrect Idna v3.3 candidate hash. The actual
patch hash was recorded as
`4c8aa9a2f5af9c2ef79dbda286ea7c7cf611fafac5c544d0a31955d61a02fb51`;
the patch was not edited to match the manifest.

## Live DeepSeek runs

The native Chat Completions path was tested with the existing controller key.
All three runs generated a patch and passed independent Docker verification.
The live runner used explicit limits of 32 requests, 32,768 output tokens per
request, 300 seconds per request, and no dollar cap.

| Case | Model | Calls | Target suite preserved | Estimated text cost |
| --- | --- | ---: | ---: | ---: |
| Synthetic traversal demo | `deepseek-flash` | 4 | 2 | $0.0044 |
| Bleach | `deepseek-v4-pro` | 20 | 335 | $0.3929 |
| Pillow | `deepseek-flash` | 13 | 7 | $0.1295 |

These are conservative local estimates, not provider invoices. No request
transcripts or credentials were retained in the repository. An earlier Bleach
preflight exposed overly broad snapshot content screening; it made zero API
calls and was corrected before the successful repeat.

Other providers have not been tested with live accounts. Secret detection
remains heuristic, and Bedrock cancellation can wait for its SDK socket timeouts.
