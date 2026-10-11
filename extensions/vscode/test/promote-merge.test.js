'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('fs');
const os = require('os');
const path = require('path');
const { execFileSync } = require('child_process');

const { autoMergePromotion } = require('../promote-merge');

const sh = (cwd, ...args) => execFileSync('git', args, { cwd, stdio: ['ignore', 'pipe', 'pipe'] }).toString();
const write = (root, rel, text) => { fs.mkdirSync(path.dirname(path.join(root, rel)), { recursive: true }); fs.writeFileSync(path.join(root, rel), text); };
const read = (root, rel) => fs.readFileSync(path.join(root, rel), 'utf8');
const LINES = (n, tag = '') => Array.from({ length: n }, (_, i) => `line ${i + 1}${tag}`).join('\n') + '\n';

/** canonical src at the KIT start, then the KIT commit, then optional canonical edits. */
function repo() {
  const ws = fs.mkdtempSync(path.join(os.tmpdir(), 'clike-promote-'));
  sh(ws, 'init', '-q', '-b', 'main');
  sh(ws, 'config', 'user.email', 't@example.com'); sh(ws, 'config', 'user.name', 't');
  write(ws, 'src/app/same.py', 'same\n');
  write(ws, 'src/app/update.py', 'v1\n');
  write(ws, 'src/app/merge.py', LINES(12));
  write(ws, 'src/app/clash.py', 'value = 1\n');
  write(ws, 'src/app/canon_only.py', 'c1\n');
  sh(ws, 'add', '-A'); sh(ws, 'commit', '-qm', 'base');
  const kit = 'runs/kit/REQ-004';
  write(ws, `${kit}/src/app/same.py`, 'same\n');
  write(ws, `${kit}/src/app/update.py`, 'v2\n');
  write(ws, `${kit}/src/app/merge.py`, LINES(12).replace('line 11\n', 'line 11 candidate\n'));
  write(ws, `${kit}/src/app/clash.py`, 'value = 2\n');
  write(ws, `${kit}/src/app/canon_only.py`, 'c1\n');
  write(ws, `${kit}/src/app/new.py`, 'new\n');
  write(ws, `${kit}/test/test_new.py`, 'def test_x():\n    assert True\n');
  write(ws, `${kit}/src/app/__pycache__/x.pyc`, 'bin');
  write(ws, `${kit}/src/web/node_modules/pkg/index.js`, 'x');
  write(ws, `${kit}/ci/LTC.json`, '{}');
  write(ws, `${kit}/reports/unit.xml`, '<x/>');
  sh(ws, 'add', '-A'); sh(ws, 'commit', '-qm', 'feat(req-004): implement');
  // canonical edits after the KIT
  write(ws, 'src/app/merge.py', LINES(12).replace('line 2\n', 'line 2 canonical\n'));
  write(ws, 'src/app/clash.py', 'value = 3\n');
  write(ws, 'src/app/canon_only.py', 'c2\n');
  return ws;
}

test('auto-merge: add, update, merge, keep and conflict per file; scratch never promoted', () => {
  const ws = repo();
  const r = autoMergePromotion({ workspaceRoot: ws, reqId: 'REQ-004', now: new Date('2026-10-11T20:00:00Z') });
  const outcome = Object.fromEntries(r.results.map((x) => [x.path, x.outcome]));
  assert.deepEqual(outcome, {
    'src/app/canon_only.py': 'kept_canonical',
    'src/app/clash.py': 'conflict',
    'src/app/merge.py': 'merged',
    'src/app/new.py': 'added',
    'src/app/same.py': 'unchanged',
    'src/app/update.py': 'updated',
    'test/test_new.py': 'added',
  });
  assert.equal(r.promoted, false);
  assert.equal(read(ws, 'src/app/update.py'), 'v2\n');
  assert.match(read(ws, 'src/app/merge.py'), /line 2 canonical\n[\s\S]*line 11 candidate\n/);
  assert.equal(read(ws, 'src/app/clash.py'), 'value = 3\n'); // conflict: canonical untouched
  const conflict = r.results.find((x) => x.path === 'src/app/clash.py').conflictFile;
  assert.match(read(ws, conflict), /<<<<<<< canonical\nvalue = 3\n\|\|\|\|\|\|\| base\nvalue = 1\n=======\nvalue = 2\n>>>>>>> REQ-004/);
  assert.equal(read(ws, 'src/app/canon_only.py'), 'c2\n');
  for (const p of ['src/app/__pycache__/x.pyc', 'src/web/node_modules/pkg/index.js', 'ci/LTC.json', 'reports/unit.xml']) {
    assert.equal(fs.existsSync(path.join(ws, p)), false, p);
  }
  const report = fs.readFileSync(r.reportPath, 'utf8');
  assert.match(report, /NOT PROMOTED — 1 conflict/);
  assert.match(report, /`src\/app\/clash\.py` \| conflict/);
  assert.match(r.summary, /NOT promoted: 1 conflict/);
});

