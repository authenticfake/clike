# CLike VS Code Extension (v0.5.3)

![Logo di Clike](images/clike_64x64.png)

> AI-native software engineering assistant for day-to-day coding and Harper-style solutioning inside VS Code.
> Works with the **CLike Orchestrator** and **CLike Gateway** across multiple providers and model families.

>**CLike** is not just an agent that writes code; it is an AI-native platform that orchestrates verifiable capabilities across specs, plans, code, tests, reviews, and release gates.

**Clike** is 
- Harper-governed
- RAG-grounded
- Eval-driven
- Human-in-the-loop
- Multi-model / agent-agnostic
- Cloud + local agent compatible

## What the extension does today

The extension currently supports three main interactive modes inside the chat panel:

- **Free** — general Q&A and contextual assistance (cloud or local agent).
- **Coding** — code generation and patch-oriented workflows with files, diffs, and apply flows (cloud or local agent).
- **Harper** — structured solutioning workflow built around:
  - `IDEA`
  - `SPEC`
  - `PLAN`
  - `KIT`
  - `EVAL`
  - `GATE`
  - `FINALIZE`

It is designed to work with:

- OpenAI models
- Anthropic models
- Ollama / local backends
- other provider-routed models exposed by the Gateway

The extension is **provider-aware**, **model-aware**, and keeps a persistent chat timeline per model/history scope.

---

## Current highlights

### Chat modes

- **Free**
  - general questions
  - architecture discussion
  - lightweight contextual assistance

- **Coding**
  - generation results rendered in:
    - **Text**
    - **Diffs**
    - **Files**
  - hardened apply flow
  - explicit file writing / patch review workflow

- **Harper**
  - workspace-oriented delivery flow
  - document-driven generation
  - REQ-based implementation flow
  - integration with SPEC / PLAN / plan.json / KIT candidates

### Execution: cloud or local agent

Every chat mode can run via the cloud or via a local agent (Claude Code / Codex
CLI), selected with the **Execution** preference in the chat header. There are
three canonical modes:

- **`cloud only`** — never use a local agent; always route to the Gateway/cloud.
- **`prefer agent`** — try a valid, available local agent first, then fall back to
  cloud if no local executor can run the request.
- **`agent only`** — use only an available local agent; **never** fall back to
  cloud (a clear, deterministic error is shown if none is available).

The default is **`prefer agent`**. Legacy values are normalized automatically at
runtime, so older persisted settings keep working: `auto → cloud_only`,
`hybrid → prefer_local_agent`, `prefer_claude_code → prefer_local_agent`,
`claude_code_only → local_agent_only`.

- Local-agent execution covers **all Harper phases** (`/idea`, `/spec`, `/plan`,
  `/kit`, `/eval`, `/finalize`, `/extend`) as well as the standalone
  **Free (Q&A)** and **Coding** modes.
- An installed **Claude Code** CLI is treated as a first-class local executor by
  default (`clike.claudeCode.enabled` defaults to `true`); set it to `false` to
  disable Claude locally. Codex stays available when its CLI is installed.
- **Model selection per agent.** On every local run CLike pins the model via the
  CLI `--model` flag, using `clike.claudeCode.model` (default `opus`) and
  `clike.localAgent.codex.model` (default `gpt-5.5-codex`). For Claude, tier
  aliases like `opus`/`sonnet` always resolve to the latest model of that tier;
  leave a setting empty to use the CLI's own default. Codex exposes no
  model-list command, so set the exact model id your Codex login supports.
- **Model actually used is captured.** Claude is invoked with
  `--output-format json`, so CLike reads back the real model from the result
  envelope (also reflecting any fallback model); for Codex the used model is the
  one pinned via `--model`. The model is logged to the **Clike** output channel
  (`model_used=…`), shown in the live bubble badge (e.g.
  `agent-claude · claude-opus-4-8`), and persisted alongside the message.
- In **Free**, the local agent answers read-only; a short execution synthesis
  appears in the **Text** panel and the answer is persisted in the per-model
  history (like the cloud path), so it survives reload.
- In **Coding**, the local agent writes the generated files under
  `generated/<id>/` in the workspace root; the bubble shows the agent badge plus
  the file list, and the files are clickable in the **Files** tab.
