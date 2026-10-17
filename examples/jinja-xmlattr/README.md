# Jinja whitespace attribute injection backport

Reproduce a real security backport for
[CVE-2024-22195](https://github.com/pallets/jinja/security/advisories/GHSA-h5c8-rqwp-cp95).
Jinja's `xmlattr` filter accepted attribute keys containing ASCII whitespace.
Applications that let users supply those keys could render unintended HTML
attributes. The upstream fix rejects such keys.

This example adapts
[upstream fix `7dd3680`](https://github.com/pallets/jinja/commit/7dd3680e6eea0d77fde024763657aa4d884ddb23)
to Jinja 3.0.3, preserving its existing function signature and escaping behavior.
The older file places the function differently, so the complete upstream source
diff does not apply cleanly. The reference adaptation inserts the same ASCII
whitespace guard at the older function's location.

Jinja 3.0.3 is a historical target for this exercise. This example is not a
recommendation to deploy that version or a claim that this single patch resolves
all Jinja vulnerabilities. Production users should follow current upstream
upgrade guidance. Later attribute-key issues are outside these recorded checks.

Run these commands from the harness repository after `uv sync --group dev`:

```sh
docker build --tag security-backport-jinja:local examples/jinja-xmlattr
uv run python examples/jinja-xmlattr/prepare.py \
  --output /tmp/jinja-backport \
  --docker docker \
  --image security-backport-jinja:local
uv run backport run \
  --repo /tmp/jinja-backport/repo \
  --fix 7dd3680e6eea0d77fde024763657aa4d884ddb23 \
  --target 3.0.3 \
  --config /tmp/jinja-backport/harness.toml \
  --candidate-patch /tmp/jinja-backport/reference.patch \
  --output /tmp/jinja-backport/evidence
```

If Docker requires passwordless privilege elevation, use `sudo -n docker build`
and pass `--docker 'sudo -n docker'` to `prepare.py`. The script also accepts
`--source /path/to/existing/jinja` to clone a local public-source cache. It never
imports or executes Jinja on the host and does not modify the original clone.

Preparation and image building require network access unless the source and
image are cached. Test containers have no network. The image preinstalls pytest
8.3.5 and MarkupSafe 2.1.5; the checked-out Jinja source is imported inside the
container. No API key or model is used: this is the independent verification
path with an explicit reference patch.

The frozen external oracle checks all six ASCII whitespace characters and three
compatibility controls: escaped valid attributes, omitted `None`/undefined
values, and the optional leading space. The relevant existing suite is
`tests/test_filters.py`. The four recorded revisions are the upstream fix's
parent, the fixed upstream commit, the unmodified 3.0.3 target, and the target
with the supplied patch. A verified result requires the expected regression to
fail before each fix, pass afterward, and the selected suite and controls to
pass. `evidence/report.json` records exact revisions, image ID, commands, test
outcomes, and artifact hashes.

The supplied reference was exercised through the real Docker runner with these
results (security checks include the three compatibility controls):

| Revision | Security checks | Existing filter suite |
| --- | --- | --- |
| Upstream parent | 1 expected failure, 3 passes | 124 passes |
| Upstream fix | 4 passes | 125 passes |
| Historical 3.0.3 target | 1 expected failure, 3 passes | 120 passes |
| Adapted target | 4 passes | 120 passes |

The upstream fixed revision adds its own regression case, explaining the extra
test relative to its parent. The target suite retains all 120 collected cases.
An intentionally broken candidate that rejected every attribute was also
rejected: the security regression passed, but all three external compatibility
controls and the existing `test_xmlattr` case failed.

The adaptation contains code from Jinja, distributed under its BSD 3-Clause
license. See [LICENSE.upstream](LICENSE.upstream). The harness does not publish
changes to the upstream repository.
