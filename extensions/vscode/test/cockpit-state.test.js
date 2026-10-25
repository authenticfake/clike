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

test('no Harper project: the next action is /init <name>', () => {
  const state = buildCockpitState(project({ 'README.md': '' }));
  assert.equal(state.next.command, '/init <name>');
});

test('right after /init the documents are its templates: the next action is /idea, not /plan', () => {
  const fsx = require('fs');
  const tpl = (f) => fsx.readFileSync(path.join(__dirname, '..', 'templates', 'harper-init', 'docs', 'harper', f), 'utf8').split('${project.name}').join('Pingboard');
  const root = project({ 'docs/harper/IDEA.md': tpl('IDEA.md'), 'docs/harper/SPEC.md': tpl('SPEC.md') });
  let state = buildCockpitState(root);
  assert.equal(state.next.command, '/idea');
  assert.deepEqual(state.phases.map((p) => p.state), ['active', 'todo', 'todo', 'todo', 'todo']);
  // /idea ran: its run is recorded in runs/idea, IDEA.md rewritten
  fsx.mkdirSync(path.join(root, 'runs', 'idea', 'docs'), { recursive: true });
  fsx.writeFileSync(path.join(root, 'runs', 'idea', 'docs', 'IDEA.md'), '# IDEA');
  state = buildCockpitState(root);
  assert.equal(state.next.command, '/spec');
  // a SPEC edited by hand (no run recorded) counts as written
  fsx.writeFileSync(path.join(root, 'docs', 'harper', 'SPEC.md'), tpl('SPEC.md') + '\n## Use Cases\nUC-01 sign in');
  assert.equal(buildCockpitState(root).next.command, '/plan');
});

test('BMAD: a phase whose roles have not all run stays a choice next to the next step', () => {
  const root = project({ 'docs/harper/IDEA.md': '# IDEA real', 'docs/harper/SPEC.md': '# SPEC real', 'runs/idea/docs/x.md': '', 'runs/spec/docs/x.md': '',
    'docs/harper/bmad/spec/PRD.md': '# PRD' });
  const bmad = { methodology: 'bmad' };
  let state = buildCockpitState(root, bmad);
  assert.equal(state.next.command, '/plan');
  assert.deepEqual(state.alternatives.map((a) => a.command), ['/spec --methodology bmad --agent ux'], 'SPEC by pm ran, by ux not yet');
  assert.deepEqual(buildCockpitState(root).alternatives, [], 'native Harper: no roles');
  // ux ran too: /plan for certain
  fs.mkdirSync(path.join(root, 'docs', 'harper', 'ux'), { recursive: true });
  fs.writeFileSync(path.join(root, 'docs', 'harper', 'ux', 'USER_JOURNEYS.md'), '# journeys');
  assert.deepEqual(buildCockpitState(root, bmad).alternatives, []);
  // PLAN by architect: /kit next, PLAN by pm still possible until the KIT starts
  fs.writeFileSync(path.join(root, 'docs', 'harper', 'plan.json'), JSON.stringify({ reqs: [{ id: 'REQ-001', status: 'open' }] }));
  fs.mkdirSync(path.join(root, 'runs', 'plan'), { recursive: true });
  fs.writeFileSync(path.join(root, 'runs', 'plan', 'x.md'), '');
  fs.mkdirSync(path.join(root, 'docs', 'harper', 'bmad', 'architecture'), { recursive: true });
  fs.writeFileSync(path.join(root, 'docs', 'harper', 'bmad', 'architecture', 'ARCHITECTURE.md'), '# arch');
  state = buildCockpitState(root, bmad);
  assert.equal(state.next.command, '/kit REQ-001');
  assert.deepEqual(state.alternatives.map((a) => a.command), ['/plan --methodology bmad --agent pm']);
  fs.writeFileSync(path.join(root, 'docs', 'harper', 'plan.json'), JSON.stringify({ reqs: [{ id: 'REQ-001', status: 'in_progress' }] }));
  assert.deepEqual(buildCockpitState(root, bmad).alternatives, [], 'the KIT started: no going back');
  // SPEC roles are a choice only until the PLAN is done
  fs.rmSync(path.join(root, 'docs', 'harper', 'ux'), { recursive: true });
  assert.ok(!buildCockpitState(root, bmad).alternatives.some((a) => a.command.startsWith('/spec')), 'no /spec --agent ux after the PLAN');
});

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