- Local agents authenticate through their own CLI session — **no cloud API key is
  required or forwarded**.
- Provider availability is computed at the Gateway from configured API keys: when
  no cloud key is set, the cloud Execution options are disabled and the model list
  hides cloud models; selecting a model whose provider key is missing surfaces a
  clear message in the **Text** panel.

### Multi-model / multi-provider chat

The chat header supports:

- **mode selection**
- **model selection**
- **history scope selection**
  - current model only
  - all models

The extension preserves model selection better than older revisions and avoids unnecessary resets when reopening chat.

### Bubble timeline

The chat keeps a persistent bubble timeline with:

- user messages
- assistant messages
- system messages
- timestamps

### RAG support

The extension supports manual RAG flows:

- explicit indexing
- explicit search
- attaching RAG hits to the current conversation

### Attachments

The chat supports:

- inline attachments
- RAG attachments

These are used across Free / Coding / Harper flows.

### Themes

The chat panel supports four themes:

- `classic`
- `pro`
- `studio`
- `paper`

Current default: **`pro`**

---

## Quick start

### 1. Backend

Make sure these services are available:

- **Orchestrator**: `http://localhost:8080`
- **Gateway**: `http://localhost:8000`

Model routing and provider configuration are resolved through backend configuration.

### 2. Extension

From the extension folder:

```bash
npm install
```

Then:

- press **F5** to launch an Extension Development Host
- open Command Palette
- run **`CLike: Chat (Q&A / Harper / Coding)`**

### 3. Use the chat header

Select:

- mode
- model
- history scope

Then start working in Free, Coding, or Harper mode.

---

## Slash commands

Type commands directly in the chat input.

### General

- **`/help`** — shows the quick help overlay
- **`/status`** — shows current Harper/project context status
- **`/where`** — shows current workspace / doc-root path
- **`/switch <name|path>`** — switches to another Harper project

### Harper workspace

- **`/init <name> [--path <abs>] [--force]`**
  - initializes a Harper project/workspace scaffold
  - creates core Harper files and support structure

- **`/idea`**
  - formalizes or updates `IDEA.md`

- **`/spec [file|text]`**
  - generates or updates `SPEC.md` from IDEA/context

- **`/plan [spec_path]`**
  - generates or updates:
    - `PLAN.md`
    - `plan.json`
    - lane guides

### KIT flow

The extension currently supports a **base KIT run by default**, plus optional explicit follow-up phases.

- **`/kit`**
  - runs KIT on the next eligible REQ

- **`/kit REQ-001`**
  - runs base KIT for the selected REQ

- **`/kit REQ-001 --integrity`**
  - runs `integrity_eval`

- **`/kit REQ-001 --hardener`**
  - runs `promotion_hardener`

- **`/kit REQ-001 --promotion-eval`**
  - runs `promotion_eval`

- **`/kit REQ-001 --phases=kit,integrity_eval,promotion_hardener,promotion_eval`**
  - runs an explicit chained multi-phase KIT pipeline

### Eval / Gate

- **`/eval <REQ-ID>`**
  - evaluates the current KIT output for that REQ

- **`/gate <REQ-ID>`**
  - runs gate checks and promotion logic for that REQ

### Finalization

- **`/finalize`**
  - final gates / closure step for Harper workflows

### RAG

- **`/rag <query>`**
  - searches in RAG and shows top results

- **`/rag +<N>`**
  - attaches result `N` from the last RAG search

- **`/rag list`**
  - shows current attached files / RAG references

- **`/rag clear`**
  - clears current attachments

- **`/ragIndex [glob]`**
  - manually indexes content into RAG
  - examples:
    - `/ragIndex docs/**/*.md`
    - `/ragIndex **/*`

- **`/ragSearch <query>`**
  - searches the RAG directly and returns top results

---

## Current Harper behavior

### `/init`

The workspace initializer creates the Harper scaffold and support files such as:

- `README.md`
- `.clike/`
- `.github/`
- `docs/harper/`
- `runs/`

### `/plan`

The plan flow is expected to produce promotion-grade planning artifacts, including:

