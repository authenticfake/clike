

## CLike – Product Roadmap 

### Horizon 1

**Title:** *Multi-agent core, MCP-ready, minimal UX*

#### H1-T1 — Harper Quickstart (multi-agent, LangGraph-based)

* Implement a `CLike: Harper Quickstart` command (via command palette and one concise entry point in the Harper panel).
* Behind this, use a LangGraph workflow with multiple specialized agents:

  * `IdeaAgent` → normalizes and structures `IDEA.md`.
  * `SpecAgent` → generates `SPEC.md` and initial REQ IDs.
  * `PlanAgent` → produces `PLAN.md` and `plan.json` with dependencies and lanes.
  * `LaneAdvisorAgent` → proposes lanes and lane-guides based on tech constraints.
  * `DocAgent` → seeds core docs (README/HOWTO skeletons).
* The output is written directly into the repo; the chat only shows a compact final summary with links to the generated files.

---

#### H1-T2 — MCP Core (CLike as MCP server and client – phase 1)

* Expose CLike’s core capabilities as an **MCP server**, including tools like:

  * `clike.fs.*` (list/read/write files),
  * `clike.git.*` (branches, tags, commits, PR helpers),
  * `clike.tests.*` / `clike.lint.*` / `clike.typecheck.*`,
  * `clike.rag.*` (index/search),
  * `clike.harper.*` (run SPEC/PLAN/KIT/EVAL/GATE/FINALIZE).
* Provide MCP manifests/config so any MCP client (Claude, ChatGPT, LangGraph, external platforms) can discover and use these tools.
* Add **MCP client** support in the orchestrator (first step): allow Harper workflows (including LangGraph flows) to call external MCP servers where needed (e.g., SaaS APIs, internal enterprise systems).

---

#### H1-T3 — Eval/Gate “one button” (outside the chat UI)

* Add new commands in the **command palette**:

  * `CLike: Run Eval for current REQ`
  * `CLike: Run Gate for current REQ`
* Introduce a **“Harper Eval” side panel**:

  * Shows REQ list and their EVAL status (pass / fail / warning).
  * Displays gate decisions and links to logs / reports.
* Keep the chat minimal:

  * Optional textual commands like `/eval REQ-003` for power users.
  * No extra buttons cluttering the conversation area.

---

#### H1-T4 — Git & RAG “zero friction” (panels and palette, not chat noise)

* **Git automation via palette & panels**:

  * Commands like:

    * `CLike: Prepare Harper Branch for REQ-XXX`
    * `CLike: Open PR for current run`
  * Show Git actions and summaries in a dedicated panel, not as noisy chat threads.
* **Dedicated “CLike Knowledge” / RAG panel**:

  * Visual list of indexed sources (docs, src, wiki) and tags (e.g., `spec`, `arch`, `sdk`).
  * Buttons for “Index folder” / “Index selection”.
* In chat:

  * Keep only essential RAG commands (`/rag search`, `/rag attach +N`) to avoid overload.

---

### Horizon 2

**Title:** *From developer tool to factory platform (SaaS + workstation)*

#### H2-T1 — Dual Deployment: Factory SaaS & Solo Workstation

* **CLike Factory mode** (centralized / SaaS or on-prem):

  * One shared orchestrator/gateway/RAG for a whole software factory.
  * Manages multiple projects, teams, and telemetry in a single place.
  * Exposes a web UI for leads/POs.
* **CLike Solo mode** (developer workstation):

  * Lightweight distribution (e.g. Docker compose or installer) running locally.
  * Same VS Code extension, targeting the local orchestrator.
  * Supports a single developer / single machine scenario with all core features.

---

#### H2-T2 — Team Hub Web: PO & Tech Lead views

* Build a **web Team Hub** on top of CLike Factory:

  * Project list with recent Harper runs, their status, and key metrics.
  * **Product Owner view**:

    * Table of REQ with value/priority/status, EVAL results, gate decisions.
    * Actions: rescope, split, reprioritize, or freeze REQ.
  * **Tech Lead view**:

    * Health of lanes (tests, coverage, security, build).
    * Failed gates and reasoning (which policy / tool failed).

---

#### H2-T3 — Smart integration with GitHub Agent HQ & GitLab Duo

* **Integration pattern with GitHub Agent HQ**:

  * Use CLike to create structured SPEC/PLAN/LTC and corresponding GitHub issues/PRs.
  * Let Agent HQ agents implement or modify code.
  * On PR creation/update, CLike:

    * Runs EVAL/GATE (tests, coverage, lint, security, custom scripts).
    * Writes structured comments back to the PR with gate results and suggestions.
* **Integration pattern with GitLab Duo / Duo Agent Platform**:

  * Add CLike EVAL/GATE stages into `.gitlab-ci.yml`.
  * Allow Duo agents to call MCP tools from CLike (tests, RAG, policy checks).
  * Position CLike as an **external AI quality gate** that standardizes evaluation across projects.

