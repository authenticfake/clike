# GET STARTED

A first project end to end with CLike, then the everyday features: the agent chat, auto-eval,
acceptance-first, and CLike from Claude Code or Codex. Install first: [INSTALL](INSTALL.md).

## 1. The chat and its three modes

Open **CLike: Chat (Q&A / Harper / Coding)**.

| Mode | For | What happens |
|---|---|---|
| **Free (Q&A)** | questions about the project | answers only, nothing is written |
| **Coding** | quick code generation | files written under `generated/<id>/` |
| **Harper** | the governed delivery process | IDEA → SPEC → PLAN → KIT → EVAL → GATE → FINALIZE |

**Execution** (selector in the chat): *cloud* (the model chosen in the model selector, through the
gateway) or *agent* (Claude Code / Codex on your machine). `/agent-model` shows what is in use.

### Talking to the agent directly

With execution = agent, the chat **is** a conversation with Claude Code or Codex:

- each mode keeps one agent session: the next message resumes it, so the agent remembers the
  conversation (`/agent-session` shows the sessions, `/agent-session new` starts a fresh one);
- the agent's answer and the tools it uses (files read or edited, commands) appear live;
- **Cancel** stops the agent;
- Free and Harper free text are read-only; Coding lets the agent write under `generated/`;
- in **Coding**, every edit and command waits for your choice (**Allow**, **Allow all this turn**,
  **Deny**) and writes outside `generated/` are denied without asking. Claude Code asks through
  CLike, Codex runs through `codex app-server`. `clike.agentChat.approvals = auto` turns the
  questions off (edits under `generated/` then run without asking).

## 2. A first Harper project

The pilots in `benchmark/projects/` (`pingboard`: backend only; `shortlink`: frontend + backend)
are small IDEAs to start with.

1. Create a folder under `CLIKE_PROJECTS_DIR`, open it in VS Code, chat in **Harper** mode.
2. `/init pingboard`
3. Put the IDEA in `docs/harper/IDEA.md` (its *Technology Constraints* block becomes
   `TECH_CONSTRAINTS.yaml`), or write it with `/idea`.
4. `/spec` then `/plan` → `docs/harper/SPEC.md`, `PLAN.md`, `plan.json` (the REQs).
5. For each REQ:
   ```text
   /kit REQ-001            # code, tests, eval profile under runs/kit/REQ-001/
   /eval REQ-001 --fix     # canonical eval; on failure a governed repair, then eval again
   /gate REQ-001           # promotion decision
   ```
6. `/finalize` when the REQs are done.

`/help` lists every command; `/status` shows where you are.

## 3. What CLike guarantees

- **Tests are locked** at the first eval: a repair cannot weaken them. If a test is itself wrong,
  the repair fixes the test (assertions unchanged) and the gate asks for your review.
- **Regression**: eval and gate also re-run the tests of the REQs already promoted.
- **Sandbox**: checks run in an isolated container without credentials.
- **Audit**: every amendment and override is recorded.

## 4. Options worth knowing

| Setting / command | Effect |
|---|---|
| `/eval REQ --fix ["hint"]` | auto-eval: up to `clike.autoEval.maxCycles` (2) governed repairs; rerun to continue, the hint guides the fix |
| `clike.autoEval.afterKit` | auto-eval after every `/kit` |
| `clike.kit.acceptanceFirst` | tests written from SPEC/PLAN and locked **before** the code |
| `clike.eval.regression` (on) | regression of promoted REQs in eval and gate |
| `clike.gate.strictWarnings` | warnings block the gate |
| `/agent-default`, `/agent-model`, `/agent-session` | choose the agent, its model, its session |

Details: [auto-eval](auto-eval.md) · [commands](commands.md) · [local agents](local-agents.md).

## 5. CLike from Claude Code or Codex

After the MCP setup in [INSTALL §6](INSTALL.md#6-use-clike-from-claude-code-or-codex-mcp), ask your
agent in plain words, for example:

```text
Use the clike tools: list the REQs of /path/to/pingboard, then run the KIT of the next open REQ,
evaluate it with fix=true and run the gate. Report the outcome of each step.
```

The operational tools (`harper_run_phase`, `eval_run`, `gate_check`, `harper_run_status`) run inside
VS Code through CLike's normal flow: same test lock, gate and write rules as the chat. Long phases
return `status: running` and a `run_id` to poll; `eval_run` with `fix` returns the final report after
the repairs. Overrides, promotion and git are not exposed. Codex: approve the CLike tools once
(INSTALL §6) or each call asks.

## 6. See what happened

- **Chat** and the **Files** / **Text** tabs for each run.
- **Telemetry portal** `http://127.0.0.1:8000/v1/metrics/harper/ui`: tokens, cost, model per phase,
  cloud and agent runs (agent cost is the API-equivalent cost).
- **Reports** under `runs/eval`, `runs/gate` and the KIT folders.

## 7. Troubleshooting

| Symptom | Fix |
|---|---|
| Eval returns 503 or the orchestrator restarts | container VM memory too low: raise it ([INSTALL §1](INSTALL.md#1-requirements)), lower `CLIKE_EVAL_SANDBOX_MEM_LIMIT` |
| "No local agent is available" | install/log in `claude` or `codex`, or switch execution to cloud |
| An answer from the agent seems to forget the conversation | `/agent-session` — a failed resume starts a new session |
| Browser (Playwright) checks are slow the first time | Chromium is downloaded on first use in the sandbox |
