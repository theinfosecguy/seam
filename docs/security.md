# Execution boundaries

The controller trusts its installed dependencies, the operator's configuration,
the external oracle, the chosen image, Git, and the Docker daemon. Repository
files, commit messages, model responses, and command output are untrusted.

The controller resolves revisions to immutable commits and uses disposable Git
clones without shared object stores. The patching agent can inspect a bounded
view of the target source and submit a diff. Repository text cannot authorize
new tools, alter spending limits, change provider endpoints, or request secrets.
Configuration and credentials are loaded only from explicitly selected inputs.

Repository code is executed in containers, not directly by the controller. Test
containers have network access disabled, bounded CPU, memory, process counts,
output, and execution time, and reduced privileges. The original checkout and
Docker socket are not mounted; API credentials are not placed in the container
environment. The external oracle is mounted separately and read-only.

The agent's proposed result is independently tested against a frozen oracle and
configuration. Setup failures, skipped tests, timeouts, malformed evidence, and
missing checks produce unresolved evidence rather than a successful verdict.
Normal-behavior controls and the project suite check whether the candidate
achieves security by breaking valid behavior.

Source snapshots materialize relative file links only when resolution stays
inside the checkout and ends at an ordinary file. Excluded paths, escapes,
directory links, absolute links, cycles and hard links remain rejected. A shared
preflight checks every selected revision before image preparation; staging repeats
the checks because preflight cannot freeze a mutable filesystem.

Public cryptographic test fixtures require exact paths and reviewed SHA-256
hashes in the operator's configuration. Staging checks those bytes in every
revision; credential-store, link and model-read restrictions remain in force.
The operator must establish that these are published disposable test keys.

An optional operator-reviewed assertion patch is frozen separately from model
proposals. It changes only existing assertions in eligible test functions;
baselines keep their original tests and the external oracle stays unchanged.
Structural validation cannot prove assertion strength. The operator owns that
judgment, and the final exported patch includes the reviewed assertions.

The operator's explicit pytest plugins, import mode and suite marker expression
are frozen verification inputs. Plugins run in the container with target code;
they must be reviewed like the image and oracle. Marker filters apply only to
the existing suite, never the explicitly selected security regression or
controls. Excluding marked cases narrows the recorded compatibility coverage.

Prefer a Docker daemon accessible to the controller without privilege elevation.
If an operator explicitly selects a `sudo` command, timeout cleanup may also use
noninteractive `sudo` to signal only the process group created for that command.
The sudo policy must permit this cleanup; a Docker-only rule cannot guarantee
termination of a hung privileged client.

These restrictions have limits:

- Docker shares the host kernel and the daemon is a powerful host service.
  Use a dedicated machine or VM for repositories you consider actively hostile.
- A test suite samples behavior. Passing it cannot establish universal security
  or prove that a patch has no unrelated changes.
- Malicious source code runs inside pytest's Python process. It can detect test
  conditions, interfere with pytest, or forge JUnit output. The external oracle
  is read-only and frozen, but this does not make runtime evidence tamper-proof.
  Human review of the target code and candidate remains necessary. The workflow
  is for adapting known fixes in reviewed code, not certifying hostile patches.
- The trusted image supply chain and installed dependencies affect results.
  Verification records the resolved local image identity. Review or build the
  image before running sensitive source.
- Source excerpts sent to the selected API provider leave your machine. Only
  enable paid adaptation for code you are authorized to send. The harness's
  bounded file reader is not a complete secret scanner.

## Credential screening

Source excerpts, prompts, feedback, tool results, model text, reasoning, and patch
submissions are screened locally. Maintained `detect-secrets` detectors recognize
structured credentials and private keys. Literal normalization adds contextual
credential assignments in Python, JSON, and common configuration text. Parsing
is bounded. Ordinary source identifiers and public hashes are not rejected just
because they resemble credential names or have high entropy.

Seam calls only installed built-in detector matching methods. It does not verify
keys over a network, load repository detector configuration or plugins, obey
source allowlist comments, or persist findings containing the matched value.
Detection failures prevent transmission. The selected controller API key and
AWS credentials are also checked by exact value before each model request,
independent of their format.

This is a precaution, not a complete secret scanner. Maintained rules can lag
new vendor formats. Unknown bare tokens, computed or obfuscated values, and
ambiguous constant references can be missed; ordinary examples containing
literal credentials can be refused. Credential-store paths and private-key
extensions are excluded separately. Do not use these checks as permission to
send an unreviewed repository to an external model.

Do not put secrets in the target repository, oracle, or model-visible source.
Keep generated artifacts out of version control unless you have reviewed their
contents. The initial implementation has no service, multi-tenant isolation,
remote execution worker, or automatic merge path.

Report inspection checks stored consistency, including the final successful
candidate's evidence. It neither authenticates JSON nor reruns execution.
