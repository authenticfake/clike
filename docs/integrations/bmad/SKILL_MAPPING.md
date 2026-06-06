# BMAD Skill Mapping

CLike does not import BMAD skills as executable behavior. It translates reviewed BMAD concepts into CLike-owned normalized mappings, then selects those mappings through the same methodology resolver that governs BMAD roles, artifacts, and phase boundaries.

The runtime mapping root inside initialized workspaces is:

```text
.clike/skills/vendor/bmad
```

These files are the stable interface consumed by cloud prompt rendering and local-agent package generation. The VS Code extension transports the vendor manifest and `SKILL.md` files through `core_blobs` for BMAD runs, so cloud execution does not depend on a mounted target workspace.

## Selection Matrix

The workspace vendor manifest stores the deterministic runtime selection map:

```text
.clike/skills/vendor/bmad/manifest.json
```

Current selections:

| Phase and agent | Selected mappings |
| --- | --- |
| `idea/analyst` | `prd-shaping` |
| `spec/pm` | `prd-shaping`, `epic-framing`, `acceptance-modeling` |
| `spec/ux` | `ux-flow-modeling` |
| `plan/architect` | `architecture-readiness`, `story-readiness` |
| `plan/pm` | `epic-framing`, `story-readiness` |
| `kit/developer` | `dev-story-execution`, `story-readiness` |
| `eval/qa` | `qa-risk-review` |
| `finalize/tech-writer` | `release-narrative` |

Unsupported methodology, phase, or agent combinations fail closed or return an empty skill selection. Native Harper runs do not receive BMAD skill references.

The table is documentation of the manifest, not an implementation duplicate. Runtime code reads `skill_selection` from the vendor manifest and loads selected `SKILL.md` files from `.clike/skills/vendor/bmad/**` blobs. Tests also read the manifest so a future mapping change updates expected behavior in one place.

## Runtime Context Shape

When `methodology=bmad` is selected, the Orchestrator adds skill data to `methodology_context`:

- `selected_skill_references`
- `selected_skill_context`
- `skill_reference_policy`

The selected context includes mapping paths, bounded snippets, required outputs, companion outputs, quality checks, forbidden behavior, governance boundaries, and optional vendor inventory metadata. The loader does not read arbitrary client-controlled paths, does not dump full vendor files into prompts, does not execute external commands, and does not fetch network resources.

The same data is also summarized in `context_envelope.bmad_methodology_skills`. CLike selected capabilities remain separate under `context_envelope.clike_capabilities`, so BMAD methodology guidance cannot replace REQ-selected packs, skills, or design profiles.

CLike capability source files travel beside BMAD vendor files but remain a different runtime branch. The extension sends `.clike/packs/**`, normal `.clike/skills/**`, `.clike/design-profiles/**`, and `.clike/capabilities.yaml` in `core_blobs` for Harper runs. The normal CLike capability index excludes `.clike/skills/vendor/bmad/**`, which is consumed only by the BMAD methodology skill resolver.

The propagation invariant is strict: for BMAD phases declared in `skill_selection`, `methodology_context.selected_skill_references`, `context_envelope.bmad_methodology_skills.selected_skill_references`, and local-agent top-level `selected_skill_references` must contain the manifest-defined list. If a compact BMAD context reaches local-agent packaging with empty skill fields, the Orchestrator rehydrates those fields from the manifest before writing the package.

The rehydration path exists for compact transport shapes such as the VS Code slash-parser context, which may contain only `methodology` and `agent`. The package builder supplies the trusted phase, then the resolver reads `manifest.json.skill_selection` and reloads the normalized mapping files. This keeps the manifest as the only skill-selection source of truth while preventing empty client-shaped contexts from suppressing BMAD skills.

## Cloud Path

Gateway renders the selected context as `BMAD Skill Reference Context` only when BMAD methodology context contains selected skills. That section identifies the mappings, summarizes the expected outputs and quality checks, and repeats the governance boundary: canonical Harper artifacts remain authoritative; Eval/Gate remain CLike-owned; arbitrary output paths and expanded write roots are forbidden.

