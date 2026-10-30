# Bringing an existing project into CLike (`/adopt`)

A project CLike did not create — hand-written, built with another tool or method, a monorepo of
several services — becomes a CLike project in place. From then on it evolves with `/idea --extend`
and the usual KIT → EVAL → GATE loop, and its existing behaviour is protected by the regression
from day one.

> **Status.** `/init` in place (step 2) and `/adopt` (step 3: survey, baseline, project memory,
> analysis, adopted REQs, run guide, README) are available. `--refresh` (step 5) is being built.

## What does not change for the team

- **The code stays where it is.** No folder is moved or renamed; CLike reads the project's own
  layout (one service or several areas).
- **The team's commands stay the commands.** CLike runs the project's own build and test commands
  (the ones the CI runs) as its checks; nobody adopts a CLike layout or a new test runner.
- **The team's process stays the process.** Review rules, PR templates and CI workflows the
  repository already has are kept; CLike's own are offered as proposals only.
- **Nothing existing is overwritten.** CLike adds its own folders; the only existing file it updates
  is the root `README.md` (at `/adopt`, then at each `/finalize`), keeping every section and every
  line it had, word for word — a run that drops or rewrites one gets the README back as it was.
  During `/adopt` CLike writes only `docs/harper/`, `.clike/`, `runs/` and the root README: a file
  the model returns elsewhere is ignored, and CLike never writes a project file — the code, the
  tests, the areas' READMEs and `docs/`. You (or another agent) can keep working in the project
  while `/adopt` runs: in a git repository, the files that changed meanwhile are named in the chat
  and left exactly as they are.
- **Work done outside CLike is fine.** A change committed without CLike is reconciled by
  `/adopt --refresh`; it is never treated as an error.

What CLike adds to the repository, and only this:

| Path | What it holds |
|---|---|
| `.clike/` | project settings (`project.json`: areas, roots, commands), policies, skills |
| `docs/harper/` | IDEA, SPEC (with use cases), PLAN and `plan.json`, TECH_CONSTRAINTS, lane guides, `HOWTO_RUN.md`, the adoption reports |
| `runs/` | KITs and evidence (mostly ignored by git) |
| `ci/SOLUTION_LTC.json` | the verification of the whole solution, written by `/finalize` |
| `README.md` | at `/adopt` and `/finalize`: the existing README with CLike's presentation and sections added, nothing removed |

## Steps

### 1. Open the project

Open the repository root in VS Code (for a monorepo, the root that holds all the services) and open
**CLike: Chat** in Harper mode. Work on a branch or a clone the first time, if you prefer to look
before keeping anything.

### 2. `/init` — available

```text
/init
```

With no parameters, `/init` initializes the folder open in VS Code, in place. It is the same as
`/init <name> <parent folder> --force`, which works as before.

- It adds `.clike/` and the `docs/harper/` skeleton, `docs/inputs/` and `docs/reference/`, and only
  the `.gitignore` rules that are missing. Every existing file is kept (the chat lists them).
- **Review, PR template and CI files** (`.github/CODEOWNERS`, `.github/pull_request_template.md`,
  `.github/workflows/clike-ci.yaml`): a repository that already has a process of its own — a CI
  workflow, a code-owners file or a PR template — keeps it, and CLike's files go to
  `.clike/proposals/.github/…` (copy them if you want them). A new folder gets them as before.

### 3. `/adopt` — available

```text
/adopt [--area <name>] [--dry-run]
```

Run it once per area (or once for all of them). Steps 1–3 run with no model, the same with any
executor: the areas are written to `.clike/project.json` (CLike's own file; a root or command you
correct there is kept by the next `/adopt`), the baseline profile to `runs/adopt/ci/LTC.json`. The
baseline runs each area's own setup and check (from its Makefile, scripts or CI) on a copy of the
project in the eval sandbox, on the runtime versions the area requires. Steps 4–5 run with the model
the chat uses: a local agent reads the repository itself; a cloud model gets the survey report with
the history, the code map, the READMEs and agent context files, and the key source files of the
areas analysed whole (entry points, routes, calls, contracts, configuration). Both start from the
code map, then the code, then git, then the documents. CLike checks the plan it
returns (step 6) before anything is committed; a rejected analysis restores the documents and keeps
the run's output aside in `runs/extend/rejected/`.

1. **Survey** (no model): stacks and versions, package managers, source and test roots per area,
   entry points, the CI's commands, existing documentation and agent context files, git state.
2. **What exists is decided by the code and git.** CLike runs the project's own tests in the eval
   sandbox (each one passing, failing or skipped), writes the **code map** `docs/harper/CODEMAP.md` —
   per area: modules and their public symbols, entry points, routes, calls to the other areas
   (client, method, path), references between areas, contracts, configuration, tests — and reads
   the **git history per area** (features and fixes, with their day; tags). Without git, the code
   and the documents; without documents, the code alone. A backlog or a plan written by hand is an
   input for future work and decisions, never the proof that something is done.
