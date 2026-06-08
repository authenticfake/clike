# Local Agents

## Overview

The current extension supports a local-agent execution path for compatible Harper flows.

This path is implemented in:
- `extensions/vscode/local-agent-executors.js`
- `extensions/vscode/utility.js`
- `extensions/vscode/extension.js`

## Supported local executors

Current supported executor IDs:
- `claude_code`
- `gpt_codex`

Display labels used by the extension:
- `Claude Code`
- `GPT Codex`

## Execution preference model

### Current normalized execution preferences
- `auto`
- `cloud_only`
- `prefer_local_agent`
- `local_agent_only`
- `hybrid`

### Backward compatibility normalization
The extension normalizes legacy values:
- `prefer_claude_code` → `prefer_local_agent`
- `claude_code_only` → `local_agent_only`

## Executor selection model

Executor selection is resolved in this order:
1. explicit executor in state, if any
2. configured preferred executor
3. available executor fallback order

Current fallback order adds both:
- `gpt_codex`
- `claude_code`

The extension checks:
- whether the executor is enabled
- whether the command exists on the machine
- whether the phase is supported

## Current settings

### Common local-agent settings
- `clike.localAgent.enabled`
- `clike.localAgent.preferredExecutor`
- `clike.localAgent.allowEval`
- `clike.localAgent.restrictToKitPhases`
- `clike.localAgent.timeoutMinutes`

### Claude Code settings
- `clike.claudeCode.enabled`
- `clike.claudeCode.command`
- `clike.claudeCode.printModeFlag`
- `clike.claudeCode.timeoutMinutes`
- `clike.claudeCode.permissionMode`

### GPT Codex settings
- `clike.localAgent.codex.enabled`
- `clike.localAgent.codex.command`
- `clike.localAgent.codex.approvalMode`
- `clike.localAgent.codex.printModeFlag`
- `clike.localAgent.codex.sandboxMode`
- `clike.localAgent.codex.timeoutMinutes`

`clike.localAgent.codex.sandboxMode` defaults to `auto`. In `auto`, CLike launches
Codex with `--sandbox workspace-write` for phases that must generate files and
with `--sandbox read-only` for inspect-only work. The supported explicit values
are `read-only`, `workspace-write`, and `danger-full-access`; `workspace-write`
is the expected mode for normal candidate generation.

## Codex write mode

KIT, eval repair/hardening, and finalize local-agent runs are write-required
tasks. CLike must not launch Codex for those phases in `read-only` mode because
the agent is expected to create or patch controlled candidate artifacts.

For `/kit`, Codex may write only inside the CLike candidate tree for the active
REQ:
- `runs/kit/<REQ-ID>/src/**`
- `runs/kit/<REQ-ID>/test/**`
- `runs/kit/<REQ-ID>/ci/**`
- `runs/kit/<REQ-ID>/docs/**`

Canonical workspace roots remain forbidden local-agent outputs:
- `src/**`
- `test/**`
- `tests/**`
- `docs/harper/**`
- `.git/**`

If the selected Codex sandbox mode is not write-capable for a write-required
phase, CLike aborts before launching Codex with
`LOCAL_AGENT_WRITE_MODE_UNAVAILABLE`. The diagnostic includes the phase, REQ,
executor, selected sandbox, and allowed write roots. This is intentionally a
fail-fast condition; a read-only Codex launch cannot produce a valid KIT
candidate.

After Codex exits, CLike validates the collected candidate artifacts before
submitting them to `/local-agent/complete`. For KIT, a result that contains only
the local-agent input package under `runs/kit/<REQ-ID>/docs/**` is rejected with
`LOCAL_AGENT_REQUIRED_OUTPUTS_MISSING`. At minimum, the candidate must include
readable artifacts under the required `src`, `test`, and `ci` KIT roots unless a
future active contract explicitly marks those output families as unsupported.

To diagnose a read-only launch, inspect the extension output line that starts
with `[CLike] [local-agent:gpt_codex]`. A valid write-required Codex KIT launch
shows an argument list containing `--sandbox` and `workspace-write`.

## Current phase support

Execution-agent (local-agent) support now covers the early Harper document
phases as well as the existing actuator phases:
- `/idea`
- `/spec`
- `/plan`
- `/kit`
- `/eval`
- `/finalize`
- `/extend`

