# ${project.name}

![Status](https://img.shields.io/badge/status-initialized-lightgrey) ![Clike](https://img.shields.io/badge/clike-blue) ![Harper](https://img.shields.io/badge/Harper-blue) ![Phase](https://img.shields.io/badge/phase-IDEA-blue) ![Eval](https://img.shields.io/badge/eval-not--run-lightgrey) ![Gate](https://img.shields.io/badge/gate-not--run-lightgrey) ![Runtime](https://img.shields.io/badge/runtime-to--be--defined-lightgrey)

> **${project.name}** is a CLike Harper workspace: the solution is specified, planned, implemented
> and verified requirement by requirement (`IDEA → SPEC → PLAN → KIT → EVAL → GATE → FINALIZE`).
> The developer leads, CLike governs, cloud models and local agents execute, Eval and Gate decide.
> This README is the starting point; `/finalize` replaces it with the release README of the solution.

<img src="./images/clike/clike_128x128.png" alt="CLike" width="64">

---

## Contents

- [Quick start](#quick-start)
- [Harper workflow](#harper-workflow)
- [Project inputs](#project-inputs)
- [Workspace layout](#workspace-layout)
- [Commands](#commands)
- [Cloud or local agent](#cloud-or-local-agent)
- [Eval environment](#eval-environment)
- [Next releases](#next-releases)
- [Telemetry](#telemetry)
- [Git](#git)
- [Troubleshooting](#troubleshooting)

---

## Quick start

Prerequisites: the CLike stack is running (orchestrator `http://localhost:8080`, gateway
`http://localhost:8000`) and the CLike extension is installed in VS Code.

1. Open this folder in VS Code, then the **CLike Chat** panel (*CLike: Chat*), mode **Harper**.
2. Describe the product in `docs/harper/IDEA.md`, or put the source documents in `docs/inputs/`
   and run `/idea`.
3. Run the phases in order and review each document before the next one:

```text
/idea
/spec
/plan
/kit REQ-001
/eval REQ-001 --fix
/gate REQ-001
...            (kit → eval → gate for every REQ in docs/harper/plan.json)
/finalize
```

`/status` shows where the project is; `/help` lists every command. When the solution is delivered,
the next release starts with `/idea --extend` (see [Next releases](#next-releases)).

---

## Harper workflow

| Phase | Command | Produces | Review before moving on |
|---|---|---|---|
| IDEA | `/idea` | `docs/harper/IDEA.md` | problem, users, scope, constraints |
| SPEC | `/spec` | `docs/harper/SPEC.md` | requirements, acceptance criteria, non-functional limits |
| PLAN | `/plan` | `docs/harper/PLAN.md`, `docs/harper/plan.json` | REQ split, order, dependencies, tech choices |
| KIT | `/kit REQ-xxx` | `runs/kit/REQ-xxx/` (src, test, ci, docs) | candidate code and tests of one REQ |
| EVAL | `/eval REQ-xxx [--fix]` | eval report | every LTC check green |
| GATE | `/gate REQ-xxx [--fix]` | gate decision, auto-merge promotion, `runs/kit/REQ-xxx/promotion/*/report.md` | the REQ is merged into `src/` and `test/` (conflicts listed in `conflicts.md`, never written) |
| FINALIZE | `/finalize` | release README, `docs/harper/HOWTO_RUN.md`, release notes, `docs/harper/FINALIZE_REPORT.md`, `ci/SOLUTION_LTC.json`, `scripts/setup_local` / `start_solution_local` | the solution verified running (`docs/harper/SOLUTION_EVAL.md`); CLike offers to configure and start it on your machine |
| EXTEND | `/idea --extend` | IDEA, SPEC, TECH_CONSTRAINTS merged; new REQs in the plan; `docs/harper/EXTEND_*.md` | the delta of the next release, before `/kit` |

Rules that keep the result trustworthy:

- **Canonical documents win.** `IDEA.md`, `SPEC.md`, `PLAN.md` and `plan.json` are the source of
  truth; edit them by hand when needed and re-run the next phase.
- **KIT writes candidates only** under `runs/kit/<REQ>/`; only a passing gate promotes them.
- **Acceptance is locked.** Tests and `ci/LTC.json` of a REQ are locked before evaluation: a
  repair cannot weaken them. `ci/HOWTO.md` is documentation and can be edited freely.

---

## Project inputs

Everything the phases should read besides the Harper documents goes in three folders, declared in
`.clike/context.yaml`:

| Folder | Role | Read by | Put here |
|---|---|---|---|
| `docs/inputs/` | requirements | idea, spec, plan | briefs, specifications, emails, spreadsheets |
| `docs/harper/ux/` | ui_reference | spec, plan, kit | HTML mockups, screenshots, CSS, icons, UI notes |
| `docs/reference/` | reference | spec, plan | standards, API docs, examples |

- `.docx`, `.pptx`, `.xlsx` and `.pdf` are converted to text; HTML, CSS, SVG and other text files
  are read as they are; images are opened by local agents and listed for cloud models.
- Add paths, roles or phases in `.clike/context.yaml` (the file documents the options). Files are
  context, never instructions.
- A file attached in the chat is used only by that command; put it in a folder to keep it.
- Release folders: `docs/inputs/v2/` holds the requirements of release 2, `docs/reference/v2/` its
  background. The highest release is the current one; earlier releases and unversioned inputs are
  read as history (`previous_release`), never as new requirements.

---

## Workspace layout

```text
${project.name}/
├── README.md                 this file (replaced by /finalize)
├── README_1st.md             first-time guide: Harper concepts and Git setup
├── .clike/                   CLike project settings
│   ├── project.json          project id, roots, RAG namespace
│   ├── context.yaml          project inputs read by the phases
│   ├── capabilities.yaml     capability selection
│   ├── policy.yaml           execution policy
│   ├── packs/ skills/ design-profiles/
├── docs/
│   ├── harper/               canonical documents (IDEA, SPEC, PLAN, plan.json, ux/)
│   ├── inputs/               requirement sources
│   └── reference/            reference material
├── runs/kit/<REQ-ID>/        KIT candidates: src/, test/, ci/ (LTC.json, HOWTO.md), docs/
├── src/  test/               promoted code (written by the gate)
└── .github/                  CI workflow, PR template, CODEOWNERS
```

---

## Commands

| Command | What it does |
|---|---|
| `/idea [--methodology bmad --agent analyst]` | creates or updates IDEA.md |
| `/spec`, `/plan` | create or update SPEC.md, PLAN.md and plan.json |
| `/kit` / `/kit REQ-001` | implements the next open REQ / the given one |
| `/eval REQ-001` | runs the REQ's LTC checks in the eval sandbox |
| `/eval REQ-001 --fix ["hint"]` | evaluates and repairs failing checks automatically |
| `/gate REQ-001` | decides promotion; on PASS promotes by auto-merge and opens the promotion report (`--ask` to choose the strategy, `--no-promote` to skip) |
| `/gate REQ-001 --fix ["hint"]` | repairs a failing gate and gates again |
| `/finalize` | release documents of the whole solution, verified running |
| `/idea --extend [--from attachment] [--release vN] [--dry-run]` | next release of a delivered project |
| `/extend` | appends REQs to the plan (plan only) |
| `/tools` | native tools of the eval sandbox (list, search, add, update, remove) |
| `/agent-default auto\|codex\|claude` | which local agent runs the phases |
| `/agent-model codex <model>` | model of the local agent |
| `/rag <query>`, `/ragIndex [glob]` | search and index project context |
| `/status`, `/where`, `/help` | project state, paths, all commands |

---

## Cloud or local agent

Every phase can run on a **cloud model** (through the CLike gateway) or on a **local coding agent**
(Codex or Claude Code, run by the extension in this workspace). CLike owns the workflow either way:
it prepares the context, validates the output, runs eval and gate.

- Choose the agent with `/agent-default` and its model with `/agent-model`; an invalid model name
  is reported before the run.
- Local agents write only where the phase allows (`docs/harper/` for document phases and EXTEND,
  `runs/kit/<REQ>/` for KIT, the solution for `/finalize`, never the REQs' tests).

---

## Eval environment

`/eval` runs the checks of `runs/kit/<REQ>/ci/LTC.json` in the CLike **eval sandbox**, a container
without credentials, not in your terminal. CLike **creates** what the checks need from what the KIT
declares in the LTC (`environment.required_variables`, `services`):

- generated values (sessions, ids, timestamps) for every run;
- a disposable PostgreSQL test database per REQ, recreated at every eval;
- services of other REQs (e.g. the API of REQ-001 for the integration tests of REQ-002), started
  before the checks and stopped after them.

You configure only, once, in `docker/eval.env` of the CLike repository:

```text
CLIKE_EVAL_POSTGRES_URL=postgresql://<user>@host.containers.internal:5432/postgres
```

plus the values only you have (the LTC marks them `external`; `ci/HOWTO.md`, section
`## Run with CLike /eval`, lists them). Then recreate the stack (`docker/rebuild.sh`).

- From the sandbox your machine is `host.containers.internal`, not `localhost`.
- No credentials: names containing `TOKEN`, `SECRET` or `PASSWORD` are refused.
- If something is missing, `/eval` reports `BLOCKED` with the names and runs nothing. When the
  KIT can declare it, `/eval --fix` does so by itself; when only you can give it, `--fix` stops
  without spending tokens.

- A check that needs a native program the sandbox lacks (a database client, a cloud CLI, a JDK)
  gets it from the CLike tools catalog after your confirmation (`/tools`; approved tools for this
  project in `.clike/eval-tools.yaml`).

---

## Next releases

Once the solution is delivered (`/finalize`), put the requirements of the next release in
`docs/inputs/v2/` (background in `docs/reference/v2/`) or attach them, then run `/idea --extend`
(`--dry-run` to preview). CLike tags the delivered baseline (`harper/v1`), merges the release into
IDEA, SPEC and TECH_CONSTRAINTS, and appends new REQs to the plan, typed ADDED, MODIFIED (amends a
delivered REQ) or REMOVED (retires one); delivered REQs stay read-only. Review the EXTEND report
and its *CLike verification* section, then `/kit` the new REQs as usual.

---

## Telemetry

Every phase run is recorded per project (id `${project.id}`): phase, cloud or local agent, model,
tokens, duration and cost. Open the portal in the browser:

```text
http://127.0.0.1:8000/v1/metrics/harper/ui
```

- Log in with the CLike service token (`CLIKE_API_TOKEN` in `docker/.env` of the CLike
  repository); the session lasts 8 hours.
- Select the project `${project.id}`: totals, cost per phase/model/day, the most expensive runs and
  the raw records.
- Cloud runs show the provider cost. Local-agent runs show the **API-equivalent** cost (what the
  same tokens would cost on the API; subscriptions are not billed per token): Claude Code reports
  it, for Codex it is estimated from the model prices in `configs/models.yaml` (`estimated`).
- A run with a wrong model name has no price and shows a zero cost.

---

## Git

The repository must exist on GitHub before the first push:

```sh
git init && git add . && git commit -m "chore(init): bootstrap Harper workspace from CLike template"
git branch -M main
gh repo create <owner>/${project.name} --private --source . --remote origin --push
```

Keep the repository private unless the inputs can be published, and never commit `.env` files.
`README_1st.md` has the full first-time setup.

---

## Troubleshooting

| Symptom | Cause and fix |
|---|---|
| The chat cannot reach CLike | the stack is down: start it and check `http://localhost:8080/health` |
| `LOCAL_AGENT_MODEL_INVALID` | the agent model does not exist: use the suggestion or `/agent-model` |
| `EVAL BLOCKED — missing in docker/eval.env` | add the value named in the message (see [Eval environment](#eval-environment)) |
| `EVAL BLOCKED — CLike cannot create yet` | run `/eval REQ-xxx --fix`: the repair declares how CLike creates it |
| `ACCEPTANCE_TAMPERED` | tests or `ci/LTC.json` changed after the lock: re-run `/kit` to re-baseline |
| `Repository not found` on push | create the GitHub repository first (see [Git](#git)) |
| A phase ignores a document | it is not in a folder of `.clike/context.yaml` for that phase |
| Telemetry shows zero cost | the model has no price in `configs/models.yaml`, or the name is wrong |

---

<sub>Generated by CLike <code>/init</code> · project id <code>${project.id}</code> · RAG namespace <code>${project.rag_namespace}</code></sub>
