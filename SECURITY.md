# Security

CLike drives cloud models and local coding agents that generate and execute code and write files.
This document describes the security model of the current release, its known limitations, and how
to report a vulnerability.

## Deployment assumption

CLike is designed for a **single developer on localhost**. The services are not meant to be exposed
on a network or shared between users.

## Security model (1.6.6)

| Area | Control |
|---|---|
| Service perimeter | Every orchestrator and gateway endpoint except `/health` requires `Authorization: Bearer <CLIKE_API_TOKEN>` (constant-time comparison). Services fail closed (HTTP 503) when no token is configured. Ports are published on `127.0.0.1` only. |
| Browser threats | No CORS. Requests with unexpected `Host` headers are rejected (DNS rebinding). The extension's local MCP server is disabled by default and, when enabled, always requires a token and rejects any request carrying an `Origin` header. |
| Service-to-service | Internal calls carry the service token. |
| Secrets in the extension | The service token is stored in VS Code SecretStorage and sent only to the configured orchestrator/gateway origins. |
| Workspace settings | Settings that select binaries, agent permission/sandbox modes, service URLs, Git remotes/push are machine-scoped; untrusted workspaces are not supported. |
| File confinement | Paths originating from requests, models or agents are confined to their roots (workspace, `runs/kit/<REQ>`, telemetry), rejecting traversal, absolute, drive/UNC paths and symlink escapes. The extension is the only workspace writer. |
| Project context sources | `.clike/context.yaml` sources are read by the orchestrator only inside the workspace (patterns with `..` or absolute paths and symlinks leaving it are ignored), read-only, size-capped, and presented to models as data, never as instructions; canonical documents win on conflict. |
| Process execution | No shell for process execution in the extension (argv only); on Windows the agent prompt goes through stdin. |
| Evaluation inputs | The gate executes the LTC profile stored in the workspace; an inline profile is accepted only if identical. The project root must be inside the configured projects directory. |
| Evaluation environment | Eval commands run without credentials (API keys, service token and similar variables are removed). What the checks need is created per run in the sandbox (generated sessions/ids, disposable PostgreSQL databases on the developer-configured `CLIKE_EVAL_POSTGRES_URL` server, services of other REQs on loopback ports, stopped after the checks); developer values come only from the git-ignored `docker/eval.env`. |
| Evaluation sandbox | Eval/gate commands run in a separate container with no credentials, no access to the gateway or vector store, non-root, read-only root filesystem, dropped capabilities and resource limits, projects mounted read-only. An offline mode removes network egress. It runs with an init that reaps orphaned processes; an exhausted sandbox (processes, memory, disk) stops the eval as environment-blocked instead of sending correct code to a repair. A local agent re-running checks (`eval-check`) goes through the extension and never receives the service token or network access. |
| Eval tools | Native tools for the checks are installed only from CLike's catalog (or the project's `.clike/eval-tools.yaml`) after the developer's confirmation, by a separate service reachable only by the orchestrator, without credentials; vendor archives are https-only and verified by sha256; the sandbox mounts them read-only. |
| Acceptance integrity | The acceptance surface of each requirement (tests, CI profile) is locked server-side before evaluation; removed/modified tests, weakened profiles and added skip markers block the gate. Auto-eval repairs may amend it only in audited, non-weakening ways (LTC command fixes, `ci/` dependency upgrades, unused imports, and test fixes with every assertion unchanged, flagged `review_required` at the gate). |
| Gate override | Manual overrides require a reason, are recorded in an audit log with an artifact digest and are reported as `OVERRIDE`, never `PASS`. |
| Gate verdict reuse | The gate reuses an eval verdict only when a digest the orchestrator computes from the project itself (code, KIT, every LTC, `plan.json`, CLike version) matches the one recorded with the passing eval in `CLIKE_STATE_DIR`, which agents cannot write; acceptance integrity and required outputs are still checked. A report edited by hand never produces a PASS. |
| KIT repository-root files | A KIT writes root deliverables only under `runs/kit/<REQ>/root/`; promotion writes them only within an allowlist (`scripts/`, `deploy/`, `infra/`, … plus `.clike/project.json` `root_folders` / `root_files`) and never `.git`, `.clike`, `runs`, `docs`, `src`, `test`, `ci`, `.env*` or keys; anything else is reported `rejected` and not written. |
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
- **`npm audit` in `extensions/vscode` reports 2 high findings** (`@azure/msal-node` 6.x,
  GHSA-xcx6-jx8p-x3h5, and `@azure/identity`, which pins `msal-node ^6`). They come only from
  `@vscode/vsce`, a development dependency that builds the `.vsix`: they are not in the installed
  extension, and the affected code is used only by `vsce publish` with Azure credentials, which CLike
  does not use. No fix exists upstream yet (`@azure/identity` 4.14.0 still requires `msal-node ^6`);
  updated when `@vscode/vsce` or `@azure/identity` move to `msal-node` 7.1+.

## Reporting a vulnerability

Please do **not** open a public issue for security problems. Use GitHub's private vulnerability
reporting for this repository (*Security → Report a vulnerability*), including affected version,
reproduction steps and impact. We aim to acknowledge reports within a few working days.
