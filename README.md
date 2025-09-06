<<<<<<< HEAD
# clike
Clike is an AI-native developer experience layer inspired by Cursor, AI Native Pipeline principles and from some visionar on internet
=======
# 🚀 CLike — AI‑Native Platform for Product Engineers

> **From intent to impact.** CLike keeps developers in flow, augments delivery with agentic workflows, and bakes in governance, eval‑driven quality, and a safe paved road for enterprises.

---

## ✨ What is CLike?

**CLike** is an AI‑native platform that merges the **Harper‑style** pipeline (SPEC → PLAN → KIT) with the **Vibe Coding** philosophy (intent/outcome‑focused, developer in flow), and operationalizes it with **agentic workflows**, **retrieval‑grounded intelligence**, and **eval‑driven** quality gates.

### Why it matters
- **Flow state by default** — minimize context switches; everything lives inside VS Code.
- **Agentic & self‑healing** — AI assistants perform actions and auto‑remediate (diffs, patches, tests).
- **Enterprise paved road** — governance, auditability, and reproducibility are built‑in, not bolted on.

> Inspired by the project’s official Manifest and aligned with AI‑Native SWE best practices.

---

## 🧱 Architecture at a Glance

```
+-----------------+        +-----------------------+        +--------------------+
| VS Code Client  | <----> | Orchestrator (FastAPI)| <----> | Gateway (FastAPI)  |
| (extension)     |        |  • Agentic ops        |        |  • Multi-model API |
| • SPEC/PLAN/KIT |        |  • RAG, diffs, tests  |        |  • Model routing   |
| • Code actions  |        |  • Guardrails/evals   |        |  • Embeddings/Chat |
+-----------------+        +-----------------------+        +--------------------+
                                     |
                                     v
                              +--------------+
                              |  Vector DB   |  (e.g., Qdrant)
                              +--------------+
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

> Tip: Enable **“Clike: Verbose Logging”** in settings if you’re debugging the extension.

---

## ⚙️ Configuration

### Models and Providers
`configs/models.yaml` declares enabled models and providers (local and/or remote). Example fields:
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
- Freeze **SPEC** → build **PLAN** with **required evals** → generate **KIT**.
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
>>>>>>> ef15915 (Initial commit)
