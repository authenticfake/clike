# Artifacts

## Canonical documentation root

The canonical Harper doc root is `docs/harper` (fixed; it is not a setting).

## Canonical Harper artifacts

Main canonical files:
- `docs/harper/IDEA.md`
- `docs/harper/SPEC.md`
- `docs/harper/PLAN.md`
- `docs/harper/plan.json`
- `docs/harper/TECH_CONSTRAINTS.yaml` (`constraints.json` is read when present)
- `docs/harper/KIT.md`
- `docs/harper/lane-guides/*`
- `docs/harper/EXTEND_<date>_<FIRST_REQ>_<LAST_REQ>.md` — report of `/extend` and `/idea --extend`
  (the cascade adds a *CLike verification* section)

Written by `/finalize`:
- `docs/harper/HOWTO_RUN.md`, `SANITY_CHECKS.md`, `RELEASE_NOTES.md`, `TODO_NEXT.md`, `PR_BODY.md`
  (`INFRA_READINESS.md` when infrastructure is detected)
- `docs/harper/FINALIZE_REPORT.md` — the developer report: how to start and see the solution,
  every variable, what only the developer can provide, changes and problems met
- `docs/harper/SOLUTION_EVAL.md` — evidence of the solution verification (cycles, last gate of
  every REQ)
- `ci/SOLUTION_LTC.json` — the eval profile of the whole solution
- `scripts/setup_local`, `scripts/start_solution_local`, `scripts/check_solution_local`
  (`.sh` / `.ps1`) — configure, start and check the solution on the developer's machine

## Project inputs

Read as context by the phases (see `context-sources.md`), never written by CLike:
- `docs/inputs/**` — requirements; `docs/inputs/vN/` = requirements of release N
- `docs/reference/**` — background; `docs/reference/vN/` = background of release N
- `docs/harper/ux/**` — UI references

Earlier release folders (and unversioned inputs, once release folders exist) are history.

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
- `runs/kit/<REQ-ID>/ci/FILE_REQUIREMENTS.json`, `ci/TARGET_CONTRACT.json`,
  `ci/REQ_PROMOTION_MANIFEST.md` — written by CLike from the plan, not part of the acceptance lock

### Candidate docs
- `runs/kit/<REQ-ID>/docs/README_<REQ-ID>.md`
- `runs/kit/<REQ-ID>/docs/KIT_<REQ-ID>.md`
- `runs/kit/<REQ-ID>/docs/AGENT_EXECUTION_CONTEXT.json`

### Follow-up promotion / integrity artifacts
Current sources also reference additional artifacts such as:
- `runs/kit/<REQ-ID>/docs/REQ_PROMOTION_MANIFEST.md`
- `runs/kit/<REQ-ID>/docs/INTEGRITY_EVAL.json`

These are required by some explicit follow-up KIT phases.

### Promotion reports
- `runs/kit/<REQ-ID>/promotion/<ts>/report.md`, `report.json`, `promotion.diff`, `conflicts.md` —
  gate auto-merge promotion (see `git-and-promotion.md`)
- `<file>.conflict-<REQ>-<ts>` next to a canonical file that could not be merged

## Eval and gate reports

- `runs/eval/<REQ-ID>/report_*.json`, `runs/gate/<REQ-ID>/report_*.json` — eval/gate evidence
  (with `inputs_fingerprint`, `tools`, `missing_tools`)
- `runs/<eval|gate>/<REQ-ID>/repair_<REQ-ID>_<ts>.md` — what each `--fix` repair received
- `runs/finalize/DIRTY_BEFORE.json` — the developer's changes before `/finalize`, kept out of its commits

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

This layout is what the orchestrator MCP run tools (`runs_list`, `runs_read`) read; the eval and
gate evidence of the extension flow is REQ-scoped under `runs/eval/<REQ-ID>/` and
`runs/gate/<REQ-ID>/` (see above).

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
- define tools and commands (`checks`), `setup` steps run before the services, `environment`
  (`required_variables` with `provision`, `tools`) and `services` started for the checks
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
