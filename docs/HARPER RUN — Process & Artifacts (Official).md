# HARPER RUN — Process & Artifacts (Official)

## Overview

Harper Run is the CLike implementation of an AI-native, eval-driven, human-in-the-loop development pipeline for featurelets:

```text
IDEA.md → /spec → /plan → (/kit → /eval → /gate)* → /finalize → Solution
```

The current implementation extends the classic Harper loop with:

- VS Code extension-first operation;
- Orchestrator-owned phase semantics;
- Gateway-backed multi-provider model execution;
- RAG-grounded context;
- optional local-agent execution through **Claude Code** and **GPT Codex**;
- MCP surfaces on both Orchestrator and VS Code extension;
- staged KIT quality phases: **KIT → INTEGRITY_EVAL → PROMOTION_HARDENER → PROMOTION_EVAL**;
- canonical executable eval and gate artifacts.

Harper remains human-governed: CLike can generate, harden, evaluate, and promote, but the developer is the final orchestrator and validator.

---

## 1) Runtime Architecture

```text
Developer / External Agent
        │
        ▼
VS Code Extension
  - Chat UI
  - Slash commands
  - workspace file collection
  - local-agent actuation
  - Git and promotion helpers
  - Extension Operational MCP server
        │
        ▼
Orchestrator
  - Harper phase control
  - RAG APIs
  - local-agent package generation
  - local-agent completion normalization
  - canonical eval/gate endpoints
  - Orchestrator MCP server
        │
        ▼
Gateway
  - model catalog and routing
  - provider adapters
  - chat/completions
  - embeddings
  - Harper prompt execution
  - telemetry APIs
        │
        ▼
Providers / Local Runtime
  - OpenAI
  - Anthropic
  - Ollama
  - vLLM
  - DeepSeek
  - Claude Code CLI
  - GPT Codex CLI
```

---

## 2) Inputs & Knowledge Model

Each phase uses scoped context. CLike avoids dumping the whole repository unless explicitly needed.

Inputs can include:

- Harper chat history with selected history scope.
- Canonical docs in `docs/harper/`.
- Core docs loaded by exact name or prefix.
- Inline attachments.
- RAG references and retrieved chunks.
- Repository context collected by the extension.
- `plan.json` REQ metadata.
- Local-agent capability and availability data.
- Git branch/status metadata.

Important canonical inputs:

```text
docs/harper/IDEA.md
docs/harper/SPEC.md
docs/harper/PLAN.md
docs/harper/plan.json
docs/harper/constraints.json
docs/harper/lane-guides/<lane>.md
```

---

## 3) Folder Structure

```text
docs/harper/
  IDEA.md
  SPEC.md
  PLAN.md
  plan.json
  KIT.md
  RELEASE_NOTES.md
  PR_BODY.md
  SANITY_CHECKS.md
  TODO_NEXT.md
  constraints.json
  lane-guides/
    <lane>.md

runs/kit/<REQ-ID>/
  src/
  test/
  ci/
    LTC.json
    HOWTO.md
    requirements.txt
  docs/
    README_<REQ-ID>.md
    KIT_<REQ-ID>.md
    AGENT_EXECUTION_CONTEXT.json
    INTEGRITY_EVAL.json

runs/<runId>/
  kit.report.json
  eval.summary.json
  gate.decisions.json
  telemetry.json
  logs/

src/
  ...promoted production code...

test/ or tests/
  ...promoted tests...
```

`runs/kit/<REQ-ID>/...` is the candidate artifact area. It is intentionally separate from canonical project roots.

---

## 4) Commands & Phases

### `/idea` → `IDEA.md`

**Purpose**  
Help the human produce a complete idea: vision, problem statement, target users, value, outcomes, and constraints.

**Output**

```text
docs/harper/IDEA.md
```

### `/spec` → `SPEC.md`

**Purpose**  
Translate IDEA into a testable product/engineering contract.

**Output**

```text
docs/harper/SPEC.md
```

SPEC must contain acceptance criteria and must not generate code.

### `/plan` → `PLAN.md` + `plan.json`

**Purpose**  
Break SPEC into dependency-aware REQ units and metadata.

**Output**

```text
docs/harper/PLAN.md
docs/harper/plan.json
```

Plan entries may include lane, domain, packs, skills, design profiles, runtime profile, gate expectations, module boundary, and dependencies.

