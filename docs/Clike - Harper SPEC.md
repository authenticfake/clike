#Come **rendiamo i modelli consapevoli** del processo (istruzioni & ruoli)

L’**Orchestrator** a runtime costruisce i prompt diversificati **per provider** ma a partire da **istruzioni standard**, così:

## 1) Preambolo di processo (comune a tutti)

* Contenuto in `PROMPTS/00_process_preamble.md` (generato da `/init`):

  * **Scopo** del ciclo Harper (outcome, non solo codice)
  * **Vincoli** (SLA, privacy/redaction, budget, policy org)
  * **Artifact contract** (formati attesi per SPEC/PLAN/KIT)
  * **Eval hooks** (cosa verrà verificato dai gate)
  * **Stile** (Markdown, sezioni, tabella backlog, “no extra chatter”)

## 2) Role Cards per fase

* In `PROMPTS/rolecards/` creiamo **carte ruolo** che definiscono *persona* e *regole* per ciascuna fase:

  * **Architect (SPEC)**: estrarre contesto, vincoli, metriche; generare SPEC con sezioni fisse; niente code.
  * **Planner (PLAN)**: backlog tabellare con ID, priorità, dipendenze, exit criteria; no arch rewrite.
  * **Builder (KIT)**: deliverables, runbook, test/validate; stub scripts solo dove richiesto.
  * **Implementer (BUILD)**: patch/diff minimali, spiegazione breve, test aggiornati.
* Per **efficienza**: i role cards includono **rubriche di autovalutazione** (“prima di rispondere, verifica di avere…”) in stile eval-driven.

## 3) Istruzioni per transizione di fase

* **IDEA→SPEC**:

  * input: `IDEA.md` (redacted se cloud), preambolo, role card Architect
  * output: `SPEC.md` con sezioni obbligatorie + “Open issues”
* **SPEC→PLAN**:

  * input: SPEC validato (o ultima bozza), preambolo, role card Planner
  * output: `PLAN.md` tabellare + TODO IDs + acceptance criteria per ogni item
* **PLAN→KIT**:

  * input: PLAN + SPEC, preambolo, role card Builder
  * output: `KIT.md` con “Deliverables / How to Run / How to Test”
* **KIT→BUILD (iterativo)**:

  * input: PLAN + contesto file (diff-aware), role card Implementer
  * output: patch/diff + aggiornamento test + mini-changelog

## 4) Consapevolezza cross-modello (GPT/Claude/DeepSeek/Ollama)

* Il **Gateway** traduce le nostre istruzioni standard nel formato richiesto dal provider (es. `system` per OpenAI, `system`/`assistant` per Anthropic, ecc.).
* **Routing** seleziona il modello **pinnato** per profilo (es. `plan.fast` → `gpt-4o-mini`, `code.strict` → `gpt-5-thinking`, `local.codegen` → `llama3`).
* **Redaction** applicata **prima** della chiamata se il provider è cloud e il toggle è attivo.
* **History scope**: per ragioni di efficienza, si passa **solo il contesto minimo** (preambolo + file di fase + estratti RAG dei file correlati); la **storia completa** non viaggia tra modelli diversi, ma è recuperata on-demand via RAG.

## 5) Ruoli specifici e prompt “a pacchetto”

* A **/init**, oltre ai file MD, depositiamo un **kit di prompt** (preambolo + role cards + scheletro per fase).
* Ad ogni comando fase, l’Orchestrator compone:
  `PROCESS_PREAMBLE + ROLE_CARD(phase) + CONSTRAINTS(env/redaction) + CONTEXT(files) + TASK(“produce SPEC.md con sez. …”) + RUBRIC(checklist)`
* Questo rende **ripetibile e coerente** l’output tra modelli e sessioni.

---

# F) Politiche di efficienza e qualità

* **Routing deterministico** con `model` pin-nato per profilo (e `strict: true` dove serve compliance).
* **Policy soft** (preferenze frontier/local) solo dove non c’è `strict`.
* **Temperatura bassa** per fasi doc (0.1–0.2), più alta solo per brainstorming in Free mode.
* **Stop conditions** chiare (“produce solo il file; niente extra”).
* **RAG**: minima quantità di contesto mirato (no dump repo).
* **Autovalutazione** nel prompt (rubric), allineata ai **gate** EVAL.

