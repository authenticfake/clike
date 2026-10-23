# Git and Promotion

## Overview

Git behavior in CLike is currently extension-first and promotion-aware.

This means:
- Git automation primarily lives in the VS Code extension
- candidate artifacts are created before promotion
- gate outcomes can influence merge behavior
- promotion is REQ-oriented, not just workspace-wide staging

## Current extension commands

Git-related commands contributed by the extension:
- `clike.gitCreateBranch`
- `clike.gitCommitPatch`
- `clike.gitOpenPR`
- `clike.gitSmartPR`
- `clike.promoteReqSources`
- `clike.promoteReqSourcesQuick`

## Current settings

All automation is **off by default** (since the 2026-10 hardening). Machine-scoped settings are
read by VS Code **only from User settings** (an opened project cannot turn on commits or pushes):
a value in the project's `.vscode/settings.json` is ignored, and CLike warns about it with
**Apply in User settings**.

| Setting | Default | Meaning |
|---|---|---|
| `clike.git.autoCommit` | `false` | Commit the files produced by each Harper phase — only those files (machine-scoped) |
| `clike.git.autoPush` | `false` | Push phase commits, tags and gate merges (machine-scoped) |
| `clike.git.gitMergeOnGate` | `false` | After a PASS gate, merge the REQ branch into the default branch (`--no-ff`) |
| `clike.git.openPR` | `false` | Open a PR on `/finalize` |
| `clike.git.pushRebase` | `false` | Rebase the REQ branch on the remote default branch when the tree is clean |

Other settings: `gitDeleteBranchOnMerge`, `gitReturnToFeatureAfterMerge`, `remoteUrl`,
`commitMessage`, `remote`, `defaultBranch`, `conventionalCommits`, `branchPrefix`,
`tagPrefix`, `prPerReqDraft.enabled`, `prPerReqDraft.useGhCli`, `prBodyPath`.

## Phase sync guarantees (`clikeGitSync`)

- **No branch is ever rewritten**: the target branch is entered with `git switch`
  (existing) or `git switch -c <branch> <defaultBranch>` (new). The previous
  implementation used `checkout -B`, which reset an existing REQ branch to `HEAD`
  (dropping its commits) and could move the default branch onto unreviewed work.
- **Only the phase files are committed** (`git commit -m … -- <paths>`): unrelated
  changes, untracked files and anything the user already staged are left alone.
  No `git add -A`. Paths outside the work tree are ignored.
- If switching branch would overwrite local changes, the sync stops and leaves the
  phase files uncommitted in the working tree. One case is resolved instead: a phase run while
  another branch is checked out writes files its target branch tracks — `/kit REQ-021` after the
  gate of REQ-020 left you on `main` (`runs/kit/REQ-021/` is on `feature/req-021`), or `/finalize`
  / `/spec` run from a REQ branch older than their last run (the handoff documents are on `main`);
  untracked here, they block the switch. When every blocking file is untracked and is a file of
  the phase or inside `runs/kit/<REQ>/`, CLike copies them
  under `.git/clike-carry/`, switches, writes them back over the branch's versions (still in its
  history) and commits the phase there (`carried N file(s) … onto feature/req-<n>` in the log). Any
  other blocking file — or a failure — leaves everything where it was.
- A document phase (`/idea`, `/spec`, `/plan`, `/idea --extend`, `/finalize`) commits on the default
  branch; when it was run from another branch (a REQ branch with a KIT in progress), CLike then
  switches back to that branch and merges the default branch into it, so the REQ keeps its KIT in
  the working tree and gets the new documents. On a merge conflict it stays on the REQ branch and
  says how to merge.
- A new repository is bootstrapped with an empty commit: existing workspace files
  (for example `.env`) are never committed implicitly.
- The default branch changes only through an explicit merge-on-gate after a PASS gate, and only
  for a REQ that was promoted: a gate that passed but left promotion conflicts keeps the REQ on
  its branch (CLike says so) until the conflicts are resolved and `/gate` runs again.
- Tags `harper/<phase>/<runId>` are created locally; pushes only with `autoPush`.
- `/idea --extend` tags the delivered baseline `harper/v<N-1>` (annotated, on `HEAD`, once; not
  on `--dry-run`) before the release changes the documents.
- Paths the project ignores are left out of a phase commit (logged), so one ignored path does not
  skip the commit; tracked files of the REQ's own KIT (`runs/kit/<REQ>/`) changed outside the
  phase — CLike's agent package `docs/AGENT_*`, a `ci/HOWTO.md` a pre-pass or repair updated — are
  committed with the KIT, eval and gate phases, so they never block the switch to the default
  branch. Untracked files there (agent scratch, reports) and changes outside the KIT stay yours.
- These guarantees are covered by tests against real temporary repositories
  (`extensions/vscode/test/git-sync.test.js`).

