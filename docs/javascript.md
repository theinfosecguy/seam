# Backporting JavaScript fixes

JavaScript support is experimental. Seam can check ordinary `.js`, `.mjs` and
`.cjs` implementation changes with Node's built-in test runner or Mocha. Python
and pytest remain the default. TypeScript compilation, npm lifecycle scripts and
other test frameworks need separate support.

You need an independently reviewed regression test, normal-behavior controls,
explicit existing test files, and a prepared Docker image. The current runner is
tested with Node 24 and Mocha 12. It runs tests against disposable source copies
without network access, host dependencies, npm credentials or a Docker socket.

## Configure a case

Write an external `node:test` file with a security test named `test_security` and
at least one `test_*` control. Import the library from `/work/repo`, where Seam
stages the selected revision. Give the security assertion a distinctive message;
it must fail for that reason before the fix and pass afterward.

```toml
[oracle]
path = "oracle.mjs"
security_test = "test_security"
controls = ["test_normal_input"]
failure_marker = "EXPECTED_SECURITY_ASSERTION"

[runner]
kind = "node"
image = "your-reviewed-image@sha256:IMAGE_DIGEST"
suite = ["test/parser.js"]
```

Use `kind = "mocha"` for existing Mocha suites. The external oracle still uses
`node:test`. The image must contain Mocha at
`/opt/seam/node_modules/mocha/bin/mocha.js`; Seam uses its native XUnit reporter,
disables project configuration discovery and rejects focused `.only` suites.
Use explicit test file paths rather than globs, npm scripts or command strings.

For a narrower reviewed group, set `mocha_grep = "^relevant group "` under
`[runner]`. Mocha matches this regular expression against full test titles.
Only selected cases appear in the evidence; this establishes coverage of that
selection. The external security oracle always runs independently of the filter.
Zero matching tests, or skips and duplicate identities within the selection,
remain inconclusive.

Check a published backport with the regular command:

```bash
seam run --repo /path/to/library --fix UPSTREAM_FIX --target TARGET_COMMIT \
  --config harness.toml --candidate-patch maintainer.patch \
  --output /path/to/new-evidence
```

Use `--direct` to try the original fix unchanged. AI adaptation uses the same
verification matrix; see [API setup](api.md) before supplying a model and budget.
Tests, dependency manifests, lockfiles and build configuration remain outside
candidate patch permissions.

## Prepare dependencies

Prepare dependencies in a reviewed build container, preserving exact package
locks and integrity hashes. Use `npm ci --ignore-scripts`. Do not install the
library being evaluated as a substitute for its staged implementation.

The default image dependency directory is `/opt/seam/node_modules`. When release
lines need different versions, put separate dependency trees in the same image
and map each exact source commit explicitly:

```toml
[runner.node_dependencies]
"PARENT_COMMIT_SHA" = "/opt/seam/upstream/node_modules"
"FIX_COMMIT_SHA" = "/opt/seam/upstream/node_modules"
"TARGET_COMMIT_SHA" = "/opt/seam/target/node_modules"
```

Replace the keys with full Git object IDs. Candidate changes keep the target's
HEAD and dependency tree. A missing revision or directory stops verification;
there is no fallback to another version. The frozen configuration and execution
commands record the selection.

## Review repository prerequisites

Submodules are rejected by default. An operator may review exact gitlink paths
and object IDs under `[runner.reviewed_submodules]`. Accepted directories must
remain empty: Seam never fetches or initializes their code. Use this exception
only when those submodules are unrelated to the selected tests. Public test
certificates use the existing hash-pinned `reviewed_fixtures` setting; neither
exception permits arbitrary file changes.

Skipped tests, todos, import failures, empty suites, ambiguous test identities and
timeouts remain inconclusive. A verified result covers the selected checks. It
does not establish full npm ecosystem coverage or certify a complete library.
