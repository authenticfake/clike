# Capability Context Data Path

CLike carries two related but separate guidance streams through Harper execution. CLike selected capabilities describe the project and target REQ constraints. BMAD selected methodology skills describe phase-and-agent guidance when `methodology=bmad` is active. They are composable, but neither stream is allowed to replace canonical Harper contracts, write boundaries, EvalRunner, or Gate.

## CLike Selected Capabilities

Workspace capabilities are discovered from `.clike/packs/**`, `.clike/skills/**`, and `.clike/design-profiles/**`. For cloud execution, the VS Code extension transports the same project-visible capability source files in `core_blobs` so the Orchestrator does not need a mounted target workspace. The normal CLike skill branch deliberately excludes `.clike/skills/vendor/bmad/**`; BMAD vendor skills are resolved as methodology skills in a separate branch.

The Orchestrator builds repository-level inventory files from the mounted workspace when it is available, or from the transported `.clike/**` capability blobs when it is not:

- `CLIKE_CAPABILITY_MANIFEST.md`
- `CLIKE_CAPABILITY_INDEX.json`

For target-REQ phases such as KIT and EVAL repair, the Orchestrator also resolves selected capabilities from the target contract and plan evidence:

- `CLIKE_SELECTED_CAPABILITY_CONTEXT.md`
- `CLIKE_SELECTED_CAPABILITY_CONTEXT.json`

Those files remain CLike-owned execution context. Native Harper may receive selected capabilities when the target REQ selects them. BMAD does not replace them. When a target REQ declares packs, skills, or design profiles but selected capability context cannot be materialized, CLike fails before cloud or local-agent execution with `CLIKE_SELECTED_CAPABILITIES_MISSING` instead of silently clearing the capability branch.

## BMAD Methodology Skills

BMAD selected skills are resolved server-side from `.clike/skills/vendor/bmad/manifest.json` and `.clike/skills/vendor/bmad/**/SKILL.md` entries transported in request `core_blobs`. The vendor manifest owns runtime `skill_selection` and `skill_reference_policy`; Python code reads those values and does not hardcode the phase/agent mapping. The VS Code extension seeds the vendor tree from `extensions/vscode/templates/harper-init/.clike/skills/vendor/bmad/**`.

For BMAD runs, the same selected skill data must be visible in:

- `methodology_context.selected_skill_references`
- `methodology_context.selected_skill_context`
- `context_envelope.bmad_methodology_skills`
- cloud prompt/debug output when the phase uses Gateway
- `AGENT_EXECUTION_CONTEXT.json`, `AGENT_EVAL_CONTEXT.json`, or finalize agent context when the phase uses a local-agent package

The Orchestrator rehydrates compact BMAD contexts from the manifest before building envelopes or packages, so stale empty skill lists do not propagate into cloud or local-agent execution.

## Context Envelope

`orchestrator/services/context_envelope.py` creates the audit envelope shared by cloud and local-agent paths:

- `phase`, `req_id`, and `execution_mode`
- `clike_capabilities`
- `bmad_methodology_skills`
- `active_output_contract`
- `namespace_materialization`

Gateway prompt debug includes the envelope for cloud paths. Local-agent packages write it into the agent context JSON. The envelope is diagnostic and operational context; it does not expand write roots or create a second authority for Eval/Gate.

## Cloud Path

The extension sends `docs/harper` core artifacts, `.clike` capability source files, and, for BMAD only, `.clike/skills/vendor/bmad/**` files. The Orchestrator resolves methodology context, builds capability blobs, builds the context envelope, and forwards all of it to Gateway. Gateway renders:

- `### CLike Selected Capability Context` when selected capability context is present
- `### BMAD Skill Reference Context` when BMAD selected skill references are present
- namespace materialization guidance when FILE_REQUIREMENTS carries it

Native cloud runs may include CLike selected capabilities. They must not include BMAD skill context.

## Local-Agent Path

Local-agent packages write selected capability files under the target KIT docs root when target-REQ capability context exists. If incoming selected capability JSON is stale or empty, the package builder regenerates it from the transported capability index or the raw `.clike/**` capability blobs. They also write BMAD selected skill fields when `methodology=bmad` and the manifest declares skills for the phase/agent.

KIT packages use `AGENT_EXECUTION_CONTEXT.json` and `AGENT_PROMPT.md`. EVAL packages use `AGENT_EVAL_CONTEXT.json` and `AGENT_EVAL_PROMPT.md`. Finalize packages use the finalize agent context and prompt. In every case, BMAD skills remain methodology guidance only. The agent may use them to improve implementation readiness, repair discipline, and documentation quality; it may not execute BMAD runtime, decide Eval/Gate, or write outside the active output contract.
