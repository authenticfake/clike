# 🚀 CLike — AI‑Native Pipeline for Product Engineers 
![Logo di Clike](images/icons/clike_128x128.png) 

[![Made with Python](https://img.shields.io/badge/Made%20with-Python-3776AB?logo=python)](https://www.python.org/)  
[![VS Code Extension](https://img.shields.io/badge/VS%20Code-Extension-007ACC?logo=visualstudiocode)](extensions/vscode)  
[![Dockerized](https://img.shields.io/badge/Run%20with-Docker-2496ED?logo=docker)](docker)  

> **From intent to impact.**  
> CLike keeps developers in flow, augments delivery with agentic workflows, and bakes in governance, eval‑driven quality, and a safe paved road for enterprises.

---

## ✨ Highlights
- 🌀 **Flow state by default** — no context switching, full VS Code integration.  
- 🤖 **Agentic & self‑healing** — AI assistants that act, test, and fix.  
- 🛡️ **Enterprise‑ready** — eval‑driven gates, governance, reproducibility, TRiSM aligned.  

---

## ✨ What is CLike?

**CLike** is an AI‑native platform that merges the **Harper‑style** pipeline (SPEC → PLAN → KIT) with the **Vibe Coding** philosophy (intent/outcome‑focused, developer in flow), and operationalizes it with **agentic workflows**, **retrieval‑grounded intelligence**, and **eval‑driven** quality gates.

### Why it matters
- **Flow state by default** — minimize context switches; everything lives inside VS Code.
- **Agentic & self‑healing** — AI assistants perform actions and auto‑remediate (diffs, patches, tests).
- **Enterprise paved road** — governance, auditability, and reproducibility are built‑in, not bolted on.

> Inspired by the project’s official Manifest and aligned with AI‑Native SWE best practices.

### ✨ Where the Idea Comes From

- **Harper (blog "Codegen Hero's Journey")**  
		→ talks about a narrative workflow in which the LLM is a co-hero: 
		starting with an idea, it generates a SPEC specification file, a PLAN, then a KIT, and iterating with short feedback cycles. 
		This is the methodological and operational backbone of the solution definition phase. -
[Haprer](https://harper.blog/posts/) 

- **Vibe Coding (Karpathy + Gartner)** → emphasizes flow, intent, rapid prototyping, and cognitive offloading: the developer becomes a "composer" who works at the outcome level, not the code level. This has been incorporated by leaving the developer only with the design/intent steps and automating the build, testing, and security.
[Gartner Vibe](https://www.gartner.com/document-reader/document/6494971?ref=pubsite)

- **AI-Native Software Engineering (Gartner)** → introduces agentic workflows, autonomous improvement loops, human-in-the-loop, and security as a guardrail. The process includes SAST, DAST, UAT/E2E, make targets for automatic cycles → process exactly in line with these recommendations.
[Gartner AI](https://www.gartner.com/document-reader/document/6076795?ref=pubsite)

---

## 🧱 Architecture at a Glance

```
+-----------------+         +-----------------------+         +--------------------+
| VS Code Client  | <-----> | Orchestrator (FastAPI)| <-----> |  Gateway (FastAPI) |
| (extension)     |         |  • Agentic ops        |         |  • Multi-model API  |
| • SPEC/PLAN/KIT |         |  • RAG, diffs, tests  |         |  • Model routing    |
| • Code actions  |         |  • Guardrails/evals   |         |  • Embeddings/Chat  |
+-----------------+         +-----------+-----------+         +----------+---------+
                                      ^                                 ^
                                      |                                 |
                                      |  Orchestrator API               |  Gateway API
                                      |  (REST/WS/MCP Client)           |  (REST/WS/MCP Server)
                                      |                                 |
                                      |                                 |
                                      v                                 v
                              +--------------+                   +--------------+
                              |  Vector DB   |  (e.g., Qdrant)   |  Provider SDK|
                              +--------------+                   +------+-------+
                                                                         |
         +---------------------+-----------------------+------------------+-------------------+
         |                     |                       |                                      |
   [LOCAL LLMs]           [LOCAL Embeds]          [CLOUD LLMs]                          [CLOUD Embeds]
   • Ollama (Llama,       • Ollama embeddings     • OpenAI (GPT, o1)                    • OpenAI (text-emb)
     DeepSeek, Phi, etc.) • Sentence-Tfm (HF)     • Anthropic (Claude)                  • Cohere
   • llama.cpp/vLLM       • GTE/Qdrant HNSW       • Google (Gemini)                     • VertexAI Embeddings
   • LM Studio            • text-embeddings-*     • Mistral (platform)                  • Mistral embed
                                                   • Azure OpenAI                        • AWS Bedrock (Titan, Cohere, etc.)

```

**Key directories**
- `extensions/vscode/` — CLike VS Code extension (UI).
- `orchestrator/` — Orchestrates agentic actions, RAG, diffs, and guardrails (FastAPI).
- `gateway/` — OpenAI‑compatible chat/embeddings over multiple providers (FastAPI).
- `configs/` — Model routing and provider settings (`models.yaml`).
- `docker/` — Compose files for local dev stack.
- `apps/` — Sample apps and demos.
- `docs/` — Additional notes (install & usage).

---

## 🚀 Quick Start (Local Dev)

### Prerequisites
- **Docker** & **Docker Compose v2**
- **VS Code** (≥ 1.85) + **Node.js 18+** for packaging the extension
- Optional: **Ollama** (local models) or API keys for remote providers (Anthropic, OpenAI, etc.)

### 1) Bring up services
```bash
cd docker
docker compose up -d --build

# health checks
curl -s http://localhost:8080/health   # orchestrator
curl -s http://localhost:8000/health   # gateway
```

> The compose mounts the repo at `/workspace` inside containers. The gateway reads model config from `MODELS_CONFIG=/workspace/configs/models.yaml`. The orchestrator resolves the gateway via `GATEWAY_URL=http://gateway:8000`.

### 2) Install the VS Code extension
```bash
cd extensions/vscode
npm i
npm i -g @vscode/vsce
vsce package
code --install-extension clike-*.vsix
```

Open your workspace in VS Code and look for the **CLike** commands:

- **Clike: Add Docstring (AI via Orchestrator)**
- **Clike: Refactor (AI via Orchestrator)**
- **Clike: Generate Tests (AI via Orchestrator)**
- **Clike: RAG Reindex / RAG Search**
- **Clike: Git Create Branch / Commit Patch / Smart PR**


#### Chat themes

The **CLike Chat** panel supports four visual themes designed for different workflows.  
You can select the active theme via the VS Code setting `clike.chat.theme`.
The **CLike Chat** panel supports four visual themes designed for different workflows.  
You can select the active theme via the VS Code setting `clike.chat.theme`.

#### Configuration

Add or edit the following setting in your **User** or **Workspace** `settings.json`:

```jsonc
"clike.chat.theme": "pro"
```

Allowed values:

| Value     | Description                                                                 |
|-----------|-----------------------------------------------------------------------------|
| `classic` | Original CLike theme. Chat-style bubbles with left/right layout.            |
| `pro`     | Default professional theme. Document-style blocks, neutral dark palette aligned with VS Code. |
| `studio`  | Console-oriented dark theme with subtle colored left borders for user/assistant messages. |
| `paper`   | Light notebook-style theme with soft grey background and high-contrast text.|

> If the setting is omitted, the extension falls back to `classic`.


> Tip: Enable **“Clike: Verbose Logging”** in settings if you’re debugging the extension.

---

## ⚙️ Configuration

### Models and Providers

`configs/models.yaml` declares enabled models and providers (local and/or remote). 

Example fields:
- `provider`: `ollama`, `openai`, `anthropic`, `vllm` (OpenAI‑compatible), etc.

- `base_url`: provider endpoint (use service names inside Docker, e.g., `http://ollama:11434`).
- `api_key_env`: name of env var when using remote APIs (e.g., `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`).
- `enabled`: toggle specific models per environment.

**Gateway env**
```bash
export MODELS_CONFIG=/workspace/configs/models.yaml
```

**Orchestrator env**
```bash
export GATEWAY_URL=http://gateway:8000
```

### VS Code settings
The extension reads routes and behaviors from `Settings → Extensions → CLike` (e.g., endpoints, logging, git automation).

---

## 🧪 Eval‑Driven Development & Guardrails

CLike encourages **eval‑driven** change (unit tests, lint, SAST/DAST, UAT) and guards promotion via Harper‑style gates:

- Freeze **IDEA** → approve **SPEC** → build and test **PLAN** with **required evals** → generate **Release Solution**.
- Orchestrator returns **diffs + full content** for safe application and review.
- Integrate with your CI to run eval suites and enforce quality gates before merge.

> The current MVP ships with agentic ops (docstrings, refactor, test scaffolding) and RAG endpoints. Extend evals in your CI for enterprise policies.

---

## 🔒 Security, Governance, and the Paved Road

- **Auditability** — requests/responses are logged (redact secrets), diffs and runs are reproducible.
- **Isolation** — execute risky ops in containers; keep secrets in VS Code’s secure storage and env vars.
- **Least privilege** — gateway and orchestrator are scoped to only required tools and data.
- **Air‑gapped mode** — route to local models (e.g., Ollama) and local vector DB without external calls.

---

## 🛠️ Local Dev (without Docker)

> Recommended only if you know your Python/Node envs well.

**Orchestrator**
```bash
cd orchestrator
pip install -r requirements.txt
uvicorn app:app --host 0.0.0.0 --port 8080 --reload
```

**Gateway**
```bash
cd gateway
pip install -r requirements.txt
export MODELS_CONFIG=$(pwd)/../configs/models.yaml
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

**VS Code extension**
```bash
cd extensions/vscode
npm i
code .   # F5 for extension host or package + install
```

**Telemetry UI**

```bash
http://localhost:8000/v1/metrics/harper/ui
```
---

## 🧭 Roadmap (short)

- Evals in the VS Code Test UI (surfaced as cases).
- Model router profiles (fast/cheap/strict) + policy hooks.
- Playbooks (SPEC/PLAN/KIT) for common industry scenarios.
- Expanded RAG sources and per‑project knowledge packs.

---

## 🤝 Contributing

Issues and PRs are welcome. Please include repro steps, logs (with secrets redacted), and environment details.

---

## 📝 License

TBD — see `LICENSE` when available.


## Harper Project Bootstrap
- Docs: docs/harper/
- Runs: runs/
- Open Chat: Command Palette → "CLike: Open Chat"
