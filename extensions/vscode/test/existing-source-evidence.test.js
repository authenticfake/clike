'use strict';
// Finalize reuses the promoted code (test project: the SQLite boundary already in src/ was not
// returned by the agent, so the orchestrator rejected the finalize). The unchanged sources are sent
// as evidence; env files, dependency folders, returned files and binaries are not.
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('fs');
const os = require('os');
const path = require('path');

const { collectExistingSourceEvidence } = require('../existing-source-evidence');

function write(root, rel, content) {
  fs.mkdirSync(path.join(root, path.dirname(rel)), { recursive: true });
  fs.writeFileSync(path.join(root, rel), content);
}

test('unchanged sources are sent; env files, dependency folders, returned and binary files are not', () => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'clike-src-ev-'));
  write(root, 'src/app/storage.py', 'import sqlite3\n');
  write(root, 'src/app/config.py', 'PATH = "APP_DB_PATH"\n');
  write(root, 'src/.env', 'APP_DB_PATH=/real/path\n');
  write(root, 'src/.env.runtime/python/lib/site.py', 'x = 1\n');
  write(root, 'src/node_modules/pkg/index.js', 'module.exports = 1;\n');
  write(root, 'src/app/logo.bin', Buffer.from([1, 0, 2]));
  write(root, 'README.md', 'outside src\n');

  const out = collectExistingSourceEvidence(root, ['src/app/config.py']);
  assert.deepEqual(out.map((f) => f.path), ['src/app/storage.py']);
  assert.equal(out[0].content, 'import sqlite3\n');
});

test('the evidence is bounded and an absent source folder sends nothing', () => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'clike-src-ev-'));
  assert.deepEqual(collectExistingSourceEvidence(root, []), []);
  write(root, 'src/a.py', 'a'.repeat(10));
  write(root, 'src/b.py', 'b'.repeat(10));
  write(root, 'src/big.py', 'c'.repeat(50));
  const out = collectExistingSourceEvidence(root, [], { maxFileBytes: 20, maxFiles: 1 });
  assert.deepEqual(out.map((f) => f.path), ['src/a.py']);
});
