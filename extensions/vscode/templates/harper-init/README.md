# CLike VS Code Extension

> AI-native software engineering assistant for day-to-day coding, Harper-style solutioning, local-agent execution, RAG, Git-aware promotion, and MCP-driven agent interaction inside VS Code.

![CLike logo](./images/clike/clike_128x128.png)

The extension works with:

- **CLike Orchestrator**;
- **CLike Gateway**;
- cloud model providers;
- local coding agents;
- repository RAG;
- Harper workflow artifacts.

---

## What the extension does today

The extension supports three main interactive modes inside the chat panel:

- **Free** — general Q&A and contextual assistance.
- **Coding** — code generation and patch-oriented workflows with files, diffs, and apply flows.
- **Harper** — structured solutioning workflow built around:
  - `IDEA`
  - `SPEC`
  - `PLAN`
  - `KIT`
  - `EVAL`
  - `GATE`
  - `FINALIZE`

It is designed to work with:

- OpenAI models;
- Anthropic models;
- OpenAI-compatible models exposed by the Gateway;
- local coding agents such as Claude Code and GPT Codex;
- future provider-routed or local backends exposed by the CLike stack.

The extension is provider-aware, model-aware, workspace-aware, agent-aware, and MCP-ready.

---

## Current highlights

### Chat modes

#### Free

- general questions;
- architecture discussion;
- lightweight contextual assistance;
- optional RAG grounding.

#### Coding

- code generation;
- text/diff/file rendering;
- patch-oriented flows;
- explicit review before apply.

#### Harper

- document-driven delivery;
- REQ-based implementation flow;
- SPEC/PLAN/KIT/EVAL/GATE lifecycle;
- local-agent execution packages;
- RAG-backed workspace context;
- Git-aware promotion.

---

## Agent-centric workflow support

CLike supports two agentic operating models.

### Model 1 — Developer activates a local agent through CLike

Flow:

```text
Developer
→ VS Code Extension
→ Orchestrator
→ Agent execution package
→ Extension local actuator
→ Claude Code or GPT Codex
→ Extension collects result
→ Orchestrator normalizes
→ RAG/Git/Eval/Gate continue through CLike
```

The extension is the local actuator.

It physically runs the agent CLI, but the orchestrator owns the workflow contract.

The local agent receives files such as:

```text
runs/kit/<REQ-ID>/docs/AGENT_EXECUTION_CONTEXT.json
runs/kit/<REQ-ID>/docs/AGENT_PROMPT.md
```

For eval pre-pass flows, it may receive:

```text
runs/kit/<REQ-ID>/docs/AGENT_EVAL_CONTEXT.json
runs/kit/<REQ-ID>/docs/AGENT_EVAL_PROMPT.md
```

Local agents must write only under allowed candidate roots, such as:

```text
runs/kit/<REQ-ID>/src
runs/kit/<REQ-ID>/test
runs/kit/<REQ-ID>/ci
runs/kit/<REQ-ID>/docs
runs/kit/<REQ-ID>/reports
```

They must not write directly to canonical `src/`, `test/`, or `tests/`.

### Model 2 — External/local agent interacts with CLike through MCP

Flow:

```text
Agent
→ Extension MCP operational server
→ Extension dispatches normal slash command
→ Normal CLike flow
→ Orchestrator
→ Gateway / local-agent / RAG / Git / Eval / Gate
```

The extension MCP server does not duplicate Harper logic.

It dispatches the same slash commands the developer can type in chat.

---

## MCP support

### Extension MCP operational server

The extension can expose a local MCP-compatible operational server.

Its purpose is to let an external/local agent operate CLike safely.

Example tool surface:

- `clike_extension_status`
- `harper_next_action`
- `harper_run_phase`
- `harper_kit_next`
- `harper_continue_loop`
- `rag_reindex`
- `rag_docs_status`
- `rag_docs_reindex_if_empty`

Typical usage:

