# Experimental npm backport inputs

This bundle contains **20 standalone cases across 17 npm packages**, plus source research covering 25 libraries. It provides frozen inputs for evaluating Seam's JavaScript support. These cases are **not registered in `seam eval`**, and this bundle makes no execution or qualification claim. The accompanying runtime report supplies results and the tested controller wheel.

Each case includes an independent regression oracle, its harness configuration, implementation patches from the newer fix and maintained older line, exact Git revisions, and the upstream license. `reference.patch` contains implementation changes; the full maintainer commit may also change dependencies, tests, or metadata. `cases.json` lists the cases. `research/catalogue.json` records the broader source and release-line evidence.

`PROVENANCE.json` distinguishes unchanged input bytes from normalized case/research metadata. Host checkout paths, raw logs, source archives, cloned repositories, and full upstream test copies are omitted. Absolute `/work` and `/opt/seam` paths describe the container layout. Original upstream tests are retrieved from the pinned Git revisions.

Verify the bundle first:

```sh
sha256sum --check SHA256SUMS
```

Install the accompanying JavaScript-capable wheel into a fresh environment, then check prerequisites. Python 3.12+, Git 2.38+, and Docker are required. Configurations use `sudo -n docker`; adjust a copied configuration if your Docker setup differs.

Use the environment created from the parent bundle README. From this `npm`
directory its executable is:

```sh
../../seam-env/bin/seam doctor
```

The 20 configurations reference exactly three Linux/amd64 execution images, listed in `images/images.json`. **Exact replay requires image archives matching those IDs.** This input bundle contains recipes and locks, not image archives. Local Mocha/dependency image IDs are not public registry addresses.

Alternatively, rebuild from the pinned Node base and npm integrity locks:

```sh
docker build --platform linux/amd64 -t seam-node-runtime:rebuilt images/node-mocha
docker build --platform linux/amd64 \
  --build-arg BASE_IMAGE=seam-node-runtime:rebuilt \
  -t seam-npm-dependencies:rebuilt images/revision-dependencies
docker image inspect --format '{{.Id}}' seam-npm-dependencies:rebuilt
```

Builds need registry access; installation scripts are disabled. Runtime tests run without network access. The public dependency Dockerfile accepts the rebuilt base explicitly; `Dockerfile.executed` preserves the original recipe and local base ID. A rebuild does not reproduce the historical image ID automatically. Copy a case folder outside this bundle, change its `runner.image` to the rebuilt ID, and record the new image/configuration hashes as a new trial. Keep the other settings and per-revision dependency paths intact. Missing dependency maps and unsupported original frameworks remain evaluation gaps.

Clone ordinary maintainer repositories, including their normal history and tags. Do not use shared-object clones or substitute packaged implementations. For example, with matching recorded images available:

```sh
mkdir -p ../../npm-rerun
git clone https://github.com/debug-js/debug.git ../../npm-rerun/debug
git -C ../../npm-rerun/debug fetch --tags origin
../../seam-env/bin/seam run \
  --repo ../../npm-rerun/debug \
  --fix c38a0166c266a679c8de012d4eaccec3f944e685 \
  --target 52e1f21284322f167839e5d3a60f635c8b2dc842 \
  --config cases/debug/harness.toml \
  --candidate-patch cases/debug/reference.patch \
  --output ../../npm-rerun/debug-report
```

Use each case's immutable revisions and configuration for the other cases, choosing a new output directory every time. If a required object is unavailable, fetch the maintainer release ref containing it; preserve any fetch failure instead of changing revisions. `--candidate-patch` verifies a supplied patch without an API key. It measures verification and compatibility; it does not measure fresh model adaptation.

Preserve failed imports, missing dependencies, incompatible test frameworks, skipped assertions, and collection changes as inconclusive evidence. A passing wrapper around a foreign framework does not prove its original test identities ran.

Seam-authored inputs and documentation use the included MIT license. Upstream patches retain their case-specific `LICENSE.upstream` terms; dependencies retain their own package licenses.
