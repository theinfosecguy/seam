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

Do not put secrets in the target repository, oracle, or model-visible source.
Keep generated artifacts out of version control unless you have reviewed their
contents. The initial implementation has no service, multi-tenant isolation,
remote execution worker, or automatic merge path.