All phases share the same architecture: orchestrator execution policy,
`run_phase` dispatch, the local-agent package envelope, the
`/local-agent/complete` normalization step, the extension actuator, and the
phase-aware write policy. Cloud and local execution remain semantically
equivalent; CLike governance stays canonical and validates every result. The
agent performs bounded work; CLike validates and governs.

### Early document phases (`/idea`, `/spec`, `/plan`)
These phases produce only their canonical Harper documents. The write policy is
narrow:
- `/idea` local agent writes `docs/harper/IDEA.md`.
- `/spec` local agent writes `docs/harper/SPEC.md`.
- `/plan` local agent writes `docs/harper/PLAN.md` and `docs/harper/plan.json`
  (plus `docs/harper/lane-guides/<lane>.md` for each detected lane).

`docs/harper/` remains protected: any other `docs/harper/` path, and all of
`src/`, `test/`, `tests/`, and `.git/`, stay forbidden for these phases.
Methodology/BMAD context is passed through when enabled, but BMAD is never
mandatory and the canonical Harper outputs above are always required.

### KIT
Both local executors currently support:
- base `kit`

### EVAL
Both local executors can participate in:
- local eval pre-pass when `clike.localAgent.allowEval=true`

### Follow-up KIT phases
Current sources explicitly treat follow-up phases as restricted when:
- `clike.localAgent.restrictToKitPhases=true`

This means local agents are currently intended first for:
- base KIT generation
- optional eval pre-pass

They are not currently a full unrestricted replacement for all Harper phases.

## `AGENT_EXECUTION_CONTEXT.json`

Before invoking a local agent, the extension writes:
- `runs/kit/<REQ-ID>/docs/AGENT_EXECUTION_CONTEXT.json`

This file is the primary local execution contract.

### For KIT
The contract includes:
- requested phases
- required reads
- allowed write roots
- forbidden paths
- expected outputs
- generation rules
- project metadata
- repository root assumptions

### For EVAL
The contract includes:
- `eval_contract`
- tools
- commands
- reports
- gate policy
- constraints applied
- evaluation rules

## Local KIT prompt model

The extension builds a dedicated local KIT prompt that instructs the executor to:
- read `.clike/project.json`
- read plan and core Harper docs
- follow `AGENT_EXECUTION_CONTEXT.json`
- write only under candidate roots
- not modify canonical plan files
- not perform Git actions
- generate real source, tests, and docs

Required candidate outputs explicitly listed by the prompt:
- `runs/kit/<REQ-ID>/src/...`
- `runs/kit/<REQ-ID>/test/...`
- `runs/kit/<REQ-ID>/ci/LTC.json`
- `runs/kit/<REQ-ID>/ci/HOWTO.md`
- `runs/kit/<REQ-ID>/ci/requirements.txt`
- `runs/kit/<REQ-ID>/docs/README_<REQ-ID>.md`
- `runs/kit/<REQ-ID>/docs/KIT_<REQ-ID>.md`

## Local eval prompt model

The extension builds a dedicated local eval pre-pass prompt that instructs the executor to:
- read `LTC.json`
- read `AGENT_EXECUTION_CONTEXT.json`
- read `HOWTO.md`
- operate only inside candidate roots
- run checks and limited remediation
- avoid canonical workspace roots
- avoid Git operations
- return a concise stdout summary

## Fallback behavior

If local-agent execution is requested but no suitable executor is available:
- the extension logs availability
- `local_agent_only` fails hard
- other compatible preferences fall back to the cloud path

If local KIT fails:
- `local_agent_only` fails hard
- otherwise the extension falls back to current CLike cloud path

If local eval pre-pass fails:
- canonical eval still runs unless the flow is explicitly blocked by `local_agent_only`

## What should be documented as current truth

### Current truth
- Local agent execution exists
- GPT Codex and Claude Code are both supported
- KIT is the main supported local flow
- EVAL pre-pass exists
- `AGENT_EXECUTION_CONTEXT.json` is part of the execution contract

### Not stable enough to document as unrestricted capability
- unrestricted follow-up phase execution
- chat-command based executor switching
- local agents as canonical gate authority
