'use strict';
// clikeGitSync against real temporary git repositories (WP5).
const test = require('node:test');
const assert = require('node:assert/strict');
const Module = require('module');
const fs = require('fs');
const os = require('os');
const path = require('path');
const { execFileSync } = require('child_process');

const originalLoad = Module._load;
Module._load = function (request, parent, isMain) {
  if (request === 'vscode') return { commands: { executeCommand: async () => undefined } };
  return originalLoad.call(this, request, parent, isMain);
};
const { clikeGitSync } = require('../git');
Module._load = originalLoad;

const git = (cwd, ...args) => execFileSync('git', args, { cwd, encoding: 'utf8' }).trim();
const quietOut = { appendLine() {} };

function makeRepo({ init = true } = {}) {
  const dir = fs.realpathSync(fs.mkdtempSync(path.join(os.tmpdir(), 'clike-git-')));
  if (init) {
    git(dir, 'init', '-q', '-b', 'main');
    git(dir, 'config', 'user.name', 'Test');
    git(dir, 'config', 'user.email', 'test@example.com');
    git(dir, 'config', 'commit.gpgsign', 'false');
    fs.writeFileSync(path.join(dir, 'README.md'), 'base\n');
    git(dir, 'add', 'README.md');
    git(dir, 'commit', '-q', '-m', 'base');
  }
  return dir;
}

function settings(over = {}) {
  return {
    gitAutoCommit: true,
    gitDefaultBranch: 'main',
    gitRemote: 'origin',
    gitRemoteUrl: '',
    gitBranchPrefix: 'feature',
    gitTagPrefix: 'harper',
    gitPushRebase: false,
    gitAutoPush: false,
    gitMergeOnGate: false,
    gitConventionalCommits: true,
    ...over,
  };
}

function write(dir, rel, content) {
  const p = path.join(dir, rel);
  fs.mkdirSync(path.dirname(p), { recursive: true });
  fs.writeFileSync(p, content);
  return p;
}

const sync = (dir, phase, reqId, files, s = settings()) =>
  clikeGitSync(phase, `run-${phase}`, reqId, files, { workspaceRoot: dir }, s, quietOut);

const isAncestor = (dir, a, b) => {
  try {
    git(dir, 'merge-base', '--is-ancestor', a, b);
    return true;
  } catch {
    return false;
  }
};

test('a later phase on an existing REQ branch keeps its earlier commits', async () => {
  const dir = makeRepo();
  await sync(dir, 'kit', 'REQ-001', [write(dir, 'runs/kit/REQ-001/src/a.py', 'a\n')]);
  const kitCommit = git(dir, 'rev-parse', 'feature/req-001');
  git(dir, 'switch', '-q', 'main'); // the user goes back to main
  await sync(dir, 'eval', 'REQ-001', [write(dir, 'runs/kit/REQ-001/reports/eval.json', '{}\n')]);
  assert.ok(isAncestor(dir, kitCommit, 'feature/req-001'), 'kit commit must still be on feature/req-001');
});

test('a document phase never moves main onto an unreviewed REQ branch', async () => {
  const dir = makeRepo();
  const mainBefore = git(dir, 'rev-parse', 'main');
  await sync(dir, 'kit', 'REQ-001', [write(dir, 'runs/kit/REQ-001/src/a.py', 'a\n')]);
  const kitCommit = git(dir, 'rev-parse', 'feature/req-001');
  // still on feature/req-001 here
  await sync(dir, 'spec', null, [write(dir, 'docs/harper/SPEC.md', '# SPEC\n')]);
  assert.equal(git(dir, 'rev-parse', 'main~1'), mainBefore, 'main advances by exactly the spec commit');
  assert.ok(!isAncestor(dir, kitCommit, 'main'), 'REQ work must not land on main');
  assert.equal(git(dir, 'rev-parse', 'feature/req-001'), kitCommit, 'REQ branch untouched');
});

test('only the phase files are committed; unrelated user changes stay uncommitted', async () => {
  const dir = makeRepo();
  write(dir, 'notes.txt', 'private notes\n');
  fs.appendFileSync(path.join(dir, 'README.md'), 'local edit\n');
  await sync(dir, 'kit', 'REQ-001', [write(dir, 'runs/kit/REQ-001/src/a.py', 'a\n')]);
  const committed = git(dir, 'show', '--name-only', '--format=', 'feature/req-001').split('\n').filter(Boolean);
  assert.deepEqual(committed, ['runs/kit/REQ-001/src/a.py']);
  const status = git(dir, 'status', '--porcelain');
  assert.match(status, /\?\? notes\.txt/);
  assert.match(status, /^ ?M README\.md/m);
});

test('without phase files nothing is committed (no add -A fallback)', async () => {
  const dir = makeRepo();
  write(dir, 'stray.txt', 'x\n');
  const head = git(dir, 'rev-parse', 'HEAD');
  await sync(dir, 'spec', null, []);
  assert.equal(git(dir, 'rev-parse', 'main'), head);
  assert.match(git(dir, 'status', '--porcelain'), /\?\? stray\.txt/);
});

