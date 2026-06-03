# BMAD Verification Guide

This guide explains what to inspect after BMAD-aware runs. It verifies that BMAD methodology context was included where expected and that CLike governance boundaries remained intact. It does not prove live model quality or replace human review.

## Cloud Prompt Verification

Cloud Harper runs flow through Gateway:

```text
VS Code -> Orchestrator -> methodology resolver -> Gateway -> cloud LLM prompt
```

After a BMAD cloud run, inspect Gateway prompt-debug output. The exact path depends on the configured telemetry directory and run ID; search from the repository root:

```text
rg -n "BMAD Companion Artifact Inventory|BMAD Companion Artifact Contract|BMAD Quality Contract|Governed Methodology Profile" .telemetry gateway/stub runs
```

Expected prompt-debug markers for BMAD runs:

- `### Active Output Contract`
- `### Governed Methodology Profile`
- `### BMAD Companion Artifact Contract`
- `### BMAD Companion Artifact Inventory`
- `### BMAD Governance Boundaries`
- `### BMAD Downstream Handoff`
- `### BMAD Quality Contract` for SPEC or PLAN when quality contracts are present

Native Harper runs without `--methodology bmad` should not include BMAD prompt blocks.
They should still include the native `### Active Output Contract` when the cloud prompt route is used.

BMAD companion artifacts are not enough. A BMAD run must satisfy both checks:

- Active Output Contract path coverage for canonical and required companion outputs.
- Canonical Harper artifact structural validation for `docs/harper/IDEA.md`, `docs/harper/SPEC.md`, `docs/harper/PLAN.md`, `docs/harper/plan.json`, and `docs/harper/lane-guides/*.md`.

If canonical validation fails, Gateway reports a structured validation result, not an infrastructure failure:

```json
{
  "ok": false,
  "phase": "idea",
  "error_code": "invalid_canonical_artifact",
  "files": [],
  "partial_files": [
    {"path": "docs/harper/bmad/idea/BRIEF.md"}
  ],
  "text": "docs/harper/IDEA.md failed canonical validation and was not written."
}
```

The Orchestrator must pass this response through without converting it to a 500 traceback. The VS Code extension must show friendly validation diagnostics, not a Python stack trace. Companion artifacts do not make the phase successful when the required canonical artifact is invalid.

For any Harper response where `ok=false`, `error_code` is present, or `errors` is non-empty, the extension must not auto-write returned files. If Gateway exposes companion artifacts from a failed phase, they must appear only as `partial_files` or `diagnostic_files`, and the UI must label them as not applied. A failed `/idea` is not a partial BMAD success just because companion artifacts were generated.

For a fresh BMAD IDEA run, prompt debug should show all exact IDEA obligations:

```text
docs/harper/IDEA.md
docs/harper/bmad/idea/BRIEF.md
docs/harper/bmad/idea/PRFAQ_NOTES.md
docs/harper/bmad/idea/ASSUMPTIONS.md
docs/harper/bmad/idea/RESEARCH_QUESTIONS.md
```

Useful grep after a fresh run:

```text
rg -n "Active Output Contract|BMAD Companion Artifact Contract|docs/harper/bmad/idea/BRIEF.md|docs/harper/bmad/idea/PRFAQ_NOTES.md|docs/harper/bmad/idea/ASSUMPTIONS.md|docs/harper/bmad/idea/RESEARCH_QUESTIONS.md" telemetry/prompt_debug gateway/runs runs .clike
```

## Companion Artifact Inventory

Server-side discovery is orchestrator-owned. It scans controlled roots only:

- `docs/harper/bmad/**`
- `docs/harper/ux/**`
- `runs/kit/<REQ-ID>/docs/**` when a REQ is active

Verify discovered inventory in cloud payloads or prompt debug by looking for:

```text
BMAD Companion Artifact Inventory
companion::docs/harper/bmad
companion::docs/harper/ux
companion::runs/kit/<REQ-ID>/docs
```

