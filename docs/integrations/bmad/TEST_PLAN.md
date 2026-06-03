# BMAD Test Plan

The BMAD integration is tested as methodology metadata and guidance, not as an execution backend. The tests should prove that CLike remains the governed runtime while BMAD enriches phase behavior.

## Local Commands

Run Python compilation for touched orchestrator and gateway modules:

```text
python -m compileall orchestrator gateway
```

Run targeted Python tests from the repository root:

```text
PYTHONPATH=orchestrator:. pytest -q orchestrator/tests/test_methodology_resolver.py
PYTHONPATH=orchestrator:. pytest -q orchestrator/tests/test_active_output_contract.py
PYTHONPATH=orchestrator:. pytest -q orchestrator/tests/test_methodology_injection.py
PYTHONPATH=orchestrator:. pytest -q orchestrator/tests/test_eval_canonical_bmad.py
PYTHONPATH=orchestrator:. pytest -q orchestrator/tests/test_bmad_companion_collector.py
PYTHONPATH=orchestrator:. pytest -q orchestrator/tests/test_bmad_safety_boundaries.py
PYTHONPATH=orchestrator:. pytest -q orchestrator/tests/test_bmad_quality_contracts.py
PYTHONPATH=orchestrator:. pytest -q orchestrator/tests/test_bmad_quality_scorecard.py
PYTHONPATH=orchestrator:. pytest -q gateway/tests/test_harper_canonical_artifact_validation.py
PYTHONPATH=orchestrator:. pytest -q gateway/tests/test_methodology_prompt.py
PYTHONPATH=orchestrator:. pytest -q gateway/tests/test_active_output_contract.py
```

Run the full orchestrator pytest suite:

```text
PYTHONPATH=orchestrator:. pytest -q orchestrator/tests
```

Run VS Code extension tests:

```text
node --test extensions/vscode/test/slash-parser.test.js extensions/vscode/test/bmad-advisory.test.js
node --test extensions/vscode/test/harper-write-guard.test.js
```

Run prompt-debug verification after a cloud BMAD run:

```text
rg -n "Active Output Contract|BMAD Companion Artifact Inventory|BMAD Companion Artifact Contract|BMAD Quality Contract|SPEC_UX_APPENDIX.md" .telemetry gateway/stub runs
rg -n "Active Output Contract|BMAD Companion Artifact Contract|docs/harper/bmad/idea/BRIEF.md|docs/harper/bmad/idea/PRFAQ_NOTES.md|docs/harper/bmad/idea/ASSUMPTIONS.md|docs/harper/bmad/idea/RESEARCH_QUESTIONS.md" telemetry/prompt_debug gateway/runs runs .clike
```

Run local-agent package verification after BMAD KIT and EVAL local-agent runs:

```text
rg -n "active_output_contract|methodology_context|companion_documents|discovered_companion_artifact_inventory|BMAD_DEV_STORY.md" runs/kit/*/docs/AGENT_EXECUTION_CONTEXT.json
rg -n "active_output_contract|methodology_context|companion_documents|BMAD_QA_ADVISORY.md|canonical_eval_owner|canonical EvalRunner remains authoritative" runs/kit/*/docs/AGENT_EVAL_CONTEXT.json runs/kit/*/docs/AGENT_EVAL_PROMPT.md
```

Run prompt conflict and contract greps:

```text
rg -n "Print EXCLUSIVELY one file block|Produce \\*\\*only\\*\\* the single|Produce only the single|No additional files" gateway/prompts gateway/utils orchestrator/services
rg -n "Active Output Contract|BMAD Companion Artifact Contract|required_outputs|allowed_optional_output_globs|forbidden_output_globs|missing_required_outputs" gateway orchestrator docs
rg -n "invalid_canonical_artifact|validateIdeaMarkdown|validateSpecMarkdown|validatePlanMarkdown|validatePlanJson|validateLaneGuideMarkdown" gateway orchestrator extensions
```

Run runtime forbidden-invocation grep checks from the repository root. This grep searches production code areas only and should return no matches:

```text
rg -n "npx\\s+bmad-method|bmad-method install|subprocess\\.(run|Popen).*bmad|os\\.system\\(.*bmad|child_process\\.(exec|spawn).*bmad" orchestrator gateway extensions --glob '!**/tests/**'
```

Run methodology/executor separation grep checks. These should not show BMAD role identity being routed through executor or profile-hint fields:

```text
rg -n "profileHint.*bmad|bmad.*profileHint|localAgentExecutor.*bmad|bmad.*localAgentExecutor" orchestrator gateway extensions --glob '!**/tests/**'
```

Run documentation policy grep checks. Matches are expected only when they describe future roadmap, out-of-scope behavior, or forbidden behavior:

```text
rg -n "BMAD runtime execution|npx bmad-method runtime invocation|BMAD importer|TEA|Party Mode|MCP write tools|automatic latest BMAD tracking" README.md docs/integrations/bmad
rg -n "MCP write tools|Party Mode|TEA|automatic latest" README.md docs
rg -n "Roun[d] [0-9]" README.md docs extensions/vscode
```

The runtime forbidden-invocation grep must not reveal BMAD CLI/runtime execution. Documentation matches are acceptable only in the documentation policy grep and only when they clearly describe out-of-scope or forbidden behavior. The final grep helps keep internal implementation-round wording out of user-facing docs.

