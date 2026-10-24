const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('fs');
const os = require('os');
const path = require('path');

const { buildCockpitState, reportCounts } = require('../cockpit-state');

function project(files) {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'clike-cockpit-'));
  for (const [rel, content] of Object.entries(files)) {
    const file = path.join(root, ...rel.split('/'));
    fs.mkdirSync(path.dirname(file), { recursive: true });
    fs.writeFileSync(file, typeof content === 'string' ? content : JSON.stringify(content));
  }
  return root;
}

const plan = {
  project: 'Pingboard',
  reqs: [
    { id: 'REQ-001', title: 'Schema', status: 'done' },
    { id: 'REQ-002', title: 'API', status: 'in_progress', dependsOn: ['REQ-001'] },
    { id: 'REQ-003', title: 'UI', status: 'open', dependsOn: ['REQ-002'] },
    { id: 'REQ-004', title: 'Export', status: 'open', dependsOn: ['REQ-001'] },
  ],
};

test('a new project: no IDEA yet, the next action is /idea', () => {
  const state = buildCockpitState(project({ 'docs/harper/.keep': '' }));
  assert.equal(state.harper, true);
  assert.equal(state.next.command, '/idea');
  assert.deepEqual(state.phases.map((p) => p.state), ['active', 'todo', 'todo', 'todo', 'todo']);
  assert.equal(state.counts.total, 0);
});

test('release, phases, REQ notes and the next action come from the repository', () => {
  const root = project({
    'docs/harper/IDEA.md': '#', 'docs/harper/SPEC.md': '#', 'docs/harper/plan.json': plan,
    'docs/inputs/v1/a.md': '', 'docs/inputs/v2/b.md': '',
    'runs/kit/REQ-001/ci/LTC.json': '{}', 'runs/kit/REQ-002/ci/LTC.json': '{}',
    'runs/gate/REQ-001/report_REQ-001_100.json': { status: 'PASS', passed_count: 10 },
    'runs/eval/REQ-002/report_REQ-002_200.json': { status: 'FAIL', summary: 'EVAL FAIL — passed=8, failed=2, blocked=0, warnings=3', inputs_fingerprint: 'f1' },
  });
  const state = buildCockpitState(root, { fingerprint: () => 'f1' });
  assert.equal(state.release, 'v2');
  assert.deepEqual(state.releases, ['v1', 'v2']);
  assert.deepEqual(state.counts, { total: 4, done: 1, in_progress: 1, open: 2, deferred: 0 });
  assert.equal(state.progress_pct, 25);
  assert.deepEqual(state.phases.map((p) => p.state), ['done', 'done', 'done', 'active', 'todo']);
  const note = Object.fromEntries(state.reqs.map((r) => [r.id, r.note]));
  assert.deepEqual(note, { 'REQ-001': 'gate PASS', 'REQ-002': 'next: /eval', 'REQ-003': 'waits REQ-002', 'REQ-004': 'ready' });
  assert.equal(state.reqs[1].has_kit, true);
  assert.equal(state.reqs[3].has_kit, false);
  // the in-progress REQ first, resumed with the auto-eval since its last eval failed
  assert.equal(state.next.command, '/eval REQ-002 --fix');
  assert.deepEqual(
    { phase: state.last_run.phase, req: state.last_run.req_id, passed: state.last_run.passed, failed: state.last_run.failed, warnings: state.last_run.warnings },
    { phase: 'eval', req: 'REQ-002', passed: 8, failed: 2, warnings: 3 },
  );
});

test('an eval that passed on the current files resumes at the gate', () => {
  const root = project({
    'docs/harper/plan.json': plan, 'runs/kit/REQ-002/ci/LTC.json': '{}',
    'runs/eval/REQ-002/report_REQ-002_200.json': { status: 'PASS_WITH_WARNINGS', inputs_fingerprint: 'same' },
  });
  assert.equal(buildCockpitState(root, { fingerprint: () => 'same' }).next.command, '/gate REQ-002');
  assert.equal(buildCockpitState(root, { fingerprint: () => 'changed' }).next.command, '/eval REQ-002 --fix');
});

test('all REQs done: FINALIZE is the active phase, then everything is done', () => {
  const done = { reqs: plan.reqs.map((r) => ({ ...r, status: 'done' })) };
  const root = project({ 'docs/harper/IDEA.md': '#', 'docs/harper/SPEC.md': '#', 'docs/harper/plan.json': done });
  let state = buildCockpitState(root);
  assert.equal(state.next.command, '/finalize');
  assert.equal(state.phases[4].state, 'active');
  fs.writeFileSync(path.join(root, 'docs', 'harper', 'FINALIZE_REPORT.md'), '#');
  state = buildCockpitState(root);
  assert.equal(state.next.command, '');
  assert.ok(state.phases.every((p) => p.state === 'done'));
});

test('report counts: fields first, the summary line otherwise', () => {
  assert.deepEqual(reportCounts({ passed_count: 3, failed: ['a'], warning_count: 1, blocked_count: 0 }), { passed: 3, failed: 1, warnings: 1, blocked: 0 });
  assert.deepEqual(reportCounts({ passed: false, summary: 'passed=286, failed=2, blocked=0, warnings=13' }), { passed: 286, failed: 2, warnings: 13, blocked: 0 });
});

test('not a Harper workspace', () => {
  const state = buildCockpitState(project({ 'README.md': '' }));
  assert.equal(state.harper, false);
  assert.equal(state.counts.total, 0);
});
