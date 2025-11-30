# CLike — Harper / Vibe Coding Playground

> ⚠️ **Draft notice**  
> This README is an **auto-generated, provisional overview**.  
> The final, production-ready documentation will be regenerated and refined during the **Harper `/finalize` phase**.

![CLike logo](./images/clike/clike_128x128.png)

CLike is a **Harper-style, AI-native development environment**.  
You work inside VS Code, talk to one or more LLMs, and drive your project through a clear sequence of phases instead of ad-hoc prompts.

The goal is simple: **turn conversations into production-grade software**, with traceability, tests, and repeatable workflows.

---

# **Clike on, code on.**
---

## 1. Harper Projects in a Nutshell

Harper is not “just prompting”.  
It is a **process** for building software with AI as a first-class collaborator:

> **IDEA → SPEC → PLAN → KIT → EVAL → GATE → FINALIZE**

Each phase produces concrete artifacts in your repo, so humans and models can collaborate reliably over time.

### 1.1 Phases & Artifacts

**IDEA — Frame the problem**

- You describe the **product vision**, target users and constraints.
- Harper turns that into a structured `docs/harper/IDEA.md`.
- The file becomes the narrative backbone: why the project exists, what “success” means, what is explicitly out of scope.

**SPEC — Turn vision into requirements**

- Harper reads the IDEA and asks: _“What must be true for this to work?”_
- It produces `docs/harper/SPEC.md` with:
  - Named capabilities and user journeys.
  - Observable, falsifiable requirements.
  - Early notes on technical constraints and risks.

**PLAN — Design the execution path**

- From SPEC, Harper generates:
  - `docs/harper/PLAN.md`: human-readable roadmap with **REQ-IDs** (REQ-001, REQ-002, …), dependencies, and acceptance hints.
  - `docs/harper/plan.json`: machine-readable structure for automation (lanes, gate policies, test profiles).
  - `docs/harper/lane-guides/*.md`: lane playbooks (e.g. `python`, `sql`, `kafka`, `infra`) describing tools, commands, and quality bars.
- PLAN defines **where code will live** (namespaces, modules, folders) so KIT can stay consistent.

**KIT — Implement one REQ at a time**

- Each `/kit` run targets one or more REQs and emits:
  - Source files under `runs/kit/<REQ-ID>/src/…`
  - Tests under `runs/kit/<REQ-ID>/test/…`
  - CI contracts `runs/kit/<REQ-ID>/ci/LTC.json`
  - How-to docs `runs/kit/<REQ-ID>/ci/HOWTO.md`
- The focus is **composition-first design**: small units, clear seams, and reuse of existing modules.

**EVAL — Run tests & checks**

- EVAL executes the commands defined in the LTC:
  - Tests, linters, type checkers, coverage, security scans…
- It produces machine-readable summaries under `runs/eval/<REQ-ID>/…` to feed back into the loop.

**GATE — Decide if a REQ passes**

- GATE applies the gate policy for each REQ:
  - “Do tests pass?”, “Is coverage above threshold?”, “Are critical issues acceptable?”
- If the gate passes, Harper can integrate changes back into the main branch following your Git policy.

**FINALIZE — Close the loop**

- Once a slice or project is ready, `/finalize`:
  - Consolidates docs into a clean `README.md` + “How to run” guides.
  - Captures a **sanity checklist** and “next ideas”.
  - Prepares release notes and a PR body.
- The README you are reading now will eventually be replaced by a **stable, curated version** at this stage.

### 1.2 How a Harper Project is Built (Day-to-day Flow)

A typical Harper-style project evolves like this:

1. **Bootstrap**
   - Run `/init` to create the basic structure.
   - Capture the initial IDEA with `/idea`.
2. **Shape the work**
   - Refine requirements via `/spec`.
   - Generate and iterate on `/plan` until REQs and lanes feel right.
3. **Implement incrementally**
   - Use `/kit` to implement a single REQ (or a small batch).
   - Reuse code and patterns from previous KIT runs via RAG context.
4. **Evaluate and gate**
   - `/eval` runs the test/contracts for that REQ.
   - `/gate` decides if the work is ready to be merged or needs another KIT loop.
5. **Finalize**
   - When a milestone is reached, `/finalize` consolidates documentation and release artifacts.

Harper’s superpower is **memory through files**: every phase leaves a trace in the repo, so both humans and models can reason over an evolving, shared source of truth.

---

## 2. The CLike VS Code Extension

The CLike VS Code extension is your **Harper cockpit**.  
It connects chat, models, files, and Git into a single, opinionated developer experience.

### 2.1 What the Extension Does

- **Multi-model chat panel**
  - Talk to different models (OpenAI GPT-5.x / Codex, Anthropic, local models… depending on your setup).
  - Switch models per conversation or per Harper command.

- **Harper command layer**
  - Run `/idea`, `/spec`, `/plan`, `/kit`, `/eval`, `/gate`, `/finalize` directly from the chat.
  - Each command routes through the gateway/orchestrator and writes the appropriate files under `docs/harper/` or `runs/`.

