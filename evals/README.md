# Evaluation packages

The [Python package](python/README.md) contains eight public cases for testing
Seam's backport workflow: Jinja2, Requests, Flask, h11, sqlparse,
python-multipart, urllib3 and Authlib. Each case includes an external oracle,
selected project tests, a reference implementation patch, a container recipe,
dependency hashes and provenance. It fetches the upstream checkout by immutable
commit rather than including a source archive.

A reference run asks whether these frozen inputs can reproduce the recorded
before/after behavior and verify the supplied patch. It uses no model or API key.
It does not measure whether a model can find or adapt that patch. Historical
model runs in the project documentation are separate experiments.

From the repository root, install the locked development environment and check
the catalogue before rebuilding and qualifying a case:

```bash
uv sync --frozen
uv run --frozen seam eval check --dataset evals/python
uv run --frozen seam eval qualify jinja2 --dataset evals/python \
  --build-image --output .runs/eval-qualification/jinja2
```

Use a fresh output directory for each qualification. Repeat for all eight case
IDs listed in the [dataset card](python/README.md). The installed wheel also
includes the default dataset, so `--dataset` can be omitted when evaluating its
bundled revision. A separately downloaded dataset needs an explicit directory.

See the [publication guide](../docs/eval-publication.md) for release evidence,
license review and publishing the same package as a Hugging Face dataset.

Keep generated images, checkouts, reports, logs and credentials outside this
directory. Publish source inputs and a reviewed summary only after fresh
qualification succeeds for every case in the release. A setup failure, skipped
check or incomplete run remains unresolved evidence.

## Recent case-study evidence

The [24 October 2026 supplement](recent-backports/2026-10-24/README.md) publishes
four recent backport comparisons across Django, PydanticAI and LiteLLM. It includes
normalized evidence for unsuccessful setup/model attempts and separates stored
patch replays from fresh model adaptation. It is a historical evidence supplement,
not an additional `seam eval` catalogue or a qualification of changed releases.
