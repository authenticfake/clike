# BMAD Skill Reference Seed

This directory is part of the CLike workspace template. When the VS Code extension initializes a new Harper workspace, the template copy places this directory at `.clike/skills/vendor/bmad` inside the target project.

The files here are auditable methodology input, not executable authority. CLike does not execute BMAD skills directly, does not call the BMAD CLI during normal Harper phases, and does not treat vendor reference files as active prompts, tools, agents, or write policies. Native Harper runs ignore this layer.

When `methodology=bmad` is selected, the Orchestrator resolves the active phase and agent into reviewed, CLike-owned normalized mappings under `orchestrator/methodologies/bmad/skills`. Those mappings may draw on reference concepts represented by this seed, but the mappings remain the controlled interface used by cloud prompts and local-agent packages.

This separation keeps Harper governance intact. Canonical CLike artifacts remain authoritative. EvalRunner and Gate remain CLike-owned. Write roots are not expanded by this directory, and BMAD reference material cannot replace the Orchestrator methodology resolver.

Maintainers can refresh the seed through controlled local tooling, typically `tools/bmad_skill_sync.py`, using a reviewed local BMAD reference checkout or extracted reference folder. Harper runtime phases do not fetch latest BMAD content and do not update this directory automatically. Workspace copies can be refreshed manually or by a future explicit sync command, followed by review of the imported material and any normalized mapping changes.