## Current phase relationship

The inspected codebase and reference docs support this phase-aware model:

- `/spec` updates Harper docs
- `/plan` updates Harper docs and plan state
- `/kit` produces candidate artifacts under `runs/kit/<REQ-ID>/...`
- `/eval` produces eval evidence
- `/gate` produces gate decisions and may allow promotion
- `/finalize` is release-oriented: it commits the verified solution on the default branch (only
  its own files; the developer's earlier changes stay out) and warns when REQ branches are not
  merged into it
- `/idea --extend` starts the next release: IDEA/SPEC/TECH_CONSTRAINTS merged, new REQs appended
  to the plan

## Candidate-first promotion

Promotion is not direct generation into canonical roots.

The current sources justify documenting this rule:
- generation happens under `runs/kit/<REQ-ID>/...`
- promotion into canonical roots is a distinct operation

This separation is important for:
- reviewability
- local agent safety
- eval/gate reproducibility
- Git traceability

## Gate auto-merge promotion (default)

On a passing `/gate` (`PASS`, `PASS_WITH_WARNINGS` with accepted warnings, or an audited
override) the REQ is promoted **without prompts** (`clike.gate.autoPromote`, default `merge`;
`extensions/vscode/promote-merge.js`):

- only `runs/kit/<REQ>/{src,test,tests}/**` are promoted into the canonical roots, plus
  `runs/kit/<REQ>/root/<path>` → `<path>` for repository-root deliverables (see below); installed
  or generated content (`node_modules`, `__pycache__`, `.venv`, caches, `.next`, `.tmp`) never is;
- every file gets a **3-way merge**: base = what the KIT started from (the file of the last
  direct dependency KIT in `plan.json` `dependsOn` that has it, else the canonical file at the
  parent of the KIT commit, else at the last commit before the KIT was generated), ours = the
  canonical file now, theirs = the candidate. Two kinds of overlapping change resolve without
  you: lines added at the same place by both sides (both kept, canonical first — unless one side
  already contains the other: then that side alone, so a REQ promoted again, or a KIT whose base
  is older than `src/`, never adds lines `src/` already has; additions that share lines without
  one containing the other are a conflict), and a spot where
  the candidate holds the whole canonical side plus its own additions (a later KIT rewrote a line
  from the code an earlier REQ had already promoted; compared word by word, whitespace ignored):
  the candidate is kept, nothing of `src/` is lost and it is what the gate tested. The opposite
  (canonical holds the whole candidate) stays a conflict: `src/` was not tested with this REQ.
  A third kind resolves only when **the gate ran this candidate with the regression of the
  promoted REQs** (not an override): a spot where the candidate **rewrote** `src/` lines without
  dropping any — each `src/` line it does not repeat has its new form there (most of its words),
  and none of its words (identifiers, strings, numbers) is gone from the candidate file, as when an
  expression is renamed and defined from the old one (`legacyProviders = providers.value …`). The
  candidate is kept and the report lists each rewritten pair under *Rewritten lines kept from
  <REQ> (review)*. A `src/` line whose words the candidate no longer has (`['q', 'owner']` →
  `['q', 'fit_min']` loses `owner`) is a loss and stays a conflict, tested or not.
  Without a merge base the same rules apply to the whole file. **Promotion is idempotent:** a
  merge that would repeat significant lines both sides added (the same block received earlier
  from another REQ, placed elsewhere) is a conflict, never written. **Merged files are checked**
  before they are written — Python compiles, JSON parses, JS/MJS pass `node --check` — and a
  merged file that is not valid is a conflict with the reason. Outcomes: `added`, `updated` (canonical unchanged since the KIT),
  `merged` (both changed, merged cleanly by `git merge-file`), `kept_canonical`, `unchanged`,
  `conflict`;
- a conflicting file is **never written**: `<name>.conflict-<REQ>-<ts>` next to it holds the
  merge with conflict markers (only the spots still in conflict), the other files are promoted,
  and the REQ stays `in_progress` until the conflicts are resolved and `/gate` runs again;
- **a resolved conflict stays resolved**: once `src/` holds the right content and the
  `.conflict-…` file is deleted (as `conflicts.md` asks), the next gate keeps `src/` for that file
  (`kept_canonical`, "resolved in src/") instead of raising the same conflict again — as long as
  the KIT file is still the one that conflicted (its sha256 is recorded in `report.json`);
- **`conflicts.md`** next to the report explains every spot still in conflict, read line by line:
  **1. Rewritten by the REQ** (the `src/` line and its new form), **2. Only in `src/`** (lines
  the REQ would drop, with the words its file no longer has: keep them unless the REQ removes them
  on purpose), **3. Only in the REQ** (its additions); both versions in full, the diff and the
  base are folded below. Then what to do for the spot and for the file: when nothing of `src/` is
  lost and the REQ's file equals the merge with its side of each spot, the exact `cp` and `rm`
  commands; when `src/` has other changes the REQ lacks, keep the REQ side of each marker block in
  the `.conflict-…` file; otherwise write it by hand from the REQ's file plus the *Only in `src/`*
  lines. A **Commands** section at the end lists them all. Then `/gate` again. The `.conflict-…`, `.incoming-…` and `.bak-…` files are never copied into an
  eval workspace, so one left behind does not fail a check;
- without git history of the KIT there is no base: only new or identical files are promoted,
  the others are conflicts (nothing is overwritten silently);
- the report `runs/kit/<REQ>/promotion/<ts>/report.md` (opened at the end) lists every file with
  its outcome and lines changed; `report.json` is the machine form and `promotion.diff` the unified
  diff of everything written (`git apply -R` reverts it). The promoted files and the report are in
  the gate commit when `clike.git.autoCommit` is on.

Three ways to choose it: the setting `clike.gate.autoPromote` (`merge` default: no prompt;
`ask`: the strategy list, with **auto-merge** first, then folder / suffix / backup / skip /
overwrite; `off`: no promotion), or for one run `/gate <REQ> --auto-merge`, `--ask`,
`--no-promote`.

### Repository-root deliverables (`runs/kit/<REQ>/root/`)

Some REQs deliver files outside `src/` and `test/`: run and setup scripts, deployment scripts,
infrastructure, root manifests. The KIT writes them under `runs/kit/<REQ>/root/<repository path>`
(for example `runs/kit/REQ-033/root/deploy/aws/01_inventory.sh`) and the gate promotes them to
`<repository path>` with the same 3-way merge, report and conflict files.

- Allowed by default: the folders `scripts/`, `deploy/`, `infra/`, `ops/`, `config/`, `configs/`,
  `migrations/`, `db/` and the files `.env.example`, `compose.yml|yaml`, `docker-compose.yml|yaml`,
  `Dockerfile`, `Makefile`, `Procfile`. A project adds more in `.clike/project.json`:
  `"root_folders": ["tools"], "root_files": ["Procfile.dev"]`.
- Never: `.git`, `.clike`, `runs`, `docs`, `src`, `test`, `tests`, `ci`, `.env` and other private
  files (keys, certificates), generated folders. A file outside the policy is listed as `rejected`
  in the report and never written; the rest of the promotion goes on.
- The eval sees them where they will be: the workspace root of the eval holds the canonical
  root deliverables, those of dependency KITs not promoted yet, then the candidate's
  (`./scripts/...`, `./deploy/...`); the regression of promoted REQs runs with the candidate's
  root files too, and names them when a promoted check fails on them.

## REQ branches

Each REQ's phases are committed on `feature/req-<n>`. A new REQ branch starts from the default
branch when the current work is merged into it, otherwise it is **stacked on the current branch**
(merge-on-gate off: REQ-004 carries the REQ-003 commits it depends on). A phase that cannot be
committed (switch refused, commit error) shows a warning instead of failing silently.

## Promotion helpers

The extension contains promotion-oriented helpers and manifests, including references to:
- promotion manifests
- REQ promotion summaries
- quick promotion commands
- standard promotion commands

Promotion should therefore be documented as:
- explicit
- REQ-scoped
- manifest-aware
- gate-aware

## Current merge behavior

The settings indicate support for merge-on-gate behavior:
- `clike.git.gitMergeOnGate`

Merge is opt-in (default `false`) and happens only after a PASS gate that promoted the REQ.
With `autoPush` and a remote, CLike first fetches and merges `<remote>/<default>` into the default
branch (a PR merged on the host), then merges the REQ (`--no-ff`) and pushes; a conflict, a failed
switch or a failed push is shown as a warning with its cause and the commands to run.

## Current branch conventions

The sources and attached docs show multiple naming patterns in different places, including:
- `feature/<REQ-ID>-...`
- `harper/<phase>/<runId>`

Because both conventions appear in the inspected material, official docs should avoid overstating a single universal branch scheme unless the repository later consolidates it.

Recommended current wording:
- branch naming is phase-aware or REQ-aware depending on the operation
- feature branches are used for candidate work and PR flows
- Harper phase tags or phase branches may also be used in governance flows

## PR integration

Current settings and docs reference:
- draft PR support per REQ
- GitHub CLI support
- configurable PR body path
- optional PR opening after compatible operations

This supports documenting PR flows as:
- present
- optional
- settings-driven
- extension-initiated

## Safety guarantees to keep explicit

The current sources justify making these rules explicit:
- no direct local-agent promotion into canonical roots
- no assumption that candidate files are final until eval/gate and promotion
- gate outcomes can deny promotion
- promotion must stay artifact-aware and REQ-aware
