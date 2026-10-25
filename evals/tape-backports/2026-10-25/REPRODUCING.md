# Reproduce the recorded scopes

Install the release wheel in Python 3.12 or newer and verify the release
`SHA256SUMS`. The controller wheel and evaluation archive have separate hashes.
Read each case's `case.json`, `frozen-inputs.json` and `harness-tape.toml` before
running it. Local repository paths were removed from published metadata; use
the recorded repository URL and immutable commit IDs.

Load `seam-tape-images-2026-10-25.tar.gz` with `docker load` to obtain the recorded
runtime image `sha256:277b9b3c5907cb97119813d8c5f71cb3a4f92bf94ed60910ccb0e2d53837d09d`.
The archive also contains the minimal CI image. The runtime includes frozen
reporter research dependencies; neither those reporters nor Mocha/Tape are
controller dependencies. Its only change from the research image is the
`/opt/seam/node_modules` symlink expected by the runner.

The complete recipes and npm integrity locks are under `image/`. Rebuilding
may produce a different image ID; review and freeze a new configuration rather
than silently substituting it. Network is needed to prepare dependencies,
but target verification runs offline with no lifecycle scripts. Archive blob
integrity was checked; restoration into a clean Docker daemon was not tested.

Clone each library independently with `git clone --no-local --no-checkout URL`,
then ensure the four exact objects in the metadata are present. Do not use
shared-object clones or install the target library into the dependency image.
From a new copy of this study directory, run the reference with the actual
repository location and metadata commit IDs:

```sh
seam run --repo /path/to/independent/library \
  --fix UPSTREAM_FIX_COMMIT --target TARGET_BASELINE_COMMIT \
  --config cases/qs/harness-tape.toml \
  --candidate-patch cases/qs/reference.patch --output /path/to/new-evidence
```

The recorded config invokes Docker through `sudo -n docker`. If your Docker
access differs, record that as a new reviewed configuration. Keep the security
oracle, controls, marker, suite selection, refs and image fixed. Repeat a
qualifying reference into a new output directory. For a negative control,
apply only an implementation comment and confirm the target security test
still fails with the recorded marker while the normal controls and original
suite pass. The original fast-uri scheme scope is intentionally retained;
its inconclusive result must remain visible alongside the separate parse scope.

Use `--direct` instead of `--candidate-patch` for the qs direct-transfer trial.
An optional paid reproduction uses the same installed CLI with explicit
DeepSeek credentials, current independently checked rates, a $1 API cap and
at most 32 calls. No credentials are included. Provider behavior can change;
a new model run is a new result, even with the same alias and inputs.

The default controller tests and the real Node/Mocha/Tape integration tests
are in the source checkout. The CI workflow builds `tests/execution/javascript-image`,
installs the wheel outside the checkout and fails if any JavaScript test skips.
`adapter/README.md` describes the standalone synthetic fixtures.

A verified result requires the four-revision security matrix and passing normal
controls and selected existing tests. The adapter's framework-only runs do not
establish vulnerability or a valid backport. Missing prerequisites, skips,
empty or duplicate identities, timeouts, incomplete plans and abnormal process
lifecycles remain inconclusive. No older-Node or universal completeness claim
is made.