The inventory should contain bounded snippets, size, SHA-256, truncation status, and source group. It must not include arbitrary client-controlled paths outside the controlled roots.

## Local-Agent KIT Verification

For BMAD KIT local-agent execution, inspect:

```text
runs/kit/<REQ-ID>/docs/AGENT_EXECUTION_CONTEXT.json
runs/kit/<REQ-ID>/docs/AGENT_PROMPT.md
```

Expected `AGENT_EXECUTION_CONTEXT.json` markers:

- `active_output_contract`
- `methodology_context`
- `discovered_companion_artifact_inventory` when server-discovered companion artifacts exist
- `companion_documents.bmad`
- `companion_documents.ux`
- `source_documents.idea`
- `source_documents.spec`
- `source_documents.plan`
- `source_documents.plan_json`
- `source_documents.tech_constraints`
- `expected_outputs.bmad.mandatory_companion_outputs`
- `allowed_write_roots`
- `forbidden_paths`

Expected BMAD KIT companion output targets include:

- `runs/kit/<REQ-ID>/docs/BMAD_DEV_STORY.md`
- `runs/kit/<REQ-ID>/docs/IMPLEMENTATION_NOTES.md`
- `runs/kit/<REQ-ID>/docs/SELF_REVIEW.md`
- `runs/kit/<REQ-ID>/docs/RUNBOOK.md`

Useful grep:

```text
rg -n "active_output_contract|methodology_context|companion_documents|discovered_companion_artifact_inventory|BMAD_DEV_STORY.md|allowed_write_roots|forbidden_paths" runs/kit/<REQ-ID>/docs/AGENT_EXECUTION_CONTEXT.json
```

The allowed write roots should remain candidate roots under `runs/kit/<REQ-ID>/...`. BMAD must not add canonical `src`, `test`, `tests`, `docs/harper/PLAN.md`, or `docs/harper/plan.json` to writable roots.

## Canonical Write Guard Verification

The VS Code extension has a defense-in-depth guard before writing canonical Harper files. If malformed canonical content reaches the extension, the existing canonical artifact must not be overwritten. Rejected content is saved only under:

```text
.clike/rejected/harper/<phase>/<runId>/<safe-file-name>.invalid.md
```

Useful grep after a rejected run:

```text
rg -n "invalid_canonical_artifact|BEGIN_FILE|END_FILE|Print EXCLUSIVELY|Produce only the single|<Project Name>|My Solution Name|my-project-key" .clike/rejected
```

The rejected folder is diagnostic only. It is not canonical Harper state and must not be consumed as authoritative downstream context.

Structured errors must be rendered as readable diagnostics. The UI should never show JavaScript fallback text such as `Error: [object Object]`; it should show the error code, rejected path, failed checks, and debug path when available.

Gateway also stores rejected generated canonical candidates under the configured telemetry/debug root:

```text
telemetry/rejected/<project_id>/<runId>/<phase>/<safe-file-name>.invalid.md
```

Structured rejection objects include `debug_path` or `rejected_artifact_ref` when debug storage succeeds. These paths are for troubleshooting and repair only; they are not Harper canonical artifacts.

If an existing canonical artifact is already malformed, Gateway must not present it as authoritative prompt context. Prompt debug should instead contain:

```text
Current Canonical Artifact Validation
current_canonical_invalid: true
The current canonical artifact must not be imitated structurally.
Generate a valid replacement that follows the canonical Harper schema.
```

A valid generated canonical artifact may repair an invalid current canonical artifact. The candidate still has to pass canonical structural validation before it is written.

## Local-Agent EVAL Verification

For BMAD EVAL local-agent execution, inspect:

```text
runs/kit/<REQ-ID>/docs/AGENT_EVAL_CONTEXT.json
runs/kit/<REQ-ID>/docs/AGENT_EVAL_PROMPT.md
```

Expected `AGENT_EVAL_CONTEXT.json` markers:

- `active_output_contract`
- `methodology_context`
- `companion_documents`
- `previous_eval_reports`
- `repair_intent`
- `bmad_developer_docs`
- `bmad_qa_advisory_output_targets`
- `local_repair_policy`
- `allowed_write_roots`
- `forbidden_paths`

