# Clike — Harper Process I/O Map
**Document:** `PROCESS_IO.md`  
**Scope:** Input/Output definitions and responsibilities for the Harper pipeline phases — **SPEC → PLAN → KIT → EVAL → GATE → FINALIZE** — plus code‑impact notes for prompt‑only changes.


## 1) Phase I/O — End‑to‑End Map

Below, each phase lists **Inputs**, **LLM Responsibilities**, **Outputs**, and **Consumers**.

### 1.1 SPEC Phase

**Inputs**
- `IDEA.md` (business intent, user story, goals)
- `TECH_CONSTRAINTS.yaml` (enterprise rules, on‑prem/cloud restrictions, quality standards) — *optional but recommended*
- Repository context (prior plans/specs, existing code)

**LLM Responsibilities**
- Translate the idea into a structured **SPEC.md** (functional + non‑functional requirements, acceptance criteria)
- Identify *candidate* technologies (lanes) that might be needed
- Include a brief **“Testing Expectations”** paragraph (high‑level, lane‑agnostic)

**Outputs**
- `docs/harper/SPEC.md`

**Consumers**
- `/plan` (for REQ breakdown and lane detection)
- Human review (scope sign‑off)

---

### 1.2 PLAN Phase

**Inputs**
- `docs/harper/SPEC.md`
- `TECH_CONSTRAINTS.yaml`
- Repository auto‑discovery (marker files, structure, historical plan)

**LLM Responsibilities**
- Break the work into **REQs**; generate **dependency graph**
- Detect **lanes** (Python, JS/TS, Java, .NET, Go, Rust, C/C++, IaC/K8s/Helm, Mendix, PLC/SCADA, …)
- Produce **Lane Guides** *per lane used by the project* (see §2)
- Enrich **plan.json** with per‑REQ meta: `lane`, `test_profile`, `gate_policy_ref` (link to Lane Guide)

**Outputs**
- `docs/harper/plan.json` (REQs, deps, lane per REQ, status)
- `docs/harper/PLAN.md` (human snapshot)
- `docs/harper/lane-guides/<lane>.md` (one per detected lane)

**Consumers**
- `/kit` (to generate code/tests and REQ‑specific LTC/HOWTO)
- `/eval` & `/gate` (fallback defaults when REQ‑specific details are missing)

---

### 1.3 KIT Phase

**Inputs**
- `docs/harper/plan.json` & `docs/harper/PLAN.md`
- `docs/harper/lane-guides/<lane>.md` (project‑level defaults)
- `TECH_CONSTRAINTS.yaml` (execution constraints and enterprise runners)

**LLM Responsibilities (per REQ)**
- Generate **source** under `runs/kit/<REQ-ID>/src/` and **tests** under `runs/kit/<REQ-ID>/test/`
- Emit **LTC.json** describing: lane, tools, exact commands, report paths, normalization, thresholds, optional external runner
- Emit **HOWTO.md** containing copy‑paste CLI steps (local and/or container), and enterprise runner instructions

**Outputs (per REQ)**
- `runs/kit/<REQ-ID>/src/`
- `runs/kit/<REQ-ID>/test/`
- `runs/kit/<REQ-ID>/ci/LTC.json`
- `runs/kit/<REQ-ID>/ci/HOWTO.md`

**Consumers**
- `/eval` (reads LTC/HOWTO, executes or ingests; normalizes results)
- `/gate` (applies thresholds and dependency rules)

---

### 1.4 EVAL Phase

**Inputs**
- REQ artifacts from `/kit` (`src/`, `test/`)
- `runs/kit/<REQ-ID>/ci/LTC.json` and `HOWTO.md`
- Fallback: `docs/harper/lane-guides/<lane>.md`
- `TECH_CONSTRAINTS.yaml` (e.g., air‑gap, internal registries, Sonar required)

**LLM Responsibilities**
- Resolve the **execution recipe** (from LTC/HOWTO; fallback to Lane Guide)
- If `external_runner` is present: instruct artifact **ingestion** (no local execution)
- Define **normalization mapping** to produce a single schema

**Outputs**
- `runs/<runId>/eval.summary.json` — normalized per‑REQ results:
  - `checks`: `{ tests, lint, types, security, build, iac, container, model_quality }`
  - `metrics`: coverage, issue counts, severities, etc.
  - `logs`: references to raw outputs
  - `overall`: boolean per REQ
- Optional raw logs in `runs/<runId>/logs/`

**Consumers**
- `/gate` (quality gating)
- VS Code Test Panel, CI dashboards

---

### 1.5 GATE Phase

**Inputs**
- `docs/harper/plan.json` (REQs, deps, status)
- `runs/<runId>/eval.summary.json`
- Per‑REQ `LTC.json` or Lane Guide (for thresholds)
- `TECH_CONSTRAINTS.yaml` (e.g., Sonar Quality Gate must be GREEN)

**LLM Responsibilities**
- Enforce **dependency sequencing** (DAG if available; otherwise sequential `REQ-(k-1)` → `REQ-k`)
- Apply **gate policy**: required checks must pass; thresholds honored; enterprise gates respected
- Propose **safe promotion** list; record rationale

**Outputs**
- `runs/<runId>/gate.decisions.json` — per‑REQ decision + reason
- Updated `docs/harper/plan.json` (status `done` where eligible)
- Snapshot appended in `docs/harper/PLAN.md` (“Gate Snapshot”)

