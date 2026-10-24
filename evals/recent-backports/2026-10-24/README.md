# Recent Python backport evaluation — 24 October 2026

Four public fixes across three libraries were evaluated after Seam inventory,
directory-link and documentation changes. Maintainer references verified for all
four cases; the two Django references precede the harness fixes. Post-fix runtime
replays verified both stored Django model patches. Fresh LiteLLM model adaptation
verified; two fresh PydanticAI model attempts remained inconclusive. A deliberately
ineffective Django patch failed as intended.

Read the [human-readable results](../../../docs/recent-backports.md),
[machine-readable summary](summary.json) and [matrix audit](audits/matrix-audit.json).
The summary includes all 12 post-fix case attempts, including four environment setup
failures, both incomplete model attempts and the negative check. All ten earlier runs
are under `evidence/historical/` and are excluded from those totals.

## What is included

| Case | Frozen inputs and licensing | Source history | Selected target suite |
| --- | --- | --- | ---: |
| Django domain | [Case](cases/django-domain/case.json), [license](cases/django-domain/LICENSE.upstream), [Python notice](cases/django-domain/LICENSE.python.upstream) | Full history | 15 |
| Django Vary/cache | [Case](cases/django-vary/case.json), [license](cases/django-vary/LICENSE.upstream), [Python notice](cases/django-vary/LICENSE.python.upstream) | Full history | 6 |
| PydanticAI Host | [Case](cases/pydanticai-host/case.json), [license](cases/pydanticai-host/LICENSE.upstream) | Full hydrated history | 4 |
| LiteLLM contexts | [Case](cases/litellm-context/case.json), [license](cases/litellm-context/LICENSE.upstream) | Exact selected snapshots, original depth-two histories | 10 |

Each case supplies immutable parent/fix/target/backport commits, an external oracle,
controls, selected existing tests, a reference patch, recorded environment recipes
and installed dependency versions. Django includes stored earlier model patches;
its domain case also includes the ineffective negative patch. Successful new and
rejected model candidates are retained alongside their evidence records. Reference
patches and reports contain answers; keep them out of model context when measuring
adaptation.

`manifest.json` identifies original source bytes and each public derivative with
separate SHA-256 hashes. Source identifiers beginning `gap-fixes/` and
`original-evaluation/`, or strings beginning `source:`, are logical provenance
labels, not download locations. Original evidence remains frozen; it was not edited
for publication. Exact-copy assets retain their original hashes. `SHA256SUMS`
identifies every distributed file other than itself.

Published `evidence.json` files preserve status, revisions, image IDs, original
oracle/config/patch hashes, actual pytest arguments, timings, test identities and
outcomes. Raw stdout/stderr, testcase messages and embedded bootstrap code are
omitted with hashes; each testcase records whether its original message contained
the configured security failure marker. These are publication derivatives, not
original report files accepted by `seam inspect`. Config copies normalize the
oracle path to `oracle.py`, so their bytes differ from the original absolute-path
config and its recorded hash.

No credentials, provider conversations, raw model explanations, raw logs, source
clones, virtual environments, dependency wheels or container layers are included.
The authentic PydanticAI `METADATA` files were generated in isolated containers;
discarded host-generated metadata is excluded. No LiteLLM enterprise implementation
is redistributed. Its copied patches concern paths covered by the upstream MIT
license. New compilation material follows the project MIT license; copied upstream
material retains the supplied licenses and notices.

## Reproduce a reference

Use Linux x86-64, a working Docker daemon, Git 2.38 or newer, and Python 3.12 or
newer for Seam. Target code runs under the image's Python. Clone the public upstream
repository listed in `cases/CASE/case.json`, retaining immutable selected commits.
Run `seam doctor` to record the installed harness, and retain its exact commit and
wheel hash. The tested historical wheel identity is in
[`provenance/tested-implementation.json`](provenance/tested-implementation.json).
A new build needs a new result identifier.

Historical recipes under `environment/recorded/` preserve the original local image
parents. Those IDs identify executed bytes but cannot be pulled from a public
registry. Their initial Python tags were not all pinned; dependency wheels and
images were not redistributed. Historical images therefore cannot be reconstructed
bit-for-bit from this supplement alone.

The separate `environment/rebuild/` recipes flatten the recorded dependencies,
plugin/settings and authentic metadata onto the public Python digest recorded by
the Django environment. They are derived rebuild helpers, **not qualified historical
images**. They were not executed during these historical trials. They install
version pins without artifact hashes; inspect and record newly resolved artifacts.
A fresh build must pass the complete reference matrix before model comparison.
PydanticAI metadata corresponds only to the recorded revisions and this case's
patch; do not reuse it for arbitrary commits. All target implementation still comes
from Seam's staged checkout.

For example, from this directory, prepare a Django domain reference:

```bash
git clone https://github.com/django/django.git checkouts/django
docker build -t seam-recent-django-domain:rebuild \
  cases/django-domain/environment/rebuild
```

Copy `cases/django-domain/harness.toml` to a new working directory together with its
`oracle.py`. Change only `[runner].image` to the rebuilt image and `[runner].docker`
to match your Docker setup. Keep the original configuration and report this as a
new config/image identity. Then run, using that working directory:

```bash
seam run --repo /path/to/checkouts/django \
  --fix a5de13f1491f1dbf2bb0ad9b91570524ebbc8acd \
  --target 6c66eb8cec52b303af85c2c6e4dd00aa37654dbc \
  --config harness.toml --candidate-patch /path/to/cases/django-domain/reference.patch \
  --output /path/to/new-domain-reference
```

Repeat with each case's immutable commits and assets. Supplied-patch execution
uses no model or API key. For the negative check, use
`cases/django-domain/negative-no-fix.patch` and a new output directory: expect a
failed security assertion while all controls and the existing suite still pass.
An inconclusive reference establishes neither vulnerability nor a valid backport.
Inspect generated original reports and the complete four-phase matrix, not just
the CLI exit code.

Fresh AI adaptation must use the same qualified oracle, suite, image and frozen
configuration as its reference. Replace the mutually exclusive supplied-patch mode
with explicitly configured model/provider arguments from the
[usage guide](../../../docs/usage.md). Do not supply reference patches, successful
reports or prior model outputs to the model. Record unsuccessful attempts, exact
model ID, call/token limits, pricing and pending reservations. The historical new
runs used `deepseek-flash`, $1 per run and at most 32 requests. Public fixes may
already be in training data; this is not a private-holdout model benchmark.

## Interpretation

Verification is scoped to the recorded regression, normal controls and selected
suite. PydanticAI covers Host handling and app construction, not packaging or a live
server. LiteLLM covers inert encryption helpers and existing helper tests, with a
separate source comparison of both changed implementation files. Its dependency
union is disclosed in `cases/litellm-context/final-environment-deviations.json`;
it is not target-lock-identical. No full authentication service or real external
model/tool is exercised. Full library suites, complete advisory remediation,
production behavior and broad model reliability remain unestablished.
