Andiamo **a fasi** (iterativo-incrementale), così restiamo veloci, verificabili e con governance chiara. Di seguito il **percorso operativo** — niente codice finché non me lo chiedi tu; documenti e commenti **in inglese**, chat **in italiano**.

# Piano a fasi (Harper + Vibe, allineato ai sorgenti esistenti)

## ✅ Sprint 0 — Foundation (contratti & doc)

**Obiettivo:** zero ambiguità prima di toccare codice.
**Deliverable (EN):**

* `docs/API.md` (riassunto) + **OpenAPI 3.1** per `/v1/*`.
* `docs/HARPER_GUIDE.md` (IDEA→SPEC→PLAN→KIT + HITL).
* `docs/RAG_GUIDE.md` (index, search, citations, evals).
* `docs/GOVERNANCE.md` (strict/advisory, gates, audit, CI).
  **Exit criteria:** contratti JSON “freeze”, esempi request/response, flow E2E disegnato.

## 🌀 Sprint 1 — Chat 3 modalità (Q\&A / Harper / Coding)

**Backend:**

* Orchestrator: `/v1/models`, `/v1/chat (free)`, `/v1/generate (harper|coding)`, `/v1/apply`.
  **Client (VS Code):**
* Chat Panel con **model picker** e toggle **Q\&A / Harper / Coding**.
* Modale **PROMPT** (artifact, targets, evals, constraints, stage).
* Preview **Diff | Files | Evals | Sources** + **Apply/Open PR/Discard**.
  **Exit criteria:** da PROMPT a diff preview → Apply su branch → PR opzionale.

## 🧭 Sprint 2 — Harper Panel & Gates

**Backend:**

* `/v1/harper/status`, `/v1/harper/approve|reject`, persistenza `.clike/state.json`.
  **Client:**
* **Harper Panel** con stati **IDEA ▸ SPEC ▸ PLAN ▸ KIT** + badge **Pending/Approved/Rejected**.
* Blocchi UI coerenti con `strict`.
  **Exit criteria:** avanzamento stage solo dopo **HITL** e policy rispettate.

## 📚 Sprint 3 — RAG v1 (grounding esteso)

**Backend:**

* `/v1/rag/index` (per branch/paths), `/v1/rag/search` (citations obbligatorie).
* Indicizzazione repo (SPEC/PLAN/KIT/src/docs) + hybrid retrieval (BM25+vectors).
  **Client:**
* Toggle “Use RAG”, visualizzazione **Sources** nelle risposte.
  **Exit criteria:** risposte con citazioni; reindex manuale da UI.

## 🔒 Sprint 4 — Git & CI (governance)

**Repo artifacts:**

* Branch strategy Harper `clike/spec|plan|kit/*`, Coding `clike/fix/*`.
* PR templates (SPEC/PLAN/KIT) con slot **eval report** e **audit\_id**.
* Workflow CI esempio (lint/unit; ganci SAST/DAST/UAT).
  **Exit criteria:** PR bloccate in `strict` se eval KO; audit tracciato.

## ⚙️ Sprint 5 — Coding mode avanzato

* Contesto editor: `active_file` + `selection` in `/v1/generate (coding)`.
* Quick eval locale (lint/mini-unit) opzionale; in `strict` push su `clike/fix/*`.
  **Exit criteria:** patch veloci e sicure dal file corrente.

## 🛡️ Sprint 6 — Hardening & Telemetry

* Rate limit, timeouts, idempotency.
* Telemetria eventi (create prompt, preview diff, apply, eval pass/fail).
* Error model unificato.
  **Exit criteria:** stabilità e osservabilità pronte per pilota.

## 🔌 Sprint 7 — MCP (fase pragmatica)

* Adapter MCP sopra **Tool API** interna (Git, Tests, RAG).
  **Exit criteria:** tools standardizzabili senza toccare il client.

