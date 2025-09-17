#!/usr/bin/env bash
rm -rf package-lock.json node_modules
npm install
vsce package
code --install-extension clike-*.vsix 
