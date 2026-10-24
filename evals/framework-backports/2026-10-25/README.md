# Backport evaluation follow-up, 25 October 2026

Eight selected cases qualified with the installed `0.5.0.dev2` wheel: js-yaml,
Marshmallow, Pydantic, IP, Undici private-cache, body-parser, debug and serve-static.
Every reference passed twice, and every ineffective patch was rejected. Five
cases reuse the earlier frozen npm inputs; this does not rerun its entire batch.

The [results guide](https://github.com/theinfosecguy/seam/blob/main/docs/followup-benchmarks.md) explains the outcomes
and remaining gaps. These standalone inputs do not change the default eight-case
Python catalogue or provide a representative ecosystem/model success rate.

| Directory | Contents |
| --- | --- |
| `cases/js-yaml` | Frozen oracle, original selected tests, patches, licenses and exact revision/interface/dependency pins |
| `python` | Two additional issues, original and reviewed import configurations, image recipes, source-origin proofs and scope limits |
| `results` | 31 normalized CLI reports, original-to-normalized hashes, candidate patches and failed-attempt feedback |
| `tape` | Reproducible reporting investigation; no Seam Tape qualification |
| `runtime` | Seven synthetic Node 20.18.1 reports rejected for missing source-file identities |
| `validation` | Installed-wheel/source hashes, test counts, patch comparison, pricing and image-archive checks |

Reports include 19 verified outcomes, nine rejected ineffective patches and three
inconclusive outcomes. Repeats and configuration variants are records of the
same case. Pydantic's original import configuration is retained alongside its
reviewed `prepend` variant. Marshmallow covers one performance component,
excluding later deepcopy adjustments. Neither additional Python advisory is
within the preceding six months.

One fresh js-yaml adaptation verified after its first patch failed to apply.
The final patch is byte-identical to the implementation-only maintainer
reference. Direct transfer failed on the moved implementation path. Model
usage was 15 calls and a conservative estimated $0.0575424; provider billing is
authoritative. Reference patches and external oracle source were not supplied
to the adaptation model by the invocation. Provider conversations were not
retained or audited. These results do not establish older-runtime coverage.

Raw logs, conversations, credentials and copied source repositories remain
outside this publication. Test names, outcomes, hashes, prerequisite diagnostics
and failed candidate patches are retained. The normalization replaces the
operator's oracle path with its filename; configuration hashes still identify
the original frozen configuration, whose source hash is recorded separately.
The same security test must fail with the intended marker before each fix, and
normal controls and the selected existing tests must pass. Skips, missing tests,
duplicates, errors and timeouts remain inconclusive.

See [reproduction notes](REPRODUCING.md) before rebuilding or running a case.
`SHA256SUMS` covers every published input and normalized record. Exact archive
and wheel hashes are also provided with the release assets.
