# Security backport harness

Adapt an existing security fix to an older release and produce a reviewable
patch with recorded test evidence.

The repository currently contains the engineering conventions and package
foundation. The agent, CLI, and verification runner are not implemented yet.

## Initial workflow

The first implementation will accept a local Python repository, a fix commit,
and a maintained target branch. It will investigate compatibility differences,
propose a backport in a disposable clone, and validate it through an independent
container runner.

The intended output is a patch, the ported security regression test, and a report
of exact revisions, commands, results, and unresolved conditions. Verification
will mean that the recorded checks passed; it will not certify the entire app.

## Local credentials

The model integration will use the official OpenAI Python SDK and Responses API.
Store `OPENAI_API_KEY` in the local, ignored `.env` file or provide it through the
controller's environment. The SDK reads environment variables; loading a `.env`
file will be the controller's explicit responsibility.

Keep the value out of chat, Git, logs, and target execution containers. The
`.env.example` file documents the variable without containing a credential.
An ordinary project API key is sufficient; an organization admin key is not
required.

No live API call has been made. Live tests will require an explicit model and
an operator-supplied API budget. Most development tests will run offline.

## Development conventions

Read [AGENTS.md](AGENTS.md) for the coding and verification rules and primary
sources. The controller requires Python 3.12 or newer. Git and an accessible
Docker daemon will be required for end-to-end backport execution.

`pyproject.toml` configures Ruff, strict mypy, and pytest's `importlib` mode.
Runtime dependencies and a dependency lockfile will accompany implementation.
