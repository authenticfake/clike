# BMAD Governance Model

CLike owns governance. BMAD enriches phase behavior.

This integration treats BMAD as methodology context, not as a runtime, executor, authority system, or alternate Harper pipeline. BMAD can make a phase more expressive and operationally useful, but CLike still decides what artifacts are canonical, where code can be written, how eval is run, how gate is decided, and whether promotion is allowed.

## Canonical And Companion Artifacts

Canonical Harper artifacts are the documents and machine-readable files that CLike uses to drive the workflow. They include `docs/harper/IDEA.md`, `docs/harper/SPEC.md`, `docs/harper/PLAN.md`, and `docs/harper/plan.json`. CLike owns their lifecycle, format, auditability, and downstream interpretation.

Companion artifacts can enrich the canonical context without replacing it. BMAD and UX companion material may live under controlled Harper-owned roots such as `docs/harper/bmad/**` and `docs/harper/ux/**`. Examples include design notes, experience maps, PRD drafts, or role-specific planning notes. These files can inform phases, but canonical CLike artifacts remain the source of truth for `/kit`, `/eval`, `/gate`, and promotion.

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

## Local-Agent Path

For Claude Code or Codex local execution, the orchestrator resolves `methodology_context` and injects it through `local_agent_package`.

```text
VS Code -> Orchestrator -> methodology resolver -> local_agent_package -> AGENT_*_CONTEXT / AGENT_*_PROMPT -> local agent
```

The package writes methodology guidance into `AGENT_*_CONTEXT.json` and `AGENT_*_PROMPT.md`. This keeps local execution inside the CLike package contract instead of routing local prompts through Gateway.

## Eval Advisory Behavior

EvalRunner remains authoritative for eval. The canonical path is still:

```text
handleEval -> /v1/eval/run -> EvalRunner.run_profile
```

BMAD QA may add advisory guidance only after canonical eval completes. Advisory content can identify likely root causes, files to inspect, missing tests, contract gaps, risk notes, repair strategy, a suggested next command, and checks to rerun.

BMAD QA cannot replace EvalRunner, decide pass/fail, change `promotable`, change REQ status, mark candidate failures as environment blockers without evidence, or affect gate.

## Gate Authority

Gate is CLike-only. The current MVP rejects methodology flags for `/gate` so BMAD cannot enter gate authority.

Gate behavior is not delegated to an LLM. BMAD cannot override block/pass decisions, cannot promote code, and cannot change gate policy.

## Telemetry, Audit, And Promotion

Telemetry, audit trail, run metadata, canonical eval reports, gate checks, promotion status, and Git-related flows remain CLike-owned. Methodology context may be recorded as context, but it is not authority.

Promotion remains a governed CLike action after candidate generation, eval, and gate. No BMAD role can directly promote artifacts or mutate Git state.
