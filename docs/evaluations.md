# Multi-library evaluation

On 17 October 2026, ten isolated first-use reviews evaluated Seam at commit
`5c39d8783266a85fa51e2f0baf5020115c192e29`. Eight library cases eventually
verified. Pillow exposed a path-classification defect; Certifi's data-only fix
was outside the documented scope. Onboarding and historical test environments
required substantial operator work, including for several successful cases.

See [fixes and repeat evaluations](reevaluation.md) for the subsequent changes
and installed-wheel reruns.

## Contents

- [Method](#method)
- [Results](#results)
- [Ratings](#ratings)
- [Confirmed gaps and fix order](#confirmed-gaps-and-fix-order)
- [AI adaptation](#ai-adaptation)
- [Evidence and limits](#evidence-and-limits)

## Method

Each review began in a fresh session without the project conversation or other
trial results. The brief supplied the project location, public usage docs, an
assigned upstream library, and an isolated working directory. Each reviewer
selected a public fix, an older affected release, a trusted image, an external
regression test, controls, and a relevant existing suite. Product source stayed
unchanged throughout. After their ratings were saved, a separate editorial
cross-check reviewed the consolidated interpretation.

Thirteen sessions started. PyJWT, urllib3, and aiohttp sessions stopped when
automatic security review flagged vulnerability-specific analysis as possible
cybersecurity risk. Their partial attempts are preserved separately, without
invented ratings. Flask, idna, and Certifi supplied three additional independent
reviews. These interruptions are evaluation-platform failures, not Seam defects.

For each verified report, a separate evidence check confirmed input and patch
hashes, immutable revisions, marked failures on both vulnerable revisions,
passing controls, successful suites, and identical target/backport suite case
identities. First-use scores remain subjective technical judgments, not customer
research or a controlled model benchmark. The assigned libraries and selected
fixes are deliberately varied; the result is not an ecosystem success rate.

## Results

Issue links identify the exact upstream commits used. Test counts are selected
target pytest cases preserved by Seam, excluding the external oracle. Historical
release names do not imply current upstream support.

| Library | Target | Issue / fix | Method | Final result | Target cases |
| --- | --- | --- | --- | --- | ---: |
| Werkzeug | 2.1.2 | [CVE-2023-23934](https://github.com/pallets/werkzeug/commit/8c2b4b82d0cade0d37e6a88e2cd2413878e8ebd4) | Supplied adaptation | Verified | 65 |
| Requests | 2.28.2 | [CVE-2023-32681](https://github.com/psf/requests/commit/74ea7cf7a6a27a4eeb2ae24e162bcc942a6706d5) | Direct application | Verified | 61 |
| Starlette | 0.26.1 | [CVE-2023-29159](https://github.com/Kludex/starlette/commit/1797de464124b090f10cf570441e8292936d63e3) | Direct application; image bootstrap | Verified, qualified below | 51 |
| Tornado | 6.3.3 | [CVE-2024-52804](https://github.com/tornadoweb/tornado/commit/f4b3e9600e925ab57fc7b6ce250af175aa3e1356) | Direct application | Verified | 52 |
| Django | 3.2.19 | [CVE-2023-36053](https://github.com/django/django/commit/b7c5feb35a31799de6e582ad6a5a91a9de74e0f9) | Supplied adaptation; checkout workaround | Verified, qualified below | 25 |
| Pillow | 9.5.0 | [CVE-2023-44271](https://github.com/python-pillow/Pillow/commit/1fe1bb49c452b0318cad12ea9d97c3bef188e9a7) | Direct and supplied attempts | Rejected by test-path defect | — |
| Bleach | 3.1.5 | [CVE-2021-23980](https://github.com/mozilla/bleach/commit/1334134d34397966a7f7cfebd38639e9ba2c680e) | Supplied adaptation and separate Flash run | Both verified | 326 |
| Flask | 2.2.2 | [CVE-2023-30861](https://github.com/pallets/flask/commit/8646edca6f47e2cd57464081b3911218d4734f8d) | Direct application | Verified | 132 |
| idna | 3.6 | [CVE-2026-45409](https://github.com/kjd/idna/commit/e1cb465b6376f33306a26f467d197edbcd01c4b9) | Supplied adaptation | Verified | 32 |
| Certifi | 2022.12.07 | [CVE-2023-37920](https://github.com/certifi/python-certifi/commit/8fb96ed81f71e7097ed11bc4d9b19afd7ea5c909) | Direct and supplied attempts | Data-only fix outside scope | — |

Starlette required explicit AnyIO registration in a trusted image bootstrap.
Installing AnyIO alone left 24 suite errors. The bootstrap registered the plugin;
it did not alter test assertions or selection.

Django's normal documented path remained blocked by four documentation symlinks.
A Git wrapper using `core.symlinks=false` materialized those link blobs as ordinary
files while preserving commit identities. The final image pinned Python 3.10.11
and explicitly configured pytest-django and native-style warning filters. The
supplied patch retained the validator length guards while preserving the older
widget output, rather than adopting upstream's default `maxlength` change.
Its 25 passing target methods cover validators and EmailField, not all Django.

Idna's initial 2024 fix was rejected for changing the extensionless generator
`tools/idna-data`. A later fix on v3.3 hit a tracked symlink; selecting affected
v3.6 allowed the final run. Its oracle bounds executed work on one `check_label`
path, rather than making a universal remediation claim. Upstream suites passed
6,367 and 6,368 cases; the older target collected 32 cases, some with internal
loops. Both forms of `inspect` worked with the 2.38 MB final JSON report.

Pillow and Certifi each had a separate Docker matrix showing the expected
before/after behavior with their prepared inputs. Those independent matrices
are **not Seam verification successes**. Certifi's separate synthetic demo also
verified; that demo is not evidence for its certificate-bundle backport.

## Ratings

All values are out of ten. These describe each reviewer's complete experience,
including preparation and failed attempts; a final verified verdict does not
mean the documented path worked without intervention.

| Library | Setup | Documentation | Execution / reporting | Overall |
| --- | ---: | ---: | ---: | ---: |
| Werkzeug | 7 | 8 | 9 | 8 |
| Requests | 6 | 7 | 8 | 7 |
| Starlette | 6 | 7 | 8 | 7 |
| Tornado | 7 | 8 | 8 | 8 |
| Django | 4 | 6 | 7 | 6 |
| Pillow | 5 | 6 | 3 | 4 |
| Bleach | 6 | 7 | 8 | 7 |
| Flask | 7 | 8 | 9 | 8 |
| idna | 7 | 8 | 8 | 7.5 |
| Certifi | 7 | 7 | 7 | 6 |

## Confirmed gaps and fix order

1. **Fix inconsistent test-path classification.** Pillow's ordinary Python fix
   includes `Tests/test_imagefont.py`. Upstream extraction rejects it as an
   unsupported runtime change, blocking both direct and supplied-patch commands
   before report creation. A separate function-level reproduction rejects
   `tests/helper.py` but accepts `Tests/helper.py` as a candidate path. It still
   rejects `Tests/test_imagefont.py` by filename. Use one consistent path-role
   policy for extraction and candidate validation, with regression checks for
   directory capitalization and helper files. Preserve the ban on test edits.

2. **Expose repository compatibility restrictions before expensive execution.**
   Django documentation links and idna v3.3's `tools/intranges.py` stop the entire
   snapshot. Rejecting links is an intentional conservative restriction. The
   demonstrated gaps are missing setup guidance, pathless errors, and discovering
   target incompatibility after upstream checks have run. First document the
   restriction, name the offending relative path, and preflight every selected
   revision. Supporting safely contained links is a separate enhancement.

3. **Make trusted pytest integration explicit.** Plugin autoload is disabled,
   plugin environment variables are cleared, and suite selectors reject `-p`.
   Installed AnyIO or pytest-django therefore needs explicit registration through
   image/bootstrap configuration. Add a documented recipe and a validated,
   frozen runner plugin list rather than requiring custom Python launchers.
   [pytest documents explicit plugin loading](https://docs.pytest.org/en/stable/how-to/plugins.html).
   Also explain that import mode and historical framework versions matter:
   Requests failed under pytest 6.2.5 with forced importlib mode and passed with
   7.4.4; Tornado's old unittest collection failed under 8.4.2 and passed with
   7.4.4. These observations do not establish a universal pytest version pin.

4. **Make failures useful in terminals and CI.** Requests' first headline showed
   a JUnit conflict while its actionable ImportError was buried in JSON. Missing
   plugin fixtures were similarly absent from Markdown summaries. Pillow and
   Certifi preflight rejections produced no structured report. Keep strict
   evidence validation, show a bounded root-error excerpt, separate oracle/suite
   counts, and record setup rejection consistently. Name `backport.patch` in the
   output summary and usage guide.

5. **Document suite selection and its coverage cost.** Bleach's intentional
   xfails become skipped evidence and prevent verification under the existing
   conservative policy. Marker filters are rejected; selecting 49 explicit
   selectors excluded two parameter groups containing those xfails, including
   other cases in those groups. Document paths/node IDs, show a worked selection
   recipe, and distinguish xfailed from skipped in diagnostics. Preserve strict
   security-oracle requirements; do not silently ignore unsuccessful evidence.

6. **Provide concrete image and eligibility examples.** Add a small trusted-image
   Dockerfile, optional offline-wheel instructions, a pip/venv installation
   alternative, and a command to inspect changed files before image preparation.
   Explain `.py` scope, extensionless generators, and package-data fixes early.
   Describe rejected files as unsupported changed files when their runtime role
   is unknown. Native extensions need binaries supplied by the trusted image;
   Pillow's independent trial required an explicit bridge for that setup.

Missing uv, Docker socket permissions, and container PyPI timeouts were environment
failures. Premature runs before image builds finished, unsupported Docker flags,
an incorrect initial Bleach control, and exploratory launcher mistakes were
operator errors. They are preserved in individual reviews and are not counted as
Seam correctness defects. No false verified verdict was demonstrated.

## AI adaptation

Bleach's independent first-use review used a supplied patch. A subsequent,
separately labeled Flash variant used the same frozen oracle, configuration,
image, and selected suite. Direct application failed on older source contexts;
one model-generated candidate then verified. The canonical patches differ, and
each passed the recorded checks.

The Flash report records 9 API calls, 81,565 input tokens, 5,156 output tokens,
and an estimated peak, uncached cost of $0.0306567. This is an estimate, not an
invoice. The run preserved all 326 selected target cases. Credentials were
handled by the CLI; they are excluded from the evidence archive. This one case
does not establish model reliability across libraries or providers.

## Evidence and limits

The companion `seam-evaluations-2026-10-17.zip` contains individual reviews,
machine-readable results, frozen inputs, canonical patches, unsuccessful reports,
reproduction recipes, a SHA-256 manifest, and the separate evidence cross-check.
The VM originals are under `.runs/evaluations/2026-10-17/`. Private transcripts,
credentials, upstream clones, environments, downloaded wheels, and image layers
are excluded. Historical absolute paths need adjustment on another machine.

Only the recorded oracles, controls, revisions, images, and selected suites were
checked. Shared two-CPU VM timings are not performance measurements. The study
did not certify complete CVE remediation, full library suites, hostile evidence
forgery resistance, browser behavior, deployed cache/proxy behavior, or broad
model quality. Read the [execution boundaries](security.md) when interpreting a
verified result. Product fixes were not mixed into this baseline evaluation.
