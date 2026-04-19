# CLike MCP Overview

## Functional Overview

CLike is an AI-native, agent-centric software delivery environment governed by the Harper workflow:

```text
IDEA → SPEC → PLAN → KIT → EVAL → GATE → FINALIZE
```

The core idea is simple: the developer stays in control, CLike owns the workflow, and models or agents execute bounded work through explicit contracts. CLike is not only a chat interface. It is a repository-aware delivery pipeline that combines a VS Code extension, an orchestrator, a cloud gateway, RAG, Git integration, local agents, and MCP surfaces.

At functional level, CLike provides:

- a VS Code extension as the developer and agent operational surface;
- a FastAPI orchestrator as the Harper workflow brain;
- a gateway for cloud model routing and embeddings;
- RAG for repository and documentation grounding;
- local-agent execution through Claude Code and GPT Codex;
- eval-driven validation and gate-driven promotion;
- MCP interfaces for Agent → CLike and service-level explanation/context.

The governing principle is:

```text
Developer leads.
CLike governs.
Cloud models and local agents execute.
Eval verifies.
Gate promotes.
```

## Agent-Centric Model

CLike supports two distinct agentic models.

### Model 1 — Developer Uses CLike to Activate an Agent

This is the developer-driven model. The user types a command in the CLike chat or uses the VS Code UI.

```text
Developer
→ VS Code Extension / CLike UI
→ Orchestrator
→ Agent execution package
→ Extension local actuator
→ Claude Code or GPT Codex
→ Extension collects result
→ Orchestrator receives and normalizes result
→ RAG / Git / Eval / Gate continue through CLike
```

The local agent is not the workflow brain. It is an executor.

The orchestrator owns:

- Harper phase semantics;
- execution strategy;
- cloud vs local-agent decision;
- local-agent eligibility;
- executor hints;
- prompt contracts;
- `AGENT_EXECUTION_CONTEXT.json` and `AGENT_EVAL_CONTEXT.json`;
- allowed write roots;
- forbidden paths;
- expected outputs;
- fallback policy;
- result normalization;
- eval and gate decisions.

The extension owns:

- UI;
- workspace access;
- local filesystem access;
- local CLI execution;
- stdout/stderr/exit-code collection;
- candidate artifact collection;
- result submission back to the orchestrator;
- Git integration;
- user-visible chat output.

The local agent owns only:

- reading the orchestrator package;
- generating or hardening candidate artifacts;
- writing only under allowed candidate roots;
- reporting executed commands and remaining gaps.

### Model 2 — Agent Interacts with CLike

This is the agent-driven model. A local or external agent asks CLike to operate the Harper loop.

```text
Agent
→ CLike Extension MCP operational server
→ VS Code Extension dispatches normal CLike slash command
→ Normal CLike flow
→ Orchestrator
→ Gateway / Local Agent / RAG / Git / Eval / Gate
```

Model 2 deliberately does not duplicate Harper logic inside MCP tools. The MCP extension server dispatches the same slash commands that a human would type:

```text
/idea
/spec
/plan
/kit REQ-001
/eval REQ-001
/gate REQ-001
/finalize
/ragIndex docs/**/*
/ragSearch <query>
/agent-default claude
/agent-default codex
```

This keeps the architecture stable: the agent can request work, but CLike still governs execution.

## Harper Phase Flow

### `/idea`

The IDEA phase helps define the product vision and business intent.

It captures:

- vision;
- problem statement;
- target users;
- values and outcomes;
- constraints;
- technology assumptions.

This phase is orchestrator-owned and cloud-oriented.

### `/spec`

The SPEC phase turns the idea into testable requirements.

It produces:

- functional requirements;
- non-functional requirements;
- acceptance criteria;
- constraints;
- measurable success criteria.

This phase is orchestrator-owned and cloud-oriented.

### `/plan`

The PLAN phase decomposes the specification into REQ-IDs.

It produces:

- `docs/harper/PLAN.md`;
- `docs/harper/plan.json`;
- REQ table;
- dependencies;
- acceptance criteria per REQ;
- source/test root guidance;
- implementation order;
- gate strategy.

This phase is orchestrator-owned and cloud-oriented.

### `/kit`

The KIT phase creates candidate implementation artifacts for a target REQ.

Cloud KIT flow:

```text
Extension
→ Orchestrator
→ Gateway
→ Cloud model
→ Orchestrator response
→ Extension writes files
→ RAG/Git integration
```

Local-agent KIT flow:

