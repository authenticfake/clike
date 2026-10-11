# Changelog

All notable changes to CLike. Extension, orchestrator and gateway share one version.

## [Unreleased]

### Added

- **Test infrastructure for the eval sandbox** (`docker/eval.env`, git-ignored, template
  `docker/eval.env.example`): variables the projects' tests need, such as a real PostgreSQL test
  database URL, reach the sandbox only. Credential-like names are still refused.
- **`/eval` checks the required variables first.** The KIT declares them in `ci/LTC.json`
  (`environment.required_variables: [{name, purpose, example}]`; the free-form
  `environment: {NAME: "Required ..."}` of earlier KITs is understood too). When one is missing
  from the sandbox, the eval reports `BLOCKED` (`reason_code: EVAL_ENVIRONMENT_MISSING`) with the
  variable names and the `docker/eval.env` line to add, runs no check, and `/eval --fix` stops
  without a repair (no tokens spent on code that is not at fault).
- KIT (cloud and local agent): `ci/HOWTO.md` gets a mandatory `## Run with CLike /eval` section
  (required variables, `docker/eval.env` lines, one-time setup, rebuild, `/eval` and `--fix`).

### Fixed

- **`/eval` failed with `ACCEPTANCE_TAMPERED` from the second run on.** The acceptance lock hashed
  the files the eval itself writes (`ci/reports/**`: test/coverage/bandit reports, built wheels),
  so every later run found them "modified". Eval outputs (`reports/`, coverage files, `dist/`,
  `build/`, caches, `*.whl`, `*.pyc`, `*.log`) are no longer part of the acceptance surface, and
  locks written by earlier versions ignore their entries for those paths, without re-locking.
- **`/eval` with a local agent failed with `ACCEPTANCE_TAMPERED` after its own pre-pass.** The
  eval pre-pass agent repairs the candidate and could edit locked files under `test/` and `ci/`
  (e.g. add a test, rewrite a CI record) with no governance, so the canonical eval that follows
  found the surface changed. The acceptance surface is now locked before the pre-pass and the
  pre-pass changes go through the same audited amendment as the `--fix` repair: accepted ones are
  recorded, the others are restored. The eval agent is told that `test/` and `ci/` are locked and
  that evidence goes under `reports/`.
- **Telemetry portal: cost always 0 for Codex runs.** Codex reports tokens but no cost, so its
  rows had an empty `pricing`. The portal now estimates the API-equivalent cost from
  `configs/models.yaml` (new optional `cached_input_per_1k`; set for `gpt-6.1-sol`), also for the
  rows already recorded, marked `pricing.estimated`.
- **Eval sandbox OOM-killed on large JavaScript installs** (`503 eval sandbox unavailable`, then
  `npm install` exit 137 and every check `ENOENT`). Its work dirs (venvs, `node_modules`, npm
  cache) lived on the tmpfs `/tmp`, which counts against the container memory limit. They now live
  on the `eval_work` disk volume (`CLIKE_EVAL_BASE_DIR=/var/clike-eval`); `/tmp` is 1 GB. The image
  ships Node.js 22 LTS instead of 20 (current Next/Vitest/ESLint need it).
- `configs/models.yaml`: prices re-checked against the OpenAI and Anthropic price pages
  (2026-10-11); `gpt-5.4` input corrected to $2.50/M; `cached_input_per_1k` added where listed.
- `ci/HOWTO.md` (and any Markdown under `test/` or `ci/`) is documentation, no longer part of the
  acceptance lock: editing it by hand no longer reports `ACCEPTANCE_TAMPERED`.
- `/init`: `README_1st.md` showed `${project.org}` and escaped backticks; the Git steps now create
  the GitHub repository first (`gh repo create … --source . --remote origin --push`), since pushing
  to a repository that does not exist fails with "Repository not found".

## [1.3.0] — 2026-10-11 — Project context sources

### Added

