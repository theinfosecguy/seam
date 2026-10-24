# Two additional Python cases

Werkzeug multipart buffering and Django language caching both passed reference verification, repeats and ineffective-patch rejection checks. They extend the earlier eight-case dataset; they are standalone inputs rather than registered `seam eval` entries.

Each case preserves immutable maintainer refs, an external regression oracle, normal controls, explicit original test selections, implementation patches and upstream licensing. Tests import the actual staged source under Python 3.12.12; no target package is installed or built. The existing test selections contain 21 Werkzeug cases and two Django methods. The complete project suites were not run.

The first Werkzeug probe passed on vulnerable source and was correctly classified inconclusive. Its bytes remain in `oracle.trial-01.py`; `oracle-correction.json` records the corrected bounded-buffer probe. The accepted `oracle.py` includes an early newline so that it exercises the changed buffering path. No timing threshold is needed.

Research snapshots under `research/` identify 21 distinct libraries and five exact maintainer commit pairs. Their not-run labels describe the research preparation stage; the runtime evidence separately records these two completed evaluations. The other 19 candidates remain unqualified. Distributor source-descriptor downloads do not establish signature verification or a runnable benchmark.

Load the accompanying execution-image archive and install the tested wheel with its locked controller dependencies, as described in the parent README. Clone each maintainer repository normally, fetch its recorded refs, and use a fresh output directory:

```bash
../../seam-env/bin/seam run --repo /path/to/werkzeug \
  --fix b1916c0c083e0be1c9d887ee2f3d696922bfc5c1 \
  --target 26f3e95168c5019d3dbf656c9042c19d621cb54f \
  --config cases/werkzeug-multipart/harness.toml \
  --candidate-patch cases/werkzeug-multipart/reference.patch \
  --output /path/to/new-evidence
```

Run this command from the `python` directory, or adjust its input paths. Configurations use `sudo -n docker`; changing that setting creates a new configuration hash. Resolve the Django refs from its `case.json` in the same way.

`image/Dockerfile.executed` identifies the exact layered build. `image/Dockerfile` is a portable rebuild recipe with hash-locked dependencies; its resulting image has not been qualified by these historical runs. Exact replay uses image ID `sha256:5c994eb5c630681a2141849869f60e16d5b69f55617067b910702c1795b9b0d2` from the release archive. Record and qualify a new image/configuration when rebuilding.
