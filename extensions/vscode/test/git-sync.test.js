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
const { clikeGitSync, porcelainPaths } = require('../git');
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
  // the developer is back on the REQ branch, which keeps its KIT and gets the documents
  assert.equal(git(dir, 'rev-parse', '--abbrev-ref', 'HEAD'), 'feature/req-001');
  assert.ok(isAncestor(dir, kitCommit, 'feature/req-001'), 'KIT commit kept');
  assert.ok(isAncestor(dir, 'main', 'feature/req-001'), 'spec commit merged into the REQ branch');
  assert.ok(fs.existsSync(path.join(dir, 'runs/kit/REQ-001/src/a.py')), 'KIT still in the working tree');
});

test('spec/ux companion documents get their own commit message', async () => {
  const dir = makeRepo();
  await sync(dir, 'spec', null, [write(dir, 'docs/harper/ux/DESIGN.md', '# UX\n')]);
  assert.match(git(dir, 'log', '-1', '--format=%s'), /^docs\(spec\): update DESIGN\.md/);
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

test('merge-on-gate skips a REQ whose promotion left conflicts', async () => {
  const dir = makeRepo();
  await sync(dir, 'kit', 'REQ-001', [write(dir, 'runs/kit/REQ-001/src/a.py', 'a\n')]);
  const kitCommit = git(dir, 'rev-parse', 'feature/req-001');
  await clikeGitSync('gate', 'run-gate', 'REQ-001', [write(dir, 'runs/kit/REQ-001/gate.json', '{}\n')],
    { workspaceRoot: dir, skipMergeOnGate: true }, settings({ gitMergeOnGate: true }), quietOut);
  assert.ok(!isAncestor(dir, kitCommit, 'main'), 'not merged while the promotion has conflicts');
  assert.ok(isAncestor(dir, kitCommit, 'feature/req-001'), 'the gate commit stays on the REQ branch');
});

test('the next REQ branch is stacked on an unmerged REQ branch, even with local changes', async () => {
  const dir = makeRepo();
  write(dir, 'docs/harper/plan.json', '{"v":1}\n');
  git(dir, 'add', '-A'); git(dir, 'commit', '-q', '-m', 'plan');
  await sync(dir, 'kit', 'REQ-003', [write(dir, 'runs/kit/REQ-003/src/a.py', 'a\n')]);
  await sync(dir, 'gate', 'REQ-003', [write(dir, 'src/a.py', 'a\n')]);
  const req003 = git(dir, 'rev-parse', 'feature/req-003');
  // local changes that differ between main and the REQ-003 branch (as plan.json/PLAN.md did)
  write(dir, 'docs/harper/plan.json', '{"v":2}\n');
  write(dir, 'src/a.py', 'a changed locally\n');
  await sync(dir, 'kit', 'REQ-004', [write(dir, 'runs/kit/REQ-004/src/b.py', 'b\n')]);
  assert.equal(git(dir, 'rev-parse', '--abbrev-ref', 'HEAD'), 'feature/req-004');
  assert.ok(isAncestor(dir, req003, 'feature/req-004'), 'REQ-004 carries the REQ-003 commits it depends on');
  assert.match(git(dir, 'log', '-1', '--format=%s'), /^feat\(req-004\): implement/);
  assert.equal(fs.readFileSync(path.join(dir, 'src/a.py'), 'utf8'), 'a changed locally\n'); // nothing lost
});

test('ignored phase paths (eval reports, KIT report dirs) are left out; the rest is committed', async () => {
  const dir = makeRepo();
  write(dir, '.gitignore', 'runs/eval/\nruns/**/reports/\n');
  git(dir, 'add', '.gitignore'); git(dir, 'commit', '-q', '-m', 'ignore');
  const files = [
    write(dir, 'runs/kit/REQ-005/src/web/polling.ts', 'fix\n'),
    write(dir, 'runs/kit/REQ-005/reports/unit.xml', '<x/>'),
    path.join(dir, 'runs/kit/REQ-005/reports'),
    write(dir, 'runs/eval/REQ-005/report.json', '{}'),
  ];
  await sync(dir, 'kit', 'REQ-005', files);
  const committed = git(dir, 'show', '--name-only', '--format=', 'feature/req-005').split('\n').filter(Boolean);
  assert.deepEqual(committed, ['runs/kit/REQ-005/src/web/polling.ts']);
  assert.doesNotMatch(git(dir, 'status', '--porcelain', '--untracked-files=no'), /polling/);
});

test('merge-on-gate pushes main even when the remote main moved (a PR merged on the host)', async () => {
  const remote = fs.realpathSync(fs.mkdtempSync(path.join(os.tmpdir(), 'clike-remote-')));
  git(remote, 'init', '-q', '--bare', '-b', 'main');
  const dir = makeRepo();
  git(dir, 'remote', 'add', 'origin', remote);
  git(dir, 'push', '-q', 'origin', 'main');
  // Someone merges a PR on the host: origin/main gets a commit the local main does not have.
  const other = fs.realpathSync(fs.mkdtempSync(path.join(os.tmpdir(), 'clike-other-')));
  git(other, 'clone', '-q', remote, '.');
  git(other, 'config', 'user.name', 'Host');
  git(other, 'config', 'user.email', 'host@example.com');
  git(other, 'config', 'commit.gpgsign', 'false');
  git(other, 'commit', '-q', '--allow-empty', '-m', 'Merge pull request #2');
  git(other, 'push', '-q', 'origin', 'main');
  const hostCommit = git(other, 'rev-parse', 'HEAD');

  await sync(dir, 'kit', 'REQ-001', [write(dir, 'runs/kit/REQ-001/src/a.py', 'a\n')]);
  const kitCommit = git(dir, 'rev-parse', 'feature/req-001');
  await sync(dir, 'gate', 'REQ-001', [write(dir, 'runs/kit/REQ-001/gate.json', '{}\n')],
    settings({ gitMergeOnGate: true, gitAutoPush: true }));

  const remoteMain = git(remote, 'rev-parse', 'main');
  assert.ok(isAncestor(remote, kitCommit, remoteMain), 'the REQ reached the remote main');
  assert.ok(isAncestor(remote, hostCommit, remoteMain), 'the host commit is kept');
  assert.equal(git(dir, 'rev-parse', 'main'), remoteMain, 'local and remote main are in sync');
});

test('porcelain paths keep their first character even when the output arrives trimmed', () => {
  assert.deepEqual(porcelainPaths('M docs/harper/PLAN.md\n M src/a.py\n?? new file.txt\nR  old.py -> new.py\n'),
    ['docs/harper/PLAN.md', 'src/a.py', 'new file.txt', 'new.py']);
});

test('a CLike agent package file rewritten by an eval does not block merge-on-gate', async () => {
  const dir = makeRepo();
  const pkg = 'runs/kit/REQ-001/docs/AGENT_EVAL_CONTEXT.json';
  await sync(dir, 'kit', 'REQ-001', [write(dir, 'runs/kit/REQ-001/src/a.py', 'a\n'), write(dir, pkg, '{"v":1}\n')]);
  write(dir, pkg, '{"v":2}\n'); // the eval pre-pass rewrote it; not in the gate's file list
  write(dir, 'notes.txt', 'mine\n'); // the developer's own change stays theirs
  await sync(dir, 'gate', 'REQ-001', [write(dir, 'runs/kit/REQ-001/gate.json', '{}\n')], settings({ gitMergeOnGate: true }));
  assert.equal(git(dir, 'rev-parse', '--abbrev-ref', 'HEAD'), 'main');
  assert.ok(isAncestor(dir, 'feature/req-001', 'main'), 'merged into main');
  assert.equal(git(dir, 'show', `main:${pkg}`), '{"v":2}');
  assert.match(git(dir, 'status', '--porcelain'), /\?\? notes\.txt/);
});

test('a tracked KIT file of the REQ changed after its phase does not block merge-on-gate', async () => {
  const dir = makeRepo();
  const howto = 'runs/kit/REQ-001/ci/HOWTO.md';
  await sync(dir, 'kit', 'REQ-001', [write(dir, 'runs/kit/REQ-001/src/a.py', 'a\n'), write(dir, howto, 'v1\n')]);
  write(dir, howto, 'v2\n'); // a pre-pass updated it; not in the gate's file list
  write(dir, 'runs/kit/REQ-001/reports/scratch.txt', 'agent scratch\n'); // untracked: left alone
  write(dir, 'notes.txt', 'mine\n');
  await sync(dir, 'gate', 'REQ-001', [write(dir, 'runs/kit/REQ-001/gate.json', '{}\n')], settings({ gitMergeOnGate: true }));
  assert.equal(git(dir, 'rev-parse', '--abbrev-ref', 'HEAD'), 'main');
  assert.ok(isAncestor(dir, 'feature/req-001', 'main'), 'merged into main');
  assert.equal(git(dir, 'show', `main:${howto}`), 'v2');
  const status = git(dir, 'status', '--porcelain');
  assert.match(status, /\?\? notes\.txt/);
  assert.match(status, /\?\? runs\/kit\/REQ-001\/reports\//);
});

test('a phase run on main carries its REQ KIT files onto the REQ branch, which tracks them', async () => {
  const dir = makeRepo();
  await sync(dir, 'kit', 'REQ-001', [write(dir, 'runs/kit/REQ-001/ci/LTC.json', 'v1\n'), write(dir, 'runs/kit/REQ-001/src/old.py', 'old\n')]);
  git(dir, 'switch', '-q', 'main'); // e.g. the gate of another REQ merged and left the developer on main
  write(dir, 'notes.txt', 'user\n');
  // a new /kit REQ-001 on main: untracked here, tracked on feature/req-001
  const files = [write(dir, 'runs/kit/REQ-001/ci/LTC.json', 'v2\n'), write(dir, 'runs/kit/REQ-001/src/new.py', 'new\n')];
  await sync(dir, 'kit', 'REQ-001', files);
  assert.equal(git(dir, 'rev-parse', '--abbrev-ref', 'HEAD'), 'feature/req-001');
  assert.equal(git(dir, 'show', 'feature/req-001:runs/kit/REQ-001/ci/LTC.json'), 'v2');
  assert.equal(git(dir, 'show', 'feature/req-001:runs/kit/REQ-001/src/new.py'), 'new');
  assert.equal(git(dir, 'status', '--porcelain'), '?? notes.txt', 'nothing else touched');
  assert.equal(fs.readdirSync(path.join(dir, '.git')).includes('clike-carry') ? fs.readdirSync(path.join(dir, '.git', 'clike-carry')).length : 0, 0);
});

test('untracked files outside the REQ KIT that block the switch are never carried', async () => {
  const dir = makeRepo();
  await sync(dir, 'kit', 'REQ-001', [write(dir, 'runs/kit/REQ-001/ci/LTC.json', 'v1\n'), write(dir, 'src/app.py', 'kit\n')]);
  git(dir, 'switch', '-q', 'main');
  write(dir, 'src/app.py', 'user\n');
  await sync(dir, 'kit', 'REQ-001', [write(dir, 'runs/kit/REQ-001/ci/LTC.json', 'v2\n')]);
  assert.equal(git(dir, 'rev-parse', '--abbrev-ref', 'HEAD'), 'main');
  assert.equal(fs.readFileSync(path.join(dir, 'src/app.py'), 'utf8'), 'user\n');
  assert.equal(fs.readFileSync(path.join(dir, 'runs/kit/REQ-001/ci/LTC.json'), 'utf8'), 'v2\n');
});

test('a document phase run from a REQ branch carries its handoff files onto main, which tracks them', async () => {
  const dir = makeRepo();
  await sync(dir, 'kit', 'REQ-001', [write(dir, 'runs/kit/REQ-001/src/a.py', 'a\n')]);
  git(dir, 'switch', '-q', 'main');
  await sync(dir, 'finalize', null, [write(dir, 'docs/harper/FINALIZE_REPORT.md', 'v1\n')]);
  git(dir, 'switch', '-q', 'feature/req-001'); // the REQ branch predates the first finalize
  write(dir, 'user.txt', 'user\n');
  await sync(dir, 'finalize', null, [write(dir, 'docs/harper/FINALIZE_REPORT.md', 'v2\n')]);
  assert.equal(git(dir, 'show', 'main:docs/harper/FINALIZE_REPORT.md'), 'v2');
  assert.equal(git(dir, 'rev-parse', '--abbrev-ref', 'HEAD'), 'feature/req-001', 'back on the REQ branch');
  assert.equal(fs.readFileSync(path.join(dir, 'docs/harper/FINALIZE_REPORT.md'), 'utf8'), 'v2\n');
  assert.equal(fs.readFileSync(path.join(dir, 'user.txt'), 'utf8'), 'user\n');
});