### `/kit [<REQ-ID>]` → candidate implementation

**Purpose**  
Generate candidate source, tests, validation contracts, and REQ docs.

**Default behavior**

```text
/kit
```

runs the next open/in-progress REQ selected by the extension.

```text
/kit REQ-001
```

runs a specific REQ.

**Candidate outputs**

```text
runs/kit/<REQ-ID>/src/
runs/kit/<REQ-ID>/test/
runs/kit/<REQ-ID>/ci/LTC.json
runs/kit/<REQ-ID>/ci/HOWTO.md
runs/kit/<REQ-ID>/docs/README_<REQ-ID>.md
runs/kit/<REQ-ID>/docs/KIT_<REQ-ID>.md
```

### `/kit` staged phases

The current KIT path supports additional quality phases:

```text
/kit REQ-001 --phases kit,integrity_eval,promotion_hardener,promotion_eval
```

| Phase | Purpose | Notes |
|---|---|---|
| `kit` | Generate the base candidate. | Compatible with local-agent execution. |
| `integrity_eval` | Inspect candidate completeness and structural integrity. | Produces/uses integrity evidence such as `INTEGRITY_EVAL.json`. |
| `promotion_hardener` | Harden the candidate for promotion. | Requires existing candidate artifacts and normally integrity evidence. |
| `promotion_eval` | Final promotion-readiness semantic review. | Does not replace canonical executable eval. |

The extension blocks post-KIT phases when required candidate artifacts are missing.

### `/eval [<REQ-ID>]`

**Purpose**  
Run or prepare evaluation for the selected REQ.

Current behavior is split:

1. **Harper `/eval` pre-pass** may prepare a local-agent diagnostic/hardening package.
2. **Canonical eval** is executed by Orchestrator eval endpoint and produces normalized evidence.

Canonical endpoint:

```text
POST /v1/eval/run
```

Canonical output:

```text
runs/<runId>/eval.summary.json
```

### `/gate [<REQ-ID>]`

**Purpose**  
Apply dependency and quality policy, then promote eligible candidate artifacts.

Canonical endpoint:

```text
POST /v1/gate/check
```

Output:

```text
runs/<runId>/gate.decisions.json
```

Gate updates plan state and may trigger Git operations depending on settings.

### `/finalize`

**Purpose**  
Generate release artifacts after mandatory REQs are done or scope is explicitly accepted.

Outputs:

```text
docs/harper/RELEASE_NOTES.md
docs/harper/PR_BODY.md
docs/harper/SANITY_CHECKS.md
docs/harper/TODO_NEXT.md
```

---

## 5) Local-Agent Execution

CLike supports an agentic local path for compatible Harper flows.

### 5.1 Why local agents exist

Local agents allow CLike to delegate candidate implementation work to local developer tools while retaining CLike control over:

- target REQ contract;
- allowed write roots;
- forbidden paths;
- capability context;
- evidence collection;
- normalization;
- promotion and gate decisions.

### 5.2 Supported executors

| Executor | ID | Default command | Notes |
|---|---|---|---|
| Claude Code | `claude_code` | `claude` | Uses non-interactive print mode, default flag `-p`, default permission mode `acceptEdits`. |
| GPT Codex | `gpt_codex` | `codex` | Invoked as `codex exec <prompt>`. |

### 5.3 Settings

```jsonc
{
  "clike.execution.defaultPreference": "auto",
  "clike.localAgent.enabled": true,
  "clike.localAgent.preferredExecutor": "auto",
  "clike.localAgent.allowEval": true,
  "clike.localAgent.restrictToKitPhases": true,
  "clike.localAgent.timeoutMinutes": 20,

  "clike.claudeCode.enabled": false,
  "clike.claudeCode.command": "claude",
  "clike.claudeCode.printModeFlag": "-p",
  "clike.claudeCode.permissionMode": "acceptEdits",

  "clike.localAgent.codex.enabled": true,
  "clike.localAgent.codex.command": "codex"
}
```

### 5.4 `/agent-default`

The chat supports:

```text
/agent-default codex
/agent-default claude
/agent-default auto
```

This updates the preferred local executor in the extension state. It does not bypass Orchestrator ownership.

### 5.5 Local-agent package lifecycle

