# Expanded npm and Python backport evaluation

Seam can now evaluate JavaScript fixes with Node and Mocha. This study also shows where that support stops: only four of the initial 20 npm cases qualified. A later test review qualified serve-static, and a stronger body-parser control caught a defect in an earlier AI patch.

The inputs, unsuccessful attempts, normalized evidence and patch comparisons are public here. These are selected integration cases, not an ecosystem success rate or a contamination-free model ranking. The earlier eight-case Python dataset remains separate.

## Results

| Cohort | Result |
| --- | --- |
| Initial npm batch | 20 cases across 17 libraries: 4 verified, 15 inconclusive, 1 compatibility failure. |
| Initial npm rejection checks | All four qualifying references repeated successfully; all four ineffective patches were rejected. |
| Reviewed serve-static follow-up | Verified twice with 90 selected existing tests; ineffective patch rejected. The original full-selection failure remains recorded. |
| New Python cases | Werkzeug multipart and Django language-cache references verified twice; both ineffective patches rejected. |
| Initial fresh AI adaptations | IP, Undici private-cache, body-parser and debug passed their original frozen checks. |
| Direct transfer baseline | Passed IP, Undici and debug; body-parser's unchanged upstream patch did not apply. |
| Stronger body-parser check | Maintainer reference verified twice. Earlier AI patch rejected; a fresh adaptation passed the stronger checks. |
| External BackportBench check | One qs task: 6 security failures fixed, 213 preservation tests passed; ineffective patch retained all 6 failures. |

A verified Seam run checks four revisions: upstream parent, upstream fix, target baseline and candidate backport. The intended security assertion must fail on both affected revisions and pass after fixing them. Normal controls and the selected original tests must pass. Target and backport test identities must match. A repeat is a repeat, not another independent case.

The accepted npm selections contain 65 target tests for IP, 25 for Undici private-cache, 3 for body-parser, 4 for debug and 90 for the reviewed serve-static case. Python adds 21 Werkzeug cases and two Django methods. These are not full project suites. IP excludes three cases sharing an ambiguous title; body-parser selects three ordinary JSON tests; serve-static excludes two obsolete HTML-link expectations. The exact filters are frozen in their configurations.

The initial inconclusives include missing dependencies, Tape/AVA/Lab/TAP and older Mocha interface requirements, genuine duplicate test identities, a suite timeout, and fix commits that change manifests or lockfiles outside current patch permissions. Those outcomes establish neither an insecure maintainer patch nor a successful Seam backport. Detailed module diagnostics and every attempt remain in `results/`.

## The body-parser lesson

The first AI patch called `unpipe(req, stream)`. The installed `unpipe` helper accepts one stream argument and detaches every consumer, whereas the maintainer patch uses `req.unpipe(stream)` to detach only the decompressor. The original charset regression and ordinary body controls missed that difference.

The reviewed oracle adds a legitimate second consumer whose completion is pending. Maintainer source and its backport preserve it; the first AI candidate detaches it. Seam rejected that candidate when replayed with the added control. A fresh adaptation passed the stronger oracle. Both model outputs, both configurations and the failed replay are retained.

This closes the observed control gap on Node 24. It does not establish full maintainer equivalence: the new candidate still omits the maintainer's old-Node fallback and uses a different destroy call. The target declares Node >=0.8, while these executions use Node 24. Older-runtime compatibility is unverified. IP also differs from the maintainer patch in variable declarations. Undici private-cache and debug match their supplied reference patches byte-for-byte.

Five fresh model experiments used `deepseek-flash`: four initial cases and the separate stronger body-parser rerun. They made 31 requests, with a conservative estimated total cost of $0.1637985 and no remaining reservation. Each experiment had a $1 cap and a 32-request limit. Current peak text rates were supplied explicitly; provider billing is authoritative. Reference patches and oracle source were not supplied to the model. Public commits may occur in training data.

## What changed in the harness

The implementation adds language-aware inspection and patch boundaries, fixed isolated Node/Mocha execution, native JUnit dialect handling, revision-specific frozen dependencies, useful import diagnostics, static JavaScript credential checks, explicit Mocha selection and narrowly pinned empty submodule exceptions. It adds no controller dependency or generic test-framework plugin layer. Python and pytest remain the default.

The tested installed wheel is `seam-0.5.0.dev1-py3-none-any.whl`, SHA-256 `fb1afe7d89a0cfd5a50ae6094f1b1a356cb57e6d187beba597d542fe8903c35c`. All 1,281 installed-package tests passed with no skips, including real container execution and cleanup checks. Ruff and strict mypy passed. `tested-runtime-commit.json` maps the initially uncommitted build to exact runtime commit `1732e46`; all source and test hashes match.

## Reproduce and inspect

Download the wheel, evaluation bundle and optional execution images from the [development release](https://github.com/theinfosecguy/seam/releases/tag/v0.5.0.dev1). Verify its `SHA256SUMS`, then use the locked controller environment:

```bash
python3.12 -m venv ../seam-env
../seam-env/bin/pip install --only-binary=:all: --require-hashes -r controller-requirements.txt
../seam-env/bin/pip install --no-deps /path/to/seam-0.5.0.dev1-py3-none-any.whl
../seam-env/bin/seam doctor
docker load < /path/to/seam-expanded-eval-images-2026-10-24.tar.gz
```

The image archive contains the exact four executed Node/Mocha/dependency/Python images. Its manifest graph, all 53 blob hashes and root filesystem identities were checked against the executed images, and loading into the existing daemon succeeded. A clean-daemon restore was not tested. Portable rebuild recipes require a new image/configuration hash and fresh qualification.

Follow [npm inputs](npm/README.md) and [Python inputs](python/README.md) for ordinary clones, immutable refs and standalone `seam run` commands. These new cases are not registered in the default `seam eval` catalogue. Target code runs in disposable containers without network access, controller credentials, host dependencies or a Docker socket. Preserve original inputs and use new output directories.

`results/` contains normalized derivatives, original report hashes, observed test identities and outcomes, model usage and candidate patches. It omits raw logs, conversations, private checkout paths and credentials. These derivatives are not original reports for `seam inspect`. Input provenance distinguishes unchanged assets from normalized metadata. Root `SHA256SUMS` covers this bundle; nested manifests cover their original subsets.

## Broader candidate pools and external tools

Independent research identified 25 npm libraries and 21 additional Python libraries with published older-line fixes. Five Python maintainer pairs have immutable ordinary commits; sixteen distributor publications still need source-series and runtime qualification. The research snapshots predate execution of the two new Python cases.

The pinned BackportBench pool adds 65 npm pairs covering 36 advisories beyond the npm catalogue, plus 264 Python pairs across 27 projects. Those are author-labeled candidates, not additional completed evaluations. Its executable Python split is heavily concentrated in Django. See [tool assessment](external-candidates/benchmark-recommendation.md) and the [actual qs crosscheck](backportbench/README.md). That qs pair overlaps our npm cohort: external success does not turn Seam's unresolved Tape environment into a passing case.

Use BackportBench for additional independent tasks and evaluator checks. SWE-bench task export may help later; adding Inspect merely around Seam's existing verdict would not independently validate it. Next priorities are frozen framework/build support and explicit runtime compatibility, before broader model scores or TypeScript claims.

Seam-authored material uses the project MIT license. Each upstream patch retains its accompanying license; dependencies retain their package licenses. The BackportBench replay archive includes its original source and upstream license notices.