- **Project context sources** (`.clike/context.yaml`, created by `/init`; see
  [docs/context-sources.md](docs/context-sources.md)): the project files the Harper phases read as
  context, each with a path glob, a role (`requirements`, `ui_reference`, `ux_requirements`,
  `api_reference`, `data_sample`, `style_guide`, `domain_glossary`, `example_output`, `reference`)
  and the phases that read it. Resolved server-side, read-only, and delivered to both runners: the
  cloud phase message gets a `PROJECT CONTEXT SOURCES` block, the local agent the list of files to
  read (converted documents written to `runs/context/<phase>/`). docx, xlsx/xls/xlsb, pptx and pdf
  are converted to text; HTML, CSS, SVG and other text files are passed as they are; images are
  opened by the local agents and listed by name for cloud models. Without the file: `docs/inputs/**`
  → `requirements` (idea, spec, plan), `docs/harper/ux/**` → `ui_reference` (spec, plan, kit).
  Canonical Harper documents win; size caps per file and per phase; unsafe paths ignored.
- `/init` creates `docs/inputs/`, `docs/harper/ux/` and `docs/reference/`.

### Changed

- The office/PDF text extraction of RAG indexing moved to `services/document_text.py`, shared with
  the context sources.

## [1.2.4] — 2026-10-11 — Invalid agent model rejected up front, agent errors shown

### Added

- **Invalid agent model rejected before the agent starts**: `clike.localAgent.codex.model` is checked
  against the models of the Codex login (`~/.codex/models_cache.json`), `clike.claudeCode.model`
  against the Claude aliases (`opus`, `sonnet`, `haiku`) and `claude-*` ids. An invalid id blocks
  every Harper phase and agent chat turn with `LOCAL_AGENT_MODEL_INVALID` and the closest valid id
  (`gpt6-1-sol` → `gpt-6.1-sol`) until it is fixed; VS Code shows the error at start-up and when the
  setting changes (with "Use …" and "Open Settings"), and `/agent-model` refuses an invalid id.
  Without the Codex models cache the Codex id is not checked.

### Changed

- **Faster, always-current container rebuild**: `docker/rebuild.sh` builds with the layer cache,
  recreates the containers, waits for `(healthy)`, checks that each container runs the image just
  built and prunes dangling layers. The orchestrator and the eval sandbox share one image (built
  once instead of twice); the uv download cache is a build cache mount and no longer stored in the
  image layers.

### Fixed