**Consumers**
- `/finalize` (release notes, PR)
- CI/CD (promotion of code into `src/` and `tests/` in workspace root)

---

### 1.6 FINALIZE Phase

**Inputs**
- Final `docs/harper/plan.json` and `PLAN.md`
- Gate decisions
- Project metadata (branch, version, commits)

**LLM Responsibilities**
- Compose **release notes** and **PR description**
- Summarize completed REQs and key metrics

**Outputs**
- `docs/harper/RELEASE_NOTES.md`
- Git tag: `harper/finalize/<runId>`
- Optional PR text

**Consumers**
- Maintainers and pipelines (merge/release)

---

## 2) Lane Guides (project level)

**Path:** `docs/harper/lane-guides/<lane>.md`

**Purpose**
- Provide **standardized**, *re‑usable* testing/gating guidance per lane used in the repo.
- Act as **fallback** when REQ‑specific LTC/HOWTO are partially missing.

**Minimum contents**
- Tools per category: **tests**, **lint**, **types**, **security**, **build**
- CLI examples (local + container)
- **Expected report formats** (JUnit XML, JSON, SARIF…) and default paths
- **Default gate policy** (thresholds and severity rules)
- **Enterprise runner** notes (SonarQube, Jenkins/GitLab/Azure DevOps): how to trigger, where to fetch artifacts
- TECH_CONSTRAINTS integration: internal registries, air‑gap, tokens

---

## 3) REQ‑level Execution Artifacts

### 3.1 LLM Test Contract — `LTC.json`
- `lane`: selected lane (e.g., `python`, `java`, `iac/k8s/helm`, `mendix`, `plc/siemens`)
- `tools`: `{ tests, lint, types, security, build }` with tool names and versions if needed
- `commands`: explicit CLI (local and/or container) with placeholders for env/paths
- `reports`: list of `{ kind, path, format }` (e.g., `{kind:"junit", path:"…/junit.xml", format:"junit-xml"}`)
- `normalize`: mapping rules → **`eval.summary.json`** schema
- `gate_policy`: thresholds (e.g., coverage ≥ 70%, no `Critical` security issues)
- `external_runner` (optional): `{ system, job, url, artifact_paths }`
- `constraints_applied`: assumptions derived from TECH_CONSTRAINTS

### 3.2 Execution HOWTO — `HOWTO.md`
- Step‑by‑step **copy‑paste** commands (local/container)
- Runner enterprise section (how to trigger jobs; where to collect artifacts)
- Environment variables/tokens placeholders
- Troubleshooting tips and links to reports

---

## 4) Normalized Result Schemas

### 4.1 `eval.summary.json` (per runId)
```jsonc
{
  "runId": "eval-1728070212",
  "results": {
    "REQ-001": {
      "checks": {
        "tests": true,
        "lint": true,
        "types": true,
        "security": false,
        "build": true
      },
      "metrics": {
        "coverage_pct": 82.5,
        "lint_errors": 0,
        "vuln_critical": 1
      },
      "logs": {
        "junit": "runs/eval-.../logs/REQ-001/junit.xml",
        "linter": "…/eslint.txt"
      },
      "overall": false
    }
  }
}
```

### 4.2 `gate.decisions.json` (per runId)
```jsonc
{
  "runId": "gate-1728070450",
  "eligible": ["REQ-002", "REQ-003"],
  "decisions": {
    "promoted": [
      {"req": "REQ-002", "dst": "src/..."},
      {"req": "REQ-003", "dst": "tests/..."}
    ],
    "blocked": [
      {"req": "REQ-001", "reason": "security: Critical issues present"}
    ],
    "conflicts": [
      {"req": "REQ-003", "dst": "src/x.py", "backup": "runs/gate-.../backups/src/x.py"}
    ]
  }
}
```

---

## 5) Dependency Sequencing (DAG & Sequential Fallback)

- **Primary rule — DAG:** Honor the dependency graph from `plan.json`. A REQ can pass **only if all its prerequisites are `done`**.
- **Fallback — Sequential:** If no graph is present, enforce `REQ-(k-1)` → `REQ-k` order.
- **Gate enforcement:** `/gate` first checks **dependencies**, then **quality**. If either fails, **no promotion**.

---

## 6) TECH_CONSTRAINTS.yaml — How It Shapes Everything

- **Lane override:** force lane (`mendix`, `plc/siemens`, …) when auto‑discovery is ambiguous.
- **Execution rules:** require **enterprise runners** (e.g., Jenkins, SonarQube), internal container images, air‑gap operation.
- **Policy defaults:** minimum coverage, max severity, forbidden tools, standard report paths.
- **Security posture:** no internet, mirror registries, credential handling.

Prompts must instruct the LLM to **read and apply** TECH_CONSTRAINTS when generating Lane Guides, LTC, and HOWTO.

----

## 10) Glossary

- **Lane** — A technology track (e.g., Python, Java, JS/TS, IaC, Mendix, PLC).
- **Lane Guide** — Project‑level document that standardizes tools, report formats, and default quality thresholds for a lane.
- **LTC (LLM Test Contract)** — REQ‑level, machine‑oriented execution contract describing commands, reports, normalization, and thresholds.
- **HOWTO** — REQ‑level, human‑oriented operational recipe.
- **External Runner** — Enterprise system (SonarQube, Jenkins/GitLab, vendor tool) where tests/analysis actually run.
- **Normalization** — Mapping diverse tool outputs into a single, stable schema for `/eval` and `/gate`.
