# BMAD Skill Sync Guide

`tools/bmad_skill_sync.py` is a maintainer utility for refreshing local BMAD reference material in the VS Code Harper init template. It is deliberately outside the Harper runtime path. Cloud phases, local-agent phases, EvalRunner, and Gate never call it.

The template destination is:

```text
extensions/vscode/templates/harper-init/.clike/skills/vendor/bmad
```

New workspaces receive the same reference seed at:

```text
<workspace>/.clike/skills/vendor/bmad
```

The sync tool reads a local source directory, copies only allowed text files, records hashes, and writes a manifest. It never calls BMAD tooling, never calls `npx`, never imports from URLs, and never fetches network resources.

## Dry Run

Use a dry run before importing any material into the template:

```text
python3 tools/bmad_skill_sync.py \
  --source /tmp/bmad-reference \
  --dest extensions/vscode/templates/harper-init/.clike/skills/vendor/bmad \
  --dry-run
```

## Import

After reviewing the dry-run summary, import into the extension template seed:

```text
python3 tools/bmad_skill_sync.py \
  --source /tmp/bmad-reference \
  --dest extensions/vscode/templates/harper-init/.clike/skills/vendor/bmad
```

The source must be a local directory. The destination should remain the actual Harper init template vendor path unless a maintainer is testing against a temporary directory.

## Import Rules

Allowed file extensions:

- `.md`
- `.markdown`
- `.txt`
- `.json`
- `.yaml`
- `.yml`

Skipped material includes hidden directories, hidden files, `.git`, `node_modules`, Python caches, build output, coverage output, binary files, non-UTF-8 files, and oversized files. Each imported file is recorded with its relative path, byte count, and sha256 digest.

The generated manifest preserves the runtime boundary:

- `runtime_execution_enabled`: false
- `external_bmad_cli_enabled`: false
- `network_fetch_enabled`: false
- `native_harper_active`: false
- `reviewed_status`: `pending_manual_review`

## Review Flow

1. Choose a local, reviewed BMAD reference directory.
2. Run the dry run and inspect the imported/skipped counts.
3. Import into `extensions/vscode/templates/harper-init/.clike/skills/vendor/bmad`.
4. Review the file diff, manifest hashes, and README.
5. Update the template vendor `SKILL.md` material only when a reference concept should become governed CLike guidance.
6. Run the targeted tests and safety greps in `TEST_PLAN.md`.

The imported vendor material is still reference-only after sync. Activation happens only when `methodology=bmad` causes the extension to transport `.clike/skills/vendor/bmad/**` through `core_blobs` and the Orchestrator selects skills from the vendor manifest.