## Manual VS Code Smoke Tests

Run these commands from the CLike chat UI in a test workspace:

```text
/idea --methodology bmad --agent analyst
/spec --methodology bmad --agent pm
/spec --methodology bmad --agent ux
/plan --methodology bmad --agent architect
/plan --methodology bmad --agent pm
/kit REQ-001 --methodology bmad --agent developer
/kit REQ-001 --repair --methodology bmad --agent developer
/eval REQ-001 --methodology bmad --agent qa
/eval REQ-001 --methodology bmad --agent developer
/finalize --methodology bmad --agent tech-writer
```

Also verify that `/gate REQ-001 --methodology bmad --agent qa` is rejected with a clear MVP gate ownership message.

Manual smoke matrix:

| Area | Command or artifact | Expected result |
| --- | --- | --- |
| Cloud BMAD prompt | `/plan --methodology bmad --agent architect` | `prompt_debug` contains governed methodology profile, companion artifact contract, companion artifact inventory, governance boundaries, downstream handoff, and quality contract sections |
| Active output contract | `/idea --methodology bmad --agent analyst` | `prompt_debug` contains `Active Output Contract`, `BMAD Companion Artifact Contract`, and every required IDEA companion path |
| Canonical validation | malformed cloud `docs/harper/IDEA.md` response | Gateway returns structured `ok=false` with `error_code=invalid_canonical_artifact`; `files` is empty; companion outputs appear only as `partial_files` or `diagnostic_files`; Orchestrator does not convert it to a 500 traceback; extension write guard preserves the existing canonical file and saves rejected content under `.clike/rejected/**` |
| SPEC PM | `/spec --methodology bmad --agent pm` | canonical `docs/harper/SPEC.md` may be produced; PM companion files stay under `docs/harper/bmad/spec/**` |
| SPEC UX | `/spec --methodology bmad --agent ux` | canonical `docs/harper/SPEC.md` is not produced by UX; UX files stay under `docs/harper/ux/**`, including `SPEC_UX_APPENDIX.md` when useful |
| KIT local agent | `/kit REQ-001 --methodology bmad --agent developer` with local-agent execution | `AGENT_EXECUTION_CONTEXT.json` includes methodology context, companion documents, discovered inventory when present, BMAD expected outputs, unchanged write roots, and forbidden paths |
| EVAL local agent | `/eval REQ-001 --methodology bmad --agent qa` with local-agent hardening | `AGENT_EVAL_CONTEXT.json` includes BMAD advisory targets and canonical EvalRunner authority warning |
| Gate | `/gate REQ-001 --methodology bmad --agent qa` | rejected before BMAD can enter gate authority |
| Scorecard | `PYTHONPATH=orchestrator:. pytest -q orchestrator/tests/test_bmad_quality_scorecard.py` | fixture BMAD IDEA scores higher than native fixture, without claiming live model quality |

## Parser Coverage

Parser tests should cover legacy slash parsing without methodology flags, both `--methodology bmad` and `--methodology=bmad`, both `--agent developer` and `--agent=developer`, `--agent` without `--methodology`, unsupported methodology, unsupported agent, invalid phase-to-agent mapping, KIT repair, KIT phases, and gate override rejection.

## Resolver Coverage

Resolver tests should cover default agent per phase, allowed explicit agents, eval advisory-only context, gate CLike-only context, invalid methodology errors, invalid agent errors, and enriched workflow metadata.

## Injection Coverage

Injection tests should prove that cloud runs receive methodology context only through Gateway prompt composition, local-agent packages receive methodology context through `local_agent_package`, methodology context is absent when omitted, allowed write roots are unchanged when BMAD is enabled, and forbidden paths are unchanged when BMAD is enabled.

## Canonical Artifact Validation Coverage

Canonical validation tests should prove that valid native and BMAD-enriched IDEA fixtures pass, raw-YAML-first IDEA fails, prompt-template leakage fails, unresolved placeholders fail, SPEC UX cannot overwrite canonical SPEC, PLAN without REQ IDs fails, invalid JSON is rejected for `plan.json`, and lane guides must include commands plus eval/gate expectations.

BMAD companion files are additive and are not validated as canonical IDEA/SPEC/PLAN documents. The canonical artifact for the phase must still pass the same structural validator as native Harper.

Validation failure handling tests should prove that `invalid_canonical_artifact` is returned as a structured Harper result, not Gateway 502 or Orchestrator 500; rejected canonical artifacts are removed from accepted files; `files` is empty when the required canonical output failed; safe companion files may be reported as `partial_files` or `diagnostic_files` but do not make the phase successful; rejected generated content is stored under controlled telemetry/debug paths; structured errors never render as `[object Object]`; and current invalid canonical artifacts are represented in prompt context as repair material rather than authoritative context.

## Eval And Gate Coverage

Eval and gate tests should prove that `/v1/eval/run` remains canonical through `EvalRunner.run_profile`, `/eval --methodology bmad --agent qa` still invokes canonical eval before advisory handling, BMAD advisory does not change eval status, pass/fail, or promotable fields, and gate cannot be overridden by BMAD flags.

## Non-Goals

The current test plan does not cover BMAD runtime execution, `npx bmad-method` runtime invocation, the BMAD importer, TEA, Party Mode, MCP write tools, multi-agent `/spec --agents pm,ux`, or automatic latest BMAD tracking at runtime because those features are not implemented.