3. **Project memory.** Every document of the repository — Markdown, text, reStructuredText and
   AsciiDoc files wherever they are (`docs/`, the READMEs of areas and modules, the agent context
   files, the changelogs, examples and prompts), the OpenAPI and AsyncAPI contracts; tracked or new,
   not ignored by git — the code map and
   the **source code of the areas adopted** are indexed into the project's memory, so every phase
   and the **Memory** panel answer with the project's own context and cite where it comes from.
4. **Analysis, one area at a time.** Capabilities, interfaces, data, integrations and conventions,
   each marked **observed** (found in code or tests), **declared** (written in a document) or
   **open** (a question for you). Nothing unknown is invented.
5. **Proposal**, in merge mode: `project.json` with the areas, IDEA / SPEC / PLAN "as is", the
   **adopted REQs** (one per capability, each protected by the tests of its area), open REQs for the
   documented work still to do, lane guides from the project's conventions, the decisions already
   taken as constraints, `docs/harper/HOWTO_RUN.md` (setup, run and test of each area with its own
   commands) and the root **README.md integrated**: CLike's badges, summary and sections (areas,
   architecture, requirements coverage, how to run and test, made with CLike) added to the existing
   README, every existing section kept.
6. **Check, reports and commit.** CLike checks the plan the model returned (baseline REQs unchanged;
   every new REQ with an area and acceptance; `done` only with the area's baseline covering it, else
   `open`; the README with every existing section and line) and appends its verification to the analysis
   report. Two reports: `docs/harper/ADOPT_<date>.md` (the survey: areas, baseline, git history, CI,
   documentation) and `docs/harper/EXTEND_<…>.md` (the analysis: capability → files → tests per
   area, where the documents and the code disagree, the open questions, CLike's verification). The
   baseline LTCs are locked and the result is committed. Review the reports and the plan before the
   first `/idea --extend`; a rejected analysis changes nothing (its output is kept aside).

`--area <name>` adopts one area of a monorepo first; the others follow with the same command (their
REQs are numbered after the ones already adopted; an area is adopted once). The next area **adds to**
what the earlier ones wrote, it never rewrites it: every section and REQ of an area adopted before
stays (IDEA, SPEC with its use cases, HOWTO_RUN, its lane guide; TECH_CONSTRAINTS only grows). The run
replaces only a project-wide statement the new area changes (the areas, the architecture, the contracts
between areas, the coverage counts) or an open point the new code answers, and lists each replacement in
its report under *Changes to the earlier adoption*. A document that loses a section of an earlier area
is put back. In the README, CLike's own sections are updated for the new area, while every line of the
team's README (saved at the first adoption in `.clike/adopt/README.original.md`) stays. The analysis runs on a
plan without REQs or one adopted this way; a project already planned with CLike evolves with
`/idea --extend`.

What `/adopt` writes in the plan: one **baseline REQ** per area (`REQ-001`…, status `done`,
`origin: adopted`) whose LTC (`runs/kit/<REQ>/ci/LTC.json`) runs the area's own setup and check, and
is locked as its acceptance; then the capability REQs with their `area`, `done` with `covered_by`
the baseline REQ, or `open`. The commit `docs(harper): adopt …` holds the Harper documents (with
`CODEMAP.md`, `HOWTO_RUN.md` and the lane guides), the root `README.md`, `.clike/project.json`, the
reports and the baseline LTCs.
`--dry-run` writes only the report.

**Git.** With CLike's auto-commit on, the adoption is one commit `docs(harper): adopt …` on the
repository's default branch — the configured one when the repository has it, else the repository's
own (`origin/HEAD`, then the current branch: a `develop` or `master` project keeps it; CLike never
creates another default branch). It holds CLike's own files only: what `/init` added (`.clike/`,
the `docs/` skeleton, the `.gitignore` rules, `README_1st.md` and `images/clike/`; never the VS Code
workspace file), the Harper documents, `CODEMAP.md`, `HOWTO_RUN.md`, the
root README, the reports, the baseline profile and LTCs. The developers' own changes are never in it.
With auto-push on, it is pushed like any phase: on a team repository with a protected default
branch, adopt on a branch of your own (or with auto-push off) and open a pull request. A rejected
analysis commits nothing; the survey files stay in the working tree.

