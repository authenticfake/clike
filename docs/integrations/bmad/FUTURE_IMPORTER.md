# Future BMAD Artifact Importer

BMAD artifact import is a roadmap item. It is not implemented in the current integration.

## Future Goal

A future importer may read externally authored BMAD artifacts and translate them into CLike-governed Harper inputs.

Potential source artifacts:

- briefs
- personas
- PRDs
- architecture notes
- UX notes
- QA notes

Potential CLike targets:

- `docs/harper/IDEA.md`
- `docs/harper/SPEC.md`
- `docs/harper/PLAN.md`
- `docs/harper/plan.json`
- lane guides

## Governance Requirements

Any importer must:

- preserve CLike as the canonical artifact owner
- validate imported content before changing canonical docs
- avoid overwriting existing REQs without an explicit revise flow
- emit audit metadata
- keep human review in the loop
- avoid hard dependency on BMAD packages or CLIs

The importer must not call `npx bmad-method` implicitly.

