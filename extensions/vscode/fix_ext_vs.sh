#!/usr/bin/env bash
cd ~/.vscode/extensions/authenticfake.clike-0.5.3
rm -rf package-lock.json node_modules
npm install -omit-dev
cd ~/dev/authenticfake/clike/clike_mvp/extensions/vscode