```text
Agent asks: run next kit
Extension MCP resolves next open REQ
Extension dispatches: /kit REQ-002
Normal Harper flow continues
```

### MCP settings

The extension can expose settings such as:

- `clike.mcp.extensionServerEnabled`
- `clike.mcp.extensionServerHost`
- `clike.mcp.extensionServerPort`
- `clike.mcp.extensionServerToken`

Typical local endpoint:

```text
http://127.0.0.1:55742/mcp
```

Health check:

```bash
curl -s http://127.0.0.1:55742/health | jq
```

Tool list:

```bash
curl -s http://127.0.0.1:55742/mcp   -H 'content-type: application/json'   -d '{
    "jsonrpc": "2.0",
    "id": 1,
    "method": "tools/list",
    "params": {}
  }' | jq
```

Run next KIT from an agent:

```bash
curl -s http://127.0.0.1:55742/mcp   -H 'content-type: application/json'   -d '{
    "jsonrpc": "2.0",
    "id": 2,
    "method": "tools/call",
    "params": {
      "name": "harper_kit_next",
      "arguments": {}
    }
  }' | jq -r '.result.content[0].text'
```

The next REQ policy is intentionally simple:

```text
first REQ in docs/harper/plan.json with status = open
```

If no open REQ exists and no in-progress REQ exists, CLike reports `finalize_only`.

---

## Quick start

### 1. Backend

Make sure these services are available:

- Orchestrator: `http://localhost:8080`
- Gateway: `http://localhost:8000`

Model routing and provider configuration are resolved through backend configuration.

### 2. Extension

From the extension folder:

```bash
npm install
```

Then:

- press **F5** to launch an Extension Development Host;
- open Command Palette;
- run **`CLike: Chat (Q&A / Harper / Coding)`**.

### 3. Use the chat header

Select:

- mode;
- model;
- history scope.

Then start working in Free, Coding, or Harper mode.

---

## Slash commands

Type commands directly in the chat input.

### General

| Command | Description |
|---|---|
| `/help` | Shows the quick help overlay. |
| `/status` | Shows current Harper/project context status. |
| `/where` | Shows current workspace and doc-root path. |
| `/switch <name\|path>` | Switches to another Harper project. |

### Harper workspace

| Command | Description |
|---|---|
| `/init <name> [--path <abs>] [--force]` | Initializes a Harper project/workspace scaffold. |
| `/idea` | Formalizes or updates `IDEA.md`. |
| `/spec [file\|text]` | Generates or updates `SPEC.md` from IDEA/context. |
| `/plan [spec_path]` | Generates or updates `PLAN.md`, `plan.json`, and lane guides. |

### Agent selection

| Command | Description |
|---|---|
| `/agent-default auto` | Let CLike select the local executor when local-agent execution is enabled. |
| `/agent-default claude` | Prefer Claude Code as local executor. |
| `/agent-default codex` | Prefer GPT Codex / Codex CLI as local executor. |

Internal executor IDs may be normalized to:

```text
claude_code
gpt_codex
auto
```

### KIT flow

The extension supports base KIT execution plus optional follow-up phases.

| Command | Description |
|---|---|
| `/kit` | Runs KIT on the next target REQ. |
| `/kit REQ-001` | Runs base KIT for the selected REQ. |
| `/kit REQ-001 --integrity` | Runs `integrity_eval`. |
| `/kit REQ-001 --hardener` | Runs `promotion_hardener`. |
| `/kit REQ-001 --promotion-eval` | Runs `promotion_eval`. |
| `/kit REQ-001 --phases=kit,integrity_eval,promotion_hardener,promotion_eval` | Runs an explicit chained multi-phase KIT pipeline. |

KIT may execute through:

- cloud path;
- local Claude Code path;
- local GPT Codex path.

### Eval and Gate

| Command | Description |
|---|---|
| `/eval <REQ-ID>` | Evaluates the current KIT output for that REQ. |
| `/gate <REQ-ID>` | Runs gate checks and promotion logic for that REQ. |