- **RAG-aware conversations**
  - The extension can attach project files as context (SPEC, PLAN, previous KIT runs, lane guides).
  - Harper uses this RAG context to compose new code that matches your existing architecture.

- **Code patch workflow**
  - Models can propose patches as “virtual files”.
  - The extension shows diffs and lets you apply or discard them explicitly.
  - Git integration (if configured) can commit and open PRs from gated changes.

- **Theming & UX**
  - Custom chat themes and layout tuned for long-form dev conversations.
  - Clear separation between:
    - freeform chat,
    - Harper system phases,
    - raw model logs (visibility when you need to debug the pipeline).

---

## 3. Capabilities at a Glance

CLike is not just “chat in a panel”. It provides a **stack of capabilities** that you can combine as you grow the project.

### 3.1 RAG & Project-aware Reasoning

- **Repository-grounded answers**  
  Harper can read SPEC, PLAN, lane-guides, previous KIT outputs, and selected source files as **retrieval-augmented context**.  
- **REQ-aware RAG**  
  When running `/kit REQ-00X`, CLike surfaces snippets from:
  - `runs/kit/<REQ-ID>/src` and `test` from past iterations,
  - dependencies declared in `plan.json`,
  - shared modules or patterns (e.g. domain models, DTOs, error handling).
- **Stable architecture**  
  Instead of constantly “re-explaining” the project, you point Harper to files. RAG becomes your **long-term memory**, not a one-off prompt hack.

### 3.2 Attachments & Context Control

- **File attachments from the chat**  
  Drag-and-drop or select files (specs, diagrams, logs, JSON payloads, legacy code) and attach them to a conversation or a Harper command.
- **Scoped context**  
  You decide what the model sees:
  - single file for a focused refactor,
  - curated bundle for a complex KIT run,
  - minimal context for quick Q&A.
- **Repeatable debugging**  
  Attach logs or failing test output, ask Harper to propose fixes, and keep that context in the thread for future iterations.

### 3.3 Multi-model & Single-model Modes

- **Multi-model orchestration**
  - Use different models for different jobs:
    - GPT-5.x for high-level reasoning and planning,
    - Codex-style models for code-heavy KIT runs,
    - lighter models for quick edits or docs.
  - Route Harper commands to specific models (`/kit` on Codex, `/plan` on GPT-5.x, etc.).
- **Single-model focus**
  - Pin a model for a whole session when you want a consistent “voice” and behavior.
  - Helpful for long investigations, refactors, or when you are tuning costs.

### 3.4 Embeddings & Semantic Views

- **Semantic indexing of project files**  
  (When configured) CLike can build embeddings for key documents and code slices, enabling:
  - smarter RAG retrieval,
  - semantic search across SPEC, PLAN, KIT runs, and code.
- **Embedding-aware prompts**  
  Instead of passing raw file blobs, CLike can hydrate prompts from the most relevant chunks, keeping context windows efficient and focused.

### 3.5 Freeform Chat & “G-free” Mode

- **Harper-aware chat**  
  Normal conversations still benefit from Harper context: you can ask “why is REQ-003 blocked?” or “remind me how the Kafka lane works”.
- **G-free / Free chat mode**
  - Talk to models **without** Harper process envelopes when you just need:
    - brainstorming,
    - generic coding help,
    - quick lookups or explanations.
  - Perfect for exploratory phases, sketches, or when you don’t want to persist artifacts yet.

### 3.6 Coding Assistance & Refactors

- **Structured code generation**
  - Models emit **file-shaped outputs** (`file:/path.ext` + contents) that map directly into your repo or `runs/kit` structure.
  - This is ideal for Harper KIT runs but can also be used in ad-hoc coding tasks.
- **Refactor loops**
  - Ask for refactors in-place: CLike can compare new code with existing files and show diffs.
  - Combine RAG (existing modules) with model reasoning to evolve the design incrementally.
- **Test-first nudges**
  - KIT phases and lane-guides push towards tests, lint, and types.
  - Even in “plain chat”, you can ask the assistant to generate tests and CLike will keep them close to the relevant code.

---

## 4. Status: Work in Progress

The CLike extension and this README are part of an **ongoing Harper experiment**:

- APIs, commands, and UI may change as we refine the workflow.
- Some models (especially reasoning-only ones like GPT-5.1-Codex) are used in **experimental modes** and may not behave identically to standard chat models.
- Quality gates, lane-guides, and KIT/EVAL integration are being tuned to better match real-world enterprise constraints (air-gapped environments, on-prem infra, etc.).

During the **`/finalize` phase**, this README will be:

- reconciled with the current project state,
- aligned with actual lanes, commands, and REQs,
- promoted from “draft narrative” to **trusted entry point** for new developers.

---
If you are reading this inside VS Code after running `/init`, you are already in the Harper loop.  
From here, your next step is to **capture the IDEA** and let CLike help you turn it into a living, testable system.
