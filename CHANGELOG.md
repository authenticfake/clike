# Changelog

All notable changes to CLike. Extension, orchestrator and gateway share one version.

## [Unreleased]

### Changed

- One FILE_REQUIREMENTS for cloud and local agents (B15): the agent package uses the obligations
  the orchestrator builds for every KIT (the ones the cloud prompt, the output contract and the gate
  use) and keeps its extra guidance as policies; it also writes the copy the gate reads under the
  locked `ci/`. Agent KITs now get concrete file roles, the namespace, and the launcher/runtime
  manifest requirements of their family; the noisy `external_library_obligation` is gone.
- KIT autofix for every ecosystem: final newline in sources, gofmt for Go when installed.
- `/agent-model` shows execution, default agent and models; `/agent-model list` lists the models.

- KIT: `TARGET_CONTRACT.json` and `FILE_REQUIREMENTS.json` are written by CLike (in `ci/` and
  `docs/`, same content) instead of being re-emitted by the model — fewer output tokens and no
  divergent copies (B8). Follow-up KIT stages see their options in the prompt (B7). The agent
  KIT/finalize contracts ask for the same deliverables as the cloud.

- BMAD runs: SPEC, plan.json and lane guides are checked against the BMAD quality contracts
  (deterministic, no LLM) and the gaps are reported as advisory `bmad_quality:` warnings; the
  unused fixture-only IDEA scorecard module was removed (L1).
- Debt: one slash parser in the webview (L4), deterministic repository manifest (B13), lane guides
  Markdown-only in the extension (B12), single finalize auth check (B11), flat agent audit files
  (B9), valid sample documents checked in CI (B14).

### Fixed

- A follow-up KIT stage (`--hardener`, ...) after the first eval started a new KIT generation
  and could rewrite the locked tests: it now keeps the generation and its test/ci changes are
  governed like a repair (L3).
- An eval or gate whose caller disconnected kept running in the sandbox (e.g. after a stopped
  benchmark it delayed the next eval by more than 30 minutes): it is now cancelled, with its
  processes, and the orchestrator answers 499.

## [1.1.0] — 2026-10-06 — Governed auto-eval on both paths, acceptance-first KIT

### Added

- Auto-eval with local agents: the agent package carries the failed checks, the hint and the
  repair rules; the acceptance files the agent changed are governed through
  `POST /v1/acceptance/amend` and the extension restores what is rejected. Benchmark
  `--runner agent --auto-eval N`.
- **Acceptance-first KIT** (`clike.kit.acceptanceFirst`, opt-in): `/kit` first generates only the
  acceptance tests and eval profile from SPEC/PLAN and locks them (`POST /v1/acceptance/lock`),
  then the code KIT writes the implementation against the locked tests (cloud and local agents;
  benchmark `--acceptance-first`). Addresses the known limitation that criteria and code came
  from the same call.
- `/agent-model [claude|codex] [model]`: show or change the local agent model from the chat
  (any mode).
- Local-agent telemetry: usage, API-equivalent cost, model and duration of Claude Code / Codex
  runs, in `.clike/telemetry` and in the gateway portal (`POST /v1/harper/telemetry`).

### Changed

- KIT generation (cloud and local agents): an eval-readiness self-check closes the prompt, with
  one rule per failure class measured by the benchmark (checks the LTC runs, files asserted by
  tests, behaviour over internals, real library APIs, time-bounded tests, read-only project
  root). PLAN acceptance items are stated at their observable boundary.
- Generated KIT files get safe mechanical lint fixes before they are written and locked
  (per-ecosystem registry; Python: ruff import order, unused imports, whitespace).

- Local-agent KIT context: content also written as package files (selected-capability guide,
  FILE_REQUIREMENTS) is referenced by path instead of repeated (smaller context, re-read on
  every agent turn).

### Fixed

- The configured agent model (`clike.claudeCode.model`, `clike.localAgent.codex.model`) applied
  only to chat; Harper phases ran with the CLI default model.
- Local-agent runs (including the eval pre-pass) left no telemetry and were attributed to the
  cloud model selected in the UI.

## [1.0.0] — 2026-10-05 — Milestone M3: ready for evolution

### ⚠️ Breaking changes

- Gateway `POST /v1/harper/run` requires `composed_messages`: the phase messages (system prompt,
  context, output checklist) are composed by the orchestrator. The gateway adds RAG material and
  chat history and calls the provider. Orchestrator and gateway must be updated together.
- Phase prompts moved from `gateway/prompts/harper/` to `orchestrator/phases/<phase>/cloud_*.md`;
  the `PROMPT_*_SYSTEM_PATH` variables are no longer read.

### Added

