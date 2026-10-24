# Reproducing the follow-up

Install the tested wheel from the
[experimental release](https://github.com/theinfosecguy/seam/releases/tag/v0.5.0.dev2).
Verify its release checksum before installation. Use Linux/amd64 and a controller
with Python 3.12 or newer, Git and Docker. Keep API keys outside target checkouts
and containers. No API key is needed to verify a supplied reference patch.

Start by checking `SHA256SUMS` from this directory:

```sh
sha256sum --check SHA256SUMS
```

## Exact execution images

The optional `seam-framework-eval-images-2026-10-25.tar.gz` asset contains four
recorded images: Marshmallow's Python 3.12 environment, Pydantic's Python 3.9.25
environment, the Tape investigation environment and Node 20.18.1. Their identities
and the archive verification are in `validation/image-archive-proof.json`.

```sh
gzip -dc seam-framework-eval-images-2026-10-25.tar.gz | docker load
```

js-yaml uses the dependency image `sha256:52f40f96867d88d68ced00067878ab5b917744d17f5649b82506f43e72d88cba`
from the [previous release's image archive](https://github.com/theinfosecguy/seam/releases/tag/v0.5.0.dev1).
The five npm regression cases use the same earlier image archive and
[earlier inputs](https://github.com/theinfosecguy/seam/blob/main/evals/expanded-backports/2026-10-24/README.md).

All new archive blobs and descriptor references, image platforms and filesystem
identities were verified. Restoration into a clean Docker daemon was not tested.
Build recipes and dependency hashes are retained; a rebuild creates new evidence
and may produce a different image ID. Python's portable Marshmallow recipe has
not been qualified; `Dockerfile.executed` records the exact tested construction.

## Run a reference

Obtain an independent clone of the public repository named in `case.json`.
Fetch and resolve all four exact commits before execution. Do not use shared
Git objects or replace the target source with an installed distribution.
The selected implementation-only reference patch is applied to the target
baseline; the maintainer backport commit supplies comparison provenance.

For js-yaml, from this directory:

```sh
git clone https://github.com/nodeca/js-yaml.git /path/to/disposable-js-yaml
seam run --repo /path/to/disposable-js-yaml \
  --fix 383665ff4248ec2192d1274e934462bb30426879 \
  --target 37caaad57dc37d350d9a4577a5da53f482bb2983 \
  --config cases/js-yaml/harness.toml \
  --candidate-patch cases/js-yaml/reference.patch \
  --output /path/to/new-evidence
```

The recorded Docker prefix is `sudo -n docker`; adapt it in a copied configuration
if your setup differs, and retain that new configuration's hash. Inspect the
four phases, expected security marker, normal controls and every selected
project test. Repeat with a fresh output directory. A separate ineffective patch
must fail the same security regression while preserving the existing suite and
controls. The exact ineffective patches used here are under `results/attempts`.

The two Python cases have their own [image and scope notes](python/README.md).
For Pydantic, compare the original `python/cases/pydantic/harness.toml` with
`python/cases/pydantic-prepend/harness.toml`; only the import mode changes.
The original configuration is expected to remain inconclusive on the recorded
image. Do not count these variants as separate issues.

## Reporting probes and AI experiment

The [Tape notes](tape/README.md) include a reproducible isolated probe command.
Those probes examine reporter completeness and must not be counted as security
qualifications. Node 20 fixture XML is preserved verbatim beside each synthetic
source file; it lacks the file identities required by Seam's JavaScript parser.
For example, from this bundle's root, print a fresh ordinary-pass report:

```sh
docker run --rm --network none --read-only --user 65534:65534 \
  --cap-drop ALL --security-opt no-new-privileges --memory 128m --pids-limit 64 \
  --cpus 1 --env NODE_OPTIONS= --env NODE_PATH= --workdir /work/repo \
  --mount type=bind,source="$PWD/runtime/node20-fixtures/pass",target=/work/repo,readonly \
  sha256:796789f15b456fb7a2245190e89f6648ae71145b3e45c84a7bf55aa50d86ff01 \
  node --test --test-reporter=junit /work/repo/test.mjs
```

Timing and container metadata will differ from the recorded XML. Its missing
source-file attributes should still make `parse_junit(..., runner="node")` reject
the evidence.

The js-yaml AI experiment used the same frozen case, without `--candidate-patch`,
with `--provider deepseek --model deepseek-flash`, a $1 API budget, at most 32
calls and explicit conservative pricing/context settings in
`validation/provider-pricing.json`. An operator must supply their own key using
an explicit external environment file. Re-running a changing model alias is a
new experiment, not a reproduction of the recorded model response.
