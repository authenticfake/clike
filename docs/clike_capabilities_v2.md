# CLike Capabilities

## Purpose

CLike is an AI-native software generation pipeline for repository-aware, eval-driven development.

It combines:

- VS Code extension UX;
- FastAPI orchestration;
- cloud model gateway;
- local coding agents;
- RAG;
- Git integration;
- Harper workflow governance;
- MCP-based agent interoperability.

The delivery loop is:

```text
IDEA → SPEC → PLAN → KIT → EVAL → GATE → FINALIZE
```

## VS Code Extension Capabilities

The VS Code extension is the operational frontend of CLike.

### Chat and Command Surface

Supported Harper commands:

```text
/idea
/spec
/plan
/kit <REQ-ID>
/eval <REQ-ID>
/gate <REQ-ID>
/finalize
/ragIndex <glob>
/ragSearch <query>
/agent-default claude|codex|auto
```

The extension manages:

- command parsing;
- mode selection;
- model selection;
- execution preference;
- chat output;
- command state;
- response rendering.

### Workspace Awareness

The extension can access the active local workspace.

It can:

- read project files;
- write generated artifacts;
- collect candidate files;
- collect RAG items;
- inspect Git repository metadata;
- resolve workspace root;
- pass repository context to the orchestrator.

### Local File Generation

For cloud KIT responses, the extension writes files returned by the orchestrator.

For local-agent KIT/EVAL flows, the extension writes orchestrator package files and lets the agent write candidate artifacts under:

```text
runs/kit/<REQ-ID>/src
runs/kit/<REQ-ID>/test
runs/kit/<REQ-ID>/ci
runs/kit/<REQ-ID>/docs
runs/kit/<REQ-ID>/reports
```

### Local Agent Actuator

The extension physically executes local agents.

Supported executor families:

- Claude Code;
- GPT Codex / Codex CLI-style workflows.

The extension handles:

- CLI availability detection;
- command resolution;
- prompt transport;
- stdout collection;
- stderr collection;
- exit-code collection;
- artifact collection;
- result submission to the orchestrator.

The extension is the actuator, not the workflow brain.

### Git Integration

The extension owns local Git operations.

It can:

- detect repository state;
- collect branch and remote metadata;
- support gate and promotion workflows;
- integrate Git actions after CLike phases.

Local agents must not run Git commands. It is in charge to Clike.

### RAG Collection

The extension can collect and index local files.

Typical commands:

```text
/ragIndex docs/**/*
/ragIndex runs/kit/<REQ-ID>/**/*
/ragSearch <query>
```

Indexable material includes:

- docs;
- source;
- tests;
- CI contracts;
- reports;
- markdown documentation.

### Extension MCP Operational Server

The extension exposes a local MCP-compatible operational server for Model 2.

Tools include:

- `clike_extension_status`;
- `harper_next_action`;
- `harper_run_phase`;
- `harper_kit_next`;
- `harper_continue_loop`;
- `rag_reindex`;
- `rag_docs_status`;
- `rag_docs_reindex_if_empty`.

This server dispatches normal slash commands into the existing CLike flow.

## Orchestrator Capabilities

The orchestrator is the workflow brain.

### Harper Workflow Governance

The orchestrator owns:

- IDEA semantics;
- SPEC semantics;
- PLAN semantics;
- KIT strategy;
- EVAL strategy;
- GATE decisions;
- FINALIZE flow.

It defines:

- phase behavior;
- execution policy;
- local-agent eligibility;
- artifact contracts;
- output contracts;
- eval/gate rules.

### Execution Policy

The orchestrator decides whether a phase should use:

- cloud execution;
- local-agent package;
- canonical eval;
- fallback strategy.

Execution preferences may include:

```text
cloud_only
prefer_cloud
prefer_local_agent
local_agent_only
```

The extension can request a preference, but the orchestrator decides valid behavior.

### Local-Agent Package Generation

For local-agent-capable phases, the orchestrator creates explicit packages.

For `/kit`:

```text
runs/kit/<REQ-ID>/docs/AGENT_EXECUTION_CONTEXT.json
runs/kit/<REQ-ID>/docs/AGENT_PROMPT.md
```

For `/eval`:

```text
runs/kit/<REQ-ID>/docs/AGENT_EVAL_CONTEXT.json
runs/kit/<REQ-ID>/docs/AGENT_EVAL_PROMPT.md
```

These packages define:

- workflow owner;
- agent role;
- allowed write roots;
- forbidden paths;
- required inputs;
- expected outputs;
- local runtime;
- dependency analysis rules;
- test double policy;
- hard rules.

### Result Normalization

The extension sends local-agent results to:

```text
/v1/harper/local-agent/complete
```

The orchestrator normalizes:

- phase;
- REQ-ID;
- stdout;
- stderr;
- exit code;
- generated files;
- warnings;
- errors;
- execution metadata.

### Eval Ownership

CLike keeps eval ownership.

A local agent can run an eval pre-pass, but final validation remains canonical CLike eval.

Eval can use:

