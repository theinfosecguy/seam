# npm security backport candidates

Research date: 2026-10-24. **25 distinct libraries and security issues have verified source fixes on separate published release lines.** These are historical evaluation candidates; the listed versions are not current upgrade recommendations. No target package was installed, built, or executed on the controller.

A version list alone was insufficient. Each entry in `catalogue.json` records the exact newer fix and parent, exact older-line fix and parent, changed source files, package metadata, licenses, dependencies, test commands, and official release ancestry. All 50 fixed releases contain their selected fix: 49 are proved through exact Git tags; yargs-parser13.1.2 is proved through its official npm registry gitHead and maintainer ancestry, because that version has no Git tag. The broad sweep found 269 multi-line advisories across 47 libraries; only the independently pinned pairs below are counted as ready.

| Library | Issue | Published | Newer fix | Older fix | Native suite | Complexity |
| --- | --- | --- | --- | --- | --- | --- |
| qs | [CVE-2022-24999](https://github.com/advisories/GHSA-hrpp-h998-j3pp) | 2022-11-27 | 6.10.3 | 6.9.7 | tape | simple |
| semver | [CVE-2022-25883](https://github.com/advisories/GHSA-c2qf-rxjj-qqgw) | 2023-06-21 | 7.5.2 | 6.3.1 | tap | moderate |
| fast-uri | [CVE-2026-110306](https://github.com/advisories/GHSA-w74x-v6f9-j3xg) | 2026-10-23 | 4.2.3 | 3.1.9 | tape | simple |
| path-to-regexp | [CVE-2024-45296](https://github.com/advisories/GHSA-9wv6-86v2-598j) | 2024-09-09 | 1.9.0 | 0.1.10 | mocha | moderate |
| serve-static | [CVE-2024-43800](https://github.com/advisories/GHSA-cm22-4g7w-348p) | 2024-09-10 | 2.1.0 | 1.16.0 | mocha | moderate |
| body-parser | [CVE-2026-111181](https://github.com/advisories/GHSA-27r3-jxmh-p828) | 2026-10-23 | 2.4.0 | 1.20.9 | mocha | moderate |
| fast-xml-parser | [CVE-2026-33349](https://github.com/advisories/GHSA-jp2q-39xq-3w4g) | 2026-03-19 | 5.5.7 | 4.5.5 | jasmine | moderate |
| markdown-it | [CVE-2026-111758](https://github.com/advisories/GHSA-gfr2-rv44-r23c) | 2026-10-20 | 15.0.3 | 14.3.3 | node:test | complex |
| node-fetch | [CVE-2022-0235](https://github.com/advisories/GHSA-r683-j2x4-v87g) | 2022-01-21 | 3.1.1 | 2.6.7 | mocha | moderate |
| ws | [CVE-2024-37890](https://github.com/advisories/GHSA-3h5v-q93c-6h6q) | 2024-06-17 | 8.17.1 | 7.5.10 | mocha | simple |
| engine.io | [CVE-2022-41940](https://github.com/advisories/GHSA-r7qp-cfhv-p84w) | 2022-11-21 | 6.2.1 | 3.6.1 | mocha | moderate |
| handlebars | [CVE-2019-20920](https://github.com/advisories/GHSA-3cqr-58rm-57f8) | 2022-02-10 | 4.5.3 | 3.0.8 | Grunt | complex |
| undici | [CVE-2026-109869](https://github.com/advisories/GHSA-xjj6-f33q-929c) | 2026-10-23 | 8.12.2 | 7.30.1 | node:test | moderate |
| dot-prop | [CVE-2020-8116](https://github.com/advisories/GHSA-ff7x-qrg7-qggm) | 2020-07-29 | 5.1.1 | 4.2.1 | ava | simple |
| ansi-regex | [CVE-2021-3807](https://github.com/advisories/GHSA-93q8-gq69-wqmw) | 2021-09-20 | 6.0.1 | 5.0.1 | ava | simple |
| json5 | [CVE-2022-46175](https://github.com/advisories/GHSA-9c47-m6qq-7p4h) | 2022-12-29 | 2.2.2 | 1.0.2 | tap / Mocha | moderate |
| ip | [CVE-2023-42282](https://github.com/advisories/GHSA-78xj-cgh5-2h22) | 2024-02-08 | 2.0.1 | 1.1.9 | mocha | simple |
| @hapi/hoek | [CVE-2020-36604](https://github.com/advisories/GHSA-c429-5p7v-vgjp) | 2022-09-25 | 9.0.3 | 8.5.1 | lab | simple |
| http-proxy-middleware | [CVE-2024-21536](https://github.com/advisories/GHSA-c7qv-q95q-8v27) | 2024-10-19 | 3.0.3 | 2.0.7 | jest | moderate |
| debug | [CVE-2017-20165](https://github.com/advisories/GHSA-9vvw-cc9w-f27h) | 2023-01-09 | 3.1.0 | 2.6.9 | mocha | simple |
| mime | [CVE-2017-16138](https://github.com/advisories/GHSA-wrvr-8mpx-r7pp) | 2018-07-20 | 2.0.3 | 1.4.1 | Mocha / plain node | moderate |
| hosted-git-info | [CVE-2021-23362](https://github.com/advisories/GHSA-43f8-2h32-f4cj) | 2021-05-06 | 3.0.8 | 2.8.9 | tap | simple |
| axios | [CVE-2025-27152](https://github.com/advisories/GHSA-jr5f-v2jv-69x6) | 2025-03-07 | 1.8.2 | 0.30.0 | Mocha / Grunt (Mocha) | moderate |
| js-yaml | [CVE-2025-64718](https://github.com/advisories/GHSA-mh29-5h37-fv8m) | 2025-11-14 | 4.1.1 | 3.14.2 | mocha | simple |
| yargs-parser | [CVE-2020-7608](https://github.com/advisories/GHSA-p9pc-299p-vxgp) | 2020-09-04 | 18.1.1 | 13.1.2 | mocha | simple |

The eight no-build native Mocha candidates are **ws, ip, serve-static, body-parser, debug, historical Axios, yargs-parser, and historical js-yaml**. Exact package scripts, Makefiles, and Grunt tasks were checked. Original upstream Node unit files must be selected and preserved; browser suites remain outside that selected scope. The path-to-regexp1.x parent still has a TypeScript test file even though the fix renames it to JavaScript, so it is not counted in this eight-library batch. Latest markdown-it has TypeScript/node:test; latest Axios uses Vitest; JSON5 has tap versus Mocha plus a build; and engine.io has a TypeScript newer line. Those compatibility boundaries are retained in the catalogue. Native Node coverage starts with Undici.

The simplest source fixes are qs, fast-uri, dot-prop, ansi-regex, ip, and @hapi/hoek. Their native suites span tape, AVA, Mocha, and Lab. Source simplicity alone does not justify replacing selected real upstream test identities with an oracle-only check.

Two provenance traps were corrected: node-fetch’s advisory linked a pre-squash security commit, so the catalogue uses the actual landed fix `f5d3cf5e2579cb8f4c76c291871e69696aef8f80`; and several WS/form-data/cross-spawn advisory links referred only to release commits. WS was resolved to the concrete 2024 source fix. Unresolved release-only candidates are excluded from the verified count. Socket.IO parser has clear source backports but the old published version lacks a matching Git tag, so it is also excluded from that stricter count.

Backport commits for fast-xml-parser, markdown-it, and Handlebars bundle multiple fixes. Their oracle must isolate the stated issue while the evidence retains the entire upstream patch. ReDoS cases require bounded process execution and useful controls; a fragile elapsed-time comparison is insufficient.

Supply-chain account takeovers are separate: the [chalk malware advisory](https://github.com/advisories/GHSA-2v46-p5h4-248w) explicitly has no patched version; GitHub describes [Shai-Hulud](https://github.blog/security/supply-chain-security/our-plan-for-a-more-secure-npm-supply-chain/) as compromised maintainer accounts and malicious installation scripts. Those incidents are excluded from source-backport evaluation. No malware was downloaded or run.


The public `catalogue.json` preserves the source and fixed-release proof links. Raw API archives, checkouts, and historical shortlist files are omitted. Catalogue verification establishes published source lineage; it does not establish successful harness execution.
