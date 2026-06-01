# BMAD Methodology Profile

The BMAD methodology profile is a CLike-owned integration layer that maps Harper phases to BMAD-style roles. The profile is intentionally compact and operational. It is metadata and guidance, not an executor.

BMAD exists inside CLike to improve how phases reason, not to replace the Harper workflow. A role can emphasize discovery, product clarity, architecture, implementation focus, UX quality, QA repair guidance, or documentation polish. CLike still owns the artifacts and the decisions that make work governed and promotable.

## Supported Methodology

- `bmad`

No external BMAD runtime is required. CLike does not install BMAD, execute BMAD CLIs, or call `npx bmad-method`.

## Request Fields

Methodology-aware requests may include:

- `methodology`
- `agent`
- `methodology_context`

The orchestrator is the single resolver for `methodology_context`. Clients may pass user intent through `methodology` and `agent`, but resolved authority, defaults, advisory flags, workflow focus, and phase mapping belong to the orchestrator. Client-supplied `methodology_context` is not trusted as authority.

## Phase Mapping

| Harper phase | Default BMAD role | Allowed roles | Notes |
| --- | --- | --- | --- |
| `idea` | `analyst` | `analyst` | Discovery and intent framing |
| `spec` | `pm` | `pm`, `ux` | Requirements and UX acceptance detail |
| `plan` | `architect` | `architect`, `pm` | Technical slicing and dependencies |
| `kit` | `developer` | `developer` | Candidate implementation guidance |
| `eval` | `qa` | `qa`, `developer` | Advisory only; EvalRunner remains authoritative |
| `gate` | none | none | CLike-only authority |
| `finalize` | `tech-writer` | `tech-writer` | Release and documentation guidance |

## PLAN Phase Profile

For `/plan`, BMAD `architect` and `pm` roles guide requirement shaping while CLike owns the canonical `PLAN.md` and `plan.json` artifacts.

The PLAN phase should produce REQs that are implementation-ready for `/kit`. Each REQ should include or clearly imply Functional Scope, Technical Scope, Non-Functional Requirements, Security Requirements, Compliance and Privacy Requirements when applicable, Observability and Operations, Integration Contracts, Data Contracts, Dependencies, Acceptance Criteria, Test Strategy, Risk and Mitigation, TECH_CONSTRAINTS obligations, the main module boundary, what this REQ builds now, what this REQ intentionally defers, and what downstream REQs may assume.

`plan.json` should preserve machine-readable detail sufficient for `/kit`, including `id`, `title`, `status`, `lane`, `dependsOn`, `acceptance`, `functional_scope`, `technical_scope`, `non_functional_requirements`, `security_requirements`, `compliance_requirements`, `operational_requirements`, `integration_contracts`, `data_contracts`, `test_strategy`, `risk_notes`, `main_module_boundary`, `runtime_profile` when known, and `gate_expectations` when relevant.

BMAD methodology guidance must not choose a technology stack by default. Python, Node, cloud provider, runtime, database, queue, identity, deployment target, and framework choices must come from TECH_CONSTRAINTS, SPEC, repository evidence, or explicit user input.

## Prompt And Package Injection

For cloud Harper runs, the resolved methodology context is sent to Gateway so the cloud prompt can include compact role and workflow guidance.

For local-agent execution, the resolved methodology context is written into local-agent package files such as `AGENT_*_CONTEXT.json` and `AGENT_*_PROMPT.md`. Gateway is not used for local-agent prompt construction.

In both cases, prompt guidance is compact. CLike-owned BMAD profiles are intentionally bounded and do not copy or vendor external BMAD runtime content.

## Methodology Is Not Execution

Methodology identity is separate from:

- `profileHint`
- cloud model routing
- `localAgentExecutor`
- Claude Code or Codex CLI selection
- eval/gate verdicts

BMAD enriches the work style for a phase. It does not decide where execution runs, what model is used, what files can be written, or whether a REQ is promotable.

## Current MVP Boundaries

The current integration does not implement a BMAD runtime, BMAD artifact importer, TEA/Test Architect, Party Mode, or MCP write tools. It does not call `npx bmad-method` and does not add a hard dependency on BMAD packages.
