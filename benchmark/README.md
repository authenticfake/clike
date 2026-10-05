# Harper benchmark

Measures how well CLike turns an idea into promotable code, so that every improvement can be judged
on the same numbers: an improvement counts only if it moves a metric without degrading the others.

## Projects

| Project | Complexity | Source | What it is |
|---|---|---|---|
| **pingboard** | minimal | [`projects/pingboard/IDEA.md`](projects/pingboard/IDEA.md) | One-page status board polling three internal `/health` endpoints. FastAPI, no storage. The smallest end-to-end case. |
| **shortlink** | small, frontend + backend | [`projects/shortlink/IDEA.md`](projects/shortlink/IDEA.md) | Internal URL shortener: FastAPI + SQLite backend, static JavaScript page. Exercises two execution areas and persistence. |
| **coffeebuddy** | medium | [`../CoffeeBuddy/IDEA.md`](../CoffeeBuddy/IDEA.md) | Slack-based office coffee runs, on-prem. The repository's reference sample; more REQs and integrations. |

`projects.yaml` lists them; add a project by adding an `IDEA.md` with a `## Technology Constraints`
YAML block and an entry in `projects.yaml`.

## What a run does

For each project, against a running stack, with the same payloads the VS Code extension sends:

1. creates a workspace like `CLike: init` (tracked `harper-init` template files) under
   `$CLIKE_PROJECTS_DIR/clike-bench/<timestamp>/<project>` (the containers can read it);
2. `/spec` (TECH_CONSTRAINTS.yaml extracted from IDEA.md, as the extension does) → `/plan`;
3. for the first `--max-reqs` REQs of the plan: `/kit` → write the files → `/eval` → `/gate`.
   Eval and gate run with `regression: true` (dependency REQs' checks re-run), like the extension.
4. with `--auto-eval N`: after a failed eval, up to N KIT repair cycles from the real failures
   (as `/eval REQ --fix`, see `docs/auto-eval.md`), then the gate.

## Metrics

| Area | Metric |
|---|---|
| Promotability | REQs passing the gate; REQs passing eval; KITs accepted; repair cycles used |
| Quality | Stack compliance (generated code uses the framework declared in TECH_CONSTRAINTS) |
| Efficiency | Tokens, minutes, tokens per promoted REQ, cost upper bound (catalog pricing) |
| Governance | Steps rejected by validation or contracts |

## Running

```bash
cd docker && podman-compose up -d          # all services (healthy)
export CLIKE_API_TOKEN=...                   # same value as the stack .env
cd .. && orchestrator/.venv/bin/python benchmark/run_benchmark.py --model openai:gpt-6.1-sol --max-reqs 2
```

Local-agent runner (like *Execution = agent* in the extension: package from the orchestrator, the
agent CLI runs in the workspace with its own login, results validated by `/local-agent/complete`):

```bash
orchestrator/.venv/bin/python benchmark/run_benchmark.py --runner agent --executor claude_code --max-reqs 2
```

Results go to `benchmark/results/<timestamp>/` (`SUMMARY.md`, `results.json`; not versioned).
Live runs call the model provider and cost money: `--max-reqs` and `--projects` cap the spend.

## Scope and limits (v1)

Cloud and local-agent runners; KIT⇄EVAL repair with `--auto-eval` (cloud runner); the stack-compliance check is a keyword check on the
generated source. These are deliberate: the benchmark should be cheap and fast enough to run after
every improvement, and grow only when a decision needs more precision.
