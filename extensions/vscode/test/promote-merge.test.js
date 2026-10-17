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
// Python files are checked after a merge: their fixtures are valid Python.
const PYLINES = (n) => Array.from({ length: n }, (_, i) => `line_${i + 1} = ${i + 1}`).join('\n') + '\n';

/** canonical src at the KIT start, then the KIT commit, then optional canonical edits. */
function repo() {
  const ws = fs.mkdtempSync(path.join(os.tmpdir(), 'clike-promote-'));
  sh(ws, 'init', '-q', '-b', 'main');
  sh(ws, 'config', 'user.email', 't@example.com'); sh(ws, 'config', 'user.name', 't');
  write(ws, 'src/app/same.py', 'same\n');
  write(ws, 'src/app/update.py', 'v1\n');
  write(ws, 'src/app/merge.py', PYLINES(12));
  write(ws, 'src/app/clash.py', 'value = 1\n');
  write(ws, 'src/app/canon_only.py', 'c1\n');
  sh(ws, 'add', '-A'); sh(ws, 'commit', '-qm', 'base');
  const kit = 'runs/kit/REQ-004';
  write(ws, `${kit}/src/app/same.py`, 'same\n');
  write(ws, `${kit}/src/app/update.py`, 'v2\n');
  write(ws, `${kit}/src/app/merge.py`, PYLINES(12).replace('line_11 = 11\n', 'line_11 = "candidate"\n'));
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
  write(ws, 'src/app/merge.py', PYLINES(12).replace('line_2 = 2\n', 'line_2 = "canonical"\n'));
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
  assert.match(read(ws, 'src/app/merge.py'), /line_2 = "canonical"\n[\s\S]*line_11 = "candidate"\n/);
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

test('auto-merge: a new file under a [dynamic] route directory is added, not a false conflict', () => {
  const ws = repo();
  write(ws, 'src/app/clash.py', 'value = 1\n');
  sh(ws, 'add', '-A'); sh(ws, 'commit', '-qm', 'canonical edits');
  write(ws, 'runs/kit/REQ-004/src/web/app/runs/[run_id]/page.tsx', 'export default function Page() {}\n');
  sh(ws, 'add', '-A'); sh(ws, 'commit', '-qm', 'feat(req-004): dynamic route');
  const r = autoMergePromotion({ workspaceRoot: ws, reqId: 'REQ-004' });
  const entry = r.results.find((e) => e.path === 'src/web/app/runs/[run_id]/page.tsx');
  assert.equal(entry.outcome, 'added', JSON.stringify(entry));
  assert.equal(read(ws, 'src/web/app/runs/[run_id]/page.tsx'), 'export default function Page() {}\n');
});

/** One file at the KIT start (base), the candidate, then the canonical edit made after the KIT. */
function threeWay(base, candidate, canonical) {
  const ws = fs.mkdtempSync(path.join(os.tmpdir(), 'clike-promote-contains-'));
  sh(ws, 'init', '-q', '-b', 'main');
  sh(ws, 'config', 'user.email', 't@example.com'); sh(ws, 'config', 'user.name', 't');
  write(ws, 'src/api.ts', base);
  sh(ws, 'add', '-A'); sh(ws, 'commit', '-qm', 'base');
  write(ws, 'runs/kit/REQ-008/src/api.ts', candidate);
  sh(ws, 'add', '-A'); sh(ws, 'commit', '-qm', 'feat(req-008): kit');
  write(ws, 'src/api.ts', canonical);
  return ws;
}

const API = (routes, keys, tail = 'return 1;') => `${LINES(4)}const routes = /^(${routes})$/;\n${LINES(4, 'b')}const keys = [${keys}];\n${LINES(4, 'c')}${tail}\n`;

test('auto-merge: where the candidate holds the whole canonical side plus additions, the candidate wins', () => {
  // REQ-007 promoted companies/<id> after the KIT base; REQ-008 rewrote the same lines from it.
  const ws = threeWay(API('runs', "'q'"), API('runs|companies/id(/evidence)?', "'q', 'country', 'fit_min'"), API('runs|companies/id', "'q', 'country'"));
  const r = autoMergePromotion({ workspaceRoot: ws, reqId: 'REQ-008' });
  assert.equal(r.promoted, true);
  assert.equal(r.results[0].outcome, 'merged');
  assert.match(r.results[0].reason, /2 place\(s\) where REQ-008 contains src\/ plus its own additions: REQ-008 kept/);
  assert.equal(read(ws, 'src/api.ts'), API('runs|companies/id(/evidence)?', "'q', 'country', 'fit_min'"));
  assert.ok(!fs.existsSync(path.join(path.dirname(r.reportPath), 'conflicts.md')));
});

test('auto-merge: the resolvable spots are merged, only the real ones stay, explained in conflicts.md', () => {
  // keys: canonical added 'owner', which the candidate lacks: a real conflict. routes: contained.
  const ws = threeWay(API('runs', "'q'"), API('runs|companies/id(/evidence)?', "'q', 'fit_min'"), API('runs|companies/id', "'q', 'owner'"));
  const r = autoMergePromotion({ workspaceRoot: ws, reqId: 'REQ-008' });
  const c = r.results[0];
  assert.equal(r.promoted, false);
  assert.equal(c.outcome, 'conflict');
  assert.match(c.reason, /^1 overlapping change\(s\); 1 place\(s\) where REQ-008 contains/);
  const markers = read(ws, c.conflictFile);
  assert.match(markers, /const routes = \/\^\(runs\|companies\/id\(\/evidence\)\?\)\$\/;/);
  assert.equal(markers.match(/^<<<<<<< canonical$/gm).length, 1);
  assert.equal(read(ws, 'src/api.ts'), API('runs|companies/id', "'q', 'owner'"));
  const md = read(ws, path.relative(ws, path.join(path.dirname(r.reportPath), 'conflicts.md')));
  assert.ok(r.reportFiles.some((f) => f.endsWith('conflicts.md')));
  assert.match(md, /### Spot 1 of 1 — line 10 of src\//);
  assert.match(md, /\*\*src\/ now\*\*\n\n```ts\nconst keys = \['q', 'owner'\];\n```/);
  assert.match(md, /\*\*REQ-008 wants\*\*\n\n```ts\nconst keys = \['q', 'fit_min'\];\n```/);
  assert.match(md, /```diff\n-const keys = \['q', 'owner'\];\n\+const keys = \['q', 'fit_min'\];\n```/);
  assert.match(md, /each side has something the other lacks/);
  assert.match(fs.readFileSync(r.reportPath, 'utf8'), /`conflicts\.md`/);
});

test('auto-merge: canonical holding the whole candidate stays a conflict (src/ was not tested with this REQ)', () => {
  const ws = threeWay(API('runs', "'q'"), API('runs', "'q', 'fit_min'"), API('runs', "'q', 'fit_min', 'owner'"));
  const r = autoMergePromotion({ workspaceRoot: ws, reqId: 'REQ-008' });
  assert.equal(r.results[0].outcome, 'conflict');
  const md = fs.readFileSync(path.join(path.dirname(r.reportPath), 'conflicts.md'), 'utf8');
  assert.match(md, /src\/ already holds everything REQ-008 adds here, plus more: keeping src\/ is likely right/);
});

test('auto-merge: without a merge base, a candidate holding the whole canonical file is kept', () => {
  const ws = fs.mkdtempSync(path.join(os.tmpdir(), 'clike-promote-nobase-'));
  write(ws, 'src/a.ts', "export const keys = ['q'];\n");
  write(ws, 'runs/kit/REQ-001/src/a.ts', "export const keys = ['q', 'fit_min'];\nexport const more = 1;\n");
  const r = autoMergePromotion({ workspaceRoot: ws, reqId: 'REQ-001' });
  assert.equal(r.results[0].outcome, 'merged');
  assert.match(r.results[0].reason, /no merge base, but REQ-001 contains the whole canonical file/);
  assert.equal(read(ws, 'src/a.ts'), "export const keys = ['q', 'fit_min'];\nexport const more = 1;\n");
});

// Promotion is idempotent: a block src/ already received (from an earlier REQ, or the same REQ
// promoted before) is never added again. Real case: create_app() repeated 5 times in app.py.
const BLOCK = 'if qualification_config is None and "Q" in os.environ:\n    qualification_config = QualificationConfig.from_env()\n';
const APP = (...blocks) => `import os\n\n${LINES(3)}def create_app():\n${blocks.join('')}    return app\n`;

test('auto-merge: what src/ already has is not added again (same REQ twice, or an older KIT base)', () => {
  // KIT base without the block; src/ already received it from an earlier REQ, plus another one.
  const extra = 'if scoring_config is None and "S" in os.environ:\n    scoring_config = ScoringConfig.from_env()\n';
  const ws = threeWay(APP(), APP(BLOCK), APP(BLOCK, extra));
  const r = autoMergePromotion({ workspaceRoot: ws, reqId: 'REQ-008' });
  assert.equal(r.promoted, true);
  assert.match(r.results[0].reason || '', /src\/ already has what REQ-008 adds: src\/ kept/);
  assert.equal(read(ws, 'src/api.ts'), APP(BLOCK, extra));
  const again = autoMergePromotion({ workspaceRoot: ws, reqId: 'REQ-008' });
  assert.equal(read(ws, 'src/api.ts'), APP(BLOCK, extra));
  assert.equal(again.promoted, true);
});

test('auto-merge: different additions at the same place are still both kept; overlapping ones are a conflict', () => {
  const mine = 'if contacts_config is None and "C" in os.environ:\n    contacts_config = ContactsConfig.from_env()\n';
  const ws = threeWay(APP(), APP(mine), APP(BLOCK));
  const r = autoMergePromotion({ workspaceRoot: ws, reqId: 'REQ-008' });
  assert.equal(r.promoted, true);
  assert.equal(read(ws, 'src/api.ts'), APP(BLOCK, mine));
  // the candidate repeats the canonical block and adds its own: shared lines, neither contains the other
  const ws2 = threeWay(APP(), APP(`${mine}${BLOCK.replace('from_env()', 'from_env(strict=True)')}`), APP(BLOCK, 'x_value = compute_something_else()\n'));
  const r2 = autoMergePromotion({ workspaceRoot: ws2, reqId: 'REQ-008' });
  assert.equal(r2.results[0].outcome, 'conflict');
});

test('auto-merge: a clean merge that would repeat lines both sides added is a conflict', () => {
  // src/ received the block near the top; the KIT (older base) adds it near the bottom
  const top = (b) => `import os\n${b}${LINES(10)}`;
  const bottom = (b) => `import os\n${LINES(10)}${b}`;
  const ws = threeWay(`import os\n${LINES(10)}`, bottom(BLOCK), top(BLOCK));
  const r = autoMergePromotion({ workspaceRoot: ws, reqId: 'REQ-008' });
  assert.equal(r.results[0].outcome, 'conflict');
  assert.match(r.results[0].reason, /would repeat 2 line\(s\) both sides added/);
  assert.equal(read(ws, 'src/api.ts'), top(BLOCK));  // not written
});

test('auto-merge: a merged Python file that does not compile is not written', () => {
  const ws = fs.mkdtempSync(path.join(os.tmpdir(), 'clike-promote-invalid-'));
  sh(ws, 'init', '-q', '-b', 'main');
  sh(ws, 'config', 'user.email', 't@example.com'); sh(ws, 'config', 'user.name', 't');
  const sig = (params) => `${PYLINES(3)}def create_app(\n    settings=None,\n${params}):\n    return settings\n`;
  write(ws, 'src/app.py', sig(''));
  sh(ws, 'add', '-A'); sh(ws, 'commit', '-qm', 'base');
  write(ws, 'runs/kit/REQ-009/src/app.py', sig('    review_config=None,\n'));
  sh(ws, 'add', '-A'); sh(ws, 'commit', '-qm', 'feat(req-009): kit');
  write(ws, 'src/app.py', sig('    settings=None,\n'));  // src/ already broken: a duplicate argument
  const r = autoMergePromotion({ workspaceRoot: ws, reqId: 'REQ-009' });
  const has = spawnPython();
  if (!has) return;  // no Python on this machine: nothing to check
  assert.equal(r.results[0].outcome, 'conflict');
  assert.match(r.results[0].reason, /not valid Python .*duplicate argument/);
  assert.equal(read(ws, 'src/app.py'), sig('    settings=None,\n'));
  assert.ok(fs.existsSync(path.join(ws, r.results[0].conflictFile)));
});

function spawnPython() {
  const { spawnSync } = require('child_process');
  return ['python3', 'python'].some((c) => !spawnSync(c, ['--version']).error);
}
