### CLike — Git Branching Policy for Harper Pipeline

**Applies to:** SPEC → PLAN → KIT → EVAL → GATE → FINALIZE
**Default branch:** `master` (or `main` if your repo uses that; set via `clike.git.defaultBranch`)

## 1) Goals

* Keep each **REQ isolated** in its own branch.
* Allow **parallel** development of multiple REQs safely.
* Merge to default branch **only after GATE is green**.
* Ensure reproducible automation from the VS Code extension.

## 2) Branch Model

* **Default branch:** `master` (or `main`). Hosts SPEC and PLAN artifacts and final merged code.
* **REQ branch:** `feature/req-<id>` (lowercase, e.g., `feature/req-001`).

  * Created by `/kit REQ-xxx` if missing; **reused** on subsequent `/kit REQ-xxx`.
  * Contains **only** the changes required by that REQ (new files + edits to existing files if needed).

> Note: Branches are **per requirement**, not “per file”. Two REQs can modify different or overlapping files. Overlap is allowed; conflicts (if any) are resolved at merge time.

## 3) Phase → Git Mapping

| Phase       | Branch                       | Action                                                                               |
| ----------- | ---------------------------- | ------------------------------------------------------------------------------------ |
| `/spec`     | default (`master`/`main`)    | Commit/push SPEC docs and constraints.                                               |
| `/plan`     | default                      | Commit/push PLAN docs, plan metadata.                                                |
| `/kit`      | `feature/req-<id>`           | Create/switch branch from up-to-date default; write code/tests; commit/push.         |
| `/eval`     | `feature/req-<id>`           | Commit/push eval artifacts, test updates.                                            |
| `/gate`     | `feature/req-<id>` → default | If **green**, merge into default (policy-enforced). Optional tag `harper/gate/<id>`. |
| `/finalize` | default                      | Open PR and release notes using `PR_BODY.md` (configurable).                         |

## 4) Parallel REQs

* You **may** create multiple REQ branches in parallel: `feature/req-001`, `feature/req-002`, …
* **Do not** mix changes from different REQs into the same branch.
* If **REQ-B depends** on code in **REQ-A** not yet merged: either wait for A’s merge, or base B on A (stacked branches), knowing you’ll need to merge A first.
* To minimize conflicts, avoid touching the same hotspots across concurrent REQs when possible.

## 5) Workflow (per REQ)

1. Ensure default branch is **up to date** (the extension will fetch; if local edits exist, it will auto-stash before rebase).
2. `/kit REQ-<id>` → extension switches/creates `feature/req-<id>`.
3. Generated/edited files are **saved**, **added**, **committed**, **pushed** (if remote credentials exist).
4. `/eval REQ-<id>` → commits artifacts on the same branch.
5. `/gate REQ-<id>` green → **merge** `feature/req-<id>` → default.
6. `/finalize` → creates PR (or consolidated PR, if enabled) using `PR_BODY.md`.

## 6) Commit & Tag Conventions

* **Commits**:

  * `spec: update SPEC.md`
  * `plan: update PLAN.md`
  * `feat(req-001): implement <summary>`
  * `test(req-001): <summary>`
  * `chore(req-001): gate report`
* **Tags (optional):**

  * `harper/<phase>/<runId>`, e.g., `harper/kit/2025-10-28T10-30Z`
  * `harper/gate/req-001` on GATE success

## 7) PR Strategy

* **Default**: Open **final** PR at `/finalize` from the default branch, assembling changes per policy.
* **Optional feature (flag)**: **Draft PR per REQ** right after `/kit` to enable early CI/visibility.
* PR body reads from `docs/harper/PR_BODY.md` (configurable in the extension settings).

## 8) Safety & Automation Rules

* The extension:

  * Detects local edits and uses **auto-stash** for safe pull/rebase when needed.
  * Uses **idempotent checkouts** (`checkout -B`) so branches are created or switched reliably.
  * Commits **only** changed files; falls back to `-A` when unknown.
  * Pushes if a **remote** is configured and **credentials** are available; otherwise commits locally and logs a clear note.
* **Credentials** are not managed by the orchestrator/extension; use:

  * **HTTPS + Keychain** (macOS): `git config --global credential.helper osxkeychain`, first push via browser/PAT.
  * **GitHub CLI**: `gh auth login` then `gh auth setup-git` (recommended).
  * **SSH**: load your key and add it to GitHub (`ssh-add`, `gh ssh-key add`).

## 9) Conflict Management

* If two REQs touch the same files, resolve conflicts at merge.
* Prefer small, focused REQs; coordinate to avoid overlapping edits when possible.
* If using stacked branches (B based on A), **merge A first** or rebase B onto updated default after A is merged.

## 10) Quick Checklists

**Start a new REQ (clean):**

* Default updated ✔︎
* `/kit REQ-<id>` → `feature/req-<id>` ✔︎
* Commit pushed (or local if no credentials) ✔︎

**Continue the same REQ:**

* `/kit REQ-<id>` reuses branch ✔︎
* `/eval REQ-<id>` commits artifacts ✔︎

**Before merge (GATE green):**

* CI green ✔︎
* Conflicts resolved ✔︎
* Merge `feature/req-<id>` → default ✔︎
* Tag (optional) ✔︎

**Finalize:**

* `/finalize` → PR created with `PR_BODY.md` ✔︎

