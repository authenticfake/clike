# CLike — Harper Process I/O Map

**Document:** `CLike_PROCESS_IO.md`  
**Scope:** Input/output definitions, ownership boundaries, artifacts, and execution contracts for the CLike Harper pipeline — **IDEA → SPEC → PLAN → KIT → EVAL → GATE → FINALIZE** — aligned to the current VS Code extension, Orchestrator, Gateway, local-agent, RAG, MCP, skills, and capabilities implementation.

---

## 0) Operating Model

CLike is an **extension-first AI-native development pipeline**. The VS Code extension is the developer-facing control surface; the Orchestrator owns Harper semantics, RAG, local-agent contracts, eval/gate normalization, and the read-only/service MCP surface; the Gateway owns model/provider IO and Harper phase generation.

Current runtime split:

| Layer | Responsibility |
|---|---|
| **VS Code Extension** | Chat UX, slash commands, workspace file collection, local file writes, local-agent actuation, Git promotion, extension operational MCP server. |
| **Orchestrator** | Harper control plane, RAG APIs, phase request shaping, local-agent package generation, local-agent result normalization, canonical eval/gate endpoints, service/read-only MCP server. |
| **Gateway** | Model routing, provider calls, OpenAI/Anthropic/Ollama/vLLM/DeepSeek compatible chat, embeddings, Harper prompt execution, telemetry APIs. |
| **Local Agent Executors** | Optional non-interactive execution through **Claude Code** or **GPT Codex** for compatible local flows. They are actuators, not final gate authorities. |
| **Human Harper Orchestrator** | Final product/engineering authority. Approves scope, reviews outputs, runs/accepts evidence, and controls promotion. |

The current implementation supports both cloud model execution and local-agent-assisted execution. Local agents write only candidate artifacts under `runs/kit/<REQ-ID>/...`; canonical promotion into project roots remains controlled by CLike and the human.

---

## 1) Phase I/O — End-to-End Map

Each phase lists **Inputs**, **LLM / Agent Responsibilities**, **Outputs**, and **Consumers**.

### 1.1 IDEA Phase

**Inputs**
- Chat intent and business context.
- Optional attachments and RAG context.
- Existing `docs/harper/*` documents when the project is being reshaped rather than initialized.
- Optional `TECH_CONSTRAINTS.yaml` or constraint material embedded in IDEA/SPEC.

**Responsibilities**
- Help the Human Harper Orchestrator express the product idea completely.
- Define vision, problem statement, target users, business outcomes, constraints, risks, and non-goals.
- Keep the output business-oriented and implementation-light.

**Outputs**
- `docs/harper/IDEA.md`

**Consumers**
- `/spec`
- Human review and scope alignment
- RAG indexing for downstream grounding

---

### 1.2 SPEC Phase

**Inputs**
- `docs/harper/IDEA.md`
- Chat history in Harper mode.
- Inline attachments and/or RAG attachments.
- Repository context, when available.
- Constraints from `TECH_CONSTRAINTS.yaml`, IDEA, or existing canonical docs.

**Responsibilities**
- Translate the idea into structured, testable requirements.
- Produce functional requirements, non-functional requirements, constraints, non-goals, risks, and acceptance criteria.
- Identify candidate implementation lanes and capability areas without producing code.
- Preserve the human-approved intent as the scope authority for downstream phases.

**Outputs**
- `docs/harper/SPEC.md`

**Consumers**
- `/plan`
- RAG context for `/kit`, `/eval`, and `/gate`
- Human sign-off

---

### 1.3 PLAN Phase

**Inputs**
- `docs/harper/SPEC.md`
- `docs/harper/IDEA.md`, when relevant.
- Existing `docs/harper/PLAN.md` and `docs/harper/plan.json`, when iterating.
- Repository context and marker files.
- Constraints and technology policies.

**Responsibilities**
- Break the SPEC into stable **REQ-ID** units.
- Create a dependency-aware plan.
- Detect implementation lanes and capability areas.
- Declare per-REQ metadata used by KIT/EVAL/GATE, including skills and capabilities where relevant.
- Keep PLAN implementation-aware but code-free.

**Outputs**
- `docs/harper/PLAN.md`
- `docs/harper/plan.json`
- Optional `docs/harper/lane-guides/<lane>.md`

**Expected `plan.json` concepts**