Expected BMAD QA advisory targets include:

- `runs/kit/<REQ-ID>/docs/BMAD_QA_ADVISORY.md`
- `runs/kit/<REQ-ID>/docs/FIX_GUIDANCE.md`
- `runs/kit/<REQ-ID>/docs/MISSING_TESTS.md`
- `runs/kit/<REQ-ID>/docs/RISK_REVIEW.md`

Expected prompt markers:

- `canonical EvalRunner remains authoritative`
- `Never mutate canonical eval verdict fields`
- `never decide pass/fail`
- `allowed_write_roots`
- `forbidden_paths`

Useful grep:

```text
rg -n "active_output_contract|BMAD_QA_ADVISORY.md|canonical EvalRunner remains authoritative|Never mutate canonical eval verdict fields|never decide pass/fail|allowed_write_roots|forbidden_paths" runs/kit/<REQ-ID>/docs/AGENT_EVAL_CONTEXT.json runs/kit/<REQ-ID>/docs/AGENT_EVAL_PROMPT.md
```

## SPEC PM And UX Verification

For `/spec --methodology bmad --agent pm`, verify that canonical `docs/harper/SPEC.md` may be produced by normal SPEC governance and PM companion artifacts stay under:

```text
docs/harper/bmad/spec/**
```

For `/spec --methodology bmad --agent ux`, verify that UX is companion-only:

```text
docs/harper/ux/DESIGN.md
docs/harper/ux/EXPERIENCE.md
docs/harper/ux/USER_JOURNEYS.md
docs/harper/ux/INTERACTION_STATES.md
docs/harper/ux/SPEC_UX_APPENDIX.md
```

UX must not overwrite `docs/harper/SPEC.md`. Gateway cloud output validation drops forbidden SPEC output for BMAD SPEC UX runs.

## Eval And Gate Verification

Canonical eval remains:

```text
handleEval -> /v1/eval/run -> EvalRunner.run_profile
```

BMAD QA advisory can be attached only after canonical eval completes. It must not mutate `status`, `passed`, `failed`, `promotable`, `blocking_failures`, or gate-related fields.

Gate remains CLike-owned. Verify that this command is rejected in the current MVP:

```text
/gate REQ-001 --methodology bmad --agent qa
```

## Scorecard Verification

Run the deterministic scorecard tests:

```text
PYTHONPATH=orchestrator:. pytest -q orchestrator/tests/test_bmad_quality_contracts.py
PYTHONPATH=orchestrator:. pytest -q orchestrator/tests/test_bmad_quality_scorecard.py
```

The IDEA fixture scorecard should show that the BMAD experimental fixture scores higher than the native fixture. This proves evaluator sensitivity for fixed fixtures only. It does not prove live model quality and it does not replace human review.

## Safety Grep Verification

Run the runtime forbidden-invocation grep against production code areas only. It should return no matches:

```text
rg -n "npx\\s+bmad-method|bmad-method install|subprocess\\.(run|Popen).*bmad|os\\.system\\(.*bmad|child_process\\.(exec|spawn).*bmad" orchestrator gateway extensions --glob '!**/tests/**'
```

Run documentation policy grep separately. Matches are expected only when they describe future roadmap, out-of-scope behavior, or forbidden behavior:

```text
rg -n "BMAD runtime execution|npx bmad-method runtime invocation|BMAD importer|TEA|Party Mode|MCP write tools|automatic latest BMAD tracking" README.md docs/integrations/bmad
```

This split keeps runtime safety checks strict while allowing user-facing documentation to explain what is not implemented.

## Future Roadmap Boundaries

The following are out of scope for current verification because they are not current behavior:

- BMAD runtime execution
- `npx bmad-method` runtime invocation
- BMAD importer
- TEA
- Party Mode
- MCP write tools
- multi-agent `/spec --agents pm,ux`
- automatic latest BMAD tracking at runtime
