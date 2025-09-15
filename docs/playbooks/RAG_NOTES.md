# RAG Notes

- Typical include paths: `docs/`, `SPEC.md`, domain notes, API schemas, `README.md`.
- Keep context small and focused. Avoid dumping entire repositories.
- Prefer chunked retrieval with semantic filtering by phase:
  - SPEC phase: IDEA.md, prior business memos, KPIs.
  - PLAN phase: SPEC.md, architecture guidelines.
  - KIT phase: SPEC.md, PLAN.md (selected TODOs), API docs, code style guide.