```text
/kit REQ-001
  → Orchestrator chooses local-agent path when requested/supported
  → Orchestrator returns package with AGENT_EXECUTION_CONTEXT.json
  → Extension writes package files
  → Extension runs Claude Code or GPT Codex
  → Extension collects candidate artifacts under runs/kit/REQ-001/
  → Extension calls /local-agent/complete
  → Orchestrator normalizes result
  → Extension continues normal CLike flow
```

### 5.6 `AGENT_EXECUTION_CONTEXT.json`

This file is the local execution contract.

It contains:

- schema version;
- phase and run ID;
- target REQ;
- selected executor hint;
- execution preference and fallback policy;
- workflow ownership rules;
- local runtime policy;
- capability context;
- repository analysis requirements;
- allowed write roots;
- forbidden paths;
- expected outputs;
- hard rules.

Local agents must not write outside allowed roots and must not run Git commands.

---

## 6) Skills, Capabilities, Packs, and Runtime Profiles

CLike uses REQ metadata to shape prompts and local-agent contracts.

| Metadata | Meaning |
|---|---|
| `lane` | Technology lane such as Python, JS/TS, IaC, or extension work. |
| `domain` | Domain boundary, such as gateway, orchestrator, extension, RAG, MCP, or eval. |
| `runtime_profile` | Local/cloud/on-prem execution expectation. |
| `packs` | Framework/tooling packs relevant to implementation. |
| `skills` | Required engineering skills or model capabilities. |
| `design_profiles` | Architecture profiles to follow. |
| `gate_expectations` | Checks expected by eval/gate. |
| `main_module_boundary` | Primary module area the REQ should affect. |
| `future_compatibility_notes` | Constraints for future evolution. |

The local-agent prompt explicitly tells the executor to respect this context.

---

## 7) MCP Support

CLike currently has two MCP surfaces.

### 7.1 Orchestrator MCP Server

Mounted at:

```text
/mcp
```

Enabled by:

```text
CLIKE_MCP_SERVER_ENABLED=true
```

Mode:

```text
read_only / service / contract-first
```

The Orchestrator MCP server exposes tools such as:

- `clike_capabilities_list`
- `clike_health_get`
- `clike_models_list`
- `clike_profiles_list`
- `clike_routing_resolve`
- `clike_about`
- `clike_harper_workflow_explain`
- `clike_artifacts_explain`
- `harper_project_read_core`
- `harper_doc_read`
- `harper_plan_read`
- `harper_req_list`
- `harper_req_get`
- `harper_req_next`
- `harper_kit_prepare`
- `rag_search`
- `runs_list`
- `runs_read`
- `eval_read_summary`
- `gate_read_decision`
- `harper_status_read`
- `clike_operational_model_explain`
- `rag_docs_status`
- `rag_reindex_docs`
- `rag_reindex_docs_if_empty`

Not exposed:

- arbitrary shell;
- arbitrary filesystem write;
- Git mutation;
- raw provider proxying;
- direct phase execution from Orchestrator MCP;
- UI/session mutation.

### 7.2 Extension Operational MCP Server

The VS Code extension exposes a local MCP-compatible operational server.

Default URL:

```text
http://127.0.0.1:55742/mcp
```

Settings:

```jsonc
{
  "clike.mcp.extensionServerEnabled": true,
  "clike.mcp.extensionServerHost": "127.0.0.1",
  "clike.mcp.extensionServerPort": 55742,
  "clike.mcp.extensionServerToken": ""
}
```

The extension server supports JSON-RPC methods:

- `initialize`
- `notifications/initialized`
- `tools/list`
- `tools/call`

Tools:

- `clike_extension_status`
- `harper_next_action`
- `harper_run_phase`
- `harper_kit_next`
- `harper_continue_loop`
- `rag_reindex`
- `rag_docs_status`
- `rag_docs_reindex_if_empty`

The extension operational MCP server is the correct surface for **Model 2**: an external/local agent interacts with CLike by asking the extension to dispatch normal slash commands. It does not duplicate the Harper engine.

---

## 8) RAG Support

RAG is exposed both through the extension and Orchestrator.

### Extension commands

```text
/ragIndex <glob-or-path>
/ragSearch <query>
```

### Orchestrator APIs

```text
POST /v1/rag/index
POST /v1/rag/reindex
POST /v1/rag/search
POST /v1/rag/fetch
POST /v1/rag/fetch_by_paths
POST /v1/rag/purge
```

