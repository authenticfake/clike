# Security

CLike drives cloud models and local coding agents that generate and execute code and write files.
This document describes the security model of the current release, its known limitations, and how
to report a vulnerability.

## Deployment assumption

CLike is designed for a **single developer on localhost**. The services are not meant to be exposed
on a network or shared between users.

## Security model (1.0.0)

| Area | Control |
|---|---|
| Service perimeter | Every orchestrator and gateway endpoint except `/health` requires `Authorization: Bearer <CLIKE_API_TOKEN>` (constant-time comparison). Services fail closed (HTTP 503) when no token is configured. Ports are published on `127.0.0.1` only. |
| Browser threats | No CORS. Requests with unexpected `Host` headers are rejected (DNS rebinding). The extension's local MCP server is disabled by default and, when enabled, always requires a token and rejects any request carrying an `Origin` header. |
| Service-to-service | Internal calls carry the service token. |
| Secrets in the extension | The service token is stored in VS Code SecretStorage and sent only to the configured orchestrator/gateway origins. |
| Workspace settings | Settings that select binaries, agent permission/sandbox modes, service URLs, Git remotes/push are machine-scoped; untrusted workspaces are not supported. |
| File confinement | Paths originating from requests, models or agents are confined to their roots (workspace, `runs/kit/<REQ>`, telemetry), rejecting traversal, absolute, drive/UNC paths and symlink escapes. The extension is the only workspace writer. |
| Process execution | No shell for process execution in the extension (argv only); on Windows the agent prompt goes through stdin. |
| Evaluation inputs | The gate executes the LTC profile stored in the workspace; an inline profile is accepted only if identical. The project root must be inside the configured projects directory. |
| Evaluation environment | Eval commands run without credentials (API keys, service token and similar variables are removed). |
| Evaluation sandbox | Eval/gate commands run in a separate container with no credentials, no access to the gateway or vector store, non-root, read-only root filesystem, dropped capabilities and resource limits, projects mounted read-only. An offline mode removes network egress. |
| Acceptance integrity | The acceptance surface of each requirement (tests, CI profile) is locked server-side before evaluation; removed/modified tests, weakened profiles and added skip markers block the gate. Auto-eval repairs may amend it only in audited, non-weakening ways (LTC command fixes, `ci/` dependency upgrades, unused imports, and test fixes with every assertion unchanged, flagged `review_required` at the gate). |
| Gate override | Manual overrides require a reason, are recorded in an audit log with an artifact digest and are reported as `OVERRIDE`, never `PASS`. |
| Containers | Services run as a non-root user; the CLike repository (including `.git`) is mounted read-only. |
| Git | Only the files of a phase are committed; no branch is rewritten; commit, push, merge-on-gate and PR automation are opt-in. |
| Logging | Request bodies are never logged; unhandled errors return a correlation id instead of internal details. |
| Repository | A pre-commit/CI hygiene check blocks telemetry, private notes, keys and secrets from being committed. |

## Known limitations

- **Eval commands are model-authored.** They run in the eval sandbox, which by default allows
  network egress (needed for dependency installs) and can read the projects directory; use the
  offline mode to remove egress. The sandbox is long-lived (fresh working directories per run,
  not a fresh container per run).
- **Acceptance criteria and implementation come from the same KIT phase by default.** The lock
  prevents later tampering. With `clike.kit.acceptanceFirst` the tests are derived from SPEC/PLAN
  and locked by a separate call before the implementation exists.
- **Local agents** run with the permissions of the developer's CLI session; CLike constrains them
  through the phase contract and post-run validation, not through an OS sandbox.

## Reporting a vulnerability

Please do **not** open a public issue for security problems. Use GitHub's private vulnerability
reporting for this repository (*Security → Report a vulnerability*), including affected version,
reproduction steps and impact. We aim to acknowledge reports within a few working days.
