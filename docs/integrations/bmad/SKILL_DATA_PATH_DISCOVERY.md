# BMAD Skill and CLike Capability Data Path Discovery

This report maps how CLike-selected capabilities and BMAD methodology skills move through the VS Code extension, Orchestrator, Gateway cloud prompts, and local-agent packages. The current implementation carries both guidance systems through an Orchestrator-owned `context_envelope` while preserving CLike governance.

## Executive Summary

CLike has two independent guidance streams that can reach Harper execution:

- CLike selected capabilities come from workspace material under `.clike/packs/**`, `.clike/skills/**`, and `.clike/design-profiles/**`. They are discovered by the Orchestrator and rendered as `CLIKE_CAPABILITY_MANIFEST.md`, `CLIKE_CAPABILITY_INDEX.json`, and, for target REQ flows such as KIT, `CLIKE_SELECTED_CAPABILITY_CONTEXT.md` and `CLIKE_SELECTED_CAPABILITY_CONTEXT.json`.
- BMAD methodology skills come from CLike-owned vendor mappings under `.clike/skills/vendor/bmad/**`. They are selected by `methodology`, `phase`, and `agent` through `.clike/skills/vendor/bmad/manifest.json`; the extension transports the manifest and selected `SKILL.md` files through `core_blobs` for cloud and local-agent paths.

The Orchestrator is the trust boundary. It discards client-supplied `methodology_context`, resolves methodology context server-side from top-level `methodology` and `agent`, then forwards the resolved context to Gateway or local-agent packaging. When top-level `methodology=bmad` and the phase/agent pair is supported, selected BMAD skills are present in the resolved context.

Resolver tests confirm the expected selections, including `kit/developer -> dev-story-execution, story-readiness`. Gateway prompt debug receives structured `selected_skill_references` and `context_envelope` when the request passes through Orchestrator. The Orchestrator now rehydrates compact or stale BMAD contexts from the manifest before building the context envelope or local-agent package, so `methodology_context.selected_skill_references`, `context_envelope.bmad_methodology_skills.selected_skill_references`, and top-level local-agent `selected_skill_references` stay aligned.

The previous cloud KIT gap for selected CLike capabilities has been closed. Orchestrator creates `CLIKE_SELECTED_CAPABILITY_CONTEXT.*` for KIT after deriving `TARGET_CONTRACT.json` and `FILE_REQUIREMENTS.json`; Gateway now preserves those blobs through the KIT prompt filter and renders `### CLike Selected Capability Context` alongside `### BMAD Skill Reference Context` when both are present.

## Data Types

### CLike Selected Capabilities

CLike capability material is project-owned workspace input:

- `.clike/packs/**`
- `.clike/skills/**` excluding `.clike/skills/vendor/bmad/**`
- `.clike/design-profiles/**`
- `docs/harper/design*/**` for design profiles when present

The VS Code extension transports project-visible CLike capability files through `core_blobs` for Harper requests. That makes the cloud path independent of a mounted target workspace. The Orchestrator still prefers mounted workspace discovery when repository context is available, but it can now build the same capability inventory from `.clike/**` blobs:

- `build_capability_context(repository_context, core_blobs=...)` reads workspace capability material when available and otherwise indexes transported `.clike` capability blobs.
- `build_selected_capability_context(core_blobs, target_req_id, target_contract)` resolves the target REQ's selected `packs`, `skills`, and `design_profiles` against the capability index and creates `CLIKE_SELECTED_CAPABILITY_CONTEXT.md` plus `CLIKE_SELECTED_CAPABILITY_CONTEXT.json`.

Selected capability context is target-specific. It is expected for `/kit REQ-...` and downstream target-REQ local-agent work. It is not automatically available for `/idea`, `/spec`, or `/plan` because those phases do not have a target REQ unless a future project-level selection mechanism is introduced.

### BMAD Methodology Skills

BMAD skills are methodology guidance, not executable runtime behavior:

- Runtime selection source: `.clike/skills/vendor/bmad/manifest.json`
- Runtime mappings: `.clike/skills/vendor/bmad/**/SKILL.md`
- Vendor reference seed: `extensions/vscode/templates/harper-init/.clike/skills/vendor/bmad/**`
- Workspace vendor reference after init: `<workspace>/.clike/skills/vendor/bmad/**`

The selected skill context is built in `orchestrator/services/methodologies/bmad_skill_loader.py`. Runtime resolution loads the vendor manifest and selected `SKILL.md` files from request `core_blobs`, returns bounded snippets and summaries, and never executes external commands, imports BMAD runtime content, calls `npx bmad-method`, or fetches network resources. The vendor manifest remains the selection source of truth; Python code must not duplicate the phase/agent skill map.

