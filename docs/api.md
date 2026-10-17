# Optional API-backed adaptation

Offline verification and the demo need no API key. Paid adaptation is explicitly
enabled by `--model`; simply having a key in the environment does not enable it.
The CLI reads `OPENAI_API_KEY` from the controller environment or a file named
with `--env-file`. It never searches the target checkout for credentials.

An explicit credential file supports one `OPENAI_API_KEY=value` assignment,
optional matching single or double quotes, blank lines, and comments. It is not
a shell script: variable expansion, `export`, command substitutions, and extra
assignments are unsupported. Protect it with mode `0600` and exclude it from Git.

The CLI's known model registry includes `gpt-5.4-mini-2026-03-17` (the default
agent model), `gpt-5-mini-2025-08-07`, and their matching unpinned aliases. Prices
were checked against official model documentation on **17 October 2026**.
Pinned names make the intended model version explicit; remote model availability
still requires a live test. The registry uses standard-tier uncached input
prices as an upper bound and the documented output price. Recheck the registry
before relying on it after provider pricing changes.

Unknown CLI model names are rejected rather than assigned a guessed price.
Before each request, the controller reserves the model's entire documented
input context plus the configured maximum output charge from the run budget.
This is deliberately conservative and avoids estimating prompt tokens. Unknown
usage or a failed request retains its reservation. Model
calls, response tokens, tools, source reads, and adaptation attempts are bounded.
The local controller ceiling is US$10 per run; use a smaller `--api-budget-usd`
for initial integration tests. A provider dashboard budget alert is not a hard
spending cap. Account usage remains the source of truth for billing.

The model can read relevant source files and submit a unified diff. It receives
the upstream patch and feedback from independently evaluated attempts. It cannot
run a terminal command, modify the trusted oracle, access the Docker socket, or
request the API key through a tool.

Live end-to-end API behavior requires a real key and should be tested explicitly.
Offline tests exercise the same orchestration with recorded, deterministic
provider responses. They do not prove current remote model availability or
demonstrate a successful live adaptation.

Official references:

- [OpenAI quickstart](https://developers.openai.com/api/docs/quickstart)
- [Function calling](https://developers.openai.com/api/docs/guides/function-calling)
- [Spend alerts and limits](https://developers.openai.com/api/docs/guides/terraform/rate-limits-and-spend)
- [GPT-5.4 mini model](https://developers.openai.com/api/docs/models/gpt-5.4-mini)
- [GPT-5 mini model](https://developers.openai.com/api/docs/models/gpt-5-mini)
