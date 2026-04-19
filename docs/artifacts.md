# Artifacts

## Canonical documentation root

The canonical Harper doc root is currently configured around:
- `docs/harper`

The extension default setting also points to:
- `clike.docRoot = docs/harper`

## Canonical Harper artifacts

Main canonical files:
- `docs/harper/IDEA.md`
- `docs/harper/SPEC.md`
- `docs/harper/PLAN.md`
- `docs/harper/plan.json`
- `docs/harper/KIT.md`
- `docs/harper/constraints.json`
- `docs/harper/RELEASE_NOTES.md`
- `docs/harper/lane-guides/*`

## Candidate artifacts under `runs/kit/<REQ-ID>/`

The current sources treat these paths as the primary candidate area for REQ work.

### Source candidates
- `runs/kit/<REQ-ID>/src/...`

### Test candidates
- `runs/kit/<REQ-ID>/test/...`

### CI / execution artifacts
- `runs/kit/<REQ-ID>/ci/LTC.json`
- `runs/kit/<REQ-ID>/ci/HOWTO.md`
- `runs/kit/<REQ-ID>/ci/requirements.txt`

### Candidate docs
- `runs/kit/<REQ-ID>/docs/README_<REQ-ID>.md`
- `runs/kit/<REQ-ID>/docs/KIT_<REQ-ID>.md`
- `runs/kit/<REQ-ID>/docs/AGENT_EXECUTION_CONTEXT.json`

### Follow-up promotion / integrity artifacts
Current sources also reference additional artifacts such as:
- `runs/kit/<REQ-ID>/docs/REQ_PROMOTION_MANIFEST.md`
- `runs/kit/<REQ-ID>/docs/INTEGRITY_EVAL.json`

These are required by some explicit follow-up KIT phases.

## Run-level artifacts under `runs/<runId>/`

The inspected sources and reference docs consistently point to run-level evidence under:
- `runs/<runId>/`

Common files:
- `runs/<runId>/kit.report.json`
- `runs/<runId>/eval.summary.json`
- `runs/<runId>/gate.decisions.json`
- `runs/<runId>/telemetry.json`
- `runs/<runId>/manifest.json`
- `runs/<runId>/logs/`
- `runs/<runId>/artifacts/`
- `runs/<runId>/diffs/`

Different parts of the codebase reference slightly different subsets, but the important distinction is stable:
- **candidate artifacts are REQ-scoped under `runs/kit/<REQ-ID>/...`**
- **execution evidence is run-scoped under `runs/<runId>/...`**

## `plan.json`

`docs/harper/plan.json` is the main machine-readable plan artifact.

Current responsibilities:
- holds REQ inventory
- expresses dependencies
- tracks status
- feeds default REQ selection
- feeds KIT preparation
- feeds EVAL/GATE policy decisions
- feeds MCP read-only plan tools

## `PLAN.md`

`docs/harper/PLAN.md` is the human-readable plan snapshot.

Current responsibilities:
- human navigation
- narrative plan visibility
- checklist or snapshot role
- synced or updated alongside `plan.json`

## `LTC.json`

`LTC.json` is the REQ-level execution contract generated under candidate artifacts.

Current responsibilities:
- define tools and commands
- define execution recipe
- define report expectations
- define gate policy hints
- feed eval normalization
- feed local-agent eval pre-pass
- anchor reproducible execution for a REQ slice

## `HOWTO.md`

`HOWTO.md` is the operator-facing runbook for a REQ candidate.

Current responsibilities:
- explain prerequisites
- define copy-paste run steps
- explain env requirements
- explain CI execution mode
- provide troubleshooting notes

## `AGENT_EXECUTION_CONTEXT.json`

This artifact is central to local-agent compatibility.

Current responsibilities:
- capture execution contract for local KIT or local eval pre-pass
- define required reads
- define allowed write roots
- define forbidden paths
- encode project metadata
- encode expected outputs and generation rules

### Current phase-specific behavior
For `kit`:
- defines candidate generation rules
- defines expected candidate outputs

For `eval`:
- includes `eval_contract`
- includes `evaluation_rules`
- points the agent to `LTC.json` and `HOWTO.md`

## Promotion artifacts

Promotion is not modeled as raw copy-only behavior. The current code uses promotion-aware manifests and policy checks.

Promotion-related references in sources include:
- promotion manifests
- integrity eval results
- gate decisions
- Git integration
- explicit source/test promotion commands in the extension

## Artifact rules that must remain explicit in docs

The current sources justify documenting these rules explicitly:
- candidate artifacts must be generated under `runs/kit/<REQ-ID>/...`
- canonical `src/` and `test/` roots must not be mutated directly by local agents
- eval/gate consume contracts and artifacts, not just free-form model text
- plan artifacts remain canonical and protected during candidate generation