## Manifest-Driven Propagation Invariant

For every `phase/agent` key declared in `manifest.json.skill_selection`, a BMAD run must carry the same selected skill identifiers through these fields:

- `methodology_context.selected_skill_references`
- `context_envelope.bmad_methodology_skills.selected_skill_references`
- local-agent top-level `selected_skill_references` when the phase uses a local package
- cloud prompt/debug `selected_skill_references` when the phase uses Gateway prompt rendering

If a compact BMAD context reaches local-agent packaging with empty skill fields, the Orchestrator rehydrates it from `manifest.json` before writing `AGENT_*_CONTEXT.json`. This is a defensive consistency guard, not a second source of truth.

## Cloud Path

```text
VS Code slash command
  -> slash-parser preserves methodology and agent
  -> extension harperRun payload includes methodology and agent
  -> Orchestrator run_phase()
     -> removes client-supplied methodology_context
     -> resolve_methodology_context(phase, methodology, agent)
     -> build_capability_context(repository_context, core_blobs)
     -> for KIT: derive TARGET_CONTRACT and FILE_REQUIREMENTS
     -> for KIT: build_selected_capability_context(...)
     -> build context_envelope
     -> forward resolved methodology_context, context_envelope, and core_blobs
  -> Gateway /v1/harper/run
     -> build_active_output_contract(...)
     -> render_methodology_context_for_cloud_prompt(...)
     -> _compose_system_messages(...)
     -> prompt_debug/provider request
```

### Confirmed Cloud Methodology Behavior

`gateway/utils/methodology_prompt.py` renders `### BMAD Skill Reference Context` when `methodology_context.methodology == "bmad"` and `selected_skill_references` is non-empty. The section includes selected skill IDs, normalized mapping paths, bounded snippets, required outputs, companion outputs, quality checks, forbidden behavior, and governance boundaries.

Gateway prompt debug now records structured methodology evidence when it receives resolved context:

- `methodology_context.selected_skill_references`
- `methodology_context.selected_skill_context`
- `methodology_context.skill_reference_policy`
- top-level `selected_skill_references`

### Cloud Rendering

The KIT cloud prompt path preserves the selected capability blobs in `gateway/routes/harper.py::_filter_core_blobs_for_kit(...)`. `_build_kit_user_message(...)` renders:

- `### CLike Selected Capability Context`
- `### BMAD Skill Reference Context` through the methodology renderer
- `## Namespace Materialization` when FILE_REQUIREMENTS carries Python namespace guidance

When a KIT target declares CLike packs, skills, or design profiles, `run_phase()` treats an empty selected capability branch as a blocking context error. The diagnostic is `CLIKE_SELECTED_CAPABILITIES_MISSING` and includes the declared capability IDs, available capability names, whether the index was present, and whether selected context was present.

An empty BMAD skill context in a Gateway debug dump has a narrow meaning: Gateway received `methodology_context` with `methodology=bmad` but without selected skill references. Normal Orchestrator traffic should not produce that shape because `run_phase()` resolves context server-side and `context_envelope` rehydrates stale compact contexts from the manifest. A remaining empty cloud prompt points to a direct Gateway request, a request that bypassed Orchestrator's resolver, or missing top-level `methodology` and `agent`.

## Local-Agent Path

```text
VS Code slash command
  -> extension request includes methodology, agent, executionPreference
  -> Orchestrator run_phase()
     -> resolve_methodology_context(...)
     -> build_capability_context(...)
     -> for KIT: build_selected_capability_context(...)
     -> local_agent_package builder
        -> AGENT_EXECUTION_CONTEXT.json / AGENT_EVAL_CONTEXT.json
        -> AGENT_PROMPT.md / AGENT_EVAL_PROMPT.md
        -> selected capability context files under runs/kit/<REQ-ID>/docs/
```

For KIT, `orchestrator/services/local_agent_package.py` extracts capability blobs and writes:

- `runs/kit/<REQ-ID>/docs/CLIKE_CAPABILITY_MANIFEST.md`
- `runs/kit/<REQ-ID>/docs/CLIKE_CAPABILITY_INDEX.json`
- `runs/kit/<REQ-ID>/docs/CLIKE_SELECTED_CAPABILITY_CONTEXT.md`
- `runs/kit/<REQ-ID>/docs/CLIKE_SELECTED_CAPABILITY_CONTEXT.json`

