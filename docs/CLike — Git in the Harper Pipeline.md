## CLike — Git Integration in the Harper Pipeline

> **Scope:** concrete, reproducible Git behavior across the Harper phases (SPEC → PLAN → KIT → EVAL → GATE → FINALIZE) with an **extension-first, orchestrator-assisted** approach.

## 1) Phase-to-Git mapping

| Phase             | Branch                   | Git actions                                                                                                                  |
| ----------------- | ------------------------ | ---------------------------------------------------------------------------------------------------------------------------- |
| **/spec**         | `main`                   | `add/commit/push` SPEC & constraints.                                                                                        |
| **/plan**         | `main`                   | `add/commit/push` PLAN & plan JSON.                                                                                          |
| **/kit REQ-xxx**  | `feature/REQ-xxx-<slug>` | Ensure branch (create from up-to-date `main`), write sources/tests, `add/commit/push`. *(Optional flag)*: open **draft PR**. |
| **/eval REQ-xxx** | same feature branch      | Commit eval/test artifacts, `push`.                                                                                          |
| **/gate REQ-xxx** | merge policy             | If green: orchestrator/human merges to `main`; optional tag `harper/gate/REQ-xxx`.                                           |
| **/finalize**     | `main`                   | Use `PR_BODY.md` to open a **PR** (title/labels configurable).                                                               |

## 2) Commit messages & tags

* **Commits (conventional):**

  * `spec: update SPEC.md`
  * `plan: update PLAN.md`
  * `feat(req-123): implement …`
  * `test(req-123): add eval artifacts`
  * `chore(req-123): gate report`
  * `chore: finalize`
* **Tags (optional):** `harper/<phase>/<runId>`, `harper/gate/REQ-xxx`.

## 3) Safety & idempotency

* Verify repo and remote; fetch.
* Rebase before pushing (configurable).
* Stage **changed** files when known, fallback to `-A` when not.
* On conflict: surface and stop; no force push.

## 4) Settings (user/workspace)

```jsonc
{
  "clike.git.autoCommit": true,
  "clike.git.commitMessage": "clike: apply patch (AI)",
  "clike.git.openPR": true,

  "clike.git.remote": "origin",
  "clike.git.defaultBranch": "main",
  "clike.git.conventionalCommits": true,
  "clike.git.pushRebase": true,

  "clike.git.branchPrefix": "feature",
  "clike.git.tagPrefix": "harper",

  // Draft PR after /kit (optional)
  "clike.git.prPerReqDraft.enabled": false,
  "clike.git.prPerReqDraft.useGhCli": true,
  "clike.git.prBodyPath": "docs/harper/PR_BODY.md"
}
```

## 5) Responsibilities

* **VS Code extension:** runs all local Git operations and (optionally) opens PRs.
* **Orchestrator:** enforces merge policy after GATE green; may manage labels/milestones and releases.

