# Local Agents

## Overview

The current extension supports a local-agent execution path for compatible
Harper flows **and** for the standalone CLike chat modes (Free Q&A and Coding).
Across all CLike modes, a request can run via the local agent (Claude Code /
Codex CLI) instead of the cloud, governed by the Execution preference.

This path is implemented in:
- `extensions/vscode/local-agent-executors.js`
- `extensions/vscode/utility.js`
- `extensions/vscode/extension.js`
- `orchestrator/routes/v1.py` (free/coding local-execution package)
- `gateway/providers_availability.py` and `gateway/routes/models.py` (provider/key availability)

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

#### Attachments and run tracking

For document phases the orchestrator **materializes the current-run attachments**
into a workspace-local, run-scoped folder so the agent reads them from its cwd
without any external-path Read approval. Everything is tracked under
`runs/<phase>/` (e.g. `runs/idea/`):

- `runs/<phase>/docs/AGENT_<TITLE>_CONTEXT.json` — the package the agent must
  treat as the source of truth (mission, required reads, allowed writes,
  attachment manifest).
- `runs/<phase>/docs/AGENT_<TITLE>_PROMPT.md` — the rendered execution prompt.
- `runs/<phase>/attachments/<name>` — one materialized copy per attachment.

Attachment rules:
- Multiple files are supported; each file up to **10 MB** is inlined by the
  extension and written to `runs/<phase>/attachments/`. Files over 10 MB are
  referenced by path only and are **not** materialized (a warning is shown).
- The attachment **manifest** (inside `AGENT_*_CONTEXT.json` and the prompt)
  exposes `name`, `workspace_path` (the run-local copy the agent reads),
  `original_path` (metadata only — never read), `mime`, and `size`.
- `/idea` requires at least one attachment; `/spec` and `/plan` do not.
- **PDF** attachments are read for their text; **image** attachments are
  described via vision and used as evidence (native multimodal Read of the
  Claude Code executor; Codex support for images/PDF may be limited).
- Non-text binaries are excluded from RAG indexing; only their materialized copy
  reaches the agent.

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

## Standalone Free (Q&A) and Coding local execution

Beyond the Harper pipeline, the local agent also serves the standalone CLike
chat modes. These flows are intentionally separate from the Harper machinery:
there is no REQ binding, no `runs/kit/<REQ-ID>/` tree, and no Harper output
validation.

The architecture mirrors Harper: the orchestrator (`/v1/chat` and `/v1/generate`)
assembles the prompt and context and returns a local-execution package
(`{ local_execution: true, mode, prompt, executor_hint, output_root? }`) instead
of calling the gateway; the extension is the only component that spawns the CLI.

### Free chat (Q&A)
- Invocation is **read-only** (Claude Code in print mode; Codex `exec`).
- The agent answer (stdout) is rendered as a normal chat bubble, badged with the
  agent used — `agent-claude` or `agent-codex` — the way the cloud path shows the
  model name.
- A short execution synthesis is shown in the **Text** panel.

### Coding
- Invocation is **write-capable**; the agent writes the requested artifacts
  (documentation, code, images, etc.) under `generated/<id>/` in the workspace
  root, mirroring the cloud generation layout.
- The chat bubble shows the agent badge plus the generated-file list; the files
  are already on disk and are clickable in the **Files** tab (no Apply step).

### Authentication
Local agents authenticate through their own CLI session. No cloud API key is
required or forwarded for the local path; cloud provider keys are stripped from
the spawned process environment by default.

## Provider availability and executor gating

Provider availability is computed once at the gateway, which is the only process
that holds the cloud API keys:

- Cloud providers (`openai`, `anthropic`, `deepseek`) are available when their API
  key env var is set to a non-empty value.
- Local providers (`ollama`, `vllm`) are available when their base URL responds.

`GET /v1/providers` exposes this snapshot and `GET /v1/models` annotates each
model with `available` / `unavailable_reason`. The orchestrator hides models whose
provider is unavailable and forwards the `providers` summary to the extension.

The extension uses this to gate the Execution selector:
- When at least one cloud key is configured, all Execution options are available
  and `agent only` (`local_agent_only`) is the default.
- When no cloud key is configured, the cloud-dependent options are disabled and
  only `agent only` remains selectable.

Profile/routing resolution is unchanged. If a request resolves to a provider
whose key is not configured (for example, an OpenAI model while only an Anthropic
key is set), the orchestrator returns a clean message that the extension renders
in the chat **Text** panel instead of letting the gateway raise a raw 401.

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
- Local-agent execution covers all Harper phases (`/idea`, `/spec`, `/plan`, `/kit`, `/eval`, `/finalize`, `/extend`)
- Standalone Free (Q&A) and Coding chat modes can run via the local agent
- EVAL pre-pass exists
- `AGENT_EXECUTION_CONTEXT.json` is part of the Harper execution contract
- Provider/key availability gates the model list and the Execution selector

### Not stable enough to document as unrestricted capability
- unrestricted follow-up KIT phase execution
- local agents as canonical gate authority