- `LTC.json`;
- `HOWTO.md`;
- candidate files;
- tests;
- reports;
- local-agent output.

### Gate Ownership

Gate remains CLike-owned.

Gate is responsible for:

- pass/fail decision;
- plan status updates;
- Git integration;
- promotion readiness;
- workflow consistency.

### Orchestrator MCP Service

The orchestrator exposes an MCP service surface for explanation and support.

It can:

- explain CLike architecture;
- describe Harper workflow;
- provide RAG docs status;
- reindex docs when workspace access exists;
- expose service-level context to agents.

It should not bypass the extension operational flow for phase execution.

## Gateway Capabilities

The gateway abstracts cloud model providers.

### Cloud Model Routing

The gateway supports cloud model families such as:

- OpenAI GPT models;
- OpenAI Codex-oriented models;
- Anthropic Claude models.

It provides endpoints such as:

- `/v1/models`;
- `/v1/chat`;
- `/v1/generate`;
- `/v1/embeddings`.

### Provider Normalization

The gateway hides provider-specific behavior from the orchestrator.

It normalizes:

- request shape;
- model IDs;
- generation parameters;
- response format;
- embedding access.

### Cloud vs Local Frontier

CLike has two execution frontiers:

```text
Cloud frontier:
Extension → Orchestrator → Gateway → OpenAI/Anthropic

Local frontier:
Extension → Orchestrator → Agent package → Extension actuator → Claude/Codex
```

The gateway owns the cloud frontier. The extension owns the local actuator frontier.

## RAG Capabilities

CLike uses RAG to ground generation and evaluation.

### Indexed Sources

RAG can include:

- Harper docs;
- IDEA/SPEC/PLAN;
- technology constraints;
- lane guides;
- candidate source;
- candidate tests;
- CI contracts;
- generated reports;
- repository documentation.

### RAG Goals

RAG helps:

- reduce hallucination;
- improve repository awareness;
- preserve dependency context;
- support eval and gate;
- provide context to agents;
- recover when documentation context is missing.

### Reindexing

RAG can be reindexed using:

```text
/ragIndex docs/**/*
```

Model 2 MCP tools can check whether docs are indexed and reindex when empty.

## Local Agent Capabilities

CLike supports local software generation agents.

### Claude Code

Claude Code can execute local KIT and EVAL pre-pass packages.

It receives orchestrator-owned prompts and context files.

### GPT Codex

GPT Codex can execute local packages, typically through a non-interactive CLI flow.

It may receive prompts through stdin or another configured prompt transport.

### Agent Restrictions

Agents must not:

- write canonical `src/`, `test/`, or `tests/`;
- modify `docs/harper/PLAN.md`;
- modify `docs/harper/plan.json`;
- run Git commands;
- promote files;
- decide final eval/gate pass status;
- bypass the orchestrator.

Agents may:

- generate candidate code;
- generate candidate tests;
- create CI contracts;
- create docs;
- run local checks when allowed;
- repair candidate artifacts during eval pre-pass;
- report environment-blocked checks.

## Harper Phase Capabilities

### IDEA

Creates structured product intent.

### SPEC

Creates testable requirements and acceptance criteria.

### PLAN

Creates REQ-IDs, dependencies, source/test roots, and implementation order.

### KIT

Generates candidate implementation through cloud or local-agent execution.

### EVAL

Validates candidate implementation. Can include local-agent pre-pass, but canonical eval remains final.

### GATE

Decides promotability and coordinates Git/promotion state.

### FINALIZE

Produces release and handoff documentation.

## Model 2 Agent Capabilities

Through MCP, an agent can ask the extension to:

- report current CLike state;
- identify the next open REQ;
- run `/kit`;
- run `/eval`;
- run `/gate`;
- run `/finalize`;
- trigger RAG reindex;
- check RAG docs status.

The next REQ policy is intentionally simple:

```text
first REQ in plan.json with status = open
```

If no open REQ exists but one is in progress, CLike can continue it.

If no open or in-progress REQ exists, CLike reports:

```text
finalize_only
```

## Capability Boundaries

### CLike Should

- govern the workflow;
- route execution;
- generate contracts;
- normalize outputs;
- run eval/gate;
- preserve Git and RAG discipline;
- keep humans in strategic control.

### Agents Should

- request actions;
- execute packages;
- generate candidate artifacts;
- harden tests;
- report results.

### Agents Should Not

- bypass CLike;
- mutate canonical roots directly;
- own gate decisions;
- own Git promotion;
- invent unsupported routes;
- duplicate Harper logic.

## Operational Summary

```text
Extension:
  UX, workspace, local actuator, Git, operational MCP.

Orchestrator:
  Harper workflow brain, execution policy, contracts, eval/gate, service MCP.

Gateway:
  cloud model and embeddings abstraction.

RAG:
  grounding and repository-aware context.

Local Agents:
  constrained executors for code generation and hardening.

MCP:
  controlled interface for agents to operate and understand CLike.
```

The result is a governed agentic loop:

```text
Agent requests.
CLike decides.
Executor acts.
Eval verifies.
Gate promotes.
Developer remains in control.
```
