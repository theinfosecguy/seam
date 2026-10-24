# Expanded backport benchmarks

The [published evaluation bundle](../evals/expanded-backports/2026-10-24/README.md) adds npm cases, two Python cases and an actual BackportBench crosscheck.

The initial npm batch tested 20 cases across 17 libraries: four references verified, 15 were inconclusive and serve-static failed two obsolete compatibility expectations. All four qualifying cases passed repeats and rejected ineffective patches. A separately reviewed serve-static selection then qualified. Werkzeug multipart and Django language caching also qualified, including repeats and rejection checks.

Four fresh AI adaptations passed their initial checks. Direct patch transfer already worked for three of them; body-parser required adaptation. Comparing its AI patch with the maintainer patch exposed a missing normal-behavior control: decoder cleanup detached an unrelated stream consumer. The strengthened oracle rejects that earlier candidate, and a fresh adaptation passes it. Both outcomes remain published. Node 24 checks do not establish compatibility with the target's declared Node >=0.8 range.

We also ran the official BackportBench evaluator on its qs task. The maintainer reference fixed six failing security tests and preserved 213 passing tests; an ineffective patch kept all six failures. An independent audit confirmed 219 stable identities. That is one external tool crosscheck, not a full BackportBench score or a successful Seam qualification of its currently unresolved Tape suite.

The bundle includes frozen inputs, unsuccessful attempts, normalized test evidence, model usage, patch comparisons, image recipes, licenses and checksums. [Release assets](https://github.com/theinfosecguy/seam/releases/tag/v0.5.0.dev1) provide the tested wheel and optional exact execution-image archive. All 1,281 installed-package tests passed; Ruff and strict mypy passed.

These selected cases show useful progress and concrete limits. Next work should support original npm test frameworks, frozen builds and declared runtime ranges. Broad ecosystem success rates would be premature.