test('auto-merge: without conflicts it promotes, and the patch reverses the promotion', () => {
  const ws = repo();
  write(ws, 'src/app/clash.py', 'value = 1\n'); // canonical back to base: no conflict
  sh(ws, 'add', '-A'); sh(ws, 'commit', '-qm', 'canonical edits');
  const r = autoMergePromotion({ workspaceRoot: ws, reqId: 'REQ-004' });
  assert.equal(r.promoted, true, JSON.stringify(r.results));
  assert.match(r.summary, /promoted by auto-merge: 3 added|promoted by auto-merge/);
  const patch = r.reportFiles.find((f) => f.endsWith('promotion.diff'));
  sh(ws, 'apply', '--check', '-R', patch); // the patch is exactly what was applied
  assert.equal(JSON.parse(fs.readFileSync(r.reportFiles[1], 'utf8')).strategy, 'auto-merge');
});

test('auto-merge without git history: new and identical files only, others are conflicts', () => {
  const ws = fs.mkdtempSync(path.join(os.tmpdir(), 'clike-promote-nogit-'));
  write(ws, 'src/a.py', 'old\n');
  write(ws, 'runs/kit/REQ-001/src/a.py', 'new\n');
  write(ws, 'runs/kit/REQ-001/src/b.py', 'b\n');
  const r = autoMergePromotion({ workspaceRoot: ws, reqId: 'REQ-001' });
  assert.deepEqual(r.results.map((x) => [x.path, x.outcome]), [['src/a.py', 'conflict'], ['src/b.py', 'added']]);
  assert.equal(read(ws, 'src/a.py'), 'old\n');
  assert.equal(read(ws, 'src/b.py'), 'b\n');
});

test('auto-merge: an uncommitted KIT merges against the last commit before it was generated', () => {
  const ws = fs.mkdtempSync(path.join(os.tmpdir(), 'clike-promote-uncommitted-'));
  sh(ws, 'init', '-q', '-b', 'main');
  sh(ws, 'config', 'user.email', 't@example.com'); sh(ws, 'config', 'user.name', 't');
  write(ws, 'src/app.py', 'v1\n');
  sh(ws, 'add', '-A'); sh(ws, 'commit', '-qm', 'canonical');
  const kit = 'runs/kit/REQ-004';
  write(ws, `${kit}/docs/TARGET_CONTRACT.json`, '{}\n');
  write(ws, `${kit}/src/app.py`, 'v2\n');
  const future = new Date(Date.now() + 5000);
  fs.utimesSync(path.join(ws, kit, 'docs/TARGET_CONTRACT.json'), future, future); // generated after the commit
  const r = autoMergePromotion({ workspaceRoot: ws, reqId: 'REQ-004' });
  assert.equal(r.results[0].outcome, 'updated', JSON.stringify(r.results));
  assert.equal(read(ws, 'src/app.py'), 'v2\n');
  assert.match(fs.readFileSync(r.reportPath, 'utf8'), /last commit before the KIT was generated/);
});

test('auto-merge: lines added at the same place by both sides are kept; dependency KIT is the base', () => {
  const ws = fs.mkdtempSync(path.join(os.tmpdir(), 'clike-promote-union-'));
  sh(ws, 'init', '-q', '-b', 'main');
  sh(ws, 'config', 'user.email', 't@example.com'); sh(ws, 'config', 'user.name', 't');
  write(ws, 'docs/harper/plan.json', JSON.stringify({ reqs: [{ id: 'REQ-003' }, { id: 'REQ-004', dependsOn: ['REQ-003'] }] }));
  write(ws, 'src/.env.example', 'A=1\nB=2\n'); // promoted REQ-003 (uncommitted) + a local line
  write(ws, 'runs/kit/REQ-003/src/.env.example', 'A=1\n');
  write(ws, 'runs/kit/REQ-004/src/.env.example', 'A=1\nC=3\n');
  write(ws, 'runs/kit/REQ-003/src/app.py', 'v3\n');
  write(ws, 'src/app.py', 'v3\n');
  write(ws, 'runs/kit/REQ-004/src/app.py', 'v4\n');
  const r = autoMergePromotion({ workspaceRoot: ws, reqId: 'REQ-004' });
  const by = Object.fromEntries(r.results.map((x) => [x.path, x]));
  assert.equal(by['src/.env.example'].outcome, 'merged');
  assert.equal(read(ws, 'src/.env.example'), 'A=1\nB=2\nC=3\n');
  assert.equal(by['src/app.py'].outcome, 'updated');
  assert.equal(by['src/app.py'].base, 'REQ-003');
  assert.equal(r.promoted, true);
});

test('auto-merge: every conflict has its marker file, also without a merge base', () => {
  const ws = fs.mkdtempSync(path.join(os.tmpdir(), 'clike-promote-markers-'));
  write(ws, 'src/a.py', 'canonical\n');
  write(ws, 'runs/kit/REQ-001/src/a.py', 'candidate\n');
  const r = autoMergePromotion({ workspaceRoot: ws, reqId: 'REQ-001' });
  const c = r.results[0];
  assert.equal(c.outcome, 'conflict');
  assert.equal(read(ws, c.conflictFile), '<<<<<<< canonical\ncanonical\n=======\ncandidate\n>>>>>>> REQ-001\n');
  assert.match(fs.readFileSync(r.reportPath, 'utf8'), new RegExp(c.conflictFile.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')));
});
