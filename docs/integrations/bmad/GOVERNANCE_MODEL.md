# BMAD Governance Model

CLike owns governance. BMAD enriches phase behavior.

This integration treats BMAD as methodology context, not as a runtime, executor, authority system, or alternate Harper pipeline. BMAD can make a phase more expressive and operationally useful, but CLike still decides what artifacts are canonical, where code can be written, how eval is run, how gate is decided, and whether promotion is allowed.

## Canonical And Companion Artifacts

Canonical Harper artifacts are the documents and machine-readable files that CLike uses to drive the workflow. They include `docs/harper/IDEA.md`, `docs/harper/SPEC.md`, `docs/harper/PLAN.md`, and `docs/harper/plan.json`. CLike owns their lifecycle, format, auditability, and downstream interpretation.

Companion artifacts can enrich the canonical context without replacing it. BMAD and UX companion material may live under controlled Harper-owned roots such as `docs/harper/bmad/**` and `docs/harper/ux/**`. Examples include design notes, experience maps, PRD drafts, or role-specific planning notes. These files can inform phases, but canonical CLike artifacts remain the source of truth for `/kit`, `/eval`, `/gate`, and promotion.

Conflict resolution is always `canonical-wins`. If companion content disagrees with `IDEA.md`, `SPEC.md`, `PLAN.md`, `plan.json`, `TECH_CONSTRAINTS.yaml`, EvalRunner evidence, gate policy, telemetry, audit records, or write boundaries, the canonical CLike artifact or policy wins.

## Artifact Ownership Policy

The BMAD manifest includes a machine-readable `artifact_policy` keyed by phase and role, such as `spec/pm`, `spec/ux`, `plan/architect`, and `eval/qa`.

Each policy entry defines:

- canonical outputs that the phase may produce through normal CLike governance
- mandatory companion outputs that provide bounded BMAD or UX context
- allowed companion root globs for open-ended role material
- forbidden outputs that the role must not write
- downstream consumers that may treat the companion material as context
- conflict resolution, always `canonical-wins`

Companion outputs are additive, consultative, and non-authoritative. They are valid context for later phases, but they do not supersede `IDEA.md`, `SPEC.md`, `PLAN.md`, `plan.json`, EvalRunner reports, gate results, telemetry, audit records, or promotion policy.

For example, `spec/pm` may contribute to canonical `docs/harper/SPEC.md` through the normal SPEC phase and may also create companion PRD and acceptance-model material under `docs/harper/bmad/spec/**`. In contrast, `spec/ux` is companion-only in the MVP, has no canonical outputs, and explicitly forbids writing `docs/harper/SPEC.md`; UX contributes controlled companion context under `docs/harper/ux/**`, including `SPEC_UX_APPENDIX.md`, for `/plan` to consume later.

Gateway also enforces this split for cloud SPEC runs. When the resolved methodology context is `bmad` with agent `ux`, Gateway drops outputs outside `docs/harper/ux/**`, including `docs/harper/SPEC.md`. When the resolved agent is `pm`, Gateway allows `docs/harper/SPEC.md` and `docs/harper/bmad/spec/**` according to the artifact policy.

Eval QA remains advisory-only. Its companion outputs can describe fix guidance, missing tests, risk review, and QA advisory notes under the candidate KIT docs root, but they cannot change canonical eval verdicts or gate authority.

## Downstream Discovery And Ingestion

The orchestrator performs server-side companion discovery after resolving `methodology_context`. It derives allowed roots from the workspace and active REQ rather than trusting arbitrary client paths.

Current discovered roots are:

- `docs/harper/bmad/**`
- `docs/harper/ux/**`
- `runs/kit/<REQ-ID>/docs/**` when a REQ is active

The collector is bounded and path-safe. It accepts Markdown, text, JSON, YAML, and YML files; ignores hidden directories, `.git`, `node_modules`, `__pycache__`, binary files, and symlinks that escape the workspace; and records path, size, SHA-256, truncation state, snippet, and source group. The server-derived inventory is attached to `methodology_context.discovered_companion_artifacts` and inserted into `core_blobs` with stable `companion::...` keys. If a client supplied a duplicate companion key, the server-derived value wins.

Cloud prompts may render a compact `BMAD Companion Artifact Inventory` from that resolved context. Local-agent packages expose the same discovered artifacts through `AGENT_EXECUTION_CONTEXT.json` and `AGENT_EVAL_CONTEXT.json` as `discovered_companion_artifact_inventory` and `companion_documents`.

## Candidate-First Generation

