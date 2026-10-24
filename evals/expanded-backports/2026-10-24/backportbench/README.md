# BackportBench crosscheck

One official task, `qs_98`, was executed with the unchanged published evaluator. The maintainer reference fixed all six failing security tests while preserving all 213 passing tests. The unchanged implementation control retained all six failures. Our independent audit confirmed 219 stable identities before and after both runs.

This overlaps the same qs source/backport pair in the npm cohort. Seam's current qs configuration remains inconclusive because its dependencies and Tape suite are not supported by that prepared Node environment. The successful external run demonstrates available compatibility evidence; it does not count as a Seam qualification or a comparative model score.

`summary.json` preserves three image-pull attempts and all three evaluation attempts, including two aborted pulls and one permission setup failure. Successful execution disabled networking and host mounts, enabled no new privileges and dropped all capabilities except the documented `DAC_OVERRIDE` permission needed by the supplied image. No model was called.

The complete replay package contains the original evaluator, parsers, pinned task, patches, upstream licenses, dependency lock, wrappers, audit checks and all attempt metadata: [download the crosscheck archive](https://github.com/theinfosecguy/seam/releases/download/v0.5.0.dev1/backportbench-qs-crosscheck-2026-10-24.zip). Its SHA-256 is `4b8b847113fcaa762705a96e82aabc36924393e78807656e0aa32411cf94118e`.

Pinned upstream: [BackportBench at a7bb4ed](https://github.com/coxhin/BackportBench/tree/a7bb4ed2632305f1c7ef0bc81cf6b751e5d4c292). Only one of its 202 executable tasks was run. This is an external tool and oracle crosscheck, not a full benchmark score.
