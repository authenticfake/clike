# Harper Playbook (Master)

This playbook operationalizes the Harper workflow **SPEC → PLAN → KIT** for AI‑native, eval‑driven development in CLike.

> Early design reference (2025): the phase prompts now live in `orchestrator/phases/<phase>/`, and run
> evidence under `runs/kit|eval|gate/<REQ>/`. The current process (IDEA → … → FINALIZE, `/idea --extend`)
> is documented in [../harper-workflow.md](../harper-workflow.md).

## Purpose & Scope
It defines:
- roles (Human Orchestrator, Orchestrator Service, LLMs)
- how to **write** and **read** each phase document
- the **prompts** injected to models
- baseline **routing** and **RAG** behavior
- minimal **audit** requirements

## Roles
- **Human Orchestrator**: sets intent, approves SPEC, curates PLAN, reviews KIT.
- **Orchestrator Service**: injects the right phase prompt, manages history scope, routing, RAG, persists runs.
- **LLMs (multiple)**: strictly follow phase rules (no jumping ahead).

## Folder & Naming
```
docs/
  playbooks/
    PLAYBOOK.md
    SPEC_PLAYBOOK.md
    PLAN_PLAYBOOK.md
    KIT_PLAYBOOK.md
    prompts/
      SPEC_WRITE.md
      SPEC_READ.md
      PLAN_WRITE.md
      PLAN_READ.md
      KIT_BUILD.md
      KIT_VERIFY.md
SPEC.md
PLAN.md
KIT.md
IDEA.md
runs/<timestamp>-<slug>/
  manifest.json
  diffs/
  artifacts/
  logs/
```

## Cross‑phase Principles
- **Outcome over code**: each step short and verifiable.
- **Phase boundaries**: SPEC ≠ design, PLAN ≠ code, KIT = build/validate.
- **RAG on demand**: use local/spec docs to ground answers.
- **History scope**: pass only what the phase needs (prevent drift).
- **Auditability**: each run writes `runs/<id>/manifest.json` (hashes, models, seed, prompts).

## Routing and RAG
See `docs/playbooks/models.example.yaml` and `docs/playbooks/RAG_NOTES.md`.
