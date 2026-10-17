# Optional API-backed adaptation

Offline verification and the demo need no API key. Paid adaptation is explicitly
enabled by `--model`; simply having a key in the environment does not enable it.
The default provider is OpenAI. Select DeepSeek with `--provider deepseek`.

## Credentials and endpoints

The controller uses the official OpenAI Python SDK with each service's Responses
API. It reads only the selected service's credential:

| Provider | Environment variable | Endpoint |
| --- | --- | --- |
| `openai` | `OPENAI_API_KEY` | `https://api.openai.com/v1` |
| `deepseek` | `DEEPSEEK_API_KEY` | `https://api.deepseek.com` |

Each endpoint is fixed. Ambient base-URL settings, repository content, and tool
output cannot redirect authenticated requests. The key stays outside target
build and test containers.

The CLI reads the key from the controller environment or an explicitly selected
`--env-file`; it never searches the target checkout. A credential file accepts
`OPENAI_API_KEY=value` and/or `DEEPSEEK_API_KEY=value`, each at most once, plus
optional matching single or double quotes, blank lines, and comments. Only the
selected provider's assignment is used. That assignment must be present and
nonempty when a file is explicitly selected. The parser never falls back to the
other provider's key.

The file is not a shell script: it does not evaluate variable expansion,
`export`, or command substitutions. Unknown assignments and duplicate keys are
rejected. Protect credential files with mode `0600` and exclude them from Git.

```bash
# .env.deepseek contains DEEPSEEK_API_KEY=your-value; never paste it into chat.
chmod 600 .env.deepseek
uv run seam run \
  --repo /path/to/library --fix FIX_COMMIT --target release/1.x \
  --config /path/to/harness.toml --output /tmp/backport-deepseek \
  --provider deepseek --model deepseek-flash \
  --api-budget-usd 1 --env-file .env.deepseek
```

For OpenAI, store `OPENAI_API_KEY=your-value` in an ignored `.env` file with
mode `0600`. The default provider is OpenAI, so the corresponding command is:

```bash
uv run seam run \
  --repo /path/to/library --fix FIX_COMMIT --target release/1.x \
  --config /path/to/harness.toml --output /tmp/seam-openai \
  --model gpt-5.4-mini-2026-03-17 --api-budget-usd 1 --env-file .env
```

Exporting the selected provider's key in the controller environment also works;
omit `--env-file` in that case. Do not put credentials in source files or shell
arguments.

## Models and spending

DeepSeek supports `deepseek-flash` and `deepseek-v4-pro`. OpenAI's known model
registry includes `gpt-5.4-mini-2026-03-17` (the default OpenAI agent model),
`gpt-5-mini-2025-08-07`, and their matching unpinned aliases. Prices were checked
against official model documentation on **17 October 2026**. Pinned names make
the intended model version explicit; remote model availability still requires
a live test.

Unknown model names are rejected rather than assigned a guessed price. The
registry uses uncached peak input prices as an upper bound and documented peak
output prices. Before each request, the controller reserves the model's entire
documented input context plus the configured maximum output charge. This is
deliberately conservative and avoids estimating prompt tokens. Recheck the
registry after provider pricing changes. Unknown usage or a failed request
retains its reservation.

The default local dollar cap is US$10 per run. Set `--api-budget-usd` to a
different positive amount, or explicitly remove the dollar cap with
`--no-api-budget-cap`:

```bash
uv run seam run \
  --repo /path/to/library --fix FIX_COMMIT --target release/1.x \
  --config /path/to/harness.toml --output /tmp/backport-deepseek \
  --provider deepseek --model deepseek-v4-pro \
  --no-api-budget-cap --env-file .env.deepseek
```

The opt-out overrides `--api-budget-usd`; it requires an explicit `--model`.
Model calls, output tokens, tools, source reads, process duration, and adaptation
attempts remain bounded. Dollar accounting is still recorded. Provider account
usage is the source of truth for billing. A provider dashboard alert is not a
substitute for local request limits.

## Tools and evidence

The model can read relevant source files and submit a unified diff. It receives
the upstream patch and feedback from independently evaluated attempts. It cannot
run a terminal command, modify the trusted oracle, access the Docker socket, or
request the API key through a tool. Every tool argument is validated locally,
including when the provider does not enforce strict schemas. DeepSeek may
return parallel tool calls; source reads are handled in bounded batches and
patch submission must be the only call in its batch. A mixed submission/read
batch executes nothing: every call receives an error, and the model can retry
within the same cumulative call limit.

DeepSeek thinking mode uses automatic tool selection; forcing a required tool is
rejected by the live service. The controller accepts a patch only through a valid
`submit_patch` call and bounds corrective prompts for text-only responses by the
same cumulative call limit.

Live end-to-end API behavior requires a real key and must be tested explicitly.
Offline tests exercise orchestration with deterministic provider responses.
They do not prove current remote model availability or demonstrate a successful
live adaptation.

Official references:

- [OpenAI quickstart](https://developers.openai.com/api/docs/quickstart)
- [OpenAI function calling](https://developers.openai.com/api/docs/guides/function-calling)
- [Spend alerts and limits](https://developers.openai.com/api/docs/guides/terraform/rate-limits-and-spend)
- [GPT-5.4 mini model](https://developers.openai.com/api/docs/models/gpt-5.4-mini)
- [GPT-5 mini model](https://developers.openai.com/api/docs/models/gpt-5-mini)
- [DeepSeek Responses API](https://api-docs.deepseek.com/guides/responses_api/)
- [DeepSeek models and pricing](https://api-docs.deepseek.com/quick_start/pricing/)
- [DeepSeek thinking-mode tool selection](https://api-docs.deepseek.com/api/create-chat-completion/)
