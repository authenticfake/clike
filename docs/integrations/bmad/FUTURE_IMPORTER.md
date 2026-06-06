# Future BMAD Artifact Importer

BMAD artifact import is a roadmap item. It is not implemented in the current integration.

The future goal is to let teams bring externally authored BMAD-style artifacts into CLike without making BMAD a runtime dependency and without allowing imported files to bypass Harper governance. The importer would translate source material into controlled Harper artifacts, preserve provenance, and leave CLike in charge of validation, eval, gate, and promotion.

## Future Input Examples

A future importer may discover files such as:

- `_bmad-output/prd.md`
- `_bmad-output/architecture.md`
- `_bmad-output/stories/*.md`
- `_bmad-output/epics/*.md`
- `_bmad-output/decision-log.md`
- `_bmad-output/**/SPEC.md`
- `_bmad-output/**/DESIGN.md`
- `_bmad-output/**/EXPERIENCE.md`

These examples are input conventions only. The current MVP does not scan, parse, or import them.

## Future Output Examples

A future importer may write controlled Harper outputs such as:

- `docs/harper/IDEA.md`
- `docs/harper/SPEC.md`
- `docs/harper/PLAN.md`
- `docs/harper/plan.json`
- `docs/harper/ux/DESIGN.md`
- `docs/harper/ux/EXPERIENCE.md`
- `docs/harper/imports/bmad/import.report.json`
- `docs/harper/imports/bmad/IMPORT_BMAD_<timestamp>.md`

Writes must stay inside controlled Harper roots. The importer must not write directly to canonical source, canonical tests, runs, Git state, or promotion outputs.

## Expected Import Behavior

A future importer should perform artifact discovery in a bounded source root, classify known files, and report unknown material. It should support dry-run mode so users can preview mapped sections, proposed canonical changes, warnings, and conflicts before anything is written.

Import should be idempotent. Running the same import twice should not duplicate REQs, stories, UX sections, or decision records. Existing Harper docs must be treated as first-class inputs, and imported material must be reconciled with current `IDEA.md`, `SPEC.md`, `PLAN.md`, and `plan.json` rather than blindly replacing them.

Source provenance is required. Imported sections should retain enough metadata to identify source file, source heading or story, timestamp, importer version, and mapping decisions. The import report should explain what was mapped, what was skipped, what was ambiguous, and what requires human review.

No overwrite should occur without explicit force or a governed revise flow. Unmapped sections should produce warnings. Story-to-REQ mapping should preserve traceability from source stories or epics into CLike REQ IDs and dependencies.

The importer must not directly promote artifacts. Imported content must still pass through normal Harper phases, canonical eval, gate, telemetry, audit, and promotion policy.

## Non-Goals For Current MVP

The current MVP does not invoke the official BMAD package-runner command, does not load BMAD runtime packages, does not vendor BMAD code, and does not implement an importer.
