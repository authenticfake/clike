#!/usr/bin/env bash
set -euo pipefail

# Clean install of runtime dependencies only (no devDependencies leak into the
# package). The single runtime dep is 'diff', required by extension.js.
rm -rf package-lock.json node_modules
npm install --omit=dev

vsce package

# Sanity check: the 'diff' runtime dependency MUST be inside the .vsix, otherwise
# the activated extension fails with "Cannot find module 'diff'".
# Use python3's zipfile (reliable across zip variants; `unzip -l` can mis-list
# vsce packages).
VSIX="$(ls -t clike-*.vsix | head -1)"
if command -v python3 >/dev/null 2>&1; then
  if ! python3 -c "import sys,zipfile; sys.exit(0 if any('node_modules/diff/' in n for n in zipfile.ZipFile('$VSIX').namelist()) else 1)"; then
    echo "ERROR: 'diff' is missing from $VSIX — check .vscodeignore (node_modules/** must keep !node_modules/diff/**)." >&2
    exit 1
  fi
  echo "OK: 'diff' bundled in $VSIX"
else
  echo "WARN: python3 not found; skipping 'diff' bundle verification."
fi

code --install-extension "$VSIX"
