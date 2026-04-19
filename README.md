# 🚀 CLike — AI-Native Pipeline for Product Engineers

![Logo di Clike](images/icons/clike_128x128.png)

[![Made with Python](https://img.shields.io/badge/Made%20with-Python-3776AB?logo=python)](https://www.python.org/)
[![VS Code Extension](https://img.shields.io/badge/VS%20Code-Extension-007ACC?logo=visualstudiocode)](extensions/vscode)
[![Dockerized](https://img.shields.io/badge/Run%20with-Docker-2496ED?logo=docker)](docker)

> **From intent to impact.**  
> CLike keeps developers in flow, augments delivery with agentic workflows, and bakes in governance, eval-driven quality, repository grounding, and a safe paved road for enterprise-grade software delivery.

---

## ✨ Highlights

- 🌀 **Flow state by default** — no context switching, full VS Code integration.
- 🤖 **Agent-centric, CLike-governed delivery** — developers and agents can trigger the same Harper workflow without bypassing governance.
- 🛡️ **Eval-driven quality gates** — KIT/EVAL/GATE loops promote only reviewable, testable artifacts.
- 🧠 **Repository-aware generation** — RAG grounds planning, KIT, eval, and agent execution in real workspace context.
- 🔌 **MCP-ready operating model** — agents can interact with CLike through controlled MCP surfaces.

---

## ✨ What is CLike?

**Clike** is not just an agent that writes code; it is an AI-native pipeline / platform that orchestrates verifiable capabilities across specs, plans, code, tests, reviews, and release gates.

**CLike** is an AI-native platform that merges the **Harper-style** pipeline with the **Vibe Coding** philosophy and operationalizes it through:

- a VS Code extension;
- a FastAPI orchestrator;
- a FastAPI model gateway;
- RAG-backed context retrieval;
- cloud LLM execution;
- local coding-agent execution;
- Git-aware promotion;
- eval-driven governance;
- MCP surfaces for agent interoperability.

CLike is not just a chat panel. It is a governed software-generation pipeline.

The core workflow is:

```text
IDEA → SPEC → PLAN → KIT → EVAL → GATE → FINALIZE
```

The main operating principle is:

```text
The developer leads.
CLike governs.
Cloud models and local agents execute.
Eval and Gate decide.
```

---

## ✨ Where the Idea Comes From

- **Harper / Codegen Hero's Journey**  
  Harper introduces an iterative software-generation journey: start from an idea, create a SPEC, derive a PLAN, generate a KIT, evaluate, harden, and promote in short feedback loops.

- **Vibe Coding**  
  Vibe Coding emphasizes intent, flow, rapid prototyping, and cognitive offloading. The developer works at the outcome level while the system helps produce implementation artifacts.

- **AI-Native Software Engineering**  
  CLike applies agentic workflows, human-in-the-loop governance, RAG grounding, quality gates, and automated validation to make AI-generated software reviewable and promotable.

---

## 🧱 Architecture at a Glance

```text
+-------------------------------+
| Developer / External Agent    |
+---------------+---------------+
                |
                v
+-------------------------------+
| VS Code Extension             |
| - Chat UI                     |
| - Slash commands              |
| - Workspace access            |
| - Local file writes           |
| - Git integration             |
| - RAG collector               |
| - Local agent actuator        |
| - Extension MCP server        |
+---------------+---------------+
                |
                v
+-------------------------------+
| Orchestrator (FastAPI)        |
| - Harper workflow brain       |
| - Execution strategy          |
| - Agent execution packages    |
| - Eval/Gate semantics         |
| - RAG endpoints               |
| - Orchestrator MCP server     |
+---------------+---------------+
                |
                v
+-------------------------------+
| Gateway (FastAPI)             |
| - Cloud model abstraction     |
| - OpenAI / Anthropic routing  |
| - Embeddings                  |
| - Provider normalization      |
+---------------+---------------+
                |
                v
+-------------------------------+
| Providers / Vector DB         |
| - OpenAI / Anthropic          |
| - Local-compatible backends   |
| - Qdrant / Vector store       |
+-------------------------------+
```

### Key directories

- `extensions/vscode/` — CLike VS Code extension.
- `orchestrator/` — Harper workflow orchestration, RAG, agent contracts, eval/gate.
- `gateway/` — model gateway for cloud providers and embeddings.
- `configs/` — model routing and provider settings.
- `docker/` — local development stack.
- `docs/` — project documentation.
- `runs/` — Harper run artifacts and KIT candidates.

---

## 🤖 Agent-Centric Operating Model

CLike supports two complementary agentic models.

### Model 1 — Developer activates an agent through CLike

This is the local-agent execution path for `/kit` and optionally `/eval`.

```text
Developer
→ VS Code Extension
→ Orchestrator
→ Agent execution package
→ Extension local actuator
→ Claude Code or GPT Codex
→ Extension collects results
→ Orchestrator normalizes
→ RAG/Git/Eval/Gate continue through CLike
```

The orchestrator owns:

- Harper phase semantics;
- execution strategy;
- local-agent eligibility;
- executor hints;
- prompt contracts;
- `AGENT_EXECUTION_CONTEXT.json`;
- allowed write roots;
- expected outputs;
- fallback policy;
- result normalization.

The extension owns:

- UI;
- workspace access;
- local filesystem writes;
- local CLI execution;
- stdout/stderr/exit-code collection;
- generated file collection;
- Git integration.

Local agents are executors only. They must not promote files, run Git operations, or write directly to canonical `src/`, `test/`, or `tests/` roots.

### Model 2 — Agent interacts with CLike

This is the MCP-driven operating model.

```text
External/local agent
→ CLike Extension MCP operational server
→ Extension dispatches normal slash commands
→ Normal CLike flow
→ Orchestrator
→ Gateway / local-agent / RAG / Git / Eval / Gate
```

The agent does not call the orchestrator with invented Harper payloads. It asks the extension to dispatch the same slash commands a developer would type.

This keeps the workflow simple, auditable, and aligned with the existing extension/orchestrator path.

---

## 🔌 MCP Support

CLike exposes two complementary MCP surfaces.

### Extension MCP — Operational Surface

The VS Code extension exposes a local operational MCP-compatible server.

Its role is to let agents operate CLike through the same commands available in chat.

Typical tools:

- `clike_extension_status`
- `harper_next_action`
- `harper_run_phase`
- `harper_kit_next`
- `harper_continue_loop`
- `rag_reindex`
- `rag_docs_status`
- `rag_docs_reindex_if_empty`

The extension MCP server dispatches normal slash commands such as:

```text
/kit REQ-001
/eval REQ-001
/gate REQ-001
/finalize
/ragIndex docs/**/*
/agent-default codex
```

It does not duplicate Harper logic.

### Orchestrator MCP — Informational and Service Surface

The orchestrator exposes an MCP server for documentation, capability discovery, and service-oriented support.

Its role is to:

- explain CLike architecture and Harper semantics;
- expose operational model documentation;
- inspect RAG status;
- support docs reindex service when workspace access is available;
- provide context to agents.

It does not directly own Model 2 command dispatch.

### Manual Orchestrator MCP curl

The orchestrator MCP endpoint uses streamable HTTP semantics. Manual curl calls should include both `content-type` and `accept` headers.

```bash
curl -s http://localhost:8080/mcp/   -H 'content-type: application/json'   -H 'accept: application/json, text/event-stream'   -d '{
    "jsonrpc": "2.0",
    "id": 1,
    "method": "tools/list",
    "params": {}
  }' | jq
```

If the `accept` header is omitted, the endpoint may return HTTP `406`.

---

## 💬 Chat Slash Commands

Type commands directly in the CLike chat input.

### General

| Command | Description |
|---|---|
| `/help` | Shows the quick help overlay. |
| `/status` | Shows current Harper/project context status. |
| `/where` | Shows current workspace and Harper doc-root path. |
| `/switch <name\|path>` | Switches to another Harper project. |

### Harper workspace

| Command | Description |
|---|---|
| `/init <name> [--path <abs>] [--force]` | Initializes a Harper project/workspace scaffold. |
| `/idea` | Formalizes or updates `IDEA.md`. |
| `/spec [file\|text]` | Generates or updates `SPEC.md`. |
| `/plan [spec_path]` | Generates or updates `PLAN.md`, `plan.json`, and lane guides. |

### Local agent selection

| Command | Description |
|---|---|
| `/agent-default auto` | Let CLike choose the local executor when local-agent execution is enabled. |
| `/agent-default claude` | Prefer Claude Code as the local executor. |
| `/agent-default codex` | Prefer GPT Codex / Codex CLI as the local executor. |

Aliases may normalize internally to executor IDs such as `claude_code` and `gpt_codex`.

### KIT flow

| Command | Description |
|---|---|
| `/kit` | Runs KIT on the next target REQ. |
| `/kit REQ-001` | Runs KIT for a specific REQ. |
| `/kit REQ-001 --integrity` | Runs integrity evaluation phase. |
| `/kit REQ-001 --hardener` | Runs promotion hardener phase. |
| `/kit REQ-001 --promotion-eval` | Runs promotion evaluation phase. |
| `/kit REQ-001 --phases=kit,integrity_eval,promotion_hardener,promotion_eval` | Runs an explicit chained KIT pipeline. |

KIT can run through:

- cloud model path;
- local-agent path with Claude Code;
- local-agent path with GPT Codex.

### Eval and Gate

| Command | Description |
|---|---|
| `/eval <REQ-ID>` | Evaluates the current KIT output for that REQ. |
| `/gate <REQ-ID>` | Runs gate checks and promotion logic for that REQ. |

`/eval` can optionally include a local-agent pre-pass, but canonical eval remains CLike-owned.

### Finalization

| Command | Description |
|---|---|
| `/finalize` | Runs the final closure step for Harper workflows. |

When there are no open or in-progress REQs, Model 2 tools report `finalize_only`.

### RAG

| Command | Description |
|---|---|
| `/rag <query>` | Searches RAG and shows top results. |
| `/rag +<N>` | Attaches result `N` from the last RAG search. |
| `/rag list` | Shows current attached files/RAG references. |
| `/rag clear` | Clears current attachments. |
| `/ragIndex [glob]` | Manually indexes content into RAG. |
| `/ragSearch <query>` | Searches RAG directly and returns top results. |

Examples:

```text
/ragIndex docs/**/*.md
/ragIndex docs/**/*
/ragIndex runs/kit/REQ-001/**/*
/ragSearch runtime profile adapters
```

---

## 🚀 Quick Start (Local Dev)

### Prerequisites

- Docker and Docker Compose v2
- VS Code
- Node.js 18+
- Python 3.11+
- API keys for remote providers when using cloud models
- Optional: local agent CLIs such as Claude Code or GPT Codex

### 1. Bring up services

```bash
cd docker
docker compose up -d --build

curl -s http://localhost:8080/health
curl -s http://localhost:8000/health
```

### 2. Install the VS Code extension

```bash
cd extensions/vscode
npm install
npm install -g @vscode/vsce
vsce package
code --install-extension clike-*.vsix
```

Open your workspace in VS Code and run:

```text
CLike: Chat (Q&A / Harper / Coding)
```

---

## ⚙️ Configuration

### Models and Providers

`configs/models.yaml` declares enabled models and providers.

Typical provider families:

- OpenAI;
- Anthropic;
- OpenAI-compatible gateways;
- local-compatible backends.

Gateway environment:

```bash
export MODELS_CONFIG=/workspace/configs/models.yaml
```

Orchestrator environment:

```bash
export GATEWAY_URL=http://gateway:8000
```

### VS Code settings

Common settings include:

- `clike.orchestratorUrl`
- `clike.gatewayUrl`
- `clike.chat.theme`
- `clike.verboseLogging`
- `clike.docRoot`
- `clike.harperTimeout`

Local-agent settings include:

- `clike.localAgent.enabled`
- `clike.localAgent.preferredExecutor`
- `clike.localAgent.claudeCode.enabled`
- `clike.localAgent.claudeCode.command`
- `clike.localAgent.codex.enabled`
- `clike.localAgent.codex.command`

MCP extension settings include:

- `clike.mcp.extensionServerEnabled`
- `clike.mcp.extensionServerHost`
- `clike.mcp.extensionServerPort`
- `clike.mcp.extensionServerToken`

---

## 🧪 Eval-Driven Development and Guardrails

CLike encourages eval-driven development through:

- unit tests;
- lint checks;
- type checks;
- security checks;
- integration smoke checks;
- eval summaries;
- gate decisions;
- Git-aware promotion.

The key rule is:

```text
KIT can generate.
EVAL must verify.
GATE decides promotion.
```

---

## 🔒 Security, Governance, and the Paved Road

- **Auditability** — run artifacts, prompts, outputs, evals, and gate results are traceable.
- **Isolation** — local agents are constrained by allowed write roots.
- **Least privilege** — local agents must not perform Git operations or promote files directly.
- **RAG grounding** — generation is grounded in repository and docs context.
- **Human-in-the-loop** — the developer remains the final decision maker.
- **Cloud/local frontier control** — CLike can route cloud execution through the gateway and local execution through extension-actuated CLI tools.

---

## 🛠️ Local Dev Without Docker

### Orchestrator

```bash
cd orchestrator
pip install -r requirements.txt
uvicorn app:app --host 0.0.0.0 --port 8080 --reload
```

### Gateway

```bash
cd gateway
pip install -r requirements.txt
export MODELS_CONFIG=$(pwd)/../configs/models.yaml
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

### VS Code extension

```bash
cd extensions/vscode
npm install
code .
```

---

## 🧭 Roadmap

- Richer eval reporting in VS Code.
- Stronger local-agent eval hardening.
- More MCP tools for operational automation.
- Model routing profiles for cost, latency, and capability.
- Expanded RAG sources and repository knowledge packs.
- Enterprise policy hooks for guarded promotion.

---

## 🤝 Contributing

Issues and PRs are welcome. Include:

- repro steps;
- logs with secrets redacted;
- environment details;
- CLike phase and REQ-ID;
- model/executor used.

---

## 📝 License

Apache License 2.0

---

## Harper Project Bootstrap

- Docs: `docs/harper/`
- Runs: `runs/`
- Open Chat: Command Palette → `CLike: Chat (Q&A / Harper / Coding)`

---

# **CLike on, code on.**
