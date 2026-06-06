# BMAD Skill Mappings

These files are CLike-owned normalized BMAD skill mappings. They translate reviewed BMAD reference concepts into bounded Harper workflow guidance without adding a BMAD runtime dependency, executable BMAD prompt layer, or alternate authority model.

The mappings are selected by methodology, phase, and agent from `orchestrator/methodologies/bmad/manifest.json`. They may be rendered into cloud prompts or local-agent packages only when `methodology=bmad`. Native Harper runs must not receive these mappings.

The vendor reference seed under `.clike/skills/vendor/bmad/**` is workspace material copied from the VS Code Harper init template. It is a reference inventory, not the active skill system. The Orchestrator never executes vendor files, never calls the BMAD CLI, never fetches latest BMAD material during runtime phases, and never expands write roots based on reference material.

Each mapping states its intent, required inputs, required outputs, companion outputs, quality checks, evidence expectations, forbidden behavior, cloud usage notes, local-agent usage notes, and governance boundaries. Those sections are structured so the loader can provide bounded context to Gateway and local-agent packages while keeping canonical Harper artifacts authoritative. EvalRunner and Gate remain CLike-owned.