test('files outside the workspace are never staged', async () => {
  const dir = makeRepo();
  const outside = path.join(os.tmpdir(), `clike-outside-${process.pid}.txt`);
  fs.writeFileSync(outside, 'x');
  await sync(dir, 'spec', null, [outside, write(dir, 'docs/harper/SPEC.md', '# S\n')]);
  const committed = git(dir, 'show', '--name-only', '--format=', 'main').split('\n').filter(Boolean);
  assert.deepEqual(committed, ['docs/harper/SPEC.md']);
});

test('no push unless autoPush is enabled, even with a remote', async () => {
  const remote = fs.realpathSync(fs.mkdtempSync(path.join(os.tmpdir(), 'clike-remote-')));
  git(remote, 'init', '-q', '--bare');
  const dir = makeRepo();
  git(dir, 'remote', 'add', 'origin', remote);
  await sync(dir, 'kit', 'REQ-001', [write(dir, 'runs/kit/REQ-001/src/a.py', 'a\n')]);
  assert.equal(git(remote, 'for-each-ref'), '', 'nothing pushed');
  await sync(dir, 'eval', 'REQ-001', [write(dir, 'runs/kit/REQ-001/r.json', '{}\n')], settings({ gitAutoPush: true }));
  assert.match(git(remote, 'for-each-ref', '--format=%(refname)'), /refs\/heads\/feature\/req-001/);
});

test('conventional commit messages follow the conventionalCommits setting', async () => {
  const dir = makeRepo();
  await sync(dir, 'kit', 'REQ-001', [write(dir, 'runs/kit/REQ-001/src/a.py', 'a\n')]);
  assert.match(git(dir, 'log', '-1', '--format=%s', 'feature/req-001'), /^feat\(req-001\): implement/);
});

test('initializing a new repo does not commit existing workspace files', async () => {
  const dir = makeRepo({ init: false });
  write(dir, '.env', 'OPENAI_API_KEY=sk-should-never-be-committed\n');
  write(dir, 'app.py', 'print(1)\n');
  const env = { ...process.env, GIT_AUTHOR_NAME: 'T', GIT_AUTHOR_EMAIL: 't@e', GIT_COMMITTER_NAME: 'T', GIT_COMMITTER_EMAIL: 't@e' };
  const prev = { ...process.env };
  Object.assign(process.env, env);
  try {
    await sync(dir, 'spec', null, [write(dir, 'docs/harper/SPEC.md', '# S\n')]);
  } finally {
    process.env = prev;
  }
  const tracked = git(dir, 'ls-files').split('\n').filter(Boolean);
  assert.ok(!tracked.includes('.env'), '.env must not be committed');
  assert.ok(!tracked.includes('app.py'), 'unrelated files must not be committed');
  assert.ok(tracked.includes('docs/harper/SPEC.md'));
});

test('content the user already staged is not swept into the phase commit', async () => {
  const dir = makeRepo();
  write(dir, 'wip.txt', 'user work in progress\n');
  git(dir, 'add', 'wip.txt');
  await sync(dir, 'spec', null, [write(dir, 'docs/harper/SPEC.md', '# S\n')]);
  const committed = git(dir, 'show', '--name-only', '--format=', 'main').split('\n').filter(Boolean);
  assert.deepEqual(committed, ['docs/harper/SPEC.md']);
  assert.match(git(dir, 'status', '--porcelain'), /^A {2}wip\.txt/m, 'still staged for the user');
});

test('a conflicting switch aborts the sync and loses nothing', async () => {
  const dir = makeRepo();
  await sync(dir, 'kit', 'REQ-001', [write(dir, 'shared.txt', 'from kit\n')]);
  git(dir, 'switch', '-q', 'main');
  // main has no shared.txt; an untracked shared.txt with different content would be overwritten by the switch
  write(dir, 'shared.txt', 'user content\n');
  const before = git(dir, 'rev-parse', 'feature/req-001');
  await sync(dir, 'eval', 'REQ-001', [write(dir, 'runs/kit/REQ-001/r.json', '{}\n')]);
  assert.equal(git(dir, 'rev-parse', '--abbrev-ref', 'HEAD'), 'main', 'stayed on main');
  assert.equal(git(dir, 'rev-parse', 'feature/req-001'), before, 'REQ branch untouched');
  assert.equal(fs.readFileSync(path.join(dir, 'shared.txt'), 'utf8'), 'user content\n', 'user file intact');
  assert.ok(fs.existsSync(path.join(dir, 'runs/kit/REQ-001/r.json')), 'phase file kept in the working tree');
});

test('merge-on-gate is opt-in', async () => {
  const dir = makeRepo();
  await sync(dir, 'kit', 'REQ-001', [write(dir, 'runs/kit/REQ-001/src/a.py', 'a\n')]);
  const kitCommit = git(dir, 'rev-parse', 'feature/req-001');
  await sync(dir, 'gate', 'REQ-001', [write(dir, 'runs/kit/REQ-001/gate.json', '{}\n')]);
  assert.ok(!isAncestor(dir, kitCommit, 'main'), 'no merge by default');
  await sync(dir, 'gate', 'REQ-001', [write(dir, 'runs/kit/REQ-001/gate2.json', '{}\n')], settings({ gitMergeOnGate: true }));
  assert.ok(isAncestor(dir, kitCommit, 'main'), 'merged when enabled');
  assert.equal(git(dir, 'rev-parse', '--abbrev-ref', 'HEAD'), 'main');
});
