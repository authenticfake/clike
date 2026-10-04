# Security

CLike drives cloud models and local coding agents that generate and execute code and write files.
This document describes the security model of the current release, its known limitations, and how
to report a vulnerability.

## Deployment assumption

CLike is designed for a **single developer on localhost**. The services are not meant to be exposed
on a network or shared between users.

## Security model (0.9.0)

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
| Containers | Services run as a non-root user; the CLike repository (including `.git`) is mounted read-only. |
| Git | Only the files of a phase are committed; no branch is rewritten; commit, push, merge-on-gate and PR automation are opt-in. |
| Logging | Request bodies are never logged; unhandled errors return a correlation id instead of internal details. |
| Repository | A pre-commit/CI hygiene check blocks telemetry, private notes, keys and secrets from being committed. |

## Known limitations

- **Eval commands are model-authored.** The checks executed by the gate are produced during the KIT
  phase and run inside the orchestrator container (non-root, no credentials, read-only repository,
  but with network access and read access to the projects directory). Isolated, network-less
  per-run sandboxes are planned for the next milestone.
- **Acceptance criteria and implementation come from the same phase.** Freezing criteria before
  implementation and detecting test tampering is planned for the next milestone.
- **Manual gate override.** `/gate <REQ> manual pass` records a pass without executing checks; an
  authorized, audited override is planned.
- **Local agents** run with the permissions of the developer's CLI session; CLike constrains them
  through the phase contract and post-run validation, not through an OS sandbox.

## Reporting a vulnerability

Please do **not** open a public issue for security problems. Use GitHub's private vulnerability
reporting for this repository (*Security → Report a vulnerability*), including affected version,
reproduction steps and impact. We aim to acknowledge reports within a few working days.
