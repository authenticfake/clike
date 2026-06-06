#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/" && pwd)"

MODE="${1:---check}"

SOURCE="${BMAD_NORMALIZED_SKILLS_SOURCE:-${REPO_ROOT}/orchestrator/methodologies/bmad/skills}"
MANIFEST="${BMAD_PROFILE_MANIFEST:-${REPO_ROOT}/orchestrator/methodologies/bmad/manifest.json}"
DEST="${BMAD_VENDOR_DEST:-${REPO_ROOT}/extensions/vscode/templates/harper-init/.clike/skills/vendor/bmad}"

case "${MODE}" in
  --check)
    python3 "${REPO_ROOT}/tools/bmad_skill_sync.py" \
      --source "${SOURCE}" \
      --dest "${DEST}" \
      --manifest "${MANIFEST}" \
      --normalized \
      --check-only
    ;;

  --dry-run)
    python3 "${REPO_ROOT}/tools/bmad_skill_sync.py" \
      --source "${SOURCE}" \
      --dest "${DEST}" \
      --manifest "${MANIFEST}" \
      --normalized \
      --dry-run
    ;;

  --sync)
    python3 "${REPO_ROOT}/tools/bmad_skill_sync.py" \
      --source "${SOURCE}" \
      --dest "${DEST}" \
      --manifest "${MANIFEST}" \
      --normalized
    ;;

  *)
    echo "Usage: $0 [--check|--dry-run|--sync]" >&2
    exit 2
    ;;
esac