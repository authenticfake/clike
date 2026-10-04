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

All automation is **off by default** (since the 2026-10 hardening):

| Setting | Default | Meaning |
|---|---|---|
| `clike.git.autoCommit` | `false` | Commit the files produced by each Harper phase — only those files |
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
  phase files uncommitted in the working tree.
- A new repository is bootstrapped with an empty commit: existing workspace files
  (for example `.env`) are never committed implicitly.
- The default branch changes only through an explicit merge-on-gate after a PASS gate.
- Tags `harper/<phase>/<runId>` are created locally; pushes only with `autoPush`.
- These guarantees are covered by tests against real temporary repositories
  (`extensions/vscode/test/git-sync.test.js`).

## Current phase relationship

The inspected codebase and reference docs support this phase-aware model:

- `/spec` updates Harper docs
- `/plan` updates Harper docs and plan state
- `/kit` produces candidate artifacts under `runs/kit/<REQ-ID>/...`
- `/eval` produces eval evidence
- `/gate` produces gate decisions and may allow promotion
- `/finalize` is release-oriented

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

Merge is opt-in (default `false`) and happens only after a PASS gate.

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