```jsonc
{
  "reqs": [
    {
      "id": "REQ-001",
      "title": "...",
      "acceptance": ["..."],
      "dependsOn": [],
      "status": "open",
      "lane": "python",
      "domain": "backend",
      "runtime_profile": "local_or_cloud",
      "packs": ["fastapi", "pytest"],
      "skills": ["api_design", "testing"],
      "design_profiles": ["ports_adapters"],
      "gate_expectations": ["tests", "lint", "types"],
      "main_module_boundary": "src/...",
      "future_compatibility_notes": []
    }
  ]
}
```

**Consumers**
- `/kit`
- `/eval`
- `/gate`
- Extension operational MCP `harper_next_action`
- Orchestrator MCP `harper_req_*` tools


👉 Read how to extend PLAN for new REQs
[CLike_Harper_Extend_Feature.md](./CLike_Harper_Extend_Feature.md)

---

### 1.4 KIT Phase

**Inputs**
- `docs/harper/PLAN.md`
- `docs/harper/plan.json`
- Target REQ-ID from `/kit <REQ-ID>` or the extension's next-action resolver.
- Lane guides and constraints.
- Repository context, promoted source roots, promoted tests, and dependency KIT artifacts.
- Optional execution preference and local-agent executor preference.

**Responsibilities**
- Generate a REQ-scoped candidate implementation.
- Keep all candidate source/test/docs under `runs/kit/<REQ-ID>/...`.
- Emit validation contracts and human-operational instructions.
- Respect the target REQ's lane, domain, packs, skills, design profiles, gate expectations, and module boundaries.
- Avoid modifying canonical roots directly during candidate generation.

**Outputs per REQ**

```text
runs/kit/<REQ-ID>/src/                # Candidate source files
runs/kit/<REQ-ID>/test/               # Candidate tests
runs/kit/<REQ-ID>/ci/LTC.json         # Machine-readable validation contract
runs/kit/<REQ-ID>/ci/HOWTO.md         # Human-readable execution recipe
runs/kit/<REQ-ID>/ci/requirements.txt # Optional REQ-local tooling/deps
runs/kit/<REQ-ID>/docs/README_<REQ-ID>.md
runs/kit/<REQ-ID>/docs/KIT_<REQ-ID>.md
runs/kit/<REQ-ID>/docs/AGENT_EXECUTION_CONTEXT.json  # local-agent package context when used
```

**Consumers**
- Local-agent executors, when selected.
- `/eval` pre-pass and canonical `/v1/eval/run`.
- `/gate` and promotion logic.
- Human review.

---

## 2) `/kit` Execution Model and New KIT Phases

The current KIT flow can be executed as a single base phase or as a staged chain.

### 2.1 Base KIT

Base KIT is the only local-agent-compatible generation phase today.

```text
/kit REQ-001
```

Base KIT may use:

| Path | Behavior |
|---|---|
| **Cloud path** | Extension sends the Harper request to the Orchestrator, which calls the Gateway Harper route. |
| **Local-agent path** | Orchestrator returns a local-agent package. Extension writes package files, runs Claude Code or GPT Codex locally, collects artifacts, and posts the result back to `/local-agent/complete`. |

### 2.2 Integrity Eval

```text
/kit REQ-001 --phases integrity_eval
```

Orchestrator/Gateway inspect existing candidate files and produce an integrity report. This phase does not replace canonical `/eval`; it is a semantic/structural pre-check over generated candidate artifacts.

Typical output:

```text
runs/kit/<REQ-ID>/docs/INTEGRITY_EVAL.json
```

### 2.3 Promotion Hardener

```text
/kit REQ-001 --phases promotion_hardener
```

Promotion hardener uses candidate files, target contract, file requirements, repo access manifest, repo structure evidence, and repo composition evidence to harden the candidate before promotion. It is intended to fix promotability gaps, not to broaden scope.

Requires existing candidate artifacts and normally depends on integrity evidence.

### 2.4 Promotion Eval

```text
/kit REQ-001 --phases promotion_eval
```

Promotion eval performs a final semantic promotion-readiness review over candidate artifacts. It may emit a promotion evaluation report and must not be confused with the canonical executable eval summary.

### 2.5 Full staged KIT chain

```text
/kit REQ-001 --phases kit,integrity_eval,promotion_hardener,promotion_eval
```

The extension validates that post-KIT phases have the candidate artifacts they need. Promotion hardener and promotion eval are blocked when required KIT candidate files or integrity reports are missing.

---

