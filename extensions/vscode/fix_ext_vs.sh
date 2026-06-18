#!/usr/bin/env bash
set -euo pipefail

# Optional fallback: with the .vscodeignore fix the .vsix already bundles the
# 'diff' runtime dependency, so this script is normally NOT needed. Keep it to
# repair an already-installed extension dir that is missing node_modules.
cd ~/.vscode/extensions/authenticfake.clike-0.5.3
rm -rf package-lock.json node_modules
npm install --omit=dev
cd ~/dev/authenticfake/clike/clike_mvp/extensions/vscode
