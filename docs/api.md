# AI adaptation

The demo and supplied-patch verification need no API key. Seam creates a paid
client only when you supply `--model`. The model reads bounded source excerpts
and proposes a patch; Seam runs the verification independently.

Run `uv run --frozen seam doctor` from the intended checkout to see the installed
version and actual package path, alongside Git and Docker availability. This
helps distinguish environments when replaying a report with `seam inspect`.

## Choose a provider

Seam uses [PydanticAI's maintained model adapters](https://ai.pydantic.dev/models/overview/)
for native message formats, tool calls, reasoning state, and token usage. Its
own session retains control of tools, validation, request limits, and spending.

| `--provider` | Credential | API |
| --- | --- | --- |
| `openai` (default) | `OPENAI_API_KEY` | OpenAI Responses |
| `anthropic` | `ANTHROPIC_API_KEY` | Anthropic Messages |
| `google` | `GOOGLE_API_KEY` | Gemini GenerateContent |
| `deepseek` | `DEEPSEEK_API_KEY` | DeepSeek Chat Completions |
| `xai` | `XAI_API_KEY` | xAI Chat Completions |
| `mistral` | `MISTRAL_API_KEY` | Mistral Chat Completions |
| `groq` | `GROQ_API_KEY` | Groq Chat Completions |
| `openrouter` | `OPENROUTER_API_KEY` | OpenRouter Chat Completions |
| `together` | `TOGETHER_API_KEY` | Together Chat Completions |
| `azure` | `AZURE_OPENAI_API_KEY` | Azure OpenAI Responses |
| `bedrock` | Explicit AWS credentials | Bedrock Converse |
| `vertex` | Explicit service-account JSON file | Vertex Gemini GenerateContent |

Model IDs pass through to the selected adapter. There is no model allowlist;
choose a text model that supports function tools. A new model can still require
an updated adapter or different account access. This is not support for every
model, modality, authentication method, or arbitrary API-compatible host.

## API keys

Save the selected key in an ignored local file, then run:

```bash
# .env.deepseek contains DEEPSEEK_API_KEY=your-value
chmod 600 .env.deepseek
uv run seam run \
  --repo /path/to/library --fix FIX_COMMIT --target release/1.x \
  --config /path/to/harness.toml --output /tmp/seam-ai \
  --provider deepseek --model deepseek-flash \
  --api-budget-usd 1 --env-file .env.deepseek
```

For another provider, change its name, model, and key assignment. The CLI can
instead read the selected variable from the controller environment; omit
`--env-file`. Keys never enter target containers. Do not pass keys as arguments.

An explicit credential file accepts the variables in the table and
`AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_SESSION_TOKEN`. Assignments
must be unique. Matching quotes, comments, and blank lines are accepted. Unknown
variables, shell commands, and `export` are rejected; variable expansion never
runs. Seam reads only the selected service's credentials and never searches the
target repository or falls back from an explicit file to ambient credentials.

## Cloud configuration

Cloud routing belongs in a separate `--provider-config provider.toml`. This is
operator-supplied metadata, not a repository configuration or credential store.
Unknown fields and settings for a different provider are rejected.

Azure requires an OpenAI resource endpoint and an explicit API version:

```toml
azure_endpoint = "https://YOUR-RESOURCE.openai.azure.com"
azure_api_version = "2025-04-01-preview"
```

Use `--provider azure --model YOUR-DEPLOYMENT --provider-config provider.toml`
and supply `AZURE_OPENAI_API_KEY`. Azure model IDs are deployment names; provide
the underlying model's rates and context when the catalog cannot resolve them.

Bedrock requires a region in the TOML:

```toml
aws_region = "us-east-1"
```

Use `--provider bedrock --model MODEL-OR-INFERENCE-PROFILE-ID` and select
`AWS_ACCESS_KEY_ID` and `AWS_SECRET_ACCESS_KEY` through the controller environment
or `--env-file`; include `AWS_SESSION_TOKEN` for temporary credentials. Seam uses
explicit SigV4 credentials. It does not use ambient AWS profiles, metadata
services, bearer tokens, or custom endpoints.

Vertex requires these fields:

```toml
google_project = "YOUR-PROJECT"
google_location = "us-central1"
google_credentials_path = "service-account.json"
```

Use `--provider vertex --model MODEL-ID --provider-config provider.toml`.
The credential path is relative to this TOML file or absolute. Only an explicitly
selected service account with a private signing key is supported; ambient
application-default credentials and `--env-file` are not used for Vertex.
Protect the JSON file as a secret and keep it outside the target checkout.

## Prices and limits

The default CLI dollar cap is US$10 per run. Before each request, Seam reserves
the full documented context charge plus the maximum output charge. This avoids
guessing prompt size. It can refuse a request whose actual cost would be small.

Rates come from checked OpenAI/DeepSeek schedules or the bundled
[`genai-prices` catalog](https://github.com/pydantic/genai-prices). There are no
network price updates. Seam uses the highest listed text tier, including cache
write rates. Review current provider pricing before relying on a dollar cap.
For missing metadata or private deployments, set all missing values explicitly:

```text
--input-price-per-million 3 --output-price-per-million 15 --context-tokens 200000
```

Alternatively, `--no-api-budget-cap` explicitly removes the dollar cap. If prices
or context remain unknown, reported cost is `unknown`, not zero. Call, output,
source-read, tool, execution-time, and adaptation limits still apply. Missing,
invalid, or incomplete usage stops the session and retains the reservation.
Provider account billing remains the source of truth.

SDK network retries and automatic continuation are disabled. A request guard
also rejects an additional HTTP request within one reservation. Failed requests
are not automatically retried. Native SDK error bodies and debug logs are not
included in Seam's diagnostics.

The CLI defaults to 32 model requests per run. Set `--max-model-calls` to an
integer from 1 to 32 to select another request limit, for example
`--max-model-calls 16` with `--model`. The count is cumulative across all attempts;
the dollar cap and other limits remain in force. Each request allows at
most 16,384 output tokens and has a 120-second timeout. The public Python agent
also accepts explicit limits within the hard bounds; its constructor defaults
are independent of the CLI.

Bedrock uses a synchronous AWS client in a worker thread. On timeout or
cancellation, Seam waits for its in-flight call to finish before closing the
client. AWS connect/read timeouts still apply; cleanup can exceed the outer
request timeout. The reservation is retained and another request is refused.

## Tools and testing

All providers use the same confined tools and locally validated schemas. The
model cannot run commands or modify the oracle. A patch submission must be the
only call in its batch; a mixed read/submission batch executes nothing. Malformed
arguments receive generic corrective feedback without echoing rejected values.
Operator-reviewed assertion updates and fixture allowances stay frozen and grant
no additional model permissions; see the [configuration guide](usage.md).

Tests exercise native SDK serialization and replies with mock HTTP transports,
plus Bedrock and Vertex authentication paths. These checks do not establish live
availability or account permissions. Live tests require a separate credential
for each service; see [validation results](provider-validation.md) for exactly
what was run.
