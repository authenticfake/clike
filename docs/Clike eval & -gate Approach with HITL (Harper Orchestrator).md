# /eval & /gate Perimeter with HITL (Harper Orchestrator)

---

## 1) Roles and Responsibilities

* **Harper Orchestrator (Developer/Engineer, Super-User)**

  * Decides *when* and *how* to execute tests (local, enterprise CI, vendor environments, manual).
  * Validates model outputs (SPEC/PLAN/KIT, LTC/HOWTO, EVAL results).
  * Triggers **/eval** and **/gate**, approves/promotes, manages **Git** (commit/tag/PR).
  * Provides documented *overrides* (manual outcomes) when appropriate.

* **CLike (LLM-first, Semantic Orchestrator)**

  * **Generates**: Lane Guides (per lane), **LTC.json** and **HOWTO.md** for each REQ.
  * **Guides** execution: how to run tests in each context (on-prem/cloud/vendor) and where to fetch **standard reports** (JUnit, JSON, SARIF, coverage).
  * **Normalizes**: converts heterogeneous results into `eval.summary.json`.
  * **Evaluates**: applies policy and dependencies in **/gate**, but **does not enforce** execution; also accepts manual outcomes.

> Outcome: the **human remains at the center** (HITL), while CLike reduces complexity, documents, standardizes, and normalizes.

---

## 2) Testing Philosophy (No Coercion)

* **No constraint on where/how** tests are executed:

  * **Local** (developer) — e.g., `pytest`, `mvn test`, `npm test`.
  * **Enterprise CI** (Jenkins/GitLab/Azure DevOps) — dedicated jobs.
  * **Vendor Environments** (PLC/SCADA, Mendix, etc.) — proprietary suites.
  * **Manual** — when automation isn't possible or expert judgment is needed.

* **LLM generates tests** (in KIT) and **execution instructions** (HOWTO), updated to the context and **TECH_CONSTRAINTS.yaml** (air-gap, internal images, allowed tools, minimum policy).

* **CLike does not impose** "one way" to test; it **accepts** results wherever they are produced, provided they are documented.

---

## 3) Artifact Model (What We Produce and Where)

* `docs/harper/lane-guides/<lane>.md` — standard guide for the lane (tools, formats, default policy, enterprise runners).
* `runs/kit/<REQ-ID>/ci/LTC.json` — **LLM Test Contract** for the REQ (commands, reports, normalization, thresholds, external runners).
* `runs/kit/<REQ-ID>/ci/HOWTO.md` — operational (copy-paste) recipe for execution.
* `runs/<runId>/eval.summary.json` — **normalized results** (tests/lint/types/security/build, metrics, overall per REQ).
* `runs/<runId>/gate.decisions.json` — **eligible/blocked/conflicts** decision with **rationale** and **traceability**.
* `docs/harper/plan.json` + `docs/harper/PLAN.md` — updated **REQ status** and **snapshot**.
* **Git**: standard commit/tag for each phase (e.g., `harper/eval/<runId>`, `harper/gate/<runId>`).

> Everything is versioned: any run can be reconstructed, allowing us to understand where an error originated and why it was approved.

---

## 4) /eval — What it Does (and Doesn't Do)

**What it Does**

* Reads the REQ's **LTC/HOWTO** and, if needed, the Lane Guides and TECH_CONSTRAINTS.
* **Indicates how to execute** (without enforcing where): local, CI, vendor.
* **Searches/ingests** **already produced** reports (JUnit, JSON, SARIF, coverage).
* **Normalizes** → `eval.summary.json` (checks, metrics, logs refs, overall REQ).

**What it Does Not Do**

* It does not "centralize" computation in the CLike BE.
* It does not require tests to **necessarily** be launched by CLike: the human orchestrator can do it **manually** or via CI.

**Manual Outcomes (HITL)**

* If the REQ has no automatable reports (e.g., in-field OT inspection), the orchestrator can **attach evidence** (notes/logs) and set **manual check = PASS/FAIL** in the normalization layer with **rationale** (audit trail).

---

## 5) /gate — Policy and Sequence (with Tracked Override)

* **Sequencing**: respects the **DAG** from `plan.json`; sequential **fallback** (`REQ-(k-1)` before `REQ-k`).
* **Policy** per lane:

  * Common minimums (tests/lint/types/security/build) with **thresholds** from the Lane Guide or the REQ's LTC.
  * Enterprise gate (e.g., **Sonar Quality Gate = GREEN**) if declared in TECH_CONSTRAINTS.
