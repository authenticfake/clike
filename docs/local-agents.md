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
- `clike.localAgent.codex.timeoutMinutes`

## Current phase support

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
