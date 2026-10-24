# Reviewed workflow validation

Validated on **2026-10-18** using real Docker execution and preserved inputs.
These results cover the selected suites below. For current development checks,
see [Development](../README.md#development).

Configuration, image, oracle, assertion patch and fixture pins are trusted
operator inputs. The model still proposes Python implementation changes only.
An assertion patch requires a pinned hash and review reason; structural checks
preserve statements outside assertions and collection metadata, while a human
must judge assertion strength. Fixture allowances cover exact reviewed paths and
bytes, leaving model secret screening unchanged. See the
[review workflows](usage.md#review-existing-test-expectations)
and [security boundaries](security.md).

## Execution results

| Case | Adaptation | Target / backport suite | Result |
| --- | --- | --- | --- |
| urllib3, supplied candidate | Existing source patch + reviewed assertions | 59 / 59 | Verified |
| urllib3, fresh DeepSeek Flash | One model candidate + same reviewed assertions | 59 / 59 | Verified |
| Authlib | Supplied source patch + eight pinned PEM fixtures | 16 / 16 | Verified |

urllib3 fix: `644124ecd0b6e417c527191f866daa05a5a2056d`;
target: `d94029b7e2193ff47b627906a70e06377a09aae8`.
The selected suite was `test/test_retry.py`. Reviewed assertions adopted the
upstream Cookie-removal policy without changing test identities. The fresh live
run used `deepseek-flash`, 8 calls, 44,152 input tokens and 2,333 output tokens;
estimated cost was **$0.0160452**. The dollar cap was explicitly disabled and
`--max-model-calls 32` configured. Eight calls do not demonstrate a need for more
than the default of 16 in effect for that run. Its exported patch matched the
supplied-candidate result.

Authlib fix: `06f0813901a5238dd0b94521d26a7af9064497a0`;
target: `dbbfa9abcfe725001b452cf08d9e48be0ebfdce9`.
The selected suite was `tests/jose/test_jws.py`. Its supplied source patch also
includes prerequisite critical-header behavior from `eb071194`; the oracle
checks rejection behavior without requiring a newer exception class. Eight
published test PEM files reached snapshots unchanged through explicit pins.
The original `seam-20-authlib:20261018` base image had no fixture bridge or fixture
injection directory. The run used no workaround plugin (`plugins = []`) or API.

Both libraries reproduced one intended security failure on upstream parent and
target baseline, passed three controls throughout, and passed all four oracle
cases after each fix. Target/backport suite identities matched. Original inputs
and checkouts were preserved; urllib3's export passed ordinary Git application.
Wrong assertion-patch and fixture hashes were rejected before Docker preparation
or execution, with zero completed phases and no image ID.

## Stored-report inspection

Sixteen checks covered four Jinja report cases, text/JSON modes and two CLIs.
The old evaluation checkout at `eb11f4d` accepted both the exact supplied probe
and a failed final security case despite stored `verified` status (exit 0).
The review baseline at `7f16cb0` rejected both in both modes (exit 2). Both CLIs
accepted an unchanged valid report and an earlier failed attempt followed by a
successful final candidate. Both installations originally reported version
0.1.0; use `seam doctor` to identify the installed package and executable.
An installed **0.2.0** wheel repeated all four cases in text/JSON modes: all eight
checks returned the expected exits, including rejection of the exact probe.

Inspection checks recorded internal consistency. JSON is not authenticated;
self-consistent edits can pass, and cooperating target code remains an execution
assumption. These measurements do not establish complete library security.

## Local evidence

These ignored local run artifacts are outside the package:

- `.runs/reviewed-evals/urllib3/manifest.json`: supplied/live reports and hashes.
- `.runs/reviewed-evals/authlib/result.json`: matrix and wrong-pin outcome;
  `snapshot-checks.json` in the same directory records staged-file hashes.
- `.runs/latest-findings-inspect/summary.json`: 16 old/current CLI checks.
- `.runs/reviewed-evals/installed-inspect-checks.json`: eight 0.2.0 wheel checks.
