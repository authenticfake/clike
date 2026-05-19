# CLike Harper Extend Feature

## Purpose

Harper Extend introduces the `/extend` command for controlled backlog evolution in an existing CLike/Harper project.

It appends new requirements to an already generated `PLAN.md` and `plan.json` without regenerating or mutating consolidated requirements.

The command is designed for projects that have already moved through `IDEA → SPEC → PLAN → KIT → EVAL → GATE` and need to add new REQs after a stable anchor, for example after `REQ-006`.

## Public Commands

```text
/extend
/extend REQ-007 "ATDL v1 schema, validator and compiler"
/extend --after REQ-006
/extend --after REQ-006 --from attachment
/add-req
```

`/add-req` is an alias. The canonical phase and command remain `extend`.

## Pipeline Position

```text
IDEA → SPEC → PLAN → EXTEND → KIT → EVAL → GATE → FINALIZE
```

`EXTEND` is optional and repeatable.

It is not a replacement for `/plan`. It is an append-only evolution phase.

## Core Guarantees

- Existing consolidated requirements are preserved by default.
- New requirements are appended after an anchor REQ.
- `PLAN.md` and `plan.json` remain aligned.
- `SPEC.md` is updated only when the extension introduces new product/system capability scope.
- Lane-guides are updated only when the extension introduces a new concern lane or materially extends an existing lane.
- All changes are auditable through an `EXTEND_*.md` report.
- Cloud and local-agent execution paths are both supported.
- Lane values are concern-oriented and must not be interpreted as implementation language.

## Read Inputs

Required:

```text
docs/harper/PLAN.md
docs/harper/plan.json
```

Optional, when present:

```text
docs/harper/SPEC.md
docs/harper/IDEA.md
docs/harper/TECH_CONSTRAINTS.yaml
docs/harper/lane-guides/*.md
.clike/skills/**
.clike/packs/**
.clike/design-profiles/**
attachments
```

## Written Outputs

Always:

```text
docs/harper/PLAN.md
docs/harper/plan.json
docs/harper/EXTEND_<YYYY-MM-DD>_<FIRST_REQ>_<LAST_REQ>.md
```

Conditionally:

```text
docs/harper/SPEC.md
docs/harper/lane-guides/<concern>.md
```

Forbidden by default:

```text
src/
test/
tests/
runs/kit/
runs/eval/
```

## Append-Only Policy

`/extend` must not rewrite existing REQs.

Default behavior:

```text
REQ-001..REQ-N: read-only
REQ-N+1..REQ-M: appended
```

Existing REQ objects in `plan.json` must retain their semantic content.

Existing REQ sections in `PLAN.md` must not be rewritten. Shared sections such as dependency graph, milestone/backlog, and verification checkpoints may be extended only to include the new REQs.

## SPEC.md Update Policy

`SPEC.md` is updated only when the new requirements add at least one of the following:

- new product capability
- new domain language
- new safety/compliance rule
- new integration boundary
- new user-facing behavior
- new non-functional constraint

The safest default is to append a section such as:

```markdown
## Extension Scope — REQ-007..REQ-009
```

instead of rewriting consolidated SPEC content.

## Lane-Guide Update Policy

Lane-guides are concern-oriented, not language-oriented.

Good lane examples:

```text
workflow-dsl
operational-registry
risk-policy
```

Bad lane examples when used as implementation inference:

```text
node
python
java
```

A lane-guide is created or updated only when the extension introduces a new capability concern or new evaluation guidance.

## Cloud Execution Path

The cloud path is responsible for requirement interpretation and structured document generation.

The orchestrator sends the cloud model:

- current `PLAN.md`
- current `plan.json`
- optional `SPEC.md`
- optional lane-guides
- inline requirement text
- attachment text
- repository metadata and execution preference

The cloud response must produce file artifacts only under allowed Harper documentation paths.

## Local-Agent Execution Path

The local-agent path is responsible for repository-local patching while preserving exact file structure.

The orchestrator emits an `AGENT_EXTEND_CONTEXT.json` package with:

- phase: `extend`
- anchor REQ
- new requirement input
- allowed write roots
- forbidden paths
- append-only policy
- validation expectations

The agent may write only:

```text
docs/harper/PLAN.md
docs/harper/plan.json
docs/harper/SPEC.md
docs/harper/lane-guides/
docs/harper/EXTEND_*.md
```

## Validation Rules

After `/extend`, CLike must validate:

- `PLAN.md` exists.
- `plan.json` exists and parses.
- Anchor REQ exists when supplied.
- New REQ IDs are unique.
- New REQ IDs are contiguous unless explicitly supplied.
- Every new REQ has acceptance criteria.
- Every new dependency resolves to an existing or newly added REQ.
- `PLAN.md` and `plan.json` both mention the new REQs.
- Existing consolidated REQs are not modified.
- An `EXTEND_*.md` audit report is written.

## Audit Report

Example:

```text
docs/harper/EXTEND_2026-05-19_REQ-007_REQ-009.md
```

Required sections:

```markdown
# Harper Extend Report — REQ-007..REQ-009

## Command

## Input Sources

## Anchor

## Added Requirements

## Updated Files

## Preserved Requirements

## Dependency Decisions

## Validation

## Risks / Follow-up
```

## Example: ABE Requirements

```text
/extend --after REQ-006
```

Input:

```text
REQ-007 — ATDL v1 schema, validator and compiler
REQ-008 — Operational pack registry
REQ-009 — Approval and risk policy
```

Expected outputs:

```text
docs/harper/PLAN.md
docs/harper/plan.json
docs/harper/SPEC.md
docs/harper/lane-guides/workflow-dsl.md
docs/harper/lane-guides/operational-registry.md
docs/harper/lane-guides/risk-policy.md
docs/harper/EXTEND_2026-05-19_REQ-007_REQ-009.md
```