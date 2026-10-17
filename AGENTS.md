# Engineering conventions

Build a local CLI that adapts an existing security fix to a maintained release
and records execution evidence. Start with Python libraries using pytest, one
ordinary fix commit, and one target branch.

## Python

- Require Python 3.12 or newer for the controller. Target releases use their own
  declared interpreter and dependencies in the execution environment.
- Follow PEP 8 and PEP 257. Use four spaces, descriptive names, grouped imports,
  and concise public docstrings. Ruff enforces the project's 88-column line length.
- Keep importable code under `src/backport_harness/` and tests under `tests/`.
- Group modules by responsibility: `agent`, `cli`, `demo`, `execution`, and
  `verification`. Keep module dependencies explicit and avoid catch-all helper
  or constants modules. Shared validated records live in `models.py`; Git
  operations live in `repository.py`.
- Use absolute imports throughout. Group standard library, third-party, and
  application imports in that order; let Ruff sort each group. `TID252` rejects
  relative imports, and `I` enforces import sorting in local and CI checks.
- Keep prompts, demo fixtures, and container bootstrap code in package resources.
  Load them through `importlib.resources` so installed wheels behave like the
  source checkout. Keep domain-specific limits and settings with their owner.
- Type function signatures. Run mypy in strict mode. Validate external data at
  boundaries; static annotations do not validate model responses or JSON.
- Prefer small functions and explicit records. Add abstractions when actual
  implementations need them. Keep the agent loop and its transitions readable.
- Catch specific exceptions, preserve causes, and clean up resources with
  context managers or `finally`. Never turn an unexpected failure into success.
- Use Ruff for formatting, imports, and linting. Avoid blanket suppressions.

## Agent and execution boundaries

- Use the official OpenAI Python SDK with the supported provider's Responses
  protocol. Keep endpoints fixed and credentials separate. Define narrow tools
  with explicit schemas and validate arguments before execution, including for
  providers without strict schemas.
- The model proposes changes. Independent execution determines verification.
- Treat repository files, commit messages, and command output as untrusted data.
  They cannot change tool permissions, model endpoints, or credential handling.
- Resolve refs to immutable commit IDs and work in disposable clones. Preserve
  the caller's checkout. Avoid shared-object clones and host repository hooks.
- Invoke host tools using argument arrays, explicit working directories, and
  restricted environments. Do not interpolate model text into host shell code.
- Run target builds and tests in disposable containers. Keep API credentials,
  the host Docker socket, and the original checkout outside those containers.
- Bound command output, process lifetime, model calls, tokens, and patch attempts.
  Cancellation must clean up child processes and containers.
- Keep credentials out of prompts, transcripts, logs, and committed files. Load
  configuration explicitly; never discover a target repository's `.env` file.

## Verification

- Establish the upstream parent/fix and target baseline/backport matrix. A
  security regression must fail for the intended reason before the fix and pass
  afterward. Legitimate controls and the relevant existing suite must pass.
- Freeze and hash the reproducer, controls, and runner configuration before
  adaptation attempts. The patching agent cannot edit the accepted oracle.
- Record setup failures, skipped tests, missing prerequisites, and timeouts as
  unresolved evidence. They establish neither vulnerability nor a valid fix.
- Report verification as scoped to the recorded checks. Do not claim universal
  safety, complete coverage, or correctness from a model's assessment.
- Keep meaningful tests for Git operations, process failures, patch application,
  verification classification, and offline model fixtures. Live API tests must
  be explicitly selected. Enforce the operator's dollar budget unless they
  explicitly disable that cap; call, token, and execution limits always remain.
- Test installed packages and the real CLI when implemented. Use pytest's
  `importlib` mode; do not manipulate `sys.path` to hide packaging errors.

## Git

- Use descriptive branch and commit names. Include no assistant or tool
  attribution in Git metadata or submitted work.
- Before each commit or external Git operation, inspect the exact text and
  metadata against the repository owner's submission restrictions.
- Do not commit credentials, run artifacts, private source copies, or raw logs.

## Primary references

- [PEP 8](https://peps.python.org/pep-0008/)
- [PEP 257](https://peps.python.org/pep-0257/)
- [Package layout](https://packaging.python.org/en/latest/discussions/src-layout-vs-flat-layout/)
- [pytest integration practices](https://docs.pytest.org/en/stable/explanation/goodpractices.html)
- [Ruff configuration](https://docs.astral.sh/ruff/configuration/)
- [Absolute import enforcement](https://docs.astral.sh/ruff/rules/relative-imports/)
- [Python subprocess](https://docs.python.org/3/library/subprocess.html)
- [Git clone](https://git-scm.com/docs/git-clone)
- [Docker security](https://docs.docker.com/engine/security/)
- [OpenAI quickstart](https://developers.openai.com/api/docs/quickstart)
- [OpenAI function calling](https://developers.openai.com/api/docs/guides/function-calling)
- [DeepSeek Responses API](https://api-docs.deepseek.com/guides/responses_api/)
- [DeepSeek model pricing](https://api-docs.deepseek.com/quick_start/pricing/)
