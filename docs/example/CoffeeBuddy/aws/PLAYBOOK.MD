
---

## `docs/harper/PLAYBOOK.md`
```markdown
# Harper PLAYBOOK — CoffeeBuddy

## Phases

1) **SPEC** from IDEA (iterate until approved)  
2) **PLAN** from SPEC (traceability 100%, test hooks ready)  
3) **KIT** implement REQs in short cycles (code + tests + docs)  
4) **Finalize** package + SBOM + license checks

## Commands (chat)
/init CoffeeBuddy [path] — scaffold project  
/idea - generate an IDEA well formed
/spec — generate SPEC from IDEA & context  
/plan — generate PLAN from SPEC  
/kit — scaffold + incremental build cycles  

### Evals & Gates
/eval `<req-id>` — run eval profile for REQ-ID
/gate `<req-id>` — enforce gates  for REQ-ID

## Expectations
- SPEC has all sections, KPIs include a **measurement** statement, and **Technology Constraints** are defined.  
- PLAN declares **Coverage: 100%** and includes hooks for Unit/Functional/Integration/Security/UAT and Environment Profiles.  
- KIT runs lint/type/tests/security based on constraints and capabilities.  
- PRs require green checks (SPEC/PLAN/KIT Gates) before merging.

## Quick checklist before `/kit`
- SPEC approved.
- PLAN approved with traceability and hooks.  
- Local dev env configured (env vars, secrets manager, DB).