If those selected context files arrive as empty placeholders, the local-agent package builder regenerates them from `CLIKE_CAPABILITY_INDEX.json`. If the index is absent but raw `.clike/packs/**`, `.clike/skills/**`, and `.clike/design-profiles/**` blobs are present, it first builds the index from those blobs. BMAD vendor skill files stay isolated in `.clike/skills/vendor/bmad/**` and are not counted as CLike selected skills.

`AGENT_EXECUTION_CONTEXT.json` exposes:

- `capability_context.skills`
- `capability_context.packs`
- `capability_context.design_profiles`
- `capability_context.manifest.selected_context_available`
- `selected_skill_references` for BMAD
- `selected_skill_context` for BMAD
- `skill_reference_policy` for BMAD

`AGENT_PROMPT.md` tells the agent to read the execution context, target contracts, file requirements, and `CLIKE_SELECTED_CAPABILITY_CONTEXT.md` when present. When BMAD context is present, it includes `### BMAD Skill Reference Context` and explicitly treats skills as methodology guidance only.

For EVAL local-agent packaging, the same pattern applies through `AGENT_EVAL_CONTEXT.json`, `AGENT_EVAL_PROMPT.md`, and selected capability files copied under the target KIT docs root when the payload contains them. EvalRunner remains the judge; local-agent repair context is advisory and candidate-scoped.

For FINALIZE local-agent packaging, the context is solution-scoped rather than REQ-scoped. It can carry methodology context, including BMAD selected skill references for `finalize/tech-writer`, and can carry capability manifest/index metadata when present. It should not invent a target-REQ selected capability context because finalize has no single KIT target REQ.

## Phase Matrix

| Phase | Execution mode | CLike capability manifest/index | CLike selected capability context | BMAD selected skills when methodology=bmad | Notes |
| --- | --- | --- | --- | --- | --- |
| `/idea` | Cloud | Available only when repository context points to a workspace with `.clike/**` | Not expected | `analyst -> prd-shaping` | No target REQ exists. BMAD affects canonical IDEA and companion guidance only. |
| `/spec` | Cloud | Available only when repository context points to a workspace with `.clike/**` | Not expected | `pm -> prd-shaping, epic-framing, acceptance-modeling`; `ux -> ux-flow-modeling` | PM owns canonical SPEC. UX is companion-only. |
| `/plan` | Cloud | Available only when repository context points to a workspace with `.clike/**` | Not expected | `architect -> architecture-readiness, story-readiness`; `pm -> epic-framing, story-readiness` | PLAN may select capabilities per REQ in `plan.json`; those selections become actionable later. |
| `/kit` | Cloud | Built by Orchestrator before Gateway | Built by Orchestrator for the target REQ and rendered in Gateway KIT prompt | `developer -> dev-story-execution, story-readiness` | Cloud prompts can contain both CLike selected capability context and BMAD skill context. |
| `/kit` | Local-agent | Packaged under target KIT docs root | Packaged under target KIT docs root and summarized in `AGENT_EXECUTION_CONTEXT.json` | `developer -> dev-story-execution, story-readiness` | Current local-agent package path carries both data streams. |
| `/eval` | Cloud or local-agent | Available when payload carries capability blobs | Available for target-REQ repair when payload carries selected context | `qa -> qa-risk-review` | Local-agent repair does not decide Eval/Gate. |
| `/finalize` | Cloud or local-agent | Available as project capability inventory when payload carries it | Not expected unless a future finalize target model is introduced | `tech-writer -> release-narrative` | Finalize is solution narrative/release context, not REQ implementation context. |

## Extension Dispatch Findings

The VS Code slash parser preserves methodology and agent for BMAD-supported phases, including:

- `/idea --methodology bmad --agent analyst`
- `/spec --methodology bmad --agent pm`
- `/spec --methodology bmad --agent ux`
- `/plan --methodology bmad --agent architect`
- `/kit REQ-001 --methodology bmad --agent developer`
- `/eval REQ-001 --methodology bmad --agent qa`
- `/finalize --methodology bmad --agent tech-writer`

The extension request builders pass top-level `methodology` and `agent` through the Harper run payload. These top-level fields are the supported contract. Nested client-provided `methodology_context` is not a trusted source of selected skills.

## Resolver Findings

The resolver path is server-owned:

- `orchestrator/services/harper.py::run_phase` removes client-supplied `methodology_context`.
- `resolve_methodology_context(...)` derives context from top-level `methodology`, `phase`, and `agent`.
- `select_bmad_skill_context(...)` uses the manifest `skill_selection` map and normalized mapping files.

Expected BMAD selections are:

