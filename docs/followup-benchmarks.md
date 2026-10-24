# More backport evaluations

The [25 October follow-up](../evals/framework-backports/2026-10-25/README.md)
qualifies eight selected cases with the installed `0.5.0.dev2` wheel. Every
reference passed twice, and every deliberately ineffective patch was rejected.
This is a focused follow-up to the [earlier npm and Python study](expanded-benchmarks.md),
not a rerun of its entire 20-case npm batch.

| Library and selected checks | Existing tests per phase |
| --- | --- |
| js-yaml loader and prototype-safe merge | 92 / 92 / 95 / 95 |
| Marshmallow collection-merging component | 29 each |
| Pydantic date parsing, reviewed `prepend` configuration | 124 / 142 / 124 / 124 |
| IP address classification | 65 / 85 / 65 / 65 |
| Undici private-cache handling | 25 / 27 / 25 / 25 |
| body-parser cleanup, strengthened controls | 3 each |
| debug formatter bounded work | 4 each |
| serve-static, previously reviewed selection | 90 each |

Counts are ordered upstream parent, upstream fix, target baseline and proposed
backport. They describe selected tests, not complete project suites. The last
five cases reuse the earlier frozen inputs and their documented scope limits.

## What changed

js-yaml's older release uses Mocha's TDD interface, while its newer release uses
BDD. Seam now accepts those two built-in interfaces and can pin the choice to
each exact source commit. Missing pins stop verification. The external security
test keeps its separate native Node runner. No new runtime dependency is required.

A fresh js-yaml AI adaptation passed after two patch attempts. Direct transfer
could not apply because the implementation file had moved. The model's first
patch also failed to apply; its second produced a final patch byte-identical to
the implementation-only maintainer reference. The experiment used 15 model
calls, with a conservative estimated cost of $0.0575424 under a $1 cap. Both
attempts and the application failure remain in the evidence. One successful
adaptation does not establish a model success rate.

The two additional Python issues are historical. Marshmallow checks one
collection-merging performance component, using a frozen input size and CPU
budget; it excludes later deepcopy adjustments and does not establish complete
CVE remediation. Pydantic runs its pure-Python implementation on Python 3.9.25.
Its initial import configuration failed 16 unchanged project tests. A separately
reviewed configuration uses the maintainer's original `prepend` import mode and
passes. The failed configurations remain published; both configurations count
as one issue. Neither Python case measures AI adaptation difficulty: their
upstream and backport implementation patches are already identical.

## Remaining gaps

Tape remains unsupported. Container probes of qs and fast-uri completed all
eight original revision suites, and 20 synthetic probes exposed reporting
hazards: invisible static skips, failures in an unobserved second harness, late
asynchronous failures and incomplete lifecycle evidence. Existing JUnit
converters also lose identities or testcases. These are prerequisite probes,
not additional security qualifications. The [Tape investigation](../evals/framework-backports/2026-10-25/tape/README.md)
publishes the exact locks, probes and outcomes.

Node 20.18.1's native JUnit reporter omits source-file identities. All seven
synthetic reports were rejected, including an ordinary passing test. This
preserves an honest inconclusive result, but leaves older-runtime support
unfinished. Node 24 checks do not establish compatibility with every runtime a
library declares.

The earlier [official BackportBench crosscheck](expanded-benchmarks.md) remains
one executed task. This follow-up adds no external leaderboard score or broad
ecosystem success rate.

## Evidence and validation

All 1,307 installed-package tests passed with zero skips or failures, including
real container and privileged-client cleanup checks. Ruff, formatting and strict
mypy passed. Independent reviews checked the code change, frozen inputs,
verification gates and normalized evidence.

The bundle retains 31 CLI reports: 19 verified results, nine correctly rejected
ineffective patches and three inconclusive results. Repeats, configuration
variants and reference runs are separate records, not independent benchmark
cases. Original hashes connect each normalized report to its retained source.

[Release assets](https://github.com/theinfosecguy/seam/releases/tag/v0.5.0.dev2)
provide the tested wheel, inputs and optional exact execution-image archive.
The image archive's blobs, descriptor graph, platform and filesystem identities
were checked; restoration into a clean Docker daemon was not tested.
