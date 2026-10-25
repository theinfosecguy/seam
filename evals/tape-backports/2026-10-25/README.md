# Tape backport study, 25 October 2026

Two advisories were evaluated with the installed `0.5.0.dev3` wheel. qs qualifies
with its original selected parsing suite. fast-uri qualifies only within a
separately reviewed parsing scope; its original scheme suite remains
inconclusive because an old expectation aborts after the security fix.

| Record | Outcome |
| --- | --- |
| qs reference and repeat | Verified twice |
| qs ineffective patch | Rejected with the intended security failure |
| fast-uri original scheme suite | Inconclusive; candidate throws at an old expectation |
| fast-uri separate parsing reference and repeat | Verified twice |
| fast-uri parsing ineffective patch | Rejected with the intended security failure |
| qs direct transfer and fresh model run | Verified; both canonical patches match the maintainer reference |

There are nine CLI reports: six verified, two rejected ineffective patches and
one inconclusive. The two fast-uri scopes are the same advisory. These cases
reuse frozen source references and oracles from the earlier npm study; they do
not add two newly discovered issues or establish a representative model score.

| Directory | Contents |
| --- | --- |
| `cases` | Oracles, controls, explicit original suites, licenses, patches and immutable refs |
| `results` | Normalized reports, hashes of original evidence and candidate patches |
| `adapter` | 65 synthetic checks, eight original-suite checks and development regression proofs |
| `image` | Frozen runtime-image and minimal CI-image dependency recipes |
| `validation` | Installed wheel/source/test hashes, test counts, pricing, scope review and patch comparison |

The installed wheel passed 1,366 tests without skips or failures. The fresh qs
run used three model calls and one attempt, estimated conservatively at
$0.0041628 under a $1 cap. Direct transfer already works, so this demonstrates
the complete workflow rather than difficult adaptation. Reference patches and
external oracle source were not supplied to the model by the invocation;
provider conversations were not retained or audited.

The [results guide](https://github.com/theinfosecguy/seam/blob/main/docs/tape-benchmarks.md)
explains the scope and remaining work. See [reproduction notes](REPRODUCING.md)
for exact commands. Raw logs, credentials, conversations and library source
copies are excluded. Local metadata paths are omitted while original record
hashes remain available. Source snapshots are fetched by immutable Git refs,
not included as archive files. Normalized reports retain test identities,
outcomes, intended-failure-marker observations and hashes of original messages.
This study does not change the default eight-case Python catalogue.