- `idea/analyst`: `prd-shaping`
- `spec/pm`: `prd-shaping`, `epic-framing`, `acceptance-modeling`
- `spec/ux`: `ux-flow-modeling`
- `plan/architect`: `architecture-readiness`, `story-readiness`
- `plan/pm`: `epic-framing`, `story-readiness`
- `kit/developer`: `dev-story-execution`, `story-readiness`
- `eval/qa`: `qa-risk-review`
- `finalize/tech-writer`: `release-narrative`

Native Harper calls return no BMAD selected skills.

## Python Namespace Materialization Finding

The captured KIT output shape `src/coffeebuddy.runtime/` reveals a separate path-materialization issue. For Python ecosystems, dotted module boundaries must materialize as package directories:

```text
coffeebuddy.runtime -> coffeebuddy/runtime
```

This rule is language-scoped. It is not applied blindly to non-Python ecosystems, where dots can be valid names or conventional identifiers. The helper in `orchestrator/utils/namespace_paths.py` applies the conversion only when runtime evidence identifies Python, and the resulting guidance is carried through target contracts, file requirements, cloud prompts, and local-agent prompts.

## Recommended Targeted Fix Plan

1. Keep CLike capability blobs visible in Gateway KIT cloud prompts.
   `_filter_core_blobs_for_kit(...)` must continue preserving `CLIKE_CAPABILITY_MANIFEST.md`, `CLIKE_CAPABILITY_INDEX.json`, `CLIKE_SELECTED_CAPABILITY_CONTEXT.md`, and `CLIKE_SELECTED_CAPABILITY_CONTEXT.json`.

2. Keep methodology resolution server-derived.
   Continue rejecting client-supplied `methodology_context` as authoritative. Ensure every extension and Orchestrator cloud/local-agent path sends top-level `methodology` and `agent`, and keep manifest-based rehydration in the envelope and local-agent compaction path.

3. Add debug markers for capabilities.
   Prompt debug already exposes BMAD selected skill fields. Add structured selected-capability evidence such as `selected_capability_context_available` and `selected_capability_names` when the core blobs are present.

4. Preserve Python namespace materialization.
   The Python-only helper converts dotted module boundaries to package paths after runtime evidence identifies Python. Tests cover `coffeebuddy.runtime -> coffeebuddy/runtime`.

5. Extend end-to-end guardrails.
   Keep separate tests for resolver selection, cloud BMAD prompt rendering, local-agent BMAD skill context, native isolation, selected CLike capability packaging, and Python namespace materialization.

## Verification Commands

```bash
python3 -m compileall orchestrator gateway tools
PYTHONPATH=/private/tmp/clike_test_deps:orchestrator:gateway:. python3 -m pytest orchestrator/tests/test_bmad_skill_mapping.py
PYTHONPATH=/private/tmp/clike_test_deps:orchestrator:gateway:. python3 -m pytest orchestrator/tests/test_methodology_resolver.py orchestrator/tests/test_methodology_injection.py
PYTHONPATH=/private/tmp/clike_test_deps:orchestrator:gateway:. python3 -m pytest orchestrator/tests/test_local_agent_package.py
PYTHONPATH=/private/tmp/clike_test_deps:gateway:orchestrator:. python3 -m pytest gateway/tests/test_methodology_prompt.py
node --test extensions/vscode/test/slash-parser.test.js
node --test extensions/vscode/test/bmad-advisory.test.js
```

Useful inspection commands:

```bash
rg -n "CLIKE_SELECTED_CAPABILITY_CONTEXT|CLIKE_CAPABILITY_MANIFEST|BMAD Skill Reference Context|selected_skill_references" orchestrator gateway extensions docs
rg -n "_filter_core_blobs_for_kit|build_selected_capability_context|resolve_methodology_context|select_bmad_skill_context" orchestrator gateway
rg -n "npx bmad-method|subprocess\.(run|Popen).*bmad|os\.system\(.*bmad|requests\.|urllib\.|httpx\." orchestrator gateway extensions tools docs README.md
```

Expected verification results:

- BMAD resolver selects `dev-story-execution` and `story-readiness` for `kit/developer`.
- Gateway methodology prompt rendering includes `### BMAD Skill Reference Context` for BMAD KIT/developer when resolved context is supplied.
- Native KIT prompt rendering does not include BMAD skill context.
- KIT local-agent package context includes selected CLike capability metadata and BMAD selected skills for BMAD/developer.
- Native KIT local-agent package preserves selected CLike capabilities but omits BMAD selected skill fields.
- Python dotted namespace materialization maps `coffeebuddy.runtime` to `coffeebuddy/runtime` for Python and does not rewrite non-Python paths.
