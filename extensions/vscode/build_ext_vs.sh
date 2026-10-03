#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

# Reproducible install from package-lock.json (dev tools included: lint, tests, vsce).
# .vscodeignore keeps only the runtime dependency 'diff' inside the package.
npm ci
npm run check
npm run package

# Sanity check: the 'diff' runtime dependency MUST be inside the .vsix, otherwise
# the activated extension fails with "Cannot find module 'diff'".
VSIX="$(ls -t clike-*.vsix | head -1)"
python3 -c "import sys,zipfile; sys.exit(0 if any('node_modules/diff/' in n for n in zipfile.ZipFile('$VSIX').namelist()) else 1)" \
  || { echo "ERROR: 'diff' is missing from $VSIX — check .vscodeignore." >&2; exit 1; }
echo "OK: 'diff' bundled in $VSIX"

if [ "${CLIKE_INSTALL_VSIX:-1}" = "1" ] && command -v code >/dev/null 2>&1; then
  code --install-extension "$VSIX"
fi
