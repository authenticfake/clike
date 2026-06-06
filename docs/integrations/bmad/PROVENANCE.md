# BMAD Profile Provenance

CLike includes a BMAD-aware methodology profile as CLike-owned metadata. The profile is inspired by BMAD Method concepts, but it is not the official BMAD runtime, does not vendor official BMAD prompt content, and does not execute BMAD tooling.

The purpose of this document is to make reference discipline explicit. CLike may manually review public BMAD Method materials and decide which concepts should be adapted into the governed Harper workflow. That review is a maintainer action, not runtime behavior.

## Ownership

The BMAD-aware profile is owned by CLike. CLike controls the manifest, role summaries, workflow summaries, governance boundaries, tests, documentation, and release process.

BMAD is treated as a methodology reference. CLike adopts only concepts that can fit inside Harper governance:

- agent responsibilities
- workflow sequence
- artifact expectations
- handoff rules
- checklist patterns
- customization model
- project-context model

CLike excludes concepts that would break governance:

- runtime dependency
- CLI execution
- uncontrolled writes
- gate authority
- copied official prompts
- latest auto-pulled in production

## Manual Review Only

CLike does not auto-track BMAD latest at runtime. There is no runtime updater, no network fetch, no generated dependency on a BMAD package, and no automatic synchronization with an upstream repository.

Reference updates must use a manual review flow:

1. Select BMAD latest or a pinned release.
2. Review the selected materials manually.
3. Optionally compare behavior in a separate fixture workspace.
4. Record the mapping in `docs/integrations/bmad/PROFILE_SYNC_REPORT.md`.
5. Update the CLike-owned profile only where the concept fits Harper governance.
6. Run the required tests and safety checks.
7. Merge through the normal CLike review process.

## Runtime Boundary

The CLike runtime must not invoke BMAD tooling, vendor official BMAD runtime content, or allow BMAD to become an executor. Methodology context may enrich prompts and local-agent packages only after the orchestrator resolves it.

Gateway remains cloud prompt composition only. Local-agent prompts remain built through `local_agent_package`. EvalRunner remains authoritative. Gate remains CLike-owned.

The current implementation also keeps automatic latest BMAD tracking at runtime out of scope. A maintainer may manually review a selected upstream BMAD release or commit, but production CLike runs do not fetch, compare, install, or execute BMAD at runtime.

## Skill Reference Seed

CLike seeds reference-only BMAD skill material into new workspaces from the VS Code Harper init template:

```text
extensions/vscode/templates/harper-init/.clike/skills/vendor/bmad
```

After `/init`, the workspace copy lives at:

```text
.clike/skills/vendor/bmad
```

The seed is pinned and auditable through its `manifest.json`. It is not active for native Harper runs and is not an executable skill system. It exists so a workspace can carry reviewed reference material alongside the project without granting that material prompt authority, write authority, EvalRunner authority, or Gate authority.

BMAD methodology runs use CLike-owned vendor skill material from `.clike/skills/vendor/bmad`, selected by `skill_selection` in the vendor manifest transported through request `core_blobs`. The Orchestrator resolves those blobs into `methodology_context.selected_skill_references` and `methodology_context.selected_skill_context`. Gateway may render bounded summaries into the cloud prompt, and local-agent packages may include the same materialized context in `AGENT_EXECUTION_CONTEXT.json` or `AGENT_EVAL_CONTEXT.json`. Vendor files are not executed and are not treated as independent authority.

Updates use `tools/bmad_skill_sync.py` against a local reviewed source directory. Runtime phases do not fetch latest BMAD content, do not run BMAD CLI, and do not update the seed automatically. Any imported material remains reference-only until maintainers explicitly adapt it into normalized CLike mappings.

## Future Roadmap Boundaries

The following items are not current behavior:

- BMAD runtime execution
- `npx bmad-method` runtime invocation
- BMAD importer
- TEA
- Party Mode
- MCP write tools
- multi-agent `/spec --agents pm,ux`
- automatic latest BMAD tracking at runtime

If any of these are implemented later, they must be introduced through CLike governance, tests, documentation, auditability, and explicit review. Until then, documentation must describe them only as future roadmap or out of scope.

## Current Review State

The current manifest uses `manual-review-pending` for reviewed version, commit, date, and reviewer fields. Maintainers should replace those values only after completing a documented review and updating the profile sync report.