- `docs/harper/PLAN.md`
- `docs/harper/plan.json`
- lane guides under `docs/harper/lane-guides/`

### `/kit`

The extension supports REQ-based KIT execution and explicit KIT follow-up phases.

At the UX level, the current direction is:

- **base KIT first**
- additional phases only when explicitly requested

This keeps the extension compatible with more selective and cost-aware workflows.

---

## Command Palette commands

The extension currently contributes these key VS Code commands.

### Chat / core

- **CLike: Chat (Q&A / Harper / Coding)**
- **CLike: Clear Chat Session (current model)**
- **CLike: Chat Session File (current model)**
- **Clike: Ping Service**
- **Clike: Check Services**
- **Clike: List Models (via Gateway)**

### Coding / patching

- **Clike: Code Action…**
- **Clike: Add Docstring (AI via Orchestrator)**
- **Clike: Refactor (AI via Orchestrator)**
- **Clike: Generate Tests (AI via Orchestrator)**
- **Clike: Fix Errors (AI via Orchestrator)**
- **Clike: Apply Unified Diff (Hardened)**
- **Clike: Apply Unified Diff**
- **Clike: Apply New Content**
- **Clike: Apply Last Patch**

### RAG

- **Clike: RAG Reindex (via Orchestrator)**
- **Clike: RAG Search (via Orchestrator)**

### Git / promotion

- **Clike: Git Create Branch**
- **Clike: Git Commit Patch**
- **Clike: Git Open PR**
- **Clike: Git Smart PR**
- **CLike: Promote source code**
- **CLike: Quick Promote source code**

### Eval / governance

- **CLike: Run All Evals**
- **CLike: Gate Check (Phase)**
- **CLike: Sync Constraints (IDEA/SPEC)**
- **CLike: Update PLAN Checklist from Eval**
- **CLike: Harper Init…**

---

## UI guide

### Header

The chat header contains:

- mode selector
- model selector
- history scope selector

### Prompt area

The prompt area supports:

- slash commands
- attachments
- help overlay
- Harper/Coding/Free workflows

### Panels / tabs

Generation output is rendered through tabs:

- **Text**
- **Diffs**
- **Files**

### Bubble timeline

The timeline keeps contextual continuity for each chat context and supports timestamped interaction traces.

---

## Settings

Current configuration keys exposed by the extension include:

### Chat / UI

- `clike.chat.theme`
  - values:
    - `classic`
    - `pro`
    - `studio`
    - `paper`

- `clike.chat.autoOpenOnStartup`
- `clike.chat.persistDir`
- `clike.chat.never_send_source_to_cloud`
- `clike.chat.maxInMemoryMessages`
- `clike.chat.autoWriteGeneratedFiles`

### Execution / local agent

- `clike.execution.defaultPreference`
  - values: `cloud_only`, `prefer_local_agent`, `local_agent_only`
  - default: `prefer_local_agent` (legacy `auto`/`hybrid` are normalized at runtime)
- `clike.localAgent.enabled`
- `clike.localAgent.preferredExecutor` — `auto` | `claude_code` | `gpt_codex`
- `clike.claudeCode.enabled` — default `true`; treat an installed Claude CLI as a local executor
- `clike.claudeCode.command` — default `claude`
- `clike.claudeCode.model` — default `opus`; model pinned on every Claude run (`--model`). Tier aliases (`opus`/`sonnet`) always use the latest of that tier; empty = CLI default
- `clike.localAgent.codex.enabled`
- `clike.localAgent.codex.command` — default `codex`
- `clike.localAgent.codex.model` — default `gpt-5.5-codex`; model pinned on every Codex run (`--model`). Set the exact id your Codex login supports; empty = CLI default

### Backend endpoints

- `clike.orchestratorUrl`
- `clike.gatewayUrl`

### Optimization / behavior

- `clike.optimizeFor`
  - values:
    - `latency`
    - `cost`
    - `capability`

- `clike.harperTimeout`
- `clike.verboseLogging`
- `clike.docRoot`

### Apply behavior

- `clike.apply.backup`
- `clike.apply.requireCleanGit`
- `clike.apply.dryRunPreview`

