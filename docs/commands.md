# Commands

## Chat modes

The extension currently exposes three main chat modes:
- `free`
- `coding`
- `harper`

The webview keeps separate attachment buckets per mode.

## Slash commands

The current webview parser supports the following slash commands.

### Project / workspace commands
- `/help`
- `/init <name> [--path <abs>] [--force]`
- `/status`
- `/where`
- `/switch <name|path>`

### Harper commands
- `/idea`
- `/spec`
- `/plan`
- `/kit`
- `/eval <REQ-ID>`
- `/gate <REQ-ID>`
- `/finalize`

Optional governed methodology flags are supported on Harper phase commands:
- `--methodology bmad`
- `--methodology=bmad`
- `--agent developer`
- `--agent=developer`

`--agent` requires `--methodology`. Methodology identity is separate from `profileHint` and local agent executor selection.

Full BMAD command semantics are documented in `docs/integrations/bmad/COMMANDS.md`.

### RAG commands
- `/rag <query>`
- `/rag +<N>`
- `/rag list`
- `/rag clear`
- `/ragIndex [glob]`
- `/ragSearch <query>`

## Harper command semantics

### `/idea`
Formalizes or updates `IDEA.md`.

### `/spec`
Generates or updates `SPEC.md` from current Harper context.

### `/plan`
Generates or updates `PLAN.md` and `plan.json`.

### `/kit`
Runs the base KIT flow by default or explicit follow-up KIT phases.

Supported patterns in current parser:
```text
/kit
/kit REQ-001
/kit REQ-001 --integrity
/kit REQ-001 --hardener
/kit REQ-001 --promotion-eval
/kit REQ-001 --phases=kit,integrity_eval,promotion_hardener,promotion_eval
```

Normalized follow-up phase names currently used by the sources:
- `kit`
- `integrity_eval`
- `promotion_hardener`
- `promotion_eval`

### `/eval <REQ-ID>`
Runs eval for the target REQ using candidate artifacts and `LTC.json`.

### `/gate <REQ-ID>`
Runs gate checks for the target REQ using eval output and gate policy.

### `/finalize`
Runs release-oriented finalization.

## KIT follow-up phases

The current sources support follow-up KIT phases, but they are not equivalent to base KIT generation.

### Base phase
- `kit`

### Follow-up phases
- `integrity_eval`
- `promotion_hardener`
- `promotion_eval`

The extension performs preflight checks for required candidate artifacts before allowing follow-up phases.

## RAG slash semantics

### `/rag <query>`
Searches RAG and displays top results.

### `/rag +<N>`
Attaches a result from the last RAG search to the next call.

### `/rag list`
Lists current inline and RAG attachments.

### `/rag clear`
Clears current attachments.

### `/ragIndex [glob]`
Triggers manual indexing into the orchestrator RAG.

### `/ragSearch <query>`
Explicitly searches RAG through the orchestrator search path.

## Extension commands

The extension also contributes direct VS Code commands.

### Chat / session
- `clike.openChat`
- `clike.chat.clearSession`
- `clike.chat.openSessionFile`

### Harper / project
- `clike.harper.init`
- `clike.eval.runAll`
- `clike.gate.checkPhase`
- `clike.constraints.sync`
- `clike.plan.updateChecklist`

### Code actions / generation
- `clike.codeAction`
- `clike.addDocstring`
- `clike.refactor`
- `clike.generateTests`
- `clike.fixErrors`
- `clike.applyUnifiedDiffHardened`
- `clike.applyUnifiedDiff`
- `clike.applyNewContent`
- `clike.applyLastPatch`

### Models / services
- `clike.listModels`
- `clike.checkServices`

### RAG
- `clike.ragReindex`
- `clike.ragSearch`

### Git / promotion
- `clike.gitCreateBranch`
- `clike.gitCommitPatch`
- `clike.gitOpenPR`
- `clike.gitSmartPR`
- `clike.promoteReqSources`
- `clike.promoteReqSourcesQuick`

## Code-action intent surface

The orchestrator agent endpoint currently supports at least these intent families from the code-action path:
- `docstring`
- `refactor`
- `tests`
- `fix`

These flows are repository-file oriented and not Harper-phase oriented.

## Execution preference

The extension passes an execution preference with compatible Harper flows.

## Methodology Profile

Round 1 supports BMAD as a CLike-governed methodology profile. BMAD is not an executor and does not create a parallel pipeline.

Supported BMAD roles:
- `analyst`
- `pm`
- `architect`
- `developer`
- `ux`
- `qa`
- `tech-writer`

Phase defaults:
- `idea` -> `analyst`
- `spec` -> `pm`
- `plan` -> `architect`
- `kit` -> `developer`
- `eval` -> `qa` advisory only
- `gate` -> CLike-only, no BMAD authority
- `finalize` -> `tech-writer`

Round 2 injection boundaries:
- Cloud Harper runs receive resolved `methodology_context` only through Gateway cloud prompt composition.
- Local-agent runs receive resolved `methodology_context` through `local_agent_package` in `AGENT_*_CONTEXT.json` and `AGENT_*_PROMPT.md`.
- Gateway is not used as a local-agent prompt builder.
- Methodology guidance cannot expand `allowed_write_roots` or override `forbidden_paths`.

For the complete governance model, see `docs/integrations/bmad/GOVERNANCE_MODEL.md`.

### Current normalized values
- `auto`
- `cloud_only`
- `prefer_local_agent`
- `local_agent_only`
- `hybrid`

### Backward compatibility
Legacy values are normalized:
- `prefer_claude_code` → `prefer_local_agent`
- `claude_code_only` → `local_agent_only`

## Local executor selection

Current executor choices:
- `auto`
- `claude_code`
- `gpt_codex`

There is no current slash command in the inspected sources that changes the default local executor from chat. Executor choice is currently configuration-driven and state-driven, not command-driven.
