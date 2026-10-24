# Recent security backports: results and evidence

Seam was tested against four security fixes published between May and September
2026, across Django, PydanticAI and LiteLLM. After fixing two harness defects and
extending directory-link support, all four supplied maintainer patches verified.
New model adaptation verified the LiteLLM case and remained inconclusive in two
PydanticAI attempts. Two Django patches generated in the earlier evaluation also
passed fresh runtime replays.

These are selected case studies, not an ecosystem success rate. The
[public evidence bundle](../evals/recent-backports/2026-10-24/README.md) includes
frozen inputs, immutable revisions, normalized run evidence, unsuccessful attempts,
patch comparisons, environment recipes, licenses and checksums. It is separate
from the [eight-case reference dataset](../evals/python/README.md).

## Results

| Case | Maintainer reference | Model result after harness fixes | Existing target tests |
| --- | --- | --- | ---: |
| [Django domain validation, CVE-2026-53878](https://www.djangoproject.com/weblog/2026/jul/07/security-releases/) | Verified before changes | Stored model patch reverified; no new generation | 15 |
| [Django Vary/cache, CVE-2026-6907](https://www.djangoproject.com/weblog/2026/may/05/security-releases/) | Verified before changes | Stored model patch reverified; no new generation | 6 |
| [PydanticAI Host handling](https://github.com/pydantic/pydantic-ai/security/advisories/GHSA-q2xc-rrxj-58x9) | Verified after changes | Two new model attempts inconclusive | 4 |
| [LiteLLM encryption contexts](https://github.com/BerriAI/litellm/security/advisories/GHSA-7hp6-4w63-5g45) | Verified after changes | New model patch verified | 10 |

A verified run requires the intended security assertion to fail on both affected
revisions, normal controls to pass throughout, and security and existing tests to
pass with the fix and backport. Target and backport test identities must match.
The four cases retain 35 selected target tests and 13 oracle controls in total.
They do not run the libraries' complete suites.

Both Django implementation patches are byte-identical to the maintainers' patches.
LiteLLM's generated authentication file matches the maintainer file. Its crypto
file differs only in guarded prefix slicing instead of `removeprefix`, equivalent
for the declared string inputs. The complete LiteLLM patches are not byte-identical.
The runtime oracle exercises encryption helpers, so the separate two-file source
comparison is necessary; it is not a full authentication-service integration test.
PydanticAI produced no applicable verified model export, so model equivalence is
not established.

A deliberately ineffective Django patch was also replayed. Seam rejected it when
the security assertion still failed, while its three controls and 15 existing
tests passed. This is a rejection check, not a successful backport.

## What changed in Seam

The original evaluation exposed an inventory that printed every tracked filename
and object hash. Large monorepos exceeded the bounded Git output before testing.
Seam now requests only file modes, retaining the existing 1 MiB and 120 second
limits and the submodule rejection. All three original fixtures around the old
1 MiB boundary now pass inventory. They intentionally stop before image preparation
and do not count as security-test successes.

Safe direct directory links now remain links in staged source and container
copies. Real contents are checked once; cycles, escapes, excluded paths and
indirect directory-link targets still reject. This removed the recorded monorepo
coverage block. Candidate patches still cannot modify through linked paths.

The starter examples now select offline mode explicitly, describe the default
32 model requests correctly, and show how to check the actual installed version.
Git diagnostics identify the selected revision and failed bound; `doctor` checks
Git 2.38 or newer.

The tested wheel passed all **1,140 installed-package tests with no skips**,
including real Docker and privileged cleanup checks. Ruff and strict mypy passed.
Its SHA-256 is
`5469855e22fecaecea05bb3b1bc316d9a7c4c7da7ca9a18b0c9e6771ae9451d9`.
The implementation used base commit
`baac3a06a99cb697ef1d9d2c98844074db222025` plus the uncommitted changes identified
in the bundle's [tested implementation record](../evals/recent-backports/2026-10-24/provenance/tested-implementation.json).
These historical results do not automatically qualify a later release.

## Attempts and cost

All 12 post-fix case CLI attempts remain represented: five verified, one correctly
failed negative check, and six inconclusive attempts. The inconclusives comprise
four environment setup attempts and both PydanticAI model runs. The bundle also
retains ten clearly labeled earlier runs for comparison; those are excluded
from the post-fix totals.

| New model run | Result | Requests | Estimated completed-request cost | Unresolved reservation |
| --- | --- | ---: | ---: | ---: |
| PydanticAI 1 | Inconclusive; provider/request or token-usage error | 25 | $0.2302596 | $0.3342336 |
| PydanticAI 2 | Inconclusive; request limit | 32 | $0.4625343 | $0 |
| LiteLLM | Verified | 8 | $0.0802029 | $0 |
| Total | | 65 | $0.7729968 | $0.3342336 |

Each new run used `deepseek-flash`, a separate $1 cap and at most 32 requests.
The reservation reflects uncertainty retained by the controller after a request
failure, not a confirmed provider charge. Costs are estimates, not invoices, and
exclude the earlier Django generations. Both PydanticAI runs rejected their first
patch during application; neither reached a backport test phase or exported a
successful patch. The underlying first-run provider cause is not available in
the exported evidence.

## Setup work and limits

Operators supplied the oracles, controls, suite selections and trusted images.
PydanticAI needed explicit staged monorepo paths, authentic per-revision
metadata-only records, and upstream test dependencies. One early metadata build
ran on the host and used a temporary shared-object clone, contrary to the intended
setup boundary. Those outputs were discarded. Qualifying metadata was regenerated
inside isolated containers from independent clones before the successful reference.
Original source checkouts remained unchanged.

LiteLLM's first runtime attempt failed on missing real HTTPx2 imports. Its final
image uses a documented dependency union, including different real MCP SDK versions
for the two release lines. It is not identical to the target dependency lock.
No operator module stubs or installed target implementation replaced staged source.
Its history contains complete exact selected snapshots in original depth-two
histories; this is not a full-history benchmark. PydanticAI used complete hydrated
history. The October LiteLLM release-pipeline incident is outside this source-fix
comparison.

The evidence omits credentials, provider conversations, raw logs, source clones,
dependency wheels and container layers. Published evidence files are normalized
derivatives with original and published hashes, not untouched reports for
`seam inspect`. The reproduction guide distinguishes historical local image IDs
from newly derived rebuild recipes, which require their own qualification.