## 3) Local-Agent Integration I/O

### 3.1 Execution Preferences

Supported execution preferences:

| Value | Meaning |
|---|---|
| `auto` | CLike chooses the normal path. |
| `cloud_only` | Force cloud/provider path. |
| `prefer_local_agent` | Prefer local agent when supported and available; fallback can occur. |
| `local_agent_only` | Require local agent; fail if unavailable or unsupported. |
| `hybrid` | Allow local-agent-assisted execution where supported. |

Legacy values are normalized at runtime:

| Legacy | Current |
|---|---|
| `prefer_claude_code` | `prefer_local_agent` |
| `claude_code_only` | `local_agent_only` |

### 3.2 Supported Executors

| Executor | Normalized ID | Invocation model |
|---|---|---|
| Claude Code | `claude_code` | Non-interactive command, default command `claude`, print flag default `-p`, permission mode default `acceptEdits`. |
| GPT Codex | `gpt_codex` | Non-interactive command, default command `codex`, invoked as `codex exec <prompt>`. |

The extension probes command availability before executing. The Orchestrator chooses a concrete executor based on the request, preferred executor, and reported capabilities.

### 3.3 Local-Agent Package

The Orchestrator creates a local-agent execution package that includes:

- `AGENT_EXECUTION_CONTEXT.json`
- prompt content for the local executor
- allowed write roots
- forbidden paths
- expected outputs
- invocation metadata
- target REQ context and capability context

The extension is allowed to:

1. write the package files;
2. run the configured local executor;
3. collect stdout/stderr/exit code;
4. collect candidate artifacts from `runs/kit/<REQ-ID>/...`;
5. post results to `/local-agent/complete`.

The extension is not allowed to reinterpret the Harper contract or promote files directly as part of local-agent execution.

### 3.4 Local-Agent Hard Rules

Local agents must:

- write only under `runs/kit/<REQ-ID>/src`, `runs/kit/<REQ-ID>/test`, `runs/kit/<REQ-ID>/ci`, and `runs/kit/<REQ-ID>/docs`;
- never modify canonical `src/`, `test/`, `tests/`, `docs/harper/PLAN.md`, or `docs/harper/plan.json`;
- never run Git commands;
- inspect `PLAN.md`, `plan.json`, dependency KITs, canonical source roots, and canonical test roots before generating;
- avoid duplicate modules, ports, adapters, services, models, and helpers;
- produce immediately promotable candidate files aligned to the target REQ.

---

## 4) EVAL Phase

### 4.1 `/eval` Pre-Pass

`/eval` in Harper route currently prepares an optional local-agent eval pre-pass package. It is diagnostic/hardening-oriented and does not replace canonical executable evaluation.

**Inputs**
- Target REQ.
- Candidate KIT artifacts.
- LTC/HOWTO.
- Optional local-agent preference and executor capability data.

**Outputs**
- Local-agent package or pre-pass diagnostics.
- Normalized local-agent completion through `/local-agent/complete`, if used.

### 4.2 Canonical Eval

Canonical eval is exposed by the Orchestrator at:

```text
POST /v1/eval/run
```

**Engine**
- LLM Cloud Provider
- Agent

**Inputs**
- `profile`: validation profile.
- `req_id`: target REQ.
- `mode`: usually `auto`.
- Candidate artifacts and/or workspace files.
- LTC/HOWTO where available.

**Outputs**
- `runs/<runId>/eval.summary.json`
- Raw logs under `runs/<runId>/logs/`, when produced.
- A normalized check result compatible with gate.

**Checks**
- `tests`
- `lint`
- `types`
- `security`
- `build`
- optional lane-specific checks such as `iac`, `container`, or `model_quality`

---

## 5) GATE Phase

**Engine**
- LLM Cloud Provider
- Agent 

**Inputs**
- `docs/harper/plan.json`
- Candidate artifacts from `runs/kit/<REQ-ID>/...`
- Latest or selected `runs/<runId>/eval.summary.json`
- LTC/HOWTO and lane guide policies
- Git/workspace status

**Responsibilities**
- Enforce dependency sequencing.
- Apply gate policy and thresholds.
- Decide eligible/blocked/conflict outcomes.
- Promote safe candidate files into canonical roots only after checks pass.
- Update plan status and write decisions.

**Outputs**
- `runs/<runId>/gate.decisions.json`
- Updated `docs/harper/plan.json`
- Updated `docs/harper/PLAN.md` gate snapshot
- Optional Git commit, merge, tag, or PR depending on workspace settings