### Git integration

- `clike.git.autoCommit`
- `clike.git.gitMergeOnGate`
- `clike.git.gitDeleteBranchOnMerge`
- `clike.git.gitReturnToFeatureAfterMerge`
- `clike.git.remoteUrl`
- `clike.git.commitMessage`
- `clike.git.openPR`
- `clike.git.remote`
- `clike.git.defaultBranch`
- `clike.git.conventionalCommits`
- `clike.git.pushRebase`
- `clike.git.branchPrefix`
- `clike.git.tagPrefix`
- `clike.git.prPerReqDraft.enabled`
- `clike.git.prPerReqDraft.useGhCli`
- `clike.git.prBodyPath`

### Routes

- `clike.routes`
  - contains orchestrator and gateway route mapping overrides

---

## Typical flows

### Free mode

- ask questions
- attach small files inline
- use RAG for larger context

### Coding mode

- ask for code / patches
- review output in Text / Diffs / Files
- apply only after inspection

### Harper mode

Typical flow:

1. `/init <name> [--path <abs>] [--force]`
2. complete or refine `IDEA.md`
3. `/spec`
4. `/plan`
5. `/kit REQ-XXX`
6. optionally:
   - `/kit REQ-XXX --integrity`
   - `/kit REQ-XXX --hardener`
   - `/kit REQ-XXX --promotion-eval`
   - or explicit `--phases=...`
7. `/eval <REQ-ID>`
8. `/gate <REQ-ID>`
9. `/finalize`

---

## Troubleshooting

### Chat opens but something looks stale
Reload the VS Code window and reopen chat, especially after source changes in development mode.

### KIT target selection issues
If `/kit REQ-XXX` does not behave as expected, verify:

- slash parsing
- message bridge from webview to extension host
- REQ resolution logic in the extension
- plan state (`open`, `done`, dependencies)

### Provider/model issues
If a model/provider combination does not behave correctly:

- verify backend model catalog
- verify Gateway model availability
- verify routing configuration in backend settings

### RAG issues
If manual RAG commands do not return expected results:

- verify orchestrator RAG endpoints
- re-index the relevant content
- check attached RAG references

---

## Backend endpoints (reference)

### Orchestrator
- `POST /v1/chat`
- `POST /v1/generate`
- `POST /v1/harper/spec`
- `POST /v1/harper/plan`
- `POST /v1/harper/kit`
- `POST /v1/harper/eval`
- `POST /v1/harper/gate`
- `POST /v1/harper/finalize`
- `POST /v1/rag/index`
- `POST /v1/rag/search`

### Gateway
- `GET /v1/models`
- provider/model routed chat-completion compatible endpoints

---

## Current positioning

This extension is no longer just a simple chat panel.

Today it acts as a **VS Code front-end for an AI-native software delivery workflow**, combining:

- interactive chat
- coding assistance
- Harper document-driven delivery
- REQ-based KIT execution
- RAG-assisted context retrieval
- eval / gate flows
- git-aware promotion flows

---

## Changelog summary for the current state

Compared with earlier simpler revisions, the extension now includes or exposes:

- theme selection for the chat webview
- stronger multi-model / multi-provider awareness
- history scope handling in the chat UI
- persistent bubble timeline with timestamps
- manual RAG indexing and attachment workflows
- richer Harper slash commands
- explicit KIT follow-up phases
- promote / quick-promote command palette actions
- expanded git-oriented settings and promotion behavior
- more configurable apply / backup / dry-run behavior
- streamlined Execution model: only `cloud_only` / `prefer_local_agent` /
  `local_agent_only`, with legacy `auto`/`hybrid` normalized at runtime
- Claude Code enabled as a first-class local executor by default
- availability-aware local routing (no unrunnable Codex package; `prefer agent`
  falls back to cloud, `agent only` fails deterministically)
- per-agent model selection via `--model` (`clike.claudeCode.model`,
  `clike.localAgent.codex.model`) and capture of the model actually used
- local-agent answers persisted in the per-model chat history (survive reload)

---

## Repo

Part of the **CLike** project family:
- VS Code extension
- Orchestrator
- Gateway

Use together for the full workflow.