For `/kit REQ-001 --methodology bmad --agent developer`, the cloud prompt must expose the `dev-story-execution` and `story-readiness` mappings. Prompt-debug output should show either the rendered `BMAD Skill Reference Context` section in `messages` or structured `selected_skill_references` metadata, preferably both. Companion artifacts under `docs/harper/bmad/**` are useful context, but their presence is not a substitute for the selected skill context.

When KIT also has selected CLike capabilities, the cloud prompt must expose both `### CLike Selected Capability Context` and `### BMAD Skill Reference Context`. Prompt debug includes `context_envelope` so the two streams are auditable from one Orchestrator-owned object.

If the target REQ declares CLike packs, skills, or design profiles but the selected capability branch is empty, the run fails before model or local-agent execution with `CLIKE_SELECTED_CAPABILITIES_MISSING`. This guardrail protects native and BMAD runs equally. It is separate from `BMAD_SELECTED_SKILLS_MISSING`, which applies only when the BMAD vendor manifest declares skills for the current phase and agent.

Native cloud prompts do not render this section.

## Local-Agent Path

For BMAD KIT packages, `AGENT_EXECUTION_CONTEXT.json` includes the selected skill references, selected skill context, and skill reference policy. `AGENT_PROMPT.md` instructs the local agent to read the context before implementation or repair, while treating it as methodology guidance only.

For `/kit REQ-001 --methodology bmad --agent developer` with local-agent execution, `AGENT_EXECUTION_CONTEXT.json` must include `dev-story-execution`, `story-readiness`, `selected_skill_context`, and `skill_reference_policy`. `AGENT_PROMPT.md` must include `BMAD Skill Reference Context`, the selected skill identifiers, write-boundary reminders, and the explicit rule that BMAD runtime is not executed and `npx bmad-method` is not called.

The same KIT package must preserve CLike selected capabilities in `selected_clike_capabilities`, `selected_clike_packs`, `selected_clike_skills`, `selected_clike_design_profiles`, and `context_envelope.clike_capabilities`. If incoming `CLIKE_SELECTED_CAPABILITY_CONTEXT.json` is empty, the package builder regenerates it from the capability index or raw `.clike` capability blobs before writing `AGENT_EXECUTION_CONTEXT.json`. Native KIT packages may contain CLike capabilities but must omit BMAD selected skill fields.

For BMAD EVAL hardening packages, `AGENT_EVAL_CONTEXT.json` carries the same governed skill context, and `AGENT_EVAL_PROMPT.md` keeps canonical EvalRunner authority explicit. BMAD QA guidance can improve repair quality and evidence discipline, but it cannot decide pass/fail, promotability, or Gate outcome.

Native local-agent packages omit BMAD skill fields.

## Verification

Cloud verification after a BMAD run:

```text
rg -n "BMAD Skill Reference Context|selected_skill_ids" telemetry/prompt_debug gateway/stub runs
rg -n "selected_skill_references|dev-story-execution|story-readiness" telemetry/prompt_debug gateway/stub runs
```

Local-agent verification after BMAD KIT or EVAL:

```text
rg -n "selected_skill_references|skill_reference_policy|BMAD skill context" runs/kit/*/docs/AGENT_EXECUTION_CONTEXT.json runs/kit/*/docs/AGENT_PROMPT.md
rg -n "BMAD Skill Reference Context|dev-story-execution|story-readiness" runs/kit/*/docs/AGENT_EXECUTION_CONTEXT.json runs/kit/*/docs/AGENT_PROMPT.md
rg -n "selected_skill_references|skill_reference_policy|BMAD skill context" runs/kit/*/docs/AGENT_EVAL_CONTEXT.json runs/kit/*/docs/AGENT_EVAL_PROMPT.md
```