Canonical gate check endpoint:

```text
POST /v1/gate/check
```

---

## 6) FINALIZE Phase

**Engine**
- LLM Cloud Provider
- Agent

**Inputs**
- Final `docs/harper/plan.json`
- `docs/harper/PLAN.md`
- Gate decisions
- Eval summaries
- Project metadata and Git status

**Responsibilities**
- Produce release artifacts.
- Summarize completed REQs and quality evidence.
- Prepare PR body and release notes.
- Keep scope and evidence traceable.

**Outputs**

```text
docs/harper/RELEASE_NOTES.md
docs/harper/PR_BODY.md
docs/harper/SANITY_CHECKS.md
docs/harper/TODO_NEXT.md
```

Optional Git tag:

```text
harper/finalize/<runId>
```

---

## 7) Lane Guides, Skills, Capabilities, and Packs

### 7.1 Lane Guides

**Path:** `docs/harper/lane-guides/<lane>.md`

Lane guides define reusable testing and gating expectations per technology lane.

Minimum contents:

- tools for tests, lint, types, security, and build;
- CLI examples for local and container execution;
- expected report formats and paths;
- default thresholds;
- enterprise runner notes;
- constraints and policy hooks.

### 7.2 Skills and Capabilities

The current local-agent contract carries a `capability_context` for each target REQ.

Supported context fields include:

| Field | Purpose |
|---|---|
| `lane` | Technology/runtime track. |
| `domain` | Business or technical domain of the REQ. |
| `runtime_profile` | Local/cloud/on-prem runtime expectation. |
| `packs` | Reusable tool/framework packs relevant to the REQ. |
| `skills` | Capabilities the implementation requires, such as API design, testing, RAG, MCP, or VS Code extension work. |
| `design_profiles` | Architectural patterns to follow. |
| `gate_expectations` | Quality evidence expected by eval/gate. |
| `main_module_boundary` | Canonical module boundary to respect. |
| `future_compatibility_notes` | Forward-looking compatibility constraints. |

These fields are not decorative. Local agents are explicitly instructed to obey them while producing candidate artifacts.

---

## 8) REQ-Level Execution Artifacts

### 8.1 `LTC.json` — LLM Test Contract

`LTC.json` is the machine-readable validation contract for a REQ.

Expected concepts:

```jsonc
{
  "lane": "python",
  "tools": {
    "tests": ["pytest"],
    "lint": ["ruff"],
    "types": ["mypy"],
    "security": ["bandit"],
    "build": []
  },
  "checks": [
    {
      "name": "unit-tests",
      "command": "PYTHONPATH=src pytest -q",
      "cwd": ".",
      "report": "runs/kit/REQ-001/ci/junit.xml"
    }
  ],
  "reports": [
    { "kind": "junit", "path": "...", "format": "junit-xml" }
  ],
  "normalize": {
    "schema": "eval.summary.json"
  },
  "gate_policy": {
    "required": ["tests", "lint"],
    "coverage_min_pct": 70,
    "max_critical_security": 0
  }
}
```

`LTC.json` must include executable checks through one of the accepted contract sections such as `checks`, `cases`, `steps`, or `run`. A contract with no executable recipe is not gate-ready.

### 8.2 `HOWTO.md`

`HOWTO.md` is the human-readable recipe for reproducing validation.

It should include:

- prerequisites;
- environment variables;
- local execution commands;
- container or enterprise runner instructions;
- expected reports;
- troubleshooting;
- what to do when a check is environment-blocked.

---

## 9) Normalized Result Schemas

### 9.1 `eval.summary.json`

```jsonc
{
  "runId": "eval-1728070212",
  "req_id": "REQ-001",
  "mode": "auto",
  "passed": true,
  "failed": 0,
  "checks": {
    "tests": true,
    "lint": true,
    "types": true,
    "security": true,
    "build": true
  },
  "metrics": {
    "coverage_pct": 82.5,
    "lint_errors": 0,
    "vuln_critical": 0
  },
  "logs": {
    "pytest": "runs/eval-.../logs/pytest.txt"
  },
  "overall": true
}
```

### 9.2 `gate.decisions.json`

