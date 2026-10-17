# Fixes and repeat evaluation

Seam's first multi-library evaluation exposed path handling, pytest integration,
and reporting defects. This follow-up fixes those defects and repeats the same
ten library cases with an installed wheel. Nine now verify, preserving 760
selected target cases. Certifi remains outside the scope for Python implementation
changes. The earlier findings and ratings stay in [the original evaluation](evaluations.md);
these runs do not invent new user ratings.

## Contents

- [What changed](#what-changed)
- [Repeat results](#repeat-results)
- [Fresh AI adaptation](#fresh-ai-adaptation)
- [Validation and evidence](#validation-and-evidence)
- [Remaining limits](#remaining-limits)

## What changed

- **Consistent file classification.** Uppercase `Tests/` is treated like `tests/`
  in upstream extraction and candidate validation. Pillow's ordinary source fix
  can proceed; a candidate still cannot edit test helpers or assertions.
- **Safe file links and early checks.** Contained relative links to regular files
  are materialized, with descriptor-based checks and bounded traversal. Broken,
  cyclic, escaping, sensitive, directory and hard links remain rejected. All
  three baseline snapshots are checked before image preparation or test runs.
- **Explicit pytest setup.** Frozen configuration now accepts a validated plugin
  list, an import mode and a suite-only marker expression. Plugin autoload stays
  disabled. Marker selection never deselects the external security test or its
  controls, and selected skips/xfails still prevent verification.
- **Actionable reports.** Setup failures produce schema-v2 JSON and Markdown with
  unavailable provenance left null. Summaries separate oracle/suite counts, name
  `backport.patch`, label xfails, and include bounded error context. Existing
  nonempty output directories are rejected before writing; unsafe output and early
  usage errors can still reject before report creation. Schema-v1 reports remain
  readable.
- **Practical setup guidance.** Usage now includes pip installation, fix
  eligibility checks, trusted-image and offline-wheel recipes, explicit plugin
  configuration, suite-selection costs, native-extension requirements and output
  locations. Package-data and build changes are visibly outside scope.
- **Recoverable model schema errors.** Live Pro runs exposed an additional gap:
  invalid tool arguments stopped adaptation immediately. They now execute
  nothing and return a generic correction with the declared schema. Rejected
  values are not echoed. Existing request, context, token and dollar limits
  still apply; unknown tools and oversized arguments remain fatal. Reports also
  record an attempted AI adaptation if the provider fails before submitting.

An independent source review caught a symlink semantic bug during implementation:
`missing/../file` had been normalized into a valid path. The final walker checks
intermediate directories so it preserves native filesystem failures. A separate
review checked tool recovery, accounting limits and diagnostic failure paths.

## Repeat results

| Library | Target | Result | Target cases |
| --- | --- | --- | ---: |
| Werkzeug | 2.1.2 | Verified | 65 |
| Requests | 2.28.2 | Verified | 61 |
| Starlette | 0.26.1 | Verified | 51 |
| Tornado | 6.3.3 | Verified | 52 |
| Django | 3.2.19 | Verified | 25 |
| Pillow | 9.5.0 | Verified | 7 |
| Bleach | 3.1.5 | Verified | 335 |
| Flask | 2.2.2 | Verified | 132 |
| idna | 3.6 | Verified | 32 |
| Certifi | 2022.12.07 | Outside scope; structured rejection | — |

Nine main library cases preserve **760 selected target suite cases**. This
total counts each main library once.

Counts are selected target suite cases, excluding the external oracle. Successful
reports require the intended assertion on upstream parent and target, passing
controls throughout, passing fixed/backport checks, and identical target/backport
suite case identities. Oracles and comparative supplied patches are unchanged
from the first evaluation; runner changes are explicit and hashed.

Requests uses its original pytest 6.2.5 image with `import_mode = "prepend"`.
Starlette registers `anyio.pytest_plugin` explicitly without `sitecustomize`.
Django uses ordinary Git checkouts with all four real documentation symlinks and
an explicit `pytest_django.plugin`; its Python 3.10.11 environment and native
warning/settings setup remain required. Its validator-only supplied patch
preserves the older widget output, as in the original trial.

Pillow uses a trusted native bridge: unchanged source files run from the staged
checkout, while matching extension binaries load from executable image storage.
The bridge checks native source and binary hashes for the recorded revisions;
it is still operator-supplied image preparation, not automatic native builds.

Bleach selects `tests` with `suite_markers = "not xfail"`, preserving 335 target
cases rather than the earlier 326. This excludes marked expected failures and
makes the coverage choice explicit. The unfiltered negative run remains
inconclusive with six xfails. No unsuccessful selected case is ignored.

Two other supplementary runs check boundaries: idna v3.3, previously blocked by
its tracked link, verifies with 26 selected target cases; Tornado under the
incompatible pytest 8 image stays inconclusive at target collection with useful
error context. The main Tornado case retains its compatible pytest 7.4.4 image.

Certifi's `.pem` change remains outside Python implementation scope. Its rejection
now has structured evidence and names the unsupported file. This is a successful
rejection check, not a verified backport or newly added data-file support.

## Fresh AI adaptation

| Case | Model | Outcome | Requests | Recovered argument errors |
| --- | --- | --- | ---: | ---: |
| Pillow | Pro | Inconclusive; request limit | 32 | 4 |
| Werkzeug | Pro | Inconclusive; request limit | 32 | 0 |
| Django | Pro | Failed | 32 | 1 |
| Bleach | Pro | Verified | 13 | 1 |
| Pillow | Flash | Verified | 10 | 1 |

Pillow Flash submitted one candidate and verified it after correcting one invalid
read request. Its canonical patch matches the supplied reference. Pro Pillow
submitted no candidate; Pro Werkzeug submitted a patch with mismatched source
context. Both exhausted the request limit. Pro Django first fixed the security
case but broke `test_emailfield_1`; its retry had an unappliable hunk. The harness
rejected both. These outcomes remain failures or inconclusive results.

Independent review found the relevant implementation files fully readable and
Django's compatibility feedback complete. Flash's metadata-only read trace also
shows working navigation through the same Pillow source. The exact reason for
Pro's exploration failures is unknown; these trials do not establish a general
model ranking. Automatic adaptation can still fail within the configured limits.
Bleach Pro submitted one candidate and verified it while preserving all 335
selected target cases.

The four Pro variants use `deepseek-v4-pro`; the separate Pillow Flash variant
uses `deepseek-flash`. All have no dollar cap and at most 32 cumulative
requests, 32,768 output tokens per request, a 300-second request timeout, and the
same frozen case configuration, oracle, image and suite as their supplied-patch
comparison. Adaptation attempts remain bounded by each configuration. The model
cannot edit accepted tests, run shell commands or declare verification.

Original Pro failures on Pillow, Werkzeug and Django are preserved separately.
All three stopped on invalid tool arguments before an accepted proposal. Those
failures motivated the recovery fix; they are not deleted or counted as model
successes. Pro observation records only schema-rejection counts by tool. The
Flash trace adds output item types and metadata from successful validated reads,
without file contents, denied paths or raw invalid arguments. Provider
conversations are excluded. Estimated charges and actual request/token usage are
in the reports; estimates are not billing invoices.

## Validation and evidence

- **322 tests pass from source and from the final installed wheel**, with no
  skips, including Docker lifecycle and privileged cleanup checks. The source
  controller runs Python 3.12.3; the independent installation uses Python 3.13.16.
- Ruff lint/format and strict mypy pass. Wheel and source distribution build;
  all 50 installed package/resource files byte-match the wheel and frozen source.
- The first fix commit is `bad44dc2090a8386ec4071c09b072712d280c315`.
  Live recovery and final repeat runs use
  `b3eda87a090533e7876949bbefb31aa8ec8d1c49`, wheel SHA-256
  `df8970d317c8e8de858915b472a9f9a6d0b09210f5f291d6c6c49647a85ac83b`.
- An independent cross-check validates report models, immutable revisions, image
  IDs, oracle/config/patch hashes, actual pytest commands, marked baseline
  assertions, passing controls, evidence completeness and target/backport suite
  identities. Failed proposals and earlier failed backport phases remain visible.

The companion `seam-fix-evaluations-2026-10-17.zip` contains curated reports,
frozen inputs, rejected and canonical patches, preparation recipes, reproduction
drivers, checks and a SHA-256 manifest. VM originals are under
`.runs/fix-validation-2026-10-17/`. Credentials, provider conversations, standalone
raw logs, environments, upstream clones, wheels and image layers are excluded.
Public upstream licenses accompany distributed patch excerpts. Historical
absolute paths must be adjusted when reproducing elsewhere.

## Remaining limits

Verification covers the recorded oracle, controls, selected suite, revisions and
trusted image. These trials do not certify full library suites, complete CVE
remediation, resistance to hostile test-evidence forgery, or broad model
reliability. Operators still prepare compatible dependencies, settings, images
and external regression tests. Native-code, build-script, dependency and
package-data fixes remain outside the supported patch scope. Read the
[execution boundaries](security.md) before interpreting a verified result.