- **Auto-eval** (`docs/auto-eval.md`): `/eval REQ --fix ["hint"]` runs eval → KIT repair from the
  real failures → eval, up to `clike.autoEval.maxCycles` (default 2); rerunnable with a developer
  hint; `clike.autoEval.afterKit` runs it after `/kit`. Tests stay locked; an LTC command that
  cannot run and `ci/` dependency upgrades are accepted as audited amendments of the acceptance
  lock. When the eval shows that a test itself is wrong (an error raised in the test file, not a
  failed assertion), the test is fixed instead of the code, with every assertion unchanged; the
  gate reports `review_required`. API: `kit.repair` object on `/v1/harper/run`; benchmark
  `--auto-eval N`.
- **Regression of promoted REQs**: `/v1/eval/run` and `/v1/gate/check` accept `regression: true`
  (extension: `clike.eval.regression`, default on) and re-run the acceptance checks of every promoted
  REQ (plan status `done`) against the new code; the gate reports
  `GATE_BLOCKED_REGRESSION`.
- Browser e2e checks in the eval sandbox: Chromium system libraries in the image
  (`ENABLE_BROWSER`), browser downloaded on demand in the project's Playwright version.
- Harper benchmark (`benchmark/`): documented sample projects, cloud and local-agent runners,
  promotability metrics.
- `PhaseContext` v1: the typed, versioned contract of a phase run
  (`docs/contracts/phase_context.v1.schema.json`); the wire `core_blobs` are produced from it.
- Phase definitions as data in `orchestrator/phases/`: per-phase `phase.yaml` (write roots, output
  contract, rules, accepted result paths) and `text.yaml` (local-agent prompt and policy text).
- GPT-6 family support (reasoning models recognized by generation number); `openai:gpt-6.1-sol`
  in the catalog.
- Tests: characterization snapshots for local-agent packages and result normalization, phase
  definition parity with the extension, cloud/local-agent equivalence per phase.

### Changed

- Gate: warnings (failed non-blocking checks) no longer block; the gate passes with
  `GATE_PASS_WITH_WARNINGS` unless strict (`strict: true`, `clike.gate.strictWarnings`,
  `CLIKE_GATE_STRICT_WARNINGS=1`). Eval `promotable` follows the same policy.
- `services/local_agent_package.py` (6,900 lines) split into `services/local_agent/` (one module
  per phase, shared helpers, normalization); the old module is a compatibility facade.
- Local Claude Code never receives `ANTHROPIC_AUTH_TOKEN` (it would override the subscription
  login), like `ANTHROPIC_API_KEY`.

### Fixed

- Cloud `/kit` produced unusable paths for many plans: free text and placeholders became file
  paths (B18), the ecosystem was guessed from scattered words (e.g. `.js` files in a Python
  project, B19), and `__init__.py`, `ci/requirements.txt` or extra tests rejected the whole KIT
  (B20). The cloud KIT contract now matches the local agent's.
- Lane guides and selected capabilities were dropped from the cloud KIT context; the SPEC
  validator and prompt disagreed on the required sections.
- Coding mode wrote generated files to `/generated/...` outside the workspace.
- `kit.repair` sent by the extension (`/kit --repair`) is accepted as a flag or as an auto-eval
  repair request (the gateway rejected the orchestrator's default `false`).
- Eval honors the LTC `run_from` field as the commands' working directory.
- Cloud `/plan` received IDEA.md and SPEC.md by name only and could return an empty plan; it now
  receives them in full. Cloud `/kit` received no project documents and could ignore the
  technology constraints (e.g. Flask for a FastAPI project); its prompt now includes the
  technology constraints, the target REQ with its dependencies, SPEC.md and IDEA.md.
- Chat webview: REQ ids were never recognized and message previews replaced the letter "s" with
  spaces (regexes inside the webview script lost their backslashes).

### Removed

- Dead code: unused KIT/EVAL prompt builders, a shadowed duplicate function, an unused copy of
  the cloud capability renderer, unused gateway helpers.
- WP9 cleanup (about 2,700 lines): modules unreachable from any service entry point
  (`harper_flow/`, `constraints/`, `embeddings.py`, `spec_plan_gates.py`, …), unused functions and
  imports, commented-out code, the extension's `rag.js` and `fix_ext_vs.sh`.
- The gateway's own Qdrant store and embedder (unused): RAG is owned by the orchestrator; the
  gateway is a client of `/v1/rag`. The gateway no longer reads `EMBEDDING_DIM`,
  `RAG_EMBED_FAMILY`, `RAG_SCORE_THRESHOLD`.

### Changed (code quality)

- Duplicated provider result builders and local-agent failure responses consolidated; extension
  lint at zero warnings; code comments in English.

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
