# Quality and granularity — complete requirements, sized for the executor

CLike sizes the requirements on what the KIT executor can sustain and makes every requirement
complete: not only the successful path, but the error, empty, denied, expired and limit cases each
capability implies, each one proved by a test before the REQ is promoted. The same rules reach the
cloud models and the local agents.

## 1. The REQ capacity profile

`/plan` sizes the REQs on a profile (`clike.plan.capacityProfile`, default `C2`):

| Profile | Executor | Unit of work | Budget |
|---|---|---|---|
| **C1** | cloud, one generation call per REQ | one REQ of one domain | 6–8 acceptance criteria, about 2–3k lines of source and tests |
| **C2** | local coding agent (multi-turn, runs its own checks) | a vertical slice: API, data, UI and tests of the same capability in one REQ | 10–14 criteria, about 3–6k lines, up to 3 domains |
| **C3** | long-running agent, or a cloud loop driven by CLike | an epic with an internal feature list | 5–15 features, each within the C2 size |

The default C2 fits KITs written by a coding agent, whatever runs `/plan`; choose C1 when the KITs
run in the cloud. `auto` follows the executor of the `/plan` run: C2 with a local agent, C1 in the cloud. The plan never splits a capability by
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

`/init` installs fifteen **journey skills** in `.clike/skills/`, each a catalog of the scenarios a
capability implies, with stable ids and an EARS statement (`required`, or `conditional` with the
condition in brackets):

| Journey | Examples |
|---|---|
| `journey-identity-access` (IAM) | registration, login, wrong credentials, lockout, reset, session expiry, logout, permission deny, no account enumeration, CSRF, session fixation, refresh-token reuse, password policy, federated sign-in checks |
| `journey-data-lifecycle` (DAT) | validation, duplicates, concurrent edit, delete, empty list, not found, boundary values, delete with dependents, data-preserving migrations, time zones, no partial write |
| `journey-ui-states` (UI) | loading, empty, visible actionable error, denied, offline/timeout, pending submit, keyboard and focus, product language, success confirmed, unsaved changes |
| `journey-async-jobs` (JOB) | queued, progress, retry, timeout, cancel, idempotent resubmit, resume after restart, transactional outbox, ordering per key, leases, backpressure |
| `journey-integration` (INT) | provider down, timeout, rate limited, malformed response (tolerant reader), expired credentials, outbound webhooks, reconciliation, pinned contract |
| `journey-files-export` (FIL) | empty or oversized file, wrong format, unsafe names, denied download, archive limits, malware scan, spreadsheet formula injection, expiring links |
| `journey-industrial-control` (IND) | interlock, alarms, emergency stop, communication loss, bad sensor, safe start, commands safe by default, command/feedback discrepancy, watchdog, alarm flood, single point of control |
| `journey-api-contract` (API) | readable 4xx, 401, 403, 404, 409/412, versioning, pagination, size and media type, rate limit, object-level authorization, server-owned fields, entity tags, CORS |
| `journey-runtime-config` (CFG) | starts on local defaults, fails fast on missing config, no secrets in files or logs, documented configuration, production adapters only on selection, route parity, readiness, egress allowlist |
| `journey-tenancy` (TEN) | tenant from the identity, cross-tenant access refused, filtered collections and exports, tenant kept by jobs and caches, offboarding |
| `journey-ai-guardrails` (AIR) | output validated before use, model failure fallback, injected instructions ignored, deterministic eval set, grounded answers or abstain, scoped retrieval, tool allowlist |
| `journey-mobile-offline` (MOB) | offline work persists, sync exactly once, conflicts surfaced, sync failures visible, permission denied, interrupted flow resumes |
| `journey-ml-reproducibility` (MLR) | reproducible run, metric threshold gates, pinned and validated dataset, validated inference input, training/serving parity, drift |
| `journey-notifications` (NTF) | notified once, recipient language and safe content, retries and failed state, preferences and unsubscribe, expiring links |
| `journey-payments` (PAY) | charge once, decline handled, verified idempotent webhooks, exact amounts, extra authentication, refunds, reconciliation |

Each journey has `references/test-idioms.md` with one section per language (Python, TypeScript/web,
Java, .NET, Go, Rust, mobile, infrastructure as code, PLC/SCADA): the KIT prompt carries the sections
of the REQ's lane for the journeys it owns, to the cloud and to the agents alike.

The thread, the same for every executor:

