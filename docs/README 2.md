# CLike — Harper Playbook (Sprint A.1)

This package adds the Harper playbook (SPEC → PLAN → KIT) to CLike.

## What’s inside
- `docs/playbooks/PLAYBOOK.md` — master playbook
- `docs/playbooks/SPEC_PLAYBOOK.md`
- `docs/playbooks/PLAN_PLAYBOOK.md`
- `docs/playbooks/KIT_PLAYBOOK.md`
- `docs/playbooks/prompts/*.md` — system prompts per phase
- `IDEA.md`, `SPEC.md`, `PLAN.md`, `KIT.md` — ready-to-use templates
- `docs/playbooks/models.example.yaml` — routing profiles example
- `docs/playbooks/RAG_NOTES.md` — how to attach local knowledge

## How to integrate
1) Create a branch, e.g. `feat/harper-playbook-sprintA1`  
2) Copy this folder to your repo root.  
3) Commit and push.  
4) Wire the prompts into the orchestrator for each phase.  
5) In the VS Code extension, expose minimal commands (New SPEC, Generate PLAN, Build Next TODOs, Generate KIT).

## Conventions
- Documents are in English.
- Keep each step short and verifiable.
