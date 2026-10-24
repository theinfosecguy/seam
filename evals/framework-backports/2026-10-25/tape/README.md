# Tape reporting investigation

Decision: keep Tape unsupported in this release. These are runner prerequisite probes, not Seam security qualifications or AI backport results.

The pinned Tape 5.10.3 object stream preserves explicit test names, parent relationships, assertion outcomes and closure events. Grouping each scope's own assertions gives meaningful identities without inventing assertion ordinals. However, the stream alone cannot establish that every original test was observed. Tape documents both [object streams](https://github.com/tape-testing/tape#object-stream-reporter) and [independent harnesses](https://github.com/tape-testing/tape#var-htest--testcreateharness).

| Original selected suite | Upstream parent | Upstream fix | Target parent | Maintainer backport |
| --- | ---: | ---: | ---: | ---: |
| qs `test/parse.js` | 81 scopes / 215 assertions | 82 / 223 | 80 / 211 | 81 / 219 |
| fast-uri `test/scheme-validation.test.js` | 7 / 56 | 8 / 105 | 7 / 56 | 8 / 105 |

All eight original suites exited zero with all observed scopes closed, one stream completion, and no observed skips, todos or duplicate full scope names. The target parent of each library was repeated once: exact file-qualified scope identities and assertion results matched. Other revisions were not repeated. Source commits, archive hashes and raw output hashes are in `outcomes.json`.

The failure probes expose the work needed before implementing an adapter:

- `test.skip(name, callback)` is absent from Tape's text and object streams; `{skip:true}` and assertion `t.skip` are visible. The pinned [static skip implementation](https://github.com/tape-testing/tape/blob/v5.10.3/lib/test.js) constructs an unattached test.
- A custom harness can run a failing test while the observed default harness reports a complete passing stream and the process exits zero. A second Tape singleton can also escape observation. Complete scope and zero exit checks do not close this gap.
- A late asynchronous failure occurs after stream completion and is absent from the stream, but changes the process exit to one. The process result must be checked as well as stream closure.
- A short plan emits its failure after the scope's end event. Collect until stream completion; incomplete plans, unended scopes, early exits, import errors and asynchronous throws remain unresolved.
- `.only` is rejected for the default singleton with the pinned `NODE_TAPE_NO_ONLY_TEST=true` setting. This does not govern independently created harnesses.
- An empty leaf scope is observable but contains no assertion. An adapter must preserve or explicitly reject it. Duplicate full scope identities must remain ambiguous.
- Whole assertion events may contain circular values. The first research collector failed on qs for that reason; the corrected collector projects only scalar identity, outcome and lifecycle fields. These preparation failures were not library or Seam failures.

The existing reporters do not supply a complete replacement. [tap-junit 5.0.4](https://github.com/dhershman1/tap-junit/blob/v5.0.4/src/index.js) produces three indistinguishable identities for the nested same-name assertion probe. [The official tap reporter](https://tapjs.org/reporter/), pinned to `@tapjs/reporter` 4.5.0, emits no testcases for raw top-level Tape assertions. `tap-parser` 18.3.4 detects malformed plans and bailouts, but text parsing cannot restore the parent scopes already flattened by Tape. No custom TAP parser was written.

A future adapter should use structured events, one explicit scope per reported case, a separate bounded report file, strict process/lifecycle checks, and enforced accounting for skipped tests, custom harnesses and module singletons. An engineering estimate is 100–180 lines of adapter logic plus failure-mode tests. This is an estimate, not an implemented or qualified design. A generic plugin framework is unnecessary.

## Reproduce the synthetic probes

`package-lock.json` pins all dependencies and registry integrity values. The image build runs `npm ci --ignore-scripts`; target execution uses no network, credentials, Docker socket or original checkout. The recorded image is `sha256:823485b739c108393310be04e79f787db2e4476fa679ae4204080ae29e38d566` on Node 24.22.1. A rebuild may have a different image ID; retain its actual ID and lock hash.

Build from this directory:

```sh
docker build -t seam-tape-proof .
```

Run the probes in the image with this directory mounted read-only at `/proof`:

```sh
docker run --rm --network none --cap-drop ALL --security-opt no-new-privileges \
  --read-only --user 65534:65534 --memory 256m --pids-limit 64 --cpus 1 \
  --env NODE_TAPE_NO_ONLY_TEST=true --tmpfs /tmp:size=32m,mode=1777 --mount type=bind,source="$PWD",target=/proof,readonly \
  seam-tape-proof node /proof/run-probes.mjs
```

To reproduce an original suite, obtain the immutable public source revision listed in `outcomes.json`, verify its recorded snapshot or commit, and mount a disposable copy read-only at `/sources`. Run `node /proof/object-events.cjs /sources/test/parse.js` for qs or the selected fast-uri test path in the same isolated image. This diagnostic collector intentionally does not produce a verification verdict.

Raw logs, local paths and copied target source are excluded from this publication. No claim is made for other Tape versions, browser tests, custom harness coverage or universal test completeness.
