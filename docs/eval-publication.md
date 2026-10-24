# Publishing the Python evaluations

Publish the source dataset under [`evals/python`](../evals/python/README.md)
with the harness wheel and an optional Docker image archive in the
[v0.4.0 GitHub Release](https://github.com/theinfosecguy/seam/releases/tag/v0.4.0).
This is the release target; publish it only after all eight cases qualify.
The qualification workflow does not publish artifacts.

## Freeze the release inputs

Record the proposed dataset revision and exact harness Git commit. Build and
install the intended harness release, and check `seam doctor` to confirm which
package version and executable are running. A version label does not replace
the source commit or wheel hash.

Review every case's upstream URL, parent/fix/target commit IDs, oracle, selected
suite, supplied patch and asset hashes. Check container base-image manifest
digests, target platform and dependency hashes. Preserve the upstream license
files and Requests' notice. Any assertion update or fixture allowance requires
the explicit review and hash pins described in the
[usage guide](usage.md#review-existing-test-expectations).

Make a new dataset revision when a case input changes. Keep historical results
with the exact revision that produced them. Do not replace a failed attempt
with a successful rerun under the same result identifier.

## Reference qualification

Qualification runs the supplied reference implementation patch with no model
or API key. Rebuild the container for every case, fetch the pinned source, and
execute the upstream-parent/fix and target-baseline/backport matrix. Keep setup
failures, missing prerequisites, skips and timeouts visible; they do not count
as passing cases.

From a checkout of the proposed harness release:

```bash
uv sync --frozen
uv run --frozen seam eval check --dataset evals/python
uv run --frozen seam eval export --dataset evals/python \
  --output .runs/proposed-tasks.jsonl
cmp .runs/proposed-tasks.jsonl evals/python/tasks.jsonl
uv run --frozen seam eval qualify jinja2 --dataset evals/python \
  --build-image --output .runs/qualification/jinja2
```

The export output must be new. Repeat qualification for all eight case IDs in
the dataset card. `qualify` performs a reference replay, a repeat and a negative
candidate check; a single reference replay is available through
`seam eval run CASE_ID --mode reference --build-image --output NEW_OUTPUT`.
Use `--docker 'sudo -n docker'` only when required by the local daemon setup.

Run against fresh output directories outside the source package. Keep each run
manifest and report with the dataset revision, catalogue and input hashes,
installed harness version and commit, base-image manifest digest, and actual
execution image ID. Inspect the four phases and selected case identities,
rather than relying on a headline status copied from an earlier report.

The [evaluation workflow](../.github/workflows/evals.yml) runs on relevant pull
requests and manual dispatch without model secrets. It rebuilds environments
and exercises reference qualification. A green source-code unit-test workflow
alone does not qualify the dataset.

## Keep model results separate

A supplied reference patch succeeding does not demonstrate AI adaptation.
For a model experiment, freeze the same public case inputs and document the
model/provider identifier, exact limits, prompts and tool policy, reference
exposure, attempts, usage and estimated cost. Report the direct-application
baseline separately from generated candidates. Include setup failures and
inconclusive runs in the denominator you describe.

Keep oracle answers, reference patches and prior qualification reports out of
model context unless the experiment explicitly permits them. Public upstream
commits may already occur in training data, so this dataset cannot establish a
contamination-free model ranking. Do not include credentials, provider keys,
private prompts or raw private conversations in published evidence.

## Prepare the GitHub Release

After all eight cases qualify, copy the contents of `evals/python/` to a clean
dataset staging directory. Preserve the case hierarchy, machine-readable
catalogue, asset hashes, dataset card, licenses and notices. Include a concise
qualification summary that names the exact dataset and harness revisions and
points to the matching run manifests.

Review the staged file list before upload. Keep upstream clones, dependency
wheels, caches, virtual environments, credentials and raw logs out of the source
archive. Check that `tasks.jsonl` and case-relative assets resolve from its root,
then repeat catalogue validation on the staged copy.

Release the source archive, harness wheel, qualification summary and matching
run manifests with `SHA256SUMS`. Record the exact harness Git commit, wheel hash,
dataset revision, case hashes and execution image IDs. Tags alone do not identify
the tested inputs. The source archive retains its mixed upstream licenses and
notices; its `other` license label does not relicense them.

The optional `seam-python-evals-images-0.1.0.tar.gz` contains the eight qualified
Linux x86-64 images, with their configured local tags. Produce it from those
exact images after qualification:

```bash
set -o pipefail
docker save --platform linux/amd64 \
  seam-eval-jinja2:python-v1 seam-eval-requests:python-v1 \
  seam-eval-flask:python-v1 seam-eval-h11:python-v1 \
  seam-eval-sqlparse:python-v1 seam-eval-python-multipart:python-v1 \
  seam-eval-urllib3:python-v1 seam-eval-authlib:python-v1 \
  | gzip -n > seam-python-evals-images-0.1.0.tar.gz
sha256sum seam-python-evals-images-0.1.0.tar.gz
```

Include that checksum in `SHA256SUMS`. Verify the archive in a clean daemon with
`gzip -dc seam-python-evals-images-0.1.0.tar.gz | docker load`, compare loaded image
IDs with qualification evidence, and run a reference without `--build-image`.
The pinned public Dockerfiles remain the rebuild path. No registry login is
required for the release archive or the public base images and wheel URLs.

Publish the release only after reviewing its exact artifacts and checksums.
Confirm anonymous downloads and their hashes before announcing availability.

## Publish case-study evidence separately

The [recent-backport supplement](../evals/recent-backports/2026-10-24/README.md)
contains four additional historical case studies, outside the eight-case dataset.
Its normalized evidence includes all 12 post-fix attempts and all ten earlier
attempts, with setup failures, model failures and a runtime negative check intact.
Original and public derivative hashes are recorded separately; derivatives are
not original reports for `seam inspect`. Raw logs, credentials, provider
conversations, environments and source clones are excluded.

Keep this supplement and any new release qualification in separate directories.
Do not replace its tested `0.4.0.dev0` wheel identity with a new release version.
Historical local image IDs identify executed bytes; the included flattened rebuild
recipes have not themselves been qualified by those historical runs. Publish new
rebuild or release results with their own wheel, image, input hashes and attempt
identifiers, preserving unsuccessful attempts and the original evidence.