| An adopted capability… | becomes |
|---|---|
| found in the code and covered by the area's tests | REQ `done`, `covered_by` the area's baseline REQ |
| in an area whose checks already fail | the baseline REQ lists them as *failing at adoption* (reported, not blocking until a REQ fixes them) |
| found without tests | REQ `open` (tests to add) |
| documented or in the backlog, not found in the code | REQ `open` ("documented, not found"; backlog items as `import:backlog:<id>`) |

### 4. Evolve it — as any CLike project

```text
/idea --extend → ( /kit REQ-xxx → /eval REQ-xxx --fix → /gate REQ-xxx )* → /finalize
```

The regression runs the adopted baseline on every gate, so a change that breaks existing behaviour
is blocked; a change made on purpose is declared (see `/idea --extend` and `/eval --supersede` in
[commands](commands.md)). `/finalize` verifies the whole solution, journey by journey, and writes the
README in CLike's style **integrating the existing one**: every section it had stays.

**Releases, one folder each.** The adoption is `v1`; the needs of the next release go in
`docs/inputs/v2/` (background in `docs/reference/v2/`), the one after in `docs/inputs/v3/`, and so
on. `/idea --extend` reads the folder of the release it targets as its requirements and the earlier
ones as history. One file per need reads best: what it is for, what changes, the acceptance criteria,
what is out of scope.

**Extending an existing module.** Name the area in the input (`Area: aigateway`) and say what changes
in what it already does. Every new REQ gets its `area` (or `areas`, for a journey across modules); a
change to behaviour a delivered REQ verifies becomes a `MODIFIED` REQ that amends it and declares the
checks it supersedes, the rest are `ADDED` REQs through the module's existing seams.

```markdown
# aigateway — token budget per tenant
Area: aigateway
## What changes
Today a call over the rate limit is slowed down; from this release, over the monthly budget it is refused (429).
## Acceptance
- GET /v1/tenants/{id}/usage returns the month's usage and budget.
- A call over the budget answers 429 without calling the provider.
## Out of scope
Billing.
```

**A new module.** Say it is a new area, its folder at the repository root, its stack, who it calls and
who calls it, and that it has a check command like the others. The first REQ of the new area declares
it (`new_area`: folder, source, tests, commands); its scaffold — manifest, check command, tests — is
part of that REQ's acceptance. When the release is accepted CLike adds the area to
`.clike/project.json` (in the release commit), so `/kit`, `/eval` and `/gate` run it as any other
area.

```markdown
# New module: notifications
New area: notifications (folder notifications/, Python, the stack of aigateway)
## Role
Listens to the foundation events and notifies users on Teams and by e-mail.
## Interfaces
- Consumes tenant.budget.warning (from aigateway).
- Exposes GET/PUT /v1/users/{id}/preferences (called by the portal).
## Acceptance
- A tenant.budget.warning event notifies the tenant admins.
- It has its own tests and a `make check`, as the other areas.
```

CLike checks the plan: in a project of areas a new REQ without an area, an area that does not exist
and no REQ declares, or a new area inside an existing one rejects the release (the documents are
restored). A project without areas works as before: no area is asked.

### 5. When the code moves outside CLike

```text
/adopt --refresh
```

Reconciles the Harper documents and the baseline with the code as it is now, and records the changes
made outside CLike as known.

## A monorepo of several services

One CLike project at the repository root, the services as **areas**: one plan, one release `vN`,
one `/finalize` for the whole system, each REQ belonging to one area (or more, for a journey that
crosses them). The Harper documents are only at the repository root (`docs/harper/`, the root
`README.md`); inside them each area has its SPEC section, its lane guide and the `area` of its REQs.
The areas' folders, READMEs and `docs/` are read and indexed, never written. Each area keeps its own
roots and commands:

```json
{
  "areas": [
    {"name": "gateway", "root": "gateway", "source": ["gateway/src"], "tests": ["gateway/tests"],
     "commands": {"setup": "uv sync", "check": "make check"}},
    {"name": "portal", "root": "portal", "source": ["portal/apps/portal", "portal/packages"],
     "tests": ["portal/apps/portal", "portal/e2e"], "commands": {"setup": "npm ci", "check": "npm run check"}}
  ]
}
```

`/adopt` proposes this file from the survey; you correct it in the report if needed. Areas work
today (KIT → EVAL → GATE): a KIT writes an area's code and tests at their repository paths
(`runs/kit/<REQ>/root/gateway/src/…`, `…/root/gateway/tests/…`), its checks run inside the area with
its own commands, and the area's tests are locked like any acceptance test
([Git and promotion](git-and-promotion.md)).

## See also

- [Commands](commands.md) — `/init`, `/idea --extend`, `/eval --supersede`, `/finalize`.
- [Brownfield and evolution: the design](architecture/ADOPT_AND_IDEA_EXTEND.md).
- [Context sources](context-sources.md) and [RAG](rag.md) — what the project memory holds.