```text
Extension
→ Orchestrator
→ local-agent package
→ Extension actuator
→ Claude Code or GPT Codex
→ candidate files under runs/kit/<REQ-ID>
→ Extension sends result to Orchestrator
→ Orchestrator normalizes
→ RAG/Git integration
```

Candidate outputs are written under:

```text
runs/kit/<REQ-ID>/src
runs/kit/<REQ-ID>/test
runs/kit/<REQ-ID>/ci
runs/kit/<REQ-ID>/docs
```

The agent must not write directly to canonical `src/`, `test/`, or `tests/`.

### `/eval`

The EVAL phase remains CLike-owned.

When local-agent pre-pass is enabled:

```text
/eval REQ-ID
→ Orchestrator prepares eval pre-pass package
→ Extension runs Claude/Codex
→ Agent reads LTC/HOWTO/PLAN/dependencies/src/test
→ Agent repairs only candidate files
→ Extension sends result to Orchestrator
→ canonical CLike eval runs
```

The agent is a hardener, not the judge. The canonical eval remains the final authority.

### `/gate`

The GATE phase decides whether a REQ can be promoted.

It validates:

- eval status;
- candidate artifact structure;
- Git state;
- promotion readiness;
- plan status consistency.

The agent does not own gate decisions.

### `/finalize`

The FINALIZE phase produces release and handoff artifacts.

Typical outputs:

- final README;
- HOWTO_RUN;
- RELEASE_NOTES;
- SANITY_CHECKS;
- TODO_NEXT;
- PR_BODY;
- final project summary.

When all REQs are complete, Model 2 reports `finalize_only`.

## MCP Surfaces

CLike exposes two complementary MCP surfaces.

### Extension MCP — Operational Surface

The extension MCP server is the operational surface for agents.

It lets an agent request CLike operations through existing extension behavior.

Typical tools:

- `clike_extension_status`;
- `harper_next_action`;
- `harper_run_phase`;
- `harper_kit_next`;
- `harper_continue_loop`;
- `rag_reindex`;
- `rag_docs_status`;
- `rag_docs_reindex_if_empty`.

The extension MCP server can trigger normal slash commands, but it does not reimplement Harper.

### Orchestrator MCP — Informational and Service Surface

The orchestrator MCP server explains and supports CLike.

It can:

- explain CLike architecture;
- expose Harper process context;
- provide RAG status;
- reindex docs when workspace access is available;
- expose service-level knowledge to agents.

It should not be used as a phase execution bypass.

## Role Split

### VS Code Extension

The extension is the operational edge.

It owns:

- UX and chat;
- slash command dispatch;
- workspace access;
- local file writes;
- local-agent physical execution;
- Git integration;
- RAG file collection;
- Extension MCP operational server.

It does not own Harper semantics.

### Orchestrator

The orchestrator is the workflow brain.

It owns:

- Harper phase semantics;
- execution policy;
- cloud/local strategy;
- local-agent package generation;
- output contracts;
- eval/gate logic;
- RAG endpoints;
- Orchestrator MCP informational surface.

It does not physically execute local CLI agents.

### Gateway

The gateway abstracts cloud providers.

It owns:

- OpenAI calls;
- Anthropic calls;
- cloud model routing;
- embeddings;
- provider-specific request/response adaptation.

It does not own Harper workflow decisions.

### Local Agents

Claude Code and GPT Codex are constrained executors.

They may:

- read execution context;
- generate candidate source/tests;
- harden candidate outputs;
- run allowed local checks;
- report gaps.

They must not:

- run Git operations;
- promote files;
- write canonical roots;
- decide eval or gate pass status;
- bypass the orchestrator.

## Design Principles

CLike follows these principles:

- CLike stays at the center of the workflow;
- the developer keeps strategic control;
- agents execute, but do not govern;
- every phase has testable outputs;
- local agents are constrained by explicit contracts;
- RAG reduces hallucination and improves repository awareness;
- eval and gate remain authoritative;
- MCP is an interface, not a parallel workflow engine.

## Architecture Snapshot

```text
Developer / Agent
        |
        v
VS Code Extension
        |
        +--> Extension MCP operational server
        +--> Workspace / Git / RAG collector
        +--> Local agent actuator: Claude Code / GPT Codex
        |
        v
CLike Orchestrator
        |
        +--> Harper workflow engine
        +--> local-agent execution packages
        +--> eval/gate logic
        +--> RAG endpoints
        +--> Orchestrator MCP informational server
        |
        v
Gateway
        |
        +--> OpenAI
        +--> Anthropic
        +--> embeddings
```

### CLike is therefore agent-centric, but orchestrator-governed.
