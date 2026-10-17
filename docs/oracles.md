# Writing an independent oracle

Choose a small regression that distinguishes vulnerable behavior from the
intended fixed behavior. The harness needs the same security test to reproduce
on the upstream parent and the maintained release, then pass on the upstream
fix and the backport. Handle old and new public APIs explicitly if necessary.

```python
import library


def test_security_regression():
    result = library.parse("a known bad input")
    assert result.rejected, "EXPECTED_SECURITY_REGRESSION: input was accepted"


def test_ordinary_request():
    assert library.parse("ordinary input").value == "ordinary input"
```

Keep this file outside the target repository and select it through an explicit
configuration file. Use plain test functions named `test_*`; the configured
names must refer to one security test and distinct normal-behavior controls.
The security assertion's marker must be at least eight characters. Select an
unambiguous marker that an unrelated import or setup error will not produce.

Prefer a minimal behavioral reproduction over a version-number comparison or
source-code pattern. Add controls that reject tempting but invalid fixes:
ordinary requests, boundary values, and inputs resembling the exploit but still
allowed by the API. Existing project tests provide additional compatibility
evidence. Do not use skips or expected failures to disguise missing support.

The oracle is executed separately with repository test configuration disabled.
It uses the selected image's preinstalled pytest and target dependencies, with
the target's `src/` and repository root on the Python path. Keep helper code in
the oracle file; do not depend on a repository `conftest.py`. Use pytest fixtures
such as `tmp_path` to avoid writing to the read-only oracle mount.

If the upstream fix or maintained branch needs incompatible runtimes, one image
may not be enough. That is outside the initial single-image workflow; do not
interpret an environment failure as security evidence.

The oracle is a trusted input, not a mathematical proof. Review it alongside the
patch. A bad assertion, incomplete exploit, or overly broad control can produce
misleading evidence even when the harness executes it correctly.
