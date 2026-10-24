# Language support roadmap

Seam currently supports Python libraries tested with pytest. The next ecosystem
should be **JavaScript on Node.js, using npm for dependency preparation**.
TypeScript should follow once JavaScript backports work reliably.

Undici provides a useful starting point: it maintains several release lines and
publishes ordinary security fixes for older versions. Its existing tests include
Node's built-in test runner, which can produce JUnit reports. These are the same
two ingredients Seam needs: an independent regression test and a compatible
existing suite. See [Undici's support policy](https://github.com/nodejs/undici#long-term-support)
and [Node's test runner](https://nodejs.org/api/test.html#test-reporters).

## Why start with npm

This order reflects the work needed to deliver a useful first evaluation.

| Ecosystem | Useful starting point | Main work before support |
| --- | --- | --- |
| JavaScript and npm | Maintained Undici backports; source can run directly. | Handle module resolution, dependency isolation and Node test evidence. |
| Go | Consistent test tooling and [structured test results](https://pkg.go.dev/cmd/test2json). | Compile each revision and oracle; pin toolchains and dependency caches. |
| Java | [Tomcat maintains several release lines](https://tomcat.apache.org/whichversion.html); [Surefire produces XML reports](https://maven.apache.org/surefire/maven-surefire-report-plugin/index.html). | Support JDK versions, build plugins and offline Maven or Gradle dependencies. |
| Rust | Cargo supports [locked offline builds](https://doc.rust-lang.org/cargo/commands/cargo-vendor.html). | Compile each revision; account for build scripts, compiler versions and test-result conversion. |

Go would be a sensible second ecosystem after JavaScript. Its test tooling is
consistent, but [automatic toolchain downloads](https://go.dev/doc/toolchain)
must be disabled during isolated verification.

## First JavaScript milestone

Start with `.js`, `.mjs` and `.cjs` implementation changes and explicit
`node:test` suites. Keep Python as the default. A Node runner should use the same
four-revision checks, failure markers, controls, input hashes and container
isolation as the Python runner.

1. Add language-aware source filtering, configuration and model file inspection.
   Keep tests, dependency manifests, lockfiles, generated files and build scripts
   outside the model's patch permissions.
2. Add a fixed Node container bootstrap and validate reports from an exact Node
   runtime. Missing tests, skipped tests, import failures and timeouts must remain
   unresolved evidence.
3. Qualify the Undici cache-parser case below against its published backport, then
   run a deliberately ineffective patch and an AI adaptation using the same tests.
4. Publish the case, build recipe, immutable revisions, results and comparison
   with the maintainer's patch. Repeat across additional libraries before making
   broad claims about npm coverage.

Prepare dependencies in a reviewed build container using a lockfile and
[`npm ci --ignore-scripts`](https://docs.npmjs.com/cli/v11/commands/npm-ci/).
Run verification without registry access, host `node_modules`, npm credentials
or automatic `npm test` execution. Confirm that tests load the staged source,
rather than an installed copy of the library. CommonJS and ES modules need
separate resolution checks.

TypeScript adds a compiler and build configuration to this boundary. Support it
through an explicit, frozen build step after JavaScript qualification succeeds.

## Public backports to evaluate

These are candidate cases, not completed Seam evaluations. Each has a separate
source fix and older-line backport in the official Undici repository.

| Issue | Published fixes | Source fix | Older-line reference |
| --- | --- | --- | --- |
| [Set-Cookie header injection, June 17, 2026](https://github.com/nodejs/undici/security/advisories/GHSA-p88m-4jfj-68fv) | 6.27.0, 7.28.0, 8.5.0 | [5655ea4](https://github.com/nodejs/undici/commit/5655ea43af4add559ee5f94b6cd72e08a55aa621) | [25efa44 on 6.x](https://github.com/nodejs/undici/commit/25efa447997f74d5881edd144525c3fd7db945a4) |
| [Private cache directive handling, July 29, 2026](https://github.com/nodejs/undici/security/advisories/GHSA-4cwx-7wf7-3272) | 7.29.0, 8.9.0 | [4fe5bc5](https://github.com/nodejs/undici/commit/4fe5bc5fefe5ac81a200fc8e1cf84b8bf8464451) | [9f10f1e on 7.x](https://github.com/nodejs/undici/commit/9f10f1e9bfcc68b5c8b53d0459cb6d9562008fcd) |
| [Lost TLS verification callbacks, October 15, 2026](https://github.com/nodejs/undici/security/advisories/GHSA-2m5v-pch6-74hx) | 6.29.1, 7.30.1, 8.12.2 | [f75eac0](https://github.com/nodejs/undici/commit/f75eac00ac177f7b2e6c8bfbd52d4113164286e6) | [8c59f6b on 6.x](https://github.com/nodejs/undici/commit/8c59f6b302898cb2e9b0f7962cd7212b6e597c9f) |

The cache-parser case is the smallest first step: it has an existing
`node:test` suite at `test/cache-interceptor/utils.js` and can exercise the
regression without an external server. Use target release
[`v7.28.0`](https://github.com/nodejs/undici/commit/f9eba0ad9134e1c0977848476bba9d49734696e4),
freeze the oracle and runtime, and establish the complete reference matrix
before asking a model to adapt the fix.
