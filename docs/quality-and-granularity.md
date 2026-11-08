# Quality and granularity — complete requirements, sized for the executor

CLike sizes the requirements on what the KIT executor can sustain and makes every requirement
complete: not only the successful path, but the error, empty, denied, expired and limit cases each
capability implies, each one proved by a test before the REQ is promoted. The same rules reach the
cloud models and the local agents.

## 1. The REQ capacity profile

`/plan` sizes the REQs on a profile (`clike.plan.capacityProfile`, default `auto`):

| Profile | Executor | Unit of work | Budget |
|---|---|---|---|
| **C1** | cloud, one generation call per REQ | one REQ of one domain | 6–8 acceptance criteria, about 2–3k lines of source and tests |
| **C2** | local coding agent (multi-turn, runs its own checks) | a vertical slice: API, data, UI and tests of the same capability in one REQ | 10–14 criteria, about 3–6k lines, up to 3 domains |
| **C3** | long-running agent, or a cloud loop driven by CLike | an epic with an internal feature list | 5–15 features, each within the C2 size |

`auto` chooses C2 with a local agent and C1 in the cloud. The plan never splits a capability by
technical layer when the budget holds both layers, merges REQs that only add bookkeeping, and splits
a unit above the budget. Every REQ of `plan.json` carries its `profile`.

**Shared seams.** The first REQ that creates an application owns its extension points (routes and
modules registered by convention, one migration file per REQ, a service registry); later REQs add
files and register through them instead of rewriting shared composition files — the main cause of
regressions between REQs.

**Epics (C3).** An epic lists its `features` in `plan.json`. Its KIT writes
`runs/kit/<REQ>/docs/FEATURES.json` (only `status` and `checks` change afterwards) and delivers the
features one at a time, appending to `runs/kit/<REQ>/docs/PROGRESS.md`. The eval reports each feature
not delivered (`acceptance::features::<id>`), and the auto-eval repair loop continues the epic with at
least one cycle per planned feature. A cloud KIT (one bounded call) writes the list and the first
features, each repair the next ones; a local agent may deliver several per run.

## 2. Journey scenarios — from SPEC to the gate

`/init` installs eight **journey skills** in `.clike/skills/`, each a catalog of the scenarios a
capability implies, with stable ids and an EARS statement:

| Journey | Examples |
|---|---|
| `journey-identity-access` (IAM) | registration, login, wrong credentials, lockout, password reset, session expiry, logout, permission deny |
| `journey-data-lifecycle` (DAT) | per-field validation, duplicates, concurrent edit, delete with confirmation, empty list, not found |
| `journey-ui-states` (UI) | loading, empty, visible actionable error, denied, offline/timeout, pending submit, keyboard and focus, product language |
| `journey-async-jobs` (JOB) | queued, progress, retry, timeout, cancel, idempotent resubmit, resume after restart |
| `journey-integration` (INT) | provider down, timeout, rate limited, malformed response, expired credentials |
| `journey-files-export` (FIL) | empty or oversized file, wrong format, unsafe names, denied download |
| `journey-industrial-control` (IND) | interlock, fault and alarm, emergency stop, communication loss, out-of-range sensor, safe start |
| `journey-api-contract` (API) | 4xx with readable error body, 401, 403, 409, 404, versioning, pagination |

The thread, the same for every executor:

1. **SPEC** — a `## Scenarios` section: every scenario of every journey a use case touches,
   `included` or `excluded — <reason>`.
2. **PLAN** — every included scenario is owned by one REQ (`reqs[].scenarios`) and appears as an
   acceptance bullet starting with its id. After `/plan` the chat reports the included scenarios no
   REQ owns and the exclusions without a reason.
3. **KIT** — the KIT gets the statements of its scenarios; each is proved by a blocking check listed
   in `docs/ACCEPTANCE.json`, by a test that carries the scenario id, asserting what the user or the
   caller sees (the error text in the UI, the API error body, the safe state of the device).
4. **EVAL / GATE** — `acceptance::coverage` blocks the REQ while a scenario has no blocking check or
   no test names it.

## 3. Skills on every executor

One source, `.clike/skills/`:

- **Local agents** — `/init`, the command **CLike: Sync agent skills** and every local-agent Harper
  run (`clike.agentSkills.autoSync`) install the skills as native skills of the agents
  (`.claude/skills/`, `.agents/skills/`) in the open Agent Skills format, keep a CLike block of rules
  in `CLAUDE.md` and `AGENTS.md`, and add a guard hook that refuses writes to the REQ's tests and CI
  during `/eval`. Skills and files CLike does not manage are never touched.
- **Cloud** — the skills `/plan` selects for a REQ go into the prompt (the shared enforcement layer
  of several skills said once, every skill whole).
- **Vendored skills** — third-party skills live in `.clike/skills/vendor/<vendor>/<skill>/` with
  `VENDORED.json` (repository, pinned commit, license, review date, digest of every file). They are
  installed for the agents as `<vendor>-<skill>` with their license and selectable for the cloud like
  any skill. Maintenance with `tools/skills_vendor.py`: `verify` (run by the tests), `check-updates`,
  `update <vendor> [--ref R] [--apply]` (diff, license check and review findings before re-pinning).
  Nothing is fetched at run time.
- **web-e2e-harness** — deterministic frontend checks in the eval sandbox: lockfile installs, the app
  started by the test runner on loopback, cookies that work over the HTTP loopback origin, stable
  selectors, condition waits.

## 4. Repairs in the KIT's session

An auto-eval repair of a REQ resumes, forked, the local-agent session that wrote its KIT
(`clike.localAgent.resumeRepairs`, sessions younger than 24 hours, same agent and REQ): the agent
already knows the code it wrote and its context is warm.

## 5. Measure

Every Harper call records its REQ and duration; the telemetry portal (`/harper/aggregate`) returns
`per_req` with calls, cost, tokens, time and phases.

## Settings

| Setting / command | Default | Effect |
|---|---|---|
| `clike.plan.capacityProfile` | `auto` | C1, C2 or C3 sizing of the plan |
| `clike.agentSkills.autoSync` | on | skills, rules and guard hook kept current before each local-agent run |
| **CLike: Sync agent skills** | — | install the skills for the local agents now |
| `clike.localAgent.resumeRepairs` | on | a repair resumes the KIT's agent session |