RAG supports:

- indexing workspace docs/files;
- searching semantic context;
- fetching docs by prefix or exact paths;
- grounding Harper phases;
- supporting MCP tools and agent workflows.

---

## 9) Eval and Gate

### Eval

There are two levels:

| Level | Purpose |
|---|---|
| `/eval` Harper pre-pass | Optional local-agent diagnostic/hardening support. |
| `/v1/eval/run` canonical eval | Normalized executable evidence used by gate. |

Canonical eval output:

```text
runs/<runId>/eval.summary.json
```

### Gate

Gate evaluates:

- dependency readiness;
- required checks;
- thresholds;
- conflicts;
- promotion safety.

Canonical gate output:

```text
runs/<runId>/gate.decisions.json
```

Promotion is blocked when eval fails, dependencies are incomplete, or target paths conflict without explicit handling.

---

## 10) Git Governance

CLike Git behavior is implemented in the extension and assisted by Orchestrator endpoints.

Relevant extension commands include:

- `clike.gitCreateBranch`
- `clike.gitCommitPatch`
- `clike.gitOpenPR`
- `clike.gitSmartPR`
- `clike.promoteReqSources`
- `clike.promoteReqSourcesQuick`

Relevant settings:

```jsonc
{
  "clike.git.autoCommit": true,
  "clike.git.openPR": true,
  "clike.git.remote": "origin",
  "clike.git.defaultBranch": "main",
  "clike.git.conventionalCommits": true,
  "clike.git.pushRebase": true,
  "clike.git.branchPrefix": "feature",
  "clike.git.tagPrefix": "harper",
  "clike.git.prBodyPath": "docs/harper/PR_BODY.md"
}
```

Gate-time promotion and merge behavior depends on workspace configuration and must remain observable in logs and artifacts.

---

## 11) Telemetry

Telemetry is collected across phases where available.

Typical fields:

- provider;
- model;
- context window;
- prompt size;
- completion cap;
- token usage;
- phase timings;
- files written or changed;
- tests/check counts;
- gate decisions;
- execution path (`cloud`, `local_agent`, fallback reason);
- local-agent executor, when used.

Expected path:

```text
runs/<runId>/telemetry.json
```

Gateway also exposes Harper telemetry APIs and UI endpoints.

---

## 12) API Reference Summary

### Orchestrator

```text
GET  /health
GET  /version
GET  /models
GET  /models/defaults
GET  /profiles
GET  /routing/resolve
POST /session/clear
GET  /runs/{run_id}
POST /idea
POST /spec
POST /plan
POST /kit
POST /eval
POST /finalize
POST /local-agent/complete
POST /agent/code
POST /v1/eval/run
POST /v1/gate/check
POST /v1/rag/index
POST /v1/rag/reindex
POST /v1/rag/search
POST /v1/rag/fetch
POST /v1/rag/fetch_by_paths
POST /v1/rag/purge
POST /git/branch
POST /git/commit
POST /git/pr
MCP  /mcp
```

### Gateway

```text
GET  /health
GET  /v1/models
GET  /v1/models/validate
POST /v1/chat/completions
POST /v1/embeddings
POST /run
GET  /harper/ui
GET  /harper/files
GET  /harper/projects
GET  /harper/aggregate
GET  /harper/series
GET  /harper/top
GET  /harper/raw
```

---

## 13) Operational Notes

- Base `/kit` is the primary generation phase and can use the local-agent path.
- Post-KIT phases need existing candidate artifacts.
- `/eval` pre-pass is not canonical gate evidence by itself.
- Canonical eval/gate remain CLike-owned.
- MCP operational execution should go through the extension MCP server, not the Orchestrator MCP server.
- Local agents must not run Git, promote files, or mutate canonical docs directly.
- Candidate artifacts should be reviewed and promoted only through CLike gate/promotion paths.

---

## 14) Rescoping

Scope changes should be captured in `docs/harper/KIT.md` under Product Owner Notes and then reflected back into `plan.json` and `PLAN.md` through the appropriate Harper flow.

A valid rescope must preserve traceability:

```text
IDEA/SPEC intent → PLAN REQ → KIT candidate → EVAL evidence → GATE decision → FINALIZE notes
```
