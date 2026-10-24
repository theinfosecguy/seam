# Language support roadmap

JavaScript/npm is now the first experimental extension beyond Python. Seam runs ordinary `.js`, `.mjs` and `.cjs` changes with Node's test runner or Mocha. Python and pytest remain the default. See [JavaScript usage](javascript.md) and the [expanded benchmark results](expanded-benchmarks.md).

The first npm evaluation tested 20 cases across 17 libraries. Its unresolved cases show where the next work belongs: original test frameworks, frozen build steps and supported runtime versions. Adding more languages before resolving those boundaries would spread the implementation too thin.

## Next JavaScript work

1. Add the original Tape/TAP, AVA and Lab execution paths only with frozen versions, real test identities and rejection checks. Support older Mocha interfaces explicitly.
2. Add an explicit offline build step for TypeScript and packages whose committed source requires compilation. Keep build configuration outside candidate patch permissions.
3. Evaluate declared runtime ranges. The current Node 24/Mocha 12 environment does not establish older-Node compatibility; the body-parser comparison demonstrates why that matters.
4. Support dependency-changing and multi-commit fixes through a reviewed workflow. Current source-only patch permissions correctly leave those cases unresolved.
5. Expand independent BackportBench task coverage, preserving setup failures and separating supplied-patch verification from fresh AI adaptation.

Keep dependencies pinned and run target code without registry access, lifecycle scripts, host packages or credentials. Skips, missing tests, duplicate identities and timeouts remain unresolved evidence.

## After JavaScript

Go is a sensible next ecosystem: its test tooling is consistent and provides [structured results](https://pkg.go.dev/cmd/test2json). It still needs pinned toolchains, offline dependency caches and compiled oracles; [automatic toolchain downloads](https://go.dev/doc/toolchain) must be disabled during verification.

Java adds JDK and Maven/Gradle build requirements. Rust adds compiler, Cargo dependency and build-script boundaries. These should follow demonstrated JavaScript coverage rather than share a generic execution abstraction before real cases require it.
