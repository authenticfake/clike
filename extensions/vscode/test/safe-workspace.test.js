'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const path = require('path');
const { safeRelativePath, isInsideRoot, safeWorkspaceUri, resolveInsideWorkspace } = require('../safe-workspace');

// Minimal stand-in for vscode.Uri (joinPath normalizes '..' like the real one).
const FakeUri = {
  file: (p) => ({ fsPath: path.resolve(p), path: path.resolve(p) }),
  parse: (s) => FakeUri.file(decodeURIComponent(s.replace(/^file:\/\//, ''))),
  joinPath: (base, ...parts) => FakeUri.file(path.join(base.fsPath, ...parts)),
};
const ROOT = FakeUri.file('/ws/project');

test('relative paths are normalized', () => {
  assert.equal(safeRelativePath('docs/harper/SPEC.md'), 'docs/harper/SPEC.md');
  assert.equal(safeRelativePath('./runs/kit/REQ-001/src/a.py'), 'runs/kit/REQ-001/src/a.py');
  assert.equal(safeRelativePath('a\\b\\c.txt'), 'a/b/c.txt');
  assert.equal(safeRelativePath('a/./b/../c.txt'), 'a/c.txt');
});

test('escapes, absolute, drive, UNC and NUL are rejected', () => {
  for (const bad of ['../x', 'a/../../x', '..\\..\\x', '/etc/passwd', 'C:\\x', 'C:/x', '\\\\server\\share', '//server/share', '', '  ', 'a\0b', '.', 'a/..']) {
    assert.throws(() => safeRelativePath(bad), undefined, JSON.stringify(bad));
  }
});

test('safeWorkspaceUri stays inside the root', () => {
  assert.equal(safeWorkspaceUri(ROOT, 'src/a.js', FakeUri).fsPath, path.resolve('/ws/project/src/a.js'));
  assert.throws(() => safeWorkspaceUri(ROOT, '../../etc/x', FakeUri));
});

test('absolute paths are accepted only inside the workspace (no sibling prefix)', () => {
  assert.equal(resolveInsideWorkspace(ROOT, '/ws/project/a.txt', FakeUri).fsPath, path.resolve('/ws/project/a.txt'));
  assert.equal(resolveInsideWorkspace(ROOT, 'file:///ws/project/b.txt', FakeUri).fsPath, path.resolve('/ws/project/b.txt'));
  assert.throws(() => resolveInsideWorkspace(ROOT, '/ws/project2/a.txt', FakeUri));
  assert.throws(() => resolveInsideWorkspace(ROOT, '/etc/passwd', FakeUri));
  assert.throws(() => resolveInsideWorkspace(ROOT, 'file:///etc/passwd', FakeUri));
  assert.equal(isInsideRoot('/ws/project', '/ws/project'), true);
  assert.equal(isInsideRoot('/ws/project', '/ws/project2'), false);
});