test('a failed /finalize stays the next action even when the agent already wrote its report', () => {
  // test project: the local agent wrote FINALIZE_REPORT.md, CLike rejected the result, the cockpit
  // showed FINALIZE done and proposed nothing
  const { writeFinalizeOutcome } = require('../finalize-outcome');
  const done = { reqs: plan.reqs.map((r) => ({ ...r, status: 'done' })) };
  const root = project({
    'docs/harper/IDEA.md': '#', 'docs/harper/SPEC.md': '#', 'docs/harper/plan.json': done,
    'docs/harper/FINALIZE_REPORT.md': '#',
  });
  writeFinalizeOutcome(root, 'failed', 'Orchestrator rejected local-agent result: finalize_database_env_placeholders_missing');
  let state = buildCockpitState(root);
  assert.equal(state.next.command, '/finalize');
  assert.match(state.next.message, /last \/finalize failed \(Orchestrator rejected/);
  assert.equal(state.phases[4].state, 'active');
  assert.equal(state.progress_pct, 99);
  writeFinalizeOutcome(root, 'ok', 'eval PASS');
  state = buildCockpitState(root);
  assert.equal(state.next.command, '');
  assert.equal(state.progress_pct, 100);
  assert.ok(state.phases.every((p) => p.state === 'done'));
});

test('/idea --extend becomes the next action when the next release has its inputs', () => {
  const done = { reqs: plan.reqs.map((r) => ({ ...r, status: 'done' })) };
  const root = project({ 'docs/harper/IDEA.md': '#', 'docs/harper/SPEC.md': '#', 'docs/harper/plan.json': done, 'docs/inputs/v1/req.docx': 'x' });
  // delivered, not finalized, no new release: /finalize only
  let state = buildCockpitState(root);
  assert.equal(state.next.command, '/finalize');
  assert.deepEqual(state.alternatives, []);
  // the v2 requirements arrive: extend is a choice next to /finalize
  fs.mkdirSync(path.join(root, 'docs', 'inputs', 'v2'), { recursive: true });
  fs.writeFileSync(path.join(root, 'docs', 'inputs', 'v2', 'new.docx'), 'x');
  state = buildCockpitState(root);
  assert.equal(state.next.command, '/finalize');
  assert.deepEqual(state.alternatives.map((a) => a.command), ['/idea --extend']);
  assert.match(state.alternatives[0].message, /Release v2: 1 input file/);
  // finalized: the extend is the next action
  fs.writeFileSync(path.join(root, 'docs', 'harper', 'FINALIZE_REPORT.md'), '#');
  assert.equal(buildCockpitState(root).next.command, '/idea --extend');
  // an empty v2 folder is not an input
  fs.unlinkSync(path.join(root, 'docs', 'inputs', 'v2', 'new.docx'));
  state = buildCockpitState(root);
  assert.equal(state.next.command, '');
  assert.match(state.next.message, /docs\/inputs\/v2\//);
  // REQs of v2 in the plan (the extend ran): no extend proposed until a v3 arrives
  fs.writeFileSync(path.join(root, 'docs', 'inputs', 'v2', 'new.docx'), 'x');
  fs.writeFileSync(path.join(root, 'docs', 'harper', 'plan.json'), JSON.stringify({ reqs: [...done.reqs, { id: 'REQ-005', status: 'open', release: 'v2' }] }));
  assert.equal(buildCockpitState(root).next.command, '/kit REQ-005');
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

test('a REQ the plan declares not ready for its KIT: decisions first, the KIT only if forced', () => {
  const { kitBlockers } = require('../cockpit-state');
  const blockedPlan = {
    decision_register: [{ id: 'D-01', subject: 'URL policy', required: 'schemes, lengths' }],
    reqs: [{ id: 'REQ-001', status: 'open', readiness: { kit_ready: false, blockers: ['D-01', 'P-01'] } }, { id: 'REQ-002', status: 'open', dependsOn: ['REQ-001'] }],
  };
  const root = project({ 'docs/harper/IDEA.md': '#', 'docs/harper/SPEC.md': '#', 'runs/idea/a': 'x', 'runs/spec/a': 'x', 'docs/harper/plan.json': blockedPlan });
  const state = buildCockpitState(root);
  assert.equal(state.next.command, '/spec <your decisions>');
  assert.match(state.next.message, /REQ-001 is not ready for its KIT: the plan leaves 2 decision/);
  assert.deepEqual(state.next.blockers, [{ id: 'D-01', subject: 'URL policy', required: 'schemes, lengths' }, { id: 'P-01', subject: '', required: '' }]);
  assert.deepEqual(state.alternatives.map((a) => a.command), ['/kit REQ-001']);
  assert.equal(state.reqs[0].note, 'blocked: D-01 +1');
  assert.equal(state.reqs[1].note, 'waits REQ-001', 'its dependency first');
  // the KIT ran anyway and its eval failed: the sequence goes on (eval --fix), the decisions are a warning
  fs.mkdirSync(path.join(root, 'runs', 'kit', 'REQ-001', 'ci'), { recursive: true });
  fs.writeFileSync(path.join(root, 'runs', 'kit', 'REQ-001', 'ci', 'LTC.json'), '{}');
  fs.mkdirSync(path.join(root, 'runs', 'eval', 'REQ-001'), { recursive: true });
  fs.writeFileSync(path.join(root, 'runs', 'eval', 'REQ-001', 'report_REQ-001_100.json'), JSON.stringify({ status: 'FAIL', passed_count: 1, failed: 3 }));
  blockedPlan.reqs[0].status = 'in_progress';
  fs.writeFileSync(path.join(root, 'docs', 'harper', 'plan.json'), JSON.stringify(blockedPlan));
  const after = buildCockpitState(root, { methodology: 'bmad', fingerprint: () => 'x' });
  assert.equal(after.next.command, '/eval REQ-001 --fix');
  assert.match(after.next.message, /last eval of REQ-001 failed \(3 check/);
  assert.match(after.next.message, /still leaves D-01, P-01 open/);
  assert.deepEqual(after.alternatives.map((a) => a.command), ['/spec <your decisions>'], 'no SPEC/PLAN role once the KIT ran');
  assert.equal(after.reqs[0].note, 'next: /eval');
  assert.equal(kitBlockers({ readiness: { kit_ready: true } }), null);
  assert.equal(kitBlockers({}), null);
});