```jsonc
{
  "runId": "gate-1728070450",
  "req_id": "REQ-001",
  "eligible": true,
  "decisions": {
    "promoted": [
      { "req": "REQ-001", "src": "runs/kit/REQ-001/src/app/x.py", "dst": "src/app/x.py" }
    ],
    "blocked": [],
    "conflicts": []
  },
  "rationale": "All required checks passed and dependencies are done."
}
```

---

## 10) RAG I/O

### 10.1 Extension RAG

The extension can collect workspace files and send them to the Orchestrator for indexing. Chat commands include:

```text
/ragIndex <glob-or-path>
/ragSearch <query>
```

### 10.2 Orchestrator RAG APIs

```text
POST /v1/rag/index
POST /v1/rag/reindex
POST /v1/rag/search
POST /v1/rag/fetch
POST /v1/rag/fetch_by_paths
POST /v1/rag/purge
```

### 10.3 RAG in Harper

RAG is used to:

- ground SPEC/PLAN with existing docs;
- inject selected candidate/dependency context into KIT;
- support MCP tools such as `rag_search`, `rag_docs_status`, and `rag_reindex_docs_if_empty`;
- reduce prompt bloat while keeping repository context available.

---

## 11) MCP I/O

CLike currently exposes two complementary MCP surfaces.

### 11.1 Orchestrator MCP Server

Mounted by the Orchestrator at:

```text
/mcp
```

Enabled by:

```text
CLIKE_MCP_SERVER_ENABLED=true
```

Purpose:

- read-only/service context;
- explain CLike, Harper, artifacts, and operational model;
- expose plan, REQ, run, eval, gate, and RAG helper tools;
- avoid arbitrary shell, Git mutation, direct phase execution, or raw provider proxying.

### 11.2 Extension Operational MCP Server

Local extension server:

```text
http://127.0.0.1:55742/mcp
```

Purpose:

- operational surface for external/local agents;
- dispatch normal CLike slash commands through the same chat flow used by a developer;
- expose next-action and RAG helper tools;
- preserve the Orchestrator as workflow owner.

Supported operational tools:

- `clike_extension_status`
- `harper_next_action`
- `harper_run_phase`
- `harper_kit_next`
- `harper_continue_loop`
- `rag_reindex`
- `rag_docs_status`
- `rag_docs_reindex_if_empty`

---

## 12) Git and Promotion I/O

Git behavior is extension-first.

The extension handles:

- branch creation;
- commit;
- optional PR creation;
- gate-time merge/promotion depending on settings;
- protection from unsafe promotion when checks fail or conflicts exist.

Relevant settings include:

```jsonc
{
  "clike.git.autoCommit": true,
  "clike.git.openPR": true,
  "clike.git.remote": "origin",
  "clike.git.defaultBranch": "main",
  "clike.git.branchPrefix": "feature",
  "clike.git.tagPrefix": "harper",
  "clike.git.prBodyPath": "docs/harper/PR_BODY.md"
}
```

Promotion copies candidate files from:

```text
runs/kit/<REQ-ID>/src  -> src
runs/kit/<REQ-ID>/test -> test or tests
```

Promotion must never be confused with candidate generation.

---

## 13) API Surface Summary

### Orchestrator

```text
GET  /health
GET  /models
POST /chat
POST /generate
POST /apply
POST /agent/code
POST /spec
POST /idea
POST /plan
POST /kit
POST /eval
POST /gate via /v1/gate/check
POST /finalize
POST /local-agent/complete
POST /v1/eval/run
POST /v1/rag/*
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
POST /v1/harper/run or /run, depending on mounted prefix
GET  /harper/ui
GET  /harper/files|projects|aggregate|series|top|raw
```

---

## 14) Glossary

- **Candidate artifact** — A generated file under `runs/kit/<REQ-ID>/...`, not yet promoted.
- **Capability context** — Per-REQ metadata describing lane, domain, packs, skills, design profiles, gate expectations, and module boundary.
- **Extension Operational MCP** — Local MCP-compatible server exposed by the VS Code extension for agent-to-CLike operational commands.
- **Gateway** — Provider and model IO layer.
- **HITL** — Human in the loop; the developer remains final authority.
- **LTC** — LLM Test Contract; machine-readable validation recipe.
- **Orchestrator MCP** — Read-only/service MCP server exposed by the Orchestrator.
- **Promotion** — Controlled copy from `runs/kit/<REQ-ID>/...` into canonical project roots after eval/gate success.
- **Skill** — A declared implementation competency needed by a REQ, used to guide prompts and local-agent behavior.