KIT generation is candidate-first. Candidate outputs are written under `runs/kit/<REQ-ID>/...`, not directly into canonical source or canonical tests. This gives CLike a reviewable boundary for generated source, tests, docs, CI assets, target contracts, file requirements, and repair notes.

BMAD developer guidance can make the candidate package more focused, but it cannot widen write permissions. A BMAD-enabled `/kit` run is still a normal CLike KIT run with methodology guidance attached.

## Write Boundaries

Local-agent packages preserve `allowed_write_roots` and `forbidden_paths`. BMAD methodology context must not add new write roots, remove forbidden paths, or authorize writes into canonical project source.

Forbidden paths continue to include canonical source and test roots such as `src`, `test`, and `tests`, plus governance artifacts such as `docs/harper/PLAN.md` and `docs/harper/plan.json` where local-agent candidate execution must not mutate them. The exact package may include additional forbidden paths based on phase and workspace context.

## TECH_CONSTRAINTS Authority

`docs/harper/TECH_CONSTRAINTS.yaml` is an authoritative execution constraint source. BMAD profiles may help interpret it, but they cannot weaken it.

If TECH_CONSTRAINTS requires cloud/on-prem parity, air-gapped operation, provider portability, internal registries, identity constraints, deployment-specific behavior, or runtime constraints, those requirements must become explicit phase obligations. In planning, they belong in REQ scope, acceptance criteria, test strategy, downstream assumptions, and `plan.json` details rather than unowned future notes.

## Cloud Path

For cloud Harper runs, the orchestrator resolves `methodology_context` and sends it to Gateway.

```text
VS Code -> Orchestrator -> methodology resolver -> Gateway -> cloud LLM prompt
```

Gateway remains a cloud prompt composition and provider abstraction layer. Gateway does not resolve methodology identity and does not build local-agent prompts.

For cloud verification, inspect the Gateway `prompt_debug` output for:

- `### Governed Methodology Profile`
- `### BMAD Companion Artifact Contract`
- `### BMAD Companion Artifact Inventory`
- `### BMAD Governance Boundaries`
- `### BMAD Downstream Handoff`

## Local-Agent Path

For Claude Code or Codex local execution, the orchestrator resolves `methodology_context` and injects it through `local_agent_package`.

```text
VS Code -> Orchestrator -> methodology resolver -> local_agent_package -> AGENT_*_CONTEXT / AGENT_*_PROMPT -> local agent
```

The package writes methodology guidance into `AGENT_*_CONTEXT.json` and `AGENT_*_PROMPT.md`. This keeps local execution inside the CLike package contract instead of routing local prompts through Gateway.

For local-agent verification, inspect `runs/kit/<REQ-ID>/docs/AGENT_EXECUTION_CONTEXT.json` after BMAD KIT and `runs/kit/<REQ-ID>/docs/AGENT_EVAL_CONTEXT.json` after BMAD EVAL. The context should include `methodology_context`, `companion_documents`, discovered companion inventory when present, BMAD expected outputs, unchanged `allowed_write_roots`, and unchanged `forbidden_paths`.

## Eval Advisory Behavior

EvalRunner remains authoritative for eval. The canonical path is still:

```text
handleEval -> /v1/eval/run -> EvalRunner.run_profile
```

BMAD QA may add advisory guidance only after canonical eval completes. Advisory content can identify likely root causes, files to inspect, missing tests, contract gaps, risk notes, repair strategy, a suggested next command, and checks to rerun.

BMAD QA cannot replace EvalRunner, decide pass/fail, change `promotable`, change REQ status, mark candidate failures as environment blockers without evidence, or affect gate.

## Gate Authority

Gate remains CLike-owned. The current MVP rejects methodology flags for `/gate` so BMAD cannot enter gate authority.

Gate behavior is not delegated to an LLM. BMAD cannot override block/pass decisions, cannot promote code, and cannot change gate policy.

## Telemetry, Audit, And Promotion

Telemetry, audit trail, run metadata, canonical eval reports, gate checks, promotion status, and Git-related flows remain CLike-owned. Methodology context may be recorded as context, but it is not authority.

Promotion remains a governed CLike action after candidate generation, eval, and gate. No BMAD role can directly promote artifacts or mutate Git state.

## Current Out Of Scope

The current MVP does not implement BMAD runtime execution, `npx bmad-method` runtime invocation, the BMAD importer, TEA, Party Mode, MCP write tools, multi-agent `/spec --agents pm,ux`, or automatic latest BMAD tracking at runtime. These items must remain explicitly documented as future roadmap or out of scope until implemented through CLike governance.
