# 🚀 CLike — AI‑Native Platform for Product Engineers

> **From intent to impact.** CLike keeps developers in flow, augments delivery with agentic workflows, and bakes in governance, eval‑driven quality, and a safe paved road for enterprises.

---

## ✨ What is CLike?

**CLike** is an AI‑native platform that merges the **Harper‑style pipeline** (SPEC → PLAN → KIT) with the **Vibe Coding philosophy** (intent/outcome‑focused, developer in flow).  
It operationalizes this vision with **agentic workflows**, **retrieval‑grounded intelligence**, and **eval‑driven development**.

### Why it matters
- **Flow state by default** — minimize context switches; everything lives inside VS Code.  
- **Agentic & self‑healing** — AI assistants perform actions and auto‑remediate (diffs, patches, tests).  
- **Enterprise paved road** — governance, auditability, and reproducibility are built‑in, not bolted on.  

---

## 🧱 Repository Structure

```
clike_mvp/
  apps/              # Demo apps (e.g., demo-rag, demo-be)
  services/          # Backend services (gateway, orchestrator)
  orchestrator/      # Core orchestrator logic (agents, RAG, evals, routes)
  gateway/           # Model routing and provider abstraction (OpenAI, Anthropic, DeepSeek...)
  extensions/
    vscode/          # CLike VS Code extension (UI integration)
    zed/             # Experimental editor extension
  docker/            # Docker Compose configurations
  docs/              # Documentation and Postman collections
```

---

## 🛠️ Core Components

- **VS Code Extension** (`extensions/vscode/`)  
  Integrated UI with **SPEC, PLAN, KIT tabs**, Eval Panel, and AI‑powered code actions (docstring, refactor, fix_errors, test classes) and bot for **harper approach**

- **Orchestrator** (`services/orchestrator/`)  
  Runs agentic workflows, RAG pipelines, evals, diffs, and Git integrations.

- **Gateway** (`services/api-gateway/`)  
  Multi‑model routing with OpenAI‑compatible API surface.

- **Apps** (`apps/`)  
  Sample apps demonstrating usage (RAG demo, backend demo).

- **Docker setup** (`docker/`)  
  Compose files for running orchestrator, gateway, vector DB, and dependencies.

---

## 🚀 Quick Start

### Prerequisites
- **Docker** & **Docker Compose v2**
- **VS Code** (≥ 1.85) + **Node.js 18+** for extension packaging
- API keys for models (Anthropic, OpenAI, etc.) or **Ollama** for local models

### 1) Run the stack
```bash
cd docker
docker compose up -d --build

# health checks
curl -s http://localhost:8080/health   # orchestrator
curl -s http://localhost:8000/health   # gateway
```

### 2) Install the VS Code extension
```bash
cd extensions/vscode
npm install
npm install -g @vscode/vsce
vsce package
code --install-extension clike-*.vsix
```

Open your workspace in VS Code and try commands like:  
- **CLike: Add Docstring**  
- **CLike: Refactor**  
- **CLike: Generate Tests**  
- **CLike: RAG Search**  
- **CLike: Smart PR**  

---

## ⚙️ Configuration

### Models and Providers
`configs/models.yaml` defines enabled models and providers (local/remote).  

Gateway reads:
```bash
export MODELS_CONFIG=/workspace/configs/models.yaml
```

Orchestrator connects via:
```bash
export GATEWAY_URL=http://gateway:8000
```

### VS Code Settings
Manage endpoints, logging, and Git automation in:  
`Settings → Extensions → CLike`.

---

## 🧪 Eval‑Driven Development

CLike enforces **Harper guardrails**:  
- SPEC must be frozen → PLAN defined with evals → KIT generated and tested.  
- Evals include unit tests, lint, SAST/DAST, and UAT.  
- Orchestrator produces **diffs + full content** for safe reviews.

---

## 🔒 Security & Governance

- **Auditability** — reproducible runs, logged requests/responses.  
- **Isolation** — risky ops in containers; secrets managed in VS Code secure storage.  
- **Air‑gapped mode** — use local models/vector DB without external calls.  
- **Governance** — TRiSM‑aligned guardrails for enterprise use.  

---

## 🧭 Roadmap

- Surfacing evals inside VS Code Test UI  
- Model routing profiles (fast / strict / cost‑optimized)  
- Industry playbooks (SPEC/PLAN/KIT templates)  
- Expanded RAG connectors and multi‑agent workflows  

---

## 🤝 Contributing

Contributions welcome!  
Please open issues/PRs with clear repro steps, logs (redact secrets), and environment details.

---

## 📝 License

TBD — see `LICENSE`.

