# 🚀 CLike — AI-Native Pipeline for Product Engineers

![Logo di Clike](images/icons/clike_128x128.png)

[![Made with Python](https://img.shields.io/badge/Made%20with-Python-3776AB?logo=python)](https://www.python.org/)
[![VS Code Extension](https://img.shields.io/badge/VS%20Code-Extension-007ACC?logo=visualstudiocode)](extensions/vscode)
[![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)

> **From intent to impact.**  
> CLike keeps developers in flow, augments delivery with agentic workflows, and bakes in governance, eval-driven quality, repository grounding, and a safe paved road for enterprise-grade software delivery.

---

### 🚀 **Project Status & Release Info**

| 📅 **Last Updated** | 🧪 **Current Testing** | 📦 **Latest Release** |
| --- | --- | --- |
| May 19, 2026 | Added command for extending requirements (/extend). First draft implemented; testing has not started yet. [docs/CLike_Harper_Extend_Feature.md](./docs/CLike_Harper_Extend_Feature.md)| `v0.9.874` |


---

## ✨ Highlights

- 🌀 **Flow state by default** — no context switching, full VS Code integration.
- 🤖 **Agent-centric, CLike-governed delivery** — developers and agents can trigger the same Harper workflow without bypassing governance.
- 🛡️ **Eval-driven quality gates** — KIT/EVAL/GATE loops promote only reviewable, testable artifacts.
- 🧠 **Repository-aware generation** — RAG grounds planning, KIT, eval, and agent execution in real workspace context.
- 🔌 **MCP-ready operating model** — agents can interact with CLike through controlled MCP surfaces.


---

## ✨ What is CLike?

👉 AI-native governed engineering platform

### Why it matters
- **Flow state by default** — minimize context switches; everything lives inside VS Code.
- **Agentic & self‑healing** — AI assistants perform actions and auto‑remediate (diffs, patches, tests).
- **Enterprise paved road** — governance, auditability, and reproducibility are built‑in, not bolted on.

**Clike** is 
- Harper-governed
- RAG-grounded
- Eval-driven
- Human-in-the-loop
- Multi-model / agent-agnostic
- Cloud + local agent compatible

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
  Harper introduces an iterative software-generation journey: start from an idea, create a SPEC, derive a PLAN, generate a KIT, evaluate, harden, and promote in short feedback loops. -
[Haprer](https://harper.blog/posts/) 

- **Vibe Coding**  
  Vibe Coding emphasizes intent, flow, rapid prototyping, and cognitive offloading. The developer works at the outcome level while the system helps produce implementation artifacts. - [Gartner Vibe](https://www.gartner.com/document-reader/document/6494971?ref=pubsite)

- **AI-Native Software Engineering**  
  CLike applies agentic workflows, human-in-the-loop governance, RAG grounding, quality gates, and automated validation to make AI-generated software reviewable and promotable. - [Gartner AI](https://www.gartner.com/document-reader/document/6076795?ref=pubsite)

---

## 🧱 Architecture at a Glance
```
+-----------------------+       +-------------------------+       +--------------------+       +------------------------+
|  VS CODE EXTENSION    |       |  ORCHESTRATOR (FastAPI) |       |  GATEWAY (FastAPI) |       | CLOUD PROVIDERS.       |
+-----------------------+       +-------------------------+       +--------------------+       +------------------------+
| - Chat UI             | ----> | - Harper workflow brain | ----> | - Cloud model abs. | ----> | - OpenAI               |
| - Slash commands      |       | - Execution strategy    |       | - OpenAI/Anth. rout|  |    | - Anthropic            |
| - Workspace access    |       | - Agent exec. packages  |       | - Embeddings       |  |    | - ...                  |
| - Local file writes   | <---+ | - Eval/Gate semantics   |       | - Provider normal. |  |    |                        |
| - Git integration     |     | | - RAG endpoints         |       +----------^---------+  |    +------------------------+
| - RAG collector       |     | | - Orchestrator MCP srv. |                               |
| - Local agent actuator|     | +------------^------------+                               |	
| - Extension MCP server|     |              |                 +------------+             |
+-----------------------+     |              |                 |    RAG     |             |
            ^                 |              |<--------------> +------------|             |     +------------------------+
            |                 |              |                 |  Vector DB |             |     | LOCAL PROVIDERS.       |
            |                 v              |                 +------------+             +--- >+------------------------+
            |       +-----------------------------------+                                       | - OLLAMA               |
            +-------|              AGENTS               |                                       | - DeepSeek             |
                    | (Autonomous execution units)      |				          	                    +------------------------+
                    +-----------------------------------+						                                                      

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

## 🔒 Security, Governance, and the Paved Road

- **Auditability** — run artifacts, prompts, outputs, evals, and gate results are traceable.
- **Isolation** — local agents are constrained by allowed write roots.
- **Least privilege** — local agents must not perform Git operations or promote files directly.
- **RAG grounding** — generation is grounded in repository and docs context.
- **Human-in-the-loop** — the developer remains the final decision maker.
- **Cloud/local frontier control** — CLike can route cloud execution through the gateway and local execution through extension-actuated CLI tools.

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
→ Agent agnostic (Claude Code, GPT Codex,...)
→ Orchestrator normalizes
→ RAG/Git/Eval/Gate continue through CLike
```

The orchestrator owns:

- Harper phase semantics;
- execution strategy;
- local-agent eligibility;
- executor hints;
- prompt contracts;
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
| `/kit REQ-001 --integrity` | Runs integrity evaluation phase. (optinonal) |
| `/kit REQ-001 --hardener` | Runs promotion hardener phase. (optinonal) |
| `/kit REQ-001 --promotion-eval` | Runs promotion evaluation phase. (optinonal) |
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
| `/gate <REQ-ID> manual pass` | Promote at your risks - avoid unuseful guardrail. |

`/eval` can optionally include a local-agent pre-pass, but canonical eval remains CLike-owned.

### Finalization

| Command | Description |
|---|---|
| `/finalize` | Runs the final closure step for Harper workflows vai agent or cloud. |

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

👉 Read how to extend REQs
[docs/CLike_Harper_Extend_Feature.md](./docs/CLike_Harper_Extend_Feature.md)

---

## HOW-TO 

READ FIRST 👉 
[docs/Clike HARPER RUN.md](./docs/Clike%20HARPER%20RUN.md)

To get operational quickly with CLike and the Harper workflow, read [docs/HOWTO.md](./docs/HOWTO.md).

The HOWTO is the practical step-by-step guide for taking a project from initialization to finalized delivery:

```text
/init → /idea → /spec → /plan → (/kit → /eval → /gate)* → /finalize
```

It is written with a **developer-first** approach:

* the developer remains the **orchestrator** of the phases
* every generated artifact is **reviewed and validated** before moving on
* weak alignment is corrected early by refining requirements, context, or source material
* `/kit`, `/eval`, and `/gate` are treated as an iterative control loop, not as a one-shot generation flow


> **Operating rule**
>
> Do not advance to the next phase until the current output has been reviewed, refined where needed, and explicitly accepted by the developer.

---

## Capabilities, Skills, Packs, and Design Profiles

CLike includes a project-local capability system used to guide AI-native software delivery without making the platform dependent on a specific model, agent, vendor, language, or runtime.

Capabilities live inside the target workspace:

```text
.clike/
  project.json
  capabilities.yaml
  skills/
  packs/
  design-profiles/
```

During project initialization, CLike copies the default capability templates into the workspace. The orchestrator then reads these files and generates normalized capability context:

```text
CLIKE_CAPABILITY_MANIFEST.md
CLIKE_CAPABILITY_INDEX.json
```

These generated artifacts are the primary capability context for cloud models and local agents. Agents should not randomly inspect `.clike/`; they should use the manifest, the index, and the capabilities selected by PLAN.

### Capability Types

CLike uses three capability types:

| Type | Purpose |
|---|---|
| Skills | Atomic operational capabilities |
| Packs | Scenario-level capability bundles |
| Design Profiles | UI/UX constraints for frontend or operator-facing requirements |

### Skills

Skills define enforceable engineering behavior.

Examples:

- `backend-contract-boundary`
- `frontend-state-accessibility`
- `ai-rag-eval-guardrails`
- `ml-experiment-reproducibility`
- `mobile-offline-parity`
- `mendix-extension-boundary`
- `industrial-safety-simulator`
- `local-cloud-parity`
- `eval-contract-writer`
- `gate-risk-reviewer`
- `mvp-e2e-promotability`
- `backoffice-workflow-ux`
- `enterprise-solution-architecture`
- `secure-config-secrets`


A skill tells PLAN/KIT/EVAL/GATE what must be done, what must not be done, what evidence is required, and when Gate should block promotion.

### Packs

Packs represent solution scenarios.

Examples:

- `enterprise-solution`
- `startup-solution`
- `industrial-solution`
- `mendix-solution`
- `mobile-app`
- `ai-native-agent-platform`
- `enterprise-onprem`
- `industrial-manufacturing`
- `consumer-saas`

A pack does not replace requirements. It helps PLAN select the right constraints and skills for the scenario.

### Design Profiles

Design profiles constrain UI/UX generation.

Examples:

- `enterprise-console`
- `industrial-control-room`
- `startup-product-app`
- `mobile-operator-app`
- `developer-tooling-console`

Design profiles are only used for UI/UX-scoped REQs. They must not clone external brands or products.

### How Capabilities Flow Through Harper

Capabilities are used across the Harper pipeline:

```text
IDEA → SPEC → PLAN → KIT → EVAL → GATE → FINALIZE
```

- SPEC defines business and technical requirements.
- PLAN selects relevant packs, skills, and design profiles per REQ.
- KIT applies selected capabilities while generating code, tests, docs, and CI artifacts.
- EVAL checks whether the expected evidence exists and whether commands pass.
- GATE promotes only when the REQ has full PASS evidence and policy requirements are satisfied.

Capabilities must not override SPEC, TECH_CONSTRAINTS, repository evidence, explicit user instructions, or canonical Gate policy.

### Reliability Principle

CLike capability governance follows this rule:

```text
The runner produces evidence.
The agent diagnoses and repairs.
Canonical EvalRunner and Gate decide.
```

Agents and cloud models may help generate, diagnose, and repair candidate artifacts, but they cannot promote code or override Gate.

See [`docs/CAPABILITIES.md`](docs/CAPABILITIES.md) for the full technical documentation.

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

## 📝 License

Apache License 2.0

---

## Harper Project Bootstrap

- Docs: `docs/harper/`
- Runs: `runs/`
- Open Chat: Command Palette → `CLike: Chat (Q&A / Harper / Coding)`

---

# **CLike on, code on.**
