---
pretty_name: Seam Python Backport Evaluations
language:
  - en
license: other
license_name: mixed-upstream-licenses
license_link: README.md
size_categories:
  - n<1K
tags:
  - code
  - python
  - evaluation
configs:
  - config_name: default
    data_files:
      - split: test
        path: tasks.jsonl
---

# Seam Python backport evaluations

Eight small, public cases exercise an existing Python backport test harness.
Each case pins an upstream parent, fix and historical target, freezes an
external regression oracle and controls, selects existing project tests, and
includes a reference implementation patch. All reported verification is limited
to those inputs and selected checks.

This is a reproducible reference collection. A reference qualification run uses
the supplied patch and makes no model API calls. Passing it establishes that the
case works with the recorded harness and environment. Model adaptation results
must be reported separately, including unsuccessful and incomplete attempts.

## Contents

| Case | Upstream asset license | Files |
| --- | --- | --- |
| Jinja2 | BSD-3-Clause | [Case](cases/jinja2/case.json), [license](cases/jinja2/LICENSE.upstream) |
| Requests | Apache-2.0 | [Case](cases/requests/case.json), [license](cases/requests/LICENSE.upstream), [notice](cases/requests/NOTICE.upstream) |
| Flask | BSD-3-Clause | [Case](cases/flask/case.json), [license](cases/flask/LICENSE.upstream) |
| h11 | MIT | [Case](cases/h11/case.json), [license](cases/h11/LICENSE.upstream) |
| sqlparse | BSD-3-Clause | [Case](cases/sqlparse/case.json), [license](cases/sqlparse/LICENSE.upstream) |
| python-multipart | Apache-2.0 | [Case](cases/python-multipart/case.json), [license](cases/python-multipart/LICENSE.upstream) |
| urllib3 | MIT | [Case](cases/urllib3/case.json), [license](cases/urllib3/LICENSE.upstream) |
| Authlib | BSD-3-Clause | [Case](cases/authlib/case.json), [license](cases/authlib/LICENSE.upstream) |

Each case directory contains `case.json`, `harness.toml`, `oracle.py`,
`reference.patch`, `Dockerfile`, `requirements.lock` and upstream license files.
Additional reviewed assertions, fixture pins or historical environment helpers
are declared in the case assets. The JSON records contain repository URLs,
immutable revisions, asset hashes and case-specific notes.

`dataset.json` identifies dataset revision **v0.1.0**. `tasks.jsonl` is the
generated public catalogue, with one record per case. It includes upstream and
target identifiers, a problem statement, a reference patch and Seam-specific
metadata. Case assets remain separate files so their hashes and licenses can be
checked. The JSONL file contains reference answers and should not be given
wholesale to a patch-generating model.

The source package contains inputs for rebuilding environments. Upstream source
checkouts, dependency wheels, container layers, private transcripts, model
credentials and raw run logs are excluded from it. An optional, separate image
archive can supply the qualified environments without rebuilding them.

## Reproduce and identify a run

Use Linux on x86-64 with Git, a working Docker daemon and Python 3.12 or newer
for the controller. Historical releases run under the interpreter and pinned
dependencies selected by each container recipe. Fetching repositories, base
images and dependencies requires network access; test containers run with
network access disabled.

After installing the reviewed harness wheel, validate a downloaded dataset and
qualify each case from a fresh output directory:

```bash
seam eval list --dataset /path/to/python-dataset
seam eval check --dataset /path/to/python-dataset
seam eval qualify jinja2 --dataset /path/to/python-dataset \
  --build-image --output /path/to/new-qualification/jinja2
```

Repeat the last command for `requests`, `flask`, `h11`, `sqlparse`,
`python-multipart`, `urllib3` and `authlib`. `qualify` repeats the reference run
and checks a negative candidate without a model. For a single reference replay,
use `seam eval run CASE_ID --mode reference --build-image --output NEW_OUTPUT`;
pass `--dataset` when using a separate dataset directory. Add
`--docker 'sudo -n docker'` only when your local Docker setup requires it.

`--build-image` rebuilds the pinned public recipe. Omitting it uses the case's
configured local image, either previously built or loaded from the optional
release archive. Qualification reuses its first immutable execution image ID for
the repeat and negative runs.

The planned
[v0.3.0 GitHub Release](https://github.com/theinfosecguy/seam/releases/tag/v0.3.0)
distributes the source dataset, harness wheel, qualification evidence and
`SHA256SUMS`. Its optional `seam-python-evals-images-0.1.0.tar.gz` is for
**Linux x86-64 only** and preserves all eight configured image tags. After
downloading the archive and `SHA256SUMS` from that release, verify before loading:

```bash
sha256sum --check --ignore-missing SHA256SUMS
gzip -dc seam-python-evals-images-0.1.0.tar.gz | docker load
seam eval run jinja2 --mode reference --output /path/to/new-jinja2-evidence
```

The final command uses the installed wheel's bundled dataset and needs no
`--build-image`. Add `--dataset /path/to/python-dataset` to use a separately
downloaded source dataset. Loading images requires no registry account; pinned
public recipes remain available for rebuilding.

A replay output contains `source/`, `evidence/` and `run-manifest.json`; a build
also records its bounded output in `image-build.log`. A setup failure can leave
an inconclusive manifest without a test report. Qualification groups reference,
repeat and negative outputs under one directory and writes `qualification.json`.

Retain the dataset revision, exact harness commit and installed release version,
catalogue and asset hashes, base-image manifest digest, built image ID, and run
manifest with every result. Image tags and release names alone do not identify
a reproducible run. A rebuild may produce a different local image ID even from
the same recipe; record the image actually executed.

## Trust and evaluation limits

Review the recipes and frozen case assets before execution. Operator
configuration, oracles, reference patches, assertion updates and fixture pins
are trusted inputs. Repository content and test output do not grant permission
to change endpoints, credentials or tool access. Containers are disposable and
run without controller credentials, the host Docker socket or the original
checkout mounted inside them. Docker and cooperating target code remain
execution assumptions.

These cases and their upstream fixes are public. A model may have seen them
during training or prior use. Keep reference patches, expected outcomes,
qualification artifacts and hidden oracle details out of model input when
measuring adaptation; describe any intentional exposure. This collection has no
claim of a private holdout or contamination-free model ranking.

The selected cases are a convenience sample. They do not estimate ecosystem
success rates, establish full project-suite coverage, certify remediation, or
measure production performance. Authlib includes explicitly reviewed hashes of
eight published test PEM files; the files come from the pinned source checkout,
and the image supplies dependencies only. urllib3 declares a separately
reviewed assertion update for the intended historical policy change.

## Licenses

Newly authored harness and compilation material follows the project's MIT
license. Upstream-derived patches, tests and other copied assets retain the
licenses and notices linked above. The dataset metadata says `other` because
the bundle has several licenses; it introduces no replacement license. Review
each case's provenance and preserve its license and notice files when copying
or redistributing it. Downloaded dependencies and base images have their own
licenses and are excluded from the source dataset.

## Publication status

The GitHub Release above is the publication target. Publish only after all eight
cases qualify against the same dataset revision and harness release, with
matching qualification evidence and downloadable artifacts. A historical local
result does not qualify a changed package. The repository's publication guide
describes the release procedure and the separation between reference and model
results.
