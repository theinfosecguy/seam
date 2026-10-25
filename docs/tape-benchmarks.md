# Tape backport evaluations

Seam's experimental Tape runner now qualifies the selected qs backport and a
separately reviewed fast-uri parsing scope. The original fast-uri scheme suite
remains inconclusive. These are two advisories, with three recorded scopes;
configuration variants and repeats do not increase the issue count.

| Case | Maintainer reference | Repeat | Ineffective patch |
| --- | --- | --- | --- |
| qs, original `test/parse.js` | Verified | Verified | Rejected |
| fast-uri, original `test/scheme-validation.test.js` | Inconclusive: old expectation aborts | Not eligible | Not eligible |
| fast-uri, separate `test/parse.test.js` scope | Verified | Verified | Rejected |

The [frozen inputs and normalized reports](../evals/tape-backports/2026-10-25/README.md)
retain all nine CLI results, including the original inconclusive result. This
supplements the [earlier npm study](expanded-benchmarks.md) and
[framework follow-up](followup-benchmarks.md); it does not rerun their full batches
or establish an ecosystem success rate.

For [qs's published prototype-pollution fix](https://github.com/advisories/GHSA-hrpp-h998-j3pp),
the security assertion and two normal controls run independently of the original
Tape parsing suite. The maintainer reference passed twice; a comment-only patch
kept the intended security failure. Direct transfer and one fresh model run also
verified. Both canonical patches are byte-identical to the maintainer reference.
The model used three calls and one patch attempt, with a conservative estimated
cost of $0.0041628 under a $1 cap. Direct transfer already works here, so this is
an integration check rather than evidence of difficult adaptation.

The [fast-uri fix](https://github.com/advisories/GHSA-w74x-v6f9-j3xg) intentionally
rejects percent-encoded schemes. Its old scheme-validation test expects some of
those values to succeed; the implementation-only backport throws a `TypeError`
at that expectation. The security check passes, but an aborted existing suite
cannot qualify the backport. We preserved that result and separately froze the
unchanged original parsing file at every revision. That narrower scope passed
twice and rejected the ineffective patch. It establishes ordinary parsing
preservation within that file, not compatibility with the original scheme suite
or the full package suite.

The installed `0.5.0.dev3` wheel passed **1,366 tests, with zero skips, failures or
errors**. Lint, formatting and strict typing checks also passed. An additional
65 synthetic adapter checks cover named scopes, repeated assertion labels,
async failures, visible skips, duplicate identities, incomplete plans, early
exits and bounded evidence. These overlap the integration tests; their counts
must not be added together as independent backport tasks. Eight framework-only
runs also completed the original suites at all four frozen revisions.

Review caught development false passes from assertions scheduled after a parent
scope closed, hidden harnesses in workers or child processes, and `execve`
process replacement. The released runner rejects these sequences. Its result
channel is separate from stdout, and a complete stream alone cannot establish
success: the observed process must finish normally. These checks cover
cooperative framework use; they do not make arbitrary in-process code tamper-proof.

Tape support is limited to one explicit suite file, one process, Tape 5.10.3,
Node 24, and CommonJS or synchronous ESM. Top-level await, custom harnesses,
reporter lifecycle APIs, other Tape versions and older Node runtimes remain
unsupported. The default Python catalogue is unchanged. Next work is AVA/Lab,
reviewed offline TypeScript builds, older runtime evaluation and broader
independent BackportBench coverage.
