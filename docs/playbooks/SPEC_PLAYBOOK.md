# SPEC_PLAYBOOK

## Purpose
Define **intent**, **constraints**, **non‑goals**, and **success metrics**. No code.

## Instructions for Writing `SPEC.md`
1. **Business Context** – problem/opportunity & stakeholders.
2. **Goals & Outcomes** – business outcomes (not features).
3. **Constraints** – budget, time, compliance, strategic boundaries.
4. **Non‑Goals** – explicitly out of scope.
5. **Success Metrics** – KPIs with targets and horizon.
6. **Assumptions & Risks** – known risks and unknowns.
7. **Format** – Markdown, concise, no code or design.

## Instructions for Reading (LLMs)
- Extract **intent, constraints, metrics**; do **not** propose implementation.
- Treat SPEC as the **scope authority** for subsequent phases.
- If unclear, ask for clarification (don’t assume).

## System Prompts
- Write: see `prompts/SPEC_WRITE.md`
- Read:  see `prompts/SPEC_READ.md`

## Definition of Done
- `SPEC.md` contains all required sections; **no code**.
- Approved by human; becomes the single source of truth for scope.

## Template (ready to paste)
```markdown
# SPEC

## 1) Business Context
- Problem / opportunity:
- Stakeholders:

## 2) Goals & Outcomes
- Primary outcomes:
- Secondary outcomes:

## 3) Constraints
- Budget:
- Timeline:
- Compliance/Policy:
- Strategic boundaries:

## 4) Non-Goals
- Explicitly out of scope:

## 5) Success Metrics
- KPIs & targets:
- Measurement plan:

## 6) Assumptions & Risks
- Known assumptions:
- Key risks & mitigations:
```