---

#### H2-T4 — MCP & Domain/Lane Blueprints

* Finalize and package **standard MCP tools for CLike**:

  * Public, documented MCP tool set (`clike.fs`, `clike.git`, `clike.tests`, `clike.rag`, `clike.harper`, `clike.lane.*`).
* Deliver **domain-specific blueprints**, including:

  * **Industrial & Manufacturing blueprint**

    * Lanes for backend APIs (MES/IoT), operator frontends, and data pipelines.
    * Optional MCP connectors for OPC-UA, MES, PLM, data lakes.
  * **Public Sector / Digital Twin blueprint**

    * Lanes for GIS backends, geoportal frontends, and data governance.
    * RAG seeds on standards, regulation, and technical docs.
  * **Event-driven service blueprint (CoffeeBuddy-style)**

    * Lanes for Slack bots, Kafka events, and observability.

Each blueprint ships with:

* IDEA templates, SPEC & PLAN seeds,
* lane-guides, LTC baselines,
* RAG configuration and MCP tool recommendations.

---

### Horizon 3

**Title:** *Ecosystem & Analytics: CLike as de facto standard*

#### H3-T1 — Lane Marketplace

* Create a **Lane Marketplace**:

  * Community and partners can publish lane-guides, LTC sets, and MCP configurations.
  * You curate:

    * “Featured lanes” (high-quality, battle-tested),
    * “Enterprise-grade lanes” (with stronger gates and policy).

---

#### H3-T2 — Vertical Harper Templates as Products

* Offer complete **vertical Harper templates** (e.g. PA, industry, fintech, healthcare) as reusable products:

  * Repos with IDEA + SPEC + PLAN pre-modeled.
  * Associated lane-guides, LTC, and RAG/MCP setups.
  * Supported and versioned over time.

---

#### H3-T3 — CLike Insights (C-level analytics)

* Build **CLike Insights** for leadership:

  * Metrics:

    * % of REQ passing gate on first attempt.
    * Lead time per Harper phase and per lane.
    * Post-release defects vs gate configuration.
    * AI-generated vs human-generated code impact.
  * Export:

    * APIs / CSV for BI integration,
    * standard reports for steering committees and governance boards.

---

## Part 2 – Benefits 
### 1. Developer Experience & Productivity

* **H1-T1 (Harper Quickstart)**

  * Reduces the friction of the first run: developers get IDEA, SPEC, PLAN, and lanes in a single guided step.
  * Encourages consistent structure across projects, making it easier to move between repositories.

* **H1-T3 (Eval/Gate one button)**

  * Puts quality actions (tests, eval, gate) one command away, without overloading the chat.
  * Developers keep mental focus on the code, not on navigating menus.

* **H1-T4 (Git & RAG zero friction)**

  * Git workflows and RAG become predictable and visible in panels, not hidden behind “magic”.
  * Fewer surprises and less confusion for new users.

Overall, Horizon 1 makes CLike feel like a **sharp, focused tool** rather than a noisy AI gadget.

---

### 2. Product & Project Governance

* **H2-T1 / H2-T2 (Factory + Team Hub)**

  * Gives Product Owners and Tech Leads a clear view of REQ status, gates, and risks.
  * Makes Harper phases and gates auditable across teams, which is crucial in regulated or complex environments.

* **H2-T3 (Agent HQ / GitLab Duo integration)**

  * Sets CLike as the **governance and quality layer** on top of coding agents.
  * Organizations can adopt more aggressive AI coding strategies while still enforcing consistent gates and policies.

* **H3-T3 (CLike Insights)**

  * Provides hard data on how AI and CLike change delivery performance and quality.
  * Helps justify investments and steer policies (e.g., gate thresholds, lane standards).

---

### 3. Platform & Ecosystem Position

* **H1-T2 + H2-T4 (MCP core + Blueprints)**

  * Position CLike as an **MCP server of choice for AI-native software engineering**.
  * Domain blueprints make CLike relevant beyond generic web apps (industry, PA, digital twins, etc.).

* **H3-T1 / H3-T2 (Marketplace & Vertical templates)**

  * Create a real ecosystem where lanes and templates can be shared and monetized.
  * Encourages partners and internal teams to contribute lanes, making CLike more valuable over time.

---

### 4. Business & Strategic Value

* Short term (H1):

  * Stronger adoption by developers thanks to better UX and multi-agent power hidden behind simple commands.
  * Clear differentiation: “pipeline + governance”, not just autocomplete.

* Medium term (H2):

  * CLike becomes the **central fabric** of a software factory (SaaS + workstation), not just a VS Code plugin.
  * Plays nicely with big players (GitHub Agent HQ, GitLab Duo) by adding governance where they focus on agent execution.

* Long term (H3):

  * Ecosystem and analytics give CLike a defensible position as **standard for AI-native SWE governance**, especially in enterprise and regulated sectors.



