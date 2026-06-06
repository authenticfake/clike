# BMAD Skill Import Policy

CLike treats BMAD skills as methodology fuel, not execution authority. The integration is designed to let maintainers preserve useful BMAD reference material without allowing that material to become a runtime, a write policy, a gate, or a substitute for Harper's canonical artifacts.

The policy has three layers.

The extension template seed lives in the repository at:

```text
extensions/vscode/templates/harper-init/.clike/skills/vendor/bmad
```

When the VS Code extension initializes a workspace, that seed is copied into:

```text
<workspace>/.clike/skills/vendor/bmad
```

The workspace vendor directory is the runtime skill source for BMAD methodology context. The VS Code extension sends the vendor manifest and `SKILL.md` files in `core_blobs`; the Orchestrator resolves selected skills from those blobs and materializes bounded context for Gateway and local-agent packages. Native Harper does not activate this BMAD layer.

## Authority Boundary

Files under `.clike/skills/vendor/bmad` are never active prompts or executable tools. They may document reviewed BMAD concepts, but they do not decide phase behavior, output paths, write roots, test policy, EvalRunner results, or Gate promotion.

Runtime policy is closed by default:

- `runtime_import_enabled`: false
- `external_skill_execution_enabled`: false
- `external_bmad_cli_enabled`: false
- `network_fetch_enabled`: false
- `native_harper_active`: false

CLike does not call the BMAD CLI during `/idea`, `/spec`, `/plan`, `/kit`, `/eval`, `/gate`, or `/finalize`. It does not fetch latest BMAD material during Harper phases, does not add BMAD as a runtime dependency, and does not execute vendor skill files directly.

## Activation Model

Only `methodology=bmad` activates the CLike-owned vendor mappings. The Orchestrator resolves methodology, phase, and agent into `methodology_context.selected_skill_references` and `methodology_context.selected_skill_context`. Gateway can render that context into the cloud prompt as `BMAD Skill Reference Context`; local-agent packages can include it in `AGENT_EXECUTION_CONTEXT.json` or `AGENT_EVAL_CONTEXT.json`.

The selected context is bounded, summarized, and governed. It exists to improve canonical Harper outputs and BMAD companion artifacts. It cannot override active output contracts, EvalRunner authority, Gate authority, allowed write roots, forbidden paths, candidate isolation, or canonical validators.

## Review And Refresh

Vendor reference material is refreshed only through a maintainer-controlled local workflow. A maintainer selects a local BMAD reference checkout or extracted reference folder, runs the sync tool against the extension template destination, reviews the imported files and manifest hashes, and updates normalized mappings only when a concept fits CLike governance.

The sync tool records imported file paths, byte counts, and sha256 hashes in `manifest.json`. That manifest supports audit and review; it does not imply that imported material has been activated. The `reviewed_status` field remains `pending_manual_review` until a maintainer completes a documented review.

After each refresh, maintainers should run the BMAD skill mapping tests, methodology resolver tests, local-agent package tests, and safety greps documented in `TEST_PLAN.md`.
