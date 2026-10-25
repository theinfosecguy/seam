# Tape adapter checks

The adapter passed 65 synthetic checks and ran the original selected qs and fast-uri suites at all four frozen revisions. These are framework checks; they do not establish a security fix or an AI backport result.

The checks use Tape 5.10.3 and Node 24.22.1 in image `sha256:277b9b3c5907cb97119813d8c5f71cb3a4f92bf94ed60910ccb0e2d53837d09d`. The tested adapter resource has SHA-256 `6795d26b4898a9de9881dd9216ad7494403f9c1d90ad33f5900c650d326e1894`.

Each named scope contributes one reported case for its own assertions. Nested scope paths retain their identities, repeated assertion labels are allowed, and duplicate scope identities remain inconclusive. Visible skips and todos stay skipped. Mismatched plans, empty leaves, late assertions, early exits, setup errors and exceeded limits produce errors.

Review found a concrete omission in the development adapter: an independent Tape harness in a child process or worker could fail while the observed parent passed. The four fixtures in `cross-process-regression.json` reproduce that omission. The final adapter rejects worker, child-process and cluster access through module imports and `process.getBuiltinModule`. A separate process-replacement fixture showed that `process.execve` could also leave the observed harness; that API now produces an error. `process-replacement-regression.json` records the before/after result and an ESM named-import check. The incomplete development adapters were not released.

`synthetic-summary.json` records expected and observed outcomes with fixture and report hashes. `original-suites-summary.json` records the eight original-suite runs and immutable source references. Their disposable source copies were compared byte-for-byte with the earlier frozen source archives. Raw process output and copied library sources are excluded.

The implementation uses Tape's documented [object stream and harness APIs](https://github.com/tape-testing/tape/blob/v5.10.3/readme.markdown) and Node's [synchronous module hooks](https://github.com/nodejs/node/blob/v24.22.1/doc/api/module.md). Reporting uses a separate bounded channel and waits for the child process to finish.

## Reproduce the synthetic checks

Load the study's image archive or rebuild its pinned image recipe first. From this directory in a Seam checkout:

```sh
adapter_dir="$(git rev-parse --show-toplevel)/src/seam/execution/resources"
touch report.xml
chmod 666 report.xml
docker run --rm --network none --cap-drop ALL --security-opt no-new-privileges \
  --read-only --user 65534:65534 --memory 256m --pids-limit 64 --cpus 1 \
  --env NODE_PATH= --env NODE_OPTIONS= \
  --tmpfs /work:size=32m,mode=1777 --tmpfs /tmp:size=32m,mode=1777 \
  --mount type=bind,source="$PWD",target=/proof,readonly \
  --mount type=bind,source="$PWD/fixtures",target=/fixtures,readonly \
  --mount type=bind,source="$adapter_dir",target=/adapter,readonly \
  --mount type=bind,source="$PWD/report.xml",target=/report.xml \
  sha256:277b9b3c5907cb97119813d8c5f71cb3a4f92bf94ed60910ccb0e2d53837d09d \
  node /proof/run-synthetic.cjs > synthetic-results.json
```

Support is limited to one explicit suite file in one process, Tape 5.10.3, and CommonJS or synchronous ESM. Top-level await and custom harness/reporting APIs remain unsupported. These controls cover cooperative framework use; they do not make in-process code or reports tamper-proof.
