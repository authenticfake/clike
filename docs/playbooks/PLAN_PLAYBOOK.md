# PLAN_PLAYBOOK

## Purpose
Translate SPEC into a **structured backlog** of small, verifiable TODOs (≤ 2h).

## Instructions for Writing `PLAN.md`
1. **Granularity** – each TODO ≤ 2h, atomic, testable.
2. **Priority** – rank by value/urgency; tag `P1|P2|P3`.
3. **Dependencies** – list blocking IDs.
4. **Status** – `pending|in_progress|done`.
5. **Notes** – acceptance hints (what “done” looks like).
6. **Format** – Markdown table (or CSV/JSON mirror) in repo.
7. **Source** – derive only from `SPEC.md`.

## Instructions for Reading (LLMs)
- Consider only `pending` tasks unless told otherwise.
- When asked to “Build Next N”, pick by priority and dependency readiness.
- Never emit code in PLAN; only update structured tasks & statuses.

## System Prompts
- Write: see `prompts/PLAN_WRITE.md`
- Read:  see `prompts/PLAN_READ.md`

## Definition of Done
- `PLAN.md` exists with prioritized, dependency‑aware TODOs; **no code**.
- Status updates reflect progress; remains the single execution source.

## Template (ready to paste)
```markdown
# PLAN

| ID  | Description                               | Priority | Status      | Dependencies | Notes |
|-----|-------------------------------------------|----------|-------------|--------------|-------|
| T01 |                                           | P1       | pending     |              |       |
| T02 |                                           | P2       | pending     | T01          |       |
| T03 |                                           | P3       | pending     |              |       |

**Status Legend**: pending | in_progress | done
**Rule**: each TODO ≤ 2h; atomic; verifiable.
```
