# KIT_PLAYBOOK

## Purpose
Deliver **working artifacts** (code, tests, README, requirements) that satisfy SPEC via tasks in PLAN.

## Instructions for Writing `KIT.md`
1. **Deliverables** – list folders/files to be produced.
2. **How to Run** – commands to install and run.
3. **How to Test/Validate** – commands for linting, typing, unit tests, coverage.
4. **Rollout Checklist** – docs complete, sample data, CI status, license/NOTICE.
5. **Format** – clear Markdown; no hidden steps.

## Instructions for Reading (LLMs)
- Follow `KIT.md` commands exactly for build/test.
- Only implement tasks from PLAN marked `selected for build` (human/orchestrator chosen).
- Align artifacts with SPEC constraints.

## System Prompts
- Verify: see `prompts/KIT_VERIFY.md`

## Definition of Done
- `KIT.md` defines deliverables & validation clearly.
- Artifacts (code/tests/docs) exist and pass validation locally.
- Everything reproducible in `runs/<id>/artifacts/`.

## Template (ready to paste)
```markdown
# KIT

## Deliverables
- `src/` – production code
- `tests/` – unit tests (pytest)
- `README.md` – quickstart
- `requirements.txt` – tooling & deps

## How to Run
\`\`\`bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
export PYTHONPATH=src
\`\`\`

## How to Test & Validate
\`\`\`bash
ruff check .
ruff format .
mypy src
pytest -q
pytest --cov=src --cov-report=term-missing
\`\`\`

## Rollout Checklist
- [ ] README includes usage & troubleshooting
- [ ] Lint/type/test PASS locally
- [ ] Example data (if needed)
- [ ] CI workflow configured
- [ ] License/NOTICE updated
```
