# AI-Native Practices Overview

## Comparative Table

| Practice / Concept                | Definition                                                                                                              | Maturity (Gartner 2025)      | Role in Vibe Coding / Harper-Style                                                 | Key Challenges                                                 |
| --------------------------------- | ----------------------------------------------------------------------------------------------------------------------- | ---------------------------- | ---------------------------------------------------------------------------------- | -------------------------------------------------------------- |
| **Vibe Coding**                   | Paradigm by Karpathy (2025): dev “forgets the code”, prototypes rapidly via voice/minimal input, AI handles bug fixing. | *Emerging, Transformational* | Keeps developer in *flow state*. Used for prototyping and creative exploration.    | Not production-ready. Lack of governance, traceability, tests. |
| **AI-Native SWE**                 | Software engineering optimized for pervasive AI across SDLC. Integrates AI in design, dev, test, ops.                   | *Early adoption*             | Foundation layer. Defines processes/tools where Vibe Coding is one modality.       | Requires cultural shift, new tooling, security/governance.     |
| **Eval-Driven Development (EDD)** | Practice where evals (lint, unit, UAT, SAST, DAST) validate AI outputs. Not deterministic, but statistical confidence.  | *Emerging*                   | Governance pillar in Harper-style: validator/orchestrator HITL + eval harness.     | Designing reliable evals, handling false positives/negatives.  |
| **Model Context Protocol (MCP)**  | Standard to connect LLMs with external tools, APIs, and memory in a structured way.                                     | *Emerging*                   | Enables orchestration of multi-agent workflows, retrieval, integration with FS/DB. | Immature standard, tooling fragmented.                         |
| **GenAI Model Routers**           | Middleware that routes prompts to best model based on cost, latency, accuracy, policy.                                  | *Early adoption*             | Needed for Clike Gateway: pick GPT/Claude/Ollama automatically.                    | Cost optimization vs consistency.                              |
| **AI Agent Frameworks**           | Platforms to build agentic workflows with planning, memory, tool-use (LangChain, CrewAI, AutoGen).                      | *Early adoption*             | Backbone for Harper-Style orchestration (Idea → Spec → Plan → Kit).                | Complexity, evaluation of agent autonomy.                      |

---

## Key Takeaways

* **Vibe Coding** is the UX/frontier practice → developer stays in flow, but it needs **AI-Native SWE** to scale to enterprise.
* **Harper-Style** builds on this: IDEA → SPEC → PLAN → KIT with **HITL** validation.
* **EDD** ensures governance and code quality (eval gates at every step).
* **MCP** + **Agent Frameworks** provide the technical glue for orchestration and integration.
* **GenAI Model Routers** are required in Clike Gateway to support multi-model configuration (GPT, Claude, Ollama, etc.).
eorica e possiamo iniziare a scrivere i sorgenti?