`/eval` can optionally run a local-agent pre-pass, but canonical eval remains CLike-owned.

### Finalization

| Command | Description |
|---|---|
| `/finalize` | Runs final gates and closure step for Harper workflows. |

### RAG

| Command | Description |
|---|---|
| `/rag <query>` | Searches in RAG and shows top results. |
| `/rag +<N>` | Attaches result `N` from the last RAG search. |
| `/rag list` | Shows current attached files/RAG references. |
| `/rag clear` | Clears current attachments. |
| `/ragIndex [glob]` | Manually indexes content into RAG. |
| `/ragSearch <query>` | Searches the RAG directly and returns top results. |

Examples:

```text
/ragIndex docs/**/*.md
/ragIndex docs/**/*
/ragIndex runs/kit/REQ-001/**/*
/ragSearch adapter registry
```

---

## Current Harper behavior

### `/init`

The workspace initializer creates Harper scaffold and support files such as:

- `README.md`;
- `.clike/`;
- `.github/`;
- `docs/harper/`;
- `runs/`.

### `/idea`

Creates or updates product intent and problem framing.

### `/spec`

Creates or updates requirements and acceptance criteria.

### `/plan`

Produces promotion-grade planning artifacts:

- `docs/harper/PLAN.md`;
- `docs/harper/plan.json`;
- lane guides under `docs/harper/lane-guides/`.

### `/kit`

Produces candidate artifacts per REQ.

Expected candidate roots:

```text
runs/kit/<REQ-ID>/src
runs/kit/<REQ-ID>/test
runs/kit/<REQ-ID>/ci
runs/kit/<REQ-ID>/docs
```

### `/eval`

Validates candidate artifacts.

Eval may read:

- `LTC.json`;
- `HOWTO.md`;
- candidate source;
- candidate tests;
- generated reports;
- dependency KITs;
- canonical workspace source/test roots.

### `/gate`

Promotes only when quality gates pass.

Gate remains CLike-owned.

---

## Command Palette commands

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

- mode selector;
- model selector;
- history scope selector.

### Prompt area

The prompt area supports:

- slash commands;
- attachments;
- help overlay;
- Harper/Coding/Free workflows.

### Panels / tabs

Generation output is rendered through tabs:

- Text;
- Diffs;
- Files.

### Bubble timeline

The timeline keeps contextual continuity and supports timestamped interaction traces.

---

## Settings

### Chat / UI

- `clike.chat.theme`
  - `classic`
  - `pro`
  - `studio`
  - `paper`
- `clike.chat.autoOpenOnStartup`
- `clike.chat.persistDir`
- `clike.chat.never_send_source_to_cloud`
- `clike.chat.maxInMemoryMessages`
- `clike.chat.autoWriteGeneratedFiles`

### Backend endpoints

- `clike.orchestratorUrl`
- `clike.gatewayUrl`

### Harper behavior

- `clike.harperTimeout`
- `clike.docRoot`
- `clike.verboseLogging`

### Local agent

- `clike.localAgent.enabled`
- `clike.localAgent.preferredExecutor`
- `clike.localAgent.claudeCode.enabled`
- `clike.localAgent.claudeCode.command`
- `clike.localAgent.codex.enabled`
- `clike.localAgent.codex.command`

### MCP extension server

- `clike.mcp.extensionServerEnabled`
- `clike.mcp.extensionServerHost`
- `clike.mcp.extensionServerPort`
- `clike.mcp.extensionServerToken`

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
  - orchestrator and gateway route mapping overrides.

---

## Typical flows

### Free mode

- ask questions;
- attach small files inline;
- use RAG for larger context.

### Coding mode

- ask for code or patches;
- review output in Text/Diffs/Files;
- apply only after inspection.

### Harper cloud flow

```text
/init <name>
/idea
/spec
/plan
/kit REQ-001
/eval REQ-001
/gate REQ-001
/finalize
```

