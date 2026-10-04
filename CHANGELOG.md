# Changelog

All notable changes to CLike. Extension, orchestrator and gateway share one version.

## [Unreleased]

## [0.9.5] — 2026-10 — Milestone M2: correct and governed

### ⚠️ Breaking changes

- `/v1/gate/check` no longer accepts manual verdicts (`mode=manual`): use the new
  `POST /v1/gate/override` (reason required, audited). The extension does this for
  `/gate <REQ> manual pass`.
- Eval/gate refuse to run when the REQ acceptance surface changed after it was locked; re-run
  `/kit` to re-baseline.
- Orchestrator `POST /git/branch`, `/git/commit`, `/git/pr` removed (unused; they ran `git add .`
  in the server directory). The extension remains the only Git actor.
- Error statuses: a provider without an API key on the gateway is `503`
  `{code: provider_not_configured}` (was `401`); an unknown/disabled model is `400`
  `{code: model_selection_error}` (was `500`); gateway failures during any Harper phase keep their
  status and cause (`429`/`503`/`4xx` pass through, others `502`) instead of a generic `500`.
- Gateway: unknown Harper phases are rejected (`400`) and a missing phase prompt is `503`;
  `eval`/`gate` use their own prompts instead of the SPEC prompt.
- Extension settings removed (never read): `verboseLogging`, `docRoot`, `chat.autoOpenOnStartup`,
  `execution.showInChat`, `mcp.clientEnabled`, `mcp.serverEnabled`,
  `localAgent.codex.approvalMode`, `localAgent.codex.printModeFlag`.
- DeepSeek provider and the dedicated vLLM/Ollama modules removed; Ollama is reached through its
  OpenAI-compatible API.

### Added

- Acceptance lock and tamper detection for `runs/kit/<REQ>/test/**` and `ci/**`, taken before any
  local-agent eval pre-pass; reports include an `integrity` section.
- Audited gate override endpoint; overrides are reported as `OVERRIDE` and promoted only with an
  audit id.
- `eval-sandbox` service: eval/gate commands run without credentials, isolated from the gateway
  and vector store, non-root on a read-only filesystem; optional offline mode
  (`compose.eval-offline.yml`). Reports include `executor`.
- Provider support for Claude Opus 5.5 / Sonnet 5.5 and newer OpenAI models, while older models
  receive exactly the requests they did before (provider contract suite with a model matrix).
- Provider retries with backoff on 429/5xx/529 and connection errors (never on read timeouts);
  orchestrator → gateway retries only when the connection could not be opened.
- Opt-in telemetry retention: `CLIKE_TELEMETRY_RETENTION_DAYS` (default: keep everything).

### Fixed

- Anthropic: `tool_choice` `required` was sent as a string; sampling parameters are omitted for
  models that reject them; long system prompts are cached.
- Gateway chat returned provider failures as HTTP 200 with empty text; `temperature: 0` became 0.4.
- The cloud eval phase spent an LLM call whose output was discarded.
- The staged KIT chain crashed at the hardener stage (`NameError`).
- Extension: several runtime `ReferenceError`s, broken/unregistered commands, local agents left
  child processes running after a timeout, chat image previews rendered as text.
- `runId` could travel as the string `"None"`; a request without `flags` was rejected by the gateway.
- Extension `eval`/`gate` requests used `fetch`, which aborts after 300 s without response
  headers; all service calls now share one client with the Harper time budget.
- A passing gate reported `reason_code` `GATE_BLOCKED_STATUS_PASS` (now `GATE_PASS`).
- A gate `mode` passed as a query parameter was ignored.
- KIT stage artifacts were written to a non-persistent path in containers (`RUNS_DIR` now
  `/app/runs`).

## [0.9.0] — 2026-10 — Milestone M1: safe to run

Consolidation release: no new end-user features; security, correctness of Git operations,
reproducibility and test coverage.

### ⚠️ Breaking changes

- **Service token required.** Orchestrator and gateway reject requests without
  `Authorization: Bearer <CLIKE_API_TOKEN>` (503 if the token is not configured). Set
  `CLIKE_API_TOKEN` in `.env` and run *CLike: Set Service Token* in VS Code. MCP clients must send
  the same header.
- **`POST /v1/apply` removed.** The extension applies generated files locally.
- **Eval/gate confinement.** The project root must be under `CLIKE_PROJECTS_DIR` (`DEV_FOLDER`) or
  `CLIKE_EVAL_ALLOWED_ROOTS`; the LTC profile is read from the workspace and an inline profile must
  be identical (`CLIKE_ALLOW_INLINE_LTC=1` re-enables inline-only profiles).
- **Git automation off by default.** `git.autoCommit`, `git.openPR`, `git.gitMergeOnGate` and
  `git.pushRebase` default to `false`; pushing requires the new `git.autoPush`.
- **Extension MCP server off by default**; when enabled it always requires a token.
- **No CORS** on orchestrator and gateway.

### Security

- Authenticated services on loopback, Host-header validation, fail-closed configuration.
- Service-to-service authentication; telemetry UI login with an `HttpOnly`, `SameSite=Strict` cookie.
- Path confinement for workspace writes, KIT stage artifacts, telemetry and MCP reads.
- Eval commands run without credentials; containers run as non-root with the repository read-only.
- Argv-only process execution in the extension; prompt via stdin on Windows.
- Webview: cryptographic nonce, `img-src data:` only, escaped server-provided content.
- 18 security-relevant settings are machine-scoped; untrusted workspaces are not supported.
- Telemetry, certificates and build artifacts removed from the repository and its history.

### Fixed

- Harper Git sync could drop commits from an existing REQ branch and move the default branch
  (`checkout -B`); it also staged unrelated changes (`git add -A`) and committed every file when
  initializing a repository. Sync is now non-destructive and commits only the phase files.
- PR creation through the GitHub CLI never ran (it was invoked as `git gh …`).
- Conventional commit messages and per-REQ draft PRs were disabled by setting-name mismatches.
- `/v1/apply` client path fell through to the local path after a server error.

### Build and quality

- Python 3.12 for both services; `pyproject.toml` + `uv.lock` per service; container images built
  from the lockfiles; healthchecks; optional Ollama profile; Podman supported.
- Golden snapshots of the phase boundary; contract fixtures decoupling gateway tests from the
  orchestrator; security regression suites; Git tests on real repositories.
- ESLint with a frozen baseline; npm scripts; reproducible `.vsix` packaging.
- Repository hygiene check (pre-commit and CI); GitHub Actions CI.

### Removed

- Unused modules that executed shell commands (`new_eval.py`, `services/evals.py`,
  `services/embedded_ops.py`) and dead Git helpers.

## Earlier

Development history before 0.9.0 (Harper lifecycle, local agents for all phases, BMAD
methodology profile, `/extend`, capabilities) is available in the Git log.