1. **SPEC** — a `## Scenarios` section: every scenario of every journey a use case touches,
   `included` or `excluded — <reason>`.
2. **PLAN** — every included scenario is owned by one REQ (`reqs[].scenarios`) and appears as an
   acceptance bullet starting with its id. After `/plan` the chat reports the included scenarios no
   REQ owns and the exclusions without a reason.
3. **KIT** — the KIT gets the statements of its scenarios and the test idioms of its lane; each is
   proved by a blocking check listed in `docs/ACCEPTANCE.json`, by a test whose name or title carries
   the scenario id (one or two ids per test), asserting what the user or the caller sees (the error
   text in the UI, the API error body, the safe state of the device).
4. **EVAL / GATE** — `acceptance::coverage` blocks the REQ while a scenario has no blocking check or
   no test names it; a line that lists many ids (a comment, a table) proves none of them.

## 3. Skills on every executor

One source, `.clike/skills/`:

- **Local agents** — `/init`, the command **CLike: Sync agent skills** and every local-agent Harper
  run (`clike.agentSkills.autoSync`) install the skills as native skills of the agents
  (`.claude/skills/`, `.agents/skills/`) in the open Agent Skills format, keep a CLike block of rules
  in `CLAUDE.md` and `AGENTS.md`, and add a guard hook that refuses writes to the REQ's tests and CI
  during `/eval`. Skills and files CLike does not manage are never touched.
- **Cloud** — the skills `/plan` selects for a REQ go into the prompt, every skill whole and its
  frontmatter once; a skill for other phases (a gate review) is listed, not rendered, in the KIT; a
  plan that names a skill folded into another gets its successor.
- **Vendored skills** — third-party skills live in `.clike/skills/vendor/<vendor>/<skill>/` with
  `VENDORED.json` (repository, pinned commit, license, review date, digest of every file). They are
  installed for the agents as `<vendor>-<skill>` with their license and selectable for the cloud like
  any skill. Maintenance with `tools/skills_vendor.py`: `verify` (run by the tests), `check-updates`,
  `update <vendor> [--ref R] [--apply]` (diff, license check and review findings before re-pinning).
  Nothing is fetched at run time. A CLike overlay (`vendor/<vendor>/CLIKE_OVERLAY.md`) says how each
  vendored skill applies per executor: the cloud gets its static form (tests before source, the
  defect each test catches, no claimed runs), the agents get red-green in the KIT and the failing eval
  check as the red in a repair; the pinned upstream files stay untouched.
- **Methodology skills** (BMAD) reach cloud and agents through the methodology loader, only in runs
  that select the methodology; they are not installed as native agent skills.
- **web-e2e-harness** — deterministic frontend checks in the eval sandbox: lockfile installs, a
  production server started by the test runner on loopback (never a reused one), no retries,
  browsers installed by the case, cookies that work over the HTTP loopback origin, stable selectors,
  condition waits; component tests for the states of a surface, browser tests for what needs a real
  browser.

## 4. Repairs in the KIT's session

An auto-eval repair of a REQ resumes, forked, the local-agent session that wrote its KIT
(`clike.localAgent.resumeRepairs`, sessions younger than 24 hours, same agent and REQ): the agent
already knows the code it wrote and its context is warm.

## 5. Measure

Every Harper call records its REQ and duration; the telemetry portal (`/harper/aggregate`) returns
`per_req` with calls, cost, tokens, time and phases.

## 6. Estimating

A worked enterprise example — classic work breakdown and staffing against the same scenario planned
with CLike, on measured pilots — is in [estimating with CLike](estimation-example.md).

## Settings

| Setting / command | Default | Effect |
|---|---|---|
| `clike.plan.capacityProfile` | `C2` | C1, C2 or C3 sizing of the plan |
| `clike.agentSkills.autoSync` | on | skills, rules and guard hook kept current before each local-agent run |
| **CLike: Sync agent skills** | — | install the skills for the local agents now |
| `clike.localAgent.resumeRepairs` | on | a repair resumes the KIT's agent session |
| `clike.localAgent.codex.reasoningEffort` | `high` | reasoning effort of one local agent on Harper phases |
| `clike.claudeCode.effort` | CLI default | effort of the other local agent on Harper phases (`low`, `medium`, `high`, `xhigh`, `max`) |
| `CLIKE_KIT_EFFORT` / `CLIKE_KIT_MAX_OUTPUT_TOKENS` (stack `.env`) | `high` / 64000 | reasoning effort and output budget of the cloud KIT and its repairs |
