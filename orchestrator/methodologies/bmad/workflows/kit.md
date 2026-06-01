# BMAD-Aware KIT Workflow

CLike-owned compact workflow guidance. Build candidate-first artifacts only.

- Implement exactly the current REQ from PLAN and `TARGET_CONTRACT.json`.
- Read TECH_CONSTRAINTS, SPEC, PLAN, plan.json, dependency KITs, and promoted roots as evidence.
- Write only candidate files under `runs/kit/<REQ-ID>/src`, `test`, `ci`, and `docs`.
- Produce source, tests, LTC, HOWTO, and required FILE_REQUIREMENTS outputs.
- Do not promote, mutate canonical source/tests, or expand write permissions.
- When repair is requested, focus on failed checks without broad rewrites.