- **A failed agent run showed no cause**: with machine-readable output the agent writes its error on
  stdout (Codex `turn.failed`, Claude `is_error`), not on stderr; `LOCAL_AGENT_EXITED_WITH_ERROR` now
  carries that message (for example the provider's 404 for an unknown model).

## [1.2.3] — 2026-10-10 — Codex Harper phases in a project without git

### Fixed

- **Codex Harper phases in a project that is not a git repository** (a new `harper-init` project):
  Codex exited 1 ("Not inside a trusted directory and --skip-git-repo-check was not specified").
  The local-agent Harper phases now pass `--skip-git-repo-check`, as the agent chat already did.
- **A failed local-agent run reported a misleading error**: when the agent wrote nothing, the
  extension sent the files already on disk (the empty template `IDEA.md`) and the orchestrator
  answered `document_phase_output_incomplete`. The document and EXTEND phases now send only the
  files written during the run, and an agent that exits with an error and writes nothing reports
  `LOCAL_AGENT_EXITED_WITH_ERROR` with its own stderr.

## [1.2.2] — 2026-10-10 — Local document phases with Codex and BMAD companions

### Fixed

- **Codex in the local IDEA / SPEC / PLAN / EXTEND phases**: with `clike.localAgent.codex.sandboxMode`
  = `auto` (the default) these phases started Codex `--sandbox read-only`, so the agent could not
  write `IDEA.md`, `SPEC.md`, `PLAN.md`/`plan.json` or the EXTEND report and the phase failed with
  missing outputs. Every Harper local-agent phase now runs `workspace-write`; an explicit
  `read-only` is rejected up front with `LOCAL_AGENT_WRITE_MODE_UNAVAILABLE`.
- **BMAD companions in the local document phases**: the companion documents of the BMAD agent
  (`docs/harper/bmad/idea|spec|plan|architecture/**`, `docs/harper/ux/**`) are now collected by the
  extension, accepted by the write policy and by the orchestrator (paths re-derived server-side from
  the bundled BMAD manifest, Markdown only, never outside the agent's roots), and listed in the
  package write roots. Missing companions are reported as a warning.
- **BMAD `spec --agent ux` is companion-only locally too**: it no longer requires `SPEC.md`, and
  writing `SPEC.md` is rejected.
- **BMAD artifact policy lost with the workspace vendor manifest**: when the workspace carried
  `.clike/skills/vendor/bmad/manifest.json` (every `harper-init` project), it replaced the bundled
  manifest entirely and dropped its `artifact_policy`, agent profiles, workflows and quality
  contracts. The vendor manifest now overrides only the keys it defines, so the active output
  contract declares the companions again — locally and in the cloud prompt, where they are
  required outputs as documented in `docs/integrations/bmad/COMMANDS.md` (BMAD cloud prompts grow
  by 3–10 KB).
- **BMAD `finalize` in the cloud always failed**: the gateway BMAD artifact filter dropped the native
  finalize documents (`HOWTO_RUN.md`, `RELEASE_NOTES.md`, `SANITY_CHECKS.md`, `TODO_NEXT.md`,
  `PR_BODY.md`) that the active output contract then required. The native required outputs of the
  phase now stay allowed (except for companion-only agents).
- **Local BMAD prompts name the outputs of the role**: canonical outputs, mandatory companions,
  allowed companion roots and forbidden outputs of the selected agent (the workflow list mixed
  `pm` and `ux` files).

## [1.2.1] — 2026-10-06 — Agent chat approvals, Harper chat can write, readable /help

### Added

- **Approvals in the agent chat** (Coding and Harper, `clike.agentChat.approvals`, default `ask`): every
  edit and command of the agent waits for Allow / Allow all this turn / Deny in VS Code; writes
  outside the Coding output root are denied without asking. Claude Code asks through
  `--permission-prompt-tool` (a one-turn local MCP server), Codex runs through `codex app-server`
  (the same sessions as `codex exec`). `auto` keeps the previous behaviour.

### Changed

- **Harper free text with an agent can create files**: a request like "create a script that
  computes N!" in Harper mode no longer gets a read-only refusal; the agent writes only under
  `generated/<id>/` (same sandbox and approvals as Coding) and the files appear in the Files tab.
  Free (Q&A) stays read-only.
- **`/help` is readable on every theme**: VS Code theme colours, commands grouped by topic, a
  filter box, Esc / click outside to close.

### Fixed

- MCP `eval_run` with `fix` returned the report of the first eval: it now returns the report of
  the last eval after the repairs, plus `auto_eval {outcome, cycles, reason}`.
- `gpt-6.1-sol` pricing ($2.00 / $10.00 per 1M input / output tokens), 1,050,000-token context
  window and 128,000 max output tokens (B16).
- MCP setup uses `localhost` URLs (managed Claude Code policies often allow only
  `http://localhost*`); Codex approval of the CLike MCP tools is documented
  (`default_tools_approval_mode = "approve"`).

## [1.2.0] — 2026-10-06 — Native agent chat, CLike from Claude Code / Codex, contract alignment

### Added

- **Native agent chat** (H1): with execution = agent, the CLike chat talks to Claude Code / Codex as
  one continuing session per mode (free, coding, harper) — the first message starts it, the next
  ones resume it (Claude `--session-id`/`--resume`, Codex `exec resume`) and only the new turn is
  sent; the agent's text and the tools it uses stream into a live bubble; Cancel stops the agent.
  `/agent-session [new|new all]` shows or restarts the sessions. Codex chat now runs with the
  mode's sandbox (read-only, workspace-write for coding).
- **CLike from Claude Code / Codex** (H2): the extension MCP server runs phases through the
  governed chat flow and returns their outcome (`harper_run_phase` waits up to `wait_seconds`,
  then `harper_run_status`), plus `eval_run` (optionally the auto-eval `fix`) and `gate_check`;
  no overrides, promotion or git from MCP. The orchestrator MCP Harper read tools accept a
  `project_root` (confined to the projects directory). Verified with Codex calling
  `harper_req_list` on a project.

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