* **Decision**:

  * `eligible` if **dependencies** OK and **thresholds** OK.
  * `blocked` with clear **reasoning** (which check/threshold/deps).
  * `conflicts` if promoting files overlap (requires confirmation).
* **HITL Override**:

  * The orchestrator can **force** promotion in extraordinary cases. **Rationale** is required; everything ends up in `gate.decisions.json` and **Git** (commit message/tag).
  * Recommended policy: allow override **only** if a well-justified and referenced `manual_check: PASS` exists.

---

## 6) Git as Governance (Replicability & Audit)

* **Single Source of Truth**: every artifact lives in the **workspace** and is versioned: SPEC, PLAN, KIT, LTC/HOWTO, eval.summary, gate.decisions.
* **Full Traceability**:

  * Commit/tag per phase/run.
  * Standard messages with runId, affected REQs, main outcomes/thresholds.
  * Ability to **bisect** regressions between two Harper tags.
* **PR/Merge**: optionally, `/finalize` generates RELEASE NOTES/PR text; the team maintains control over `main`.

---

## 7) Test Execution Modes (Option Catalog)

* **Local (Developer)**
  Examples: `pytest`, `mypy`, `ruff`, `mvn test`, `npm test`, `go test`, `cargo test`, `ctest`, etc.
  → Reports are read by the extension and normalized.

* **Enterprise CI**
  Jenkins/GitLab/Azure DevOps with standardized jobs.
  → HOWTO explains what to launch, where to find reports; the extension ingests.

* **Vendor / Special Domains**
  Mendix (Unit Testing/QSM), Siemens TIA/PLCSIM, CODESYS Test Manager, etc.
  → HOWTO indicates the **steps** and **paths** to retrieve exportable artifacts; the extension ingests and normalizes.

* **Manual**
  Ad-hoc tasks, plant controls, non-automatable safety steps.
  → The orchestrator records a **manual outcome** (with evidence and rationale) which feeds into `eval.summary.json`.

> **No Coercion**: the lane and LTC/HOWTO are a "paved road," not chains. The orchestrator can **knowingly** deviate and leave a trace.

---

## 8) Integration with TECH_CONSTRAINTS.yaml

* **Enforces the lane** or execution constraints (air-gap, images, allowed/forbidden tools, minimum coverage).
* **Defines enterprise gates** (e.g., Sonar GREEN as a **blocking** factor).
* It is **absorbed** by the model into **Lane Guide** and **LTC/HOWTO**: CLike adapts commands, report formats, thresholds.

---

## 9) Minimal UX in VS Code (No Lock-in)

* **HOWTO Panel**: shows the steps proposed by the model for test/analysis execution.
* **EVAL Panel**: list of REQs with status (green/yellow/red), key metrics, links to raw reports.
* **Controlled Promotion**: "Gate" button that:

  * verifies dependencies,
  * applies policies,
  * manages conflicts,
  * proposes commit/tag/PR.
* **Manual Outcome**: form to add evidence and rationale → persists in the JSON.

---

## 10) Alignment with "Gartner 2025" Recommendations (Conceptual)

* **Human-led, AI-assisted**: LLM produces recipes and tests, the human **decides** and **validates** (HITL).
* **Tool-agnostic & multi-lane**: no lock-in on BE runners; integration with existing enterprise stack.
* **Governance by design**: **Git** as the audit backbone (versioned artifacts and decisions).
* **Replicability**: every decision is reproducible from the runId/tag and attached artifacts.

---

## 11) Acceptance Criteria (Operational)

* `/eval` accepts:

  * automated reports **or** manual outcome with evidence,
  * always produces `eval.summary.json` consistent with LTC/HOWTO.
* `/gate`:

  * blocks if **deps** are not satisfied,
  * applies lane/LTC **thresholds**,
  * allows override **only** with rationale,
  * updates `plan.json` and `PLAN.md`,
  * performs **Git** operations (commit/tag) from the client.
* Documentation:

  * Lane Guide for every lane used,
  * LTC/HOWTO for every REQ,
  * complete snapshot and traces in the repo.

---

### Conclusion

Principles: genuine **HITL**, **LLM as an accelerator** (not a rigid executor), **no coercion** on execution, and **Git** as governance.
The developer is the **Harper Orchestrator**: they decide, execute where it makes sense, validate, and sign off. CLike makes everything **standard, readable, and repeatable**, without dictating the "where" of testing but **guiding** the "how" and **documenting** the "why."

TODO:

* mini-SPEC for "Manual Outcome" and "Promotion Safety",
* micro-checklist that the extension can display before allowing the `Gate`.