### Harper local-agent KIT flow

```text
/agent-default codex
/kit REQ-001
/eval REQ-001
/gate REQ-001
```

or:

```text
/agent-default claude
/kit REQ-001
/eval REQ-001
/gate REQ-001
```

### Agent-driven Model 2 flow through MCP

```text
Agent calls harper_next_action
Agent calls harper_kit_next
Extension dispatches /kit REQ-XXX
Normal CLike flow runs
Agent calls harper_run_phase phase=eval req_id=REQ-XXX
Agent calls harper_run_phase phase=gate req_id=REQ-XXX
If no REQ remains, agent calls /finalize
```

---

## Troubleshooting

### MCP extension server does not respond

Check settings:

- `clike.mcp.extensionServerEnabled`
- `clike.mcp.extensionServerHost`
- `clike.mcp.extensionServerPort`

Then test:

```bash
curl -s http://127.0.0.1:55742/health | jq
```

### Agent command accepted but nothing runs

Verify that the CLike chat panel is available and that the extension posted the slash command to the webview.

Expected extension log pattern:

```text
[CLike][mcp-extension]
Agent requested: /kit REQ-001
[harperRun] normalized kit target='REQ-001'
```

### KIT target selection issues

If `/kit REQ-XXX` does not behave as expected, verify:

- slash parsing;
- webview-to-extension bridge;
- REQ resolution logic;
- `docs/harper/plan.json` state.

### Local agent issues

Verify:

- agent command is installed;
- configured command is correct;
- `/agent-default codex|claude|auto` is set as intended;
- executor availability logs are clean.

### Provider/model issues

Verify:

- gateway model catalog;
- gateway model availability;
- route configuration;
- provider API keys.

### RAG issues

Verify:

- orchestrator RAG endpoints;
- Qdrant/vector-store availability;
- reindex content with `/ragIndex docs/**/*`;
- use `rag_docs_reindex_if_empty` through MCP if needed.

---

## Backend endpoints reference

### Orchestrator

- `POST /v1/chat`
- `POST /v1/generate`
- `POST /v1/harper/spec`
- `POST /v1/harper/plan`
- `POST /v1/harper/kit`
- `POST /v1/harper/eval`
- `POST /v1/harper/gate`
- `POST /v1/harper/finalize`
- `POST /v1/harper/local-agent/complete`
- `POST /v1/rag/index`
- `POST /v1/rag/search`
- `POST /v1/rag/fetch`
- `POST /mcp/`

### Gateway

- `GET /v1/models`
- `POST /v1/chat`
- `POST /v1/generate`
- `POST /v1/embeddings`

### Extension MCP

- `GET /health`
- `GET /tools`
- `POST /mcp`

---

## Current positioning

This extension is a VS Code front-end for an AI-native software delivery workflow.

It combines:

- interactive chat;
- coding assistance;
- Harper document-driven delivery;
- REQ-based KIT execution;
- local-agent execution;
- RAG-assisted context retrieval;
- eval/gate flows;
- Git-aware promotion;
- MCP-driven agent interoperability.

---

## Changelog summary for the current state

Compared with earlier revisions, the extension now includes or exposes:

- theme selection for the chat webview;
- stronger multi-model / multi-provider awareness;
- history scope handling;
- persistent bubble timeline;
- manual RAG indexing and attachment workflows;
- richer Harper slash commands;
- explicit KIT follow-up phases;
- local-agent execution through Claude Code and GPT Codex;
- `/agent-default auto|claude|codex`;
- eval pre-pass support for local agents;
- MCP operational server for agent-to-CLike workflows;
- promote / quick-promote command palette actions;
- expanded Git settings and promotion behavior;
- configurable apply / backup / dry-run behavior.

---

## Repo

Part of the CLike project family:

- VS Code extension;
- Orchestrator;
- Gateway.

Use all three together for the full AI-native workflow.