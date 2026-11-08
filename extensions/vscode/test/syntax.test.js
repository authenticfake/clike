'use strict';
// Every module of the extension parses — extension.js included, which the unit tests cannot
// require (it needs the VS Code API): a duplicate declaration there would stop the extension
// from loading while every other test passes.
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('fs');
const path = require('path');
const { spawnSync } = require('child_process');

const ROOT = path.join(__dirname, '..');

test('every extension module parses', () => {
  const files = fs.readdirSync(ROOT).filter((f) => f.endsWith('.js'));
  assert.ok(files.includes('extension.js'));
  for (const file of files) {
    const r = spawnSync(process.execPath, ['--check', path.join(ROOT, file)], { encoding: 'utf8' });
    assert.equal(r.status, 0, `${file}: ${r.stderr}`);
  }
});
