const test = require('node:test');
const assert = require('node:assert/strict');

const { createRunTracker, stepOf, titleOf } = require('../run-tracker');

function clock(start = 1000) {
  let t = start;
  const now = () => t;
  now.add = (ms) => { t += ms; };
  return now;
}

test('the steps the card follows, and those it does not', () => {
  assert.deepEqual(stepOf({ type: 'harperRun', cmd: 'kit', targets: ['req-2'] }), { kind: 'kit', label: 'KIT', req: 'REQ-2' });
  assert.deepEqual(stepOf({ type: 'harperRun', cmd: 'kit', targetReqId: 'REQ-2', autoEvalRepair: { cycle: 2 } }),
    { kind: 'repair', label: 'REPAIR 2', req: 'REQ-2', cycle: 2 });
  assert.equal(stepOf({ type: 'harperEDD', cmd: 'eval', targetReqId: 'REQ-2', fix: { cycle: 1 } }).label, 'EVAL 2');
  assert.equal(stepOf({ type: 'harperEDD', cmd: 'eval', targetReqId: 'REQ-2', fix: { cycle: 1 }, regressionReqs: ['REQ-1'] }).label, 'EVAL 2 (targeted)');
  assert.equal(stepOf({ type: 'harperEDD', cmd: 'gate', targetReqId: 'REQ-2' }).label, 'GATE');
  assert.equal(stepOf({ type: 'harperRun', cmd: 'finalize', finalizeRepair: { cycle: 1 } }).label, 'REPAIR 1');
  assert.equal(stepOf({ type: 'harperRun', cmd: 'agent-model' }), null);
  assert.equal(stepOf({ type: 'uiChanged' }), null);
  assert.equal(stepOf({ type: 'autopilot', action: 'status' }), null);
  assert.equal(titleOf({ type: 'harperEDD', cmd: 'eval', targetReqId: 'REQ-2', fix: { hint: '' }, methodology: 'bmad' }), '/eval REQ-2 --fix --methodology bmad');
  assert.equal(titleOf({ type: 'harperRun', cmd: 'kit', rawCommand: '/kit REQ-2 --repair' }), '/kit REQ-2 --repair');
  assert.equal(titleOf({ type: 'autopilot', action: 'start', max: 3, executor: 'codex' }), '/autopilot 3 --executor codex');
});

test('/eval --fix: eval, repair, eval as nested steps, cycle and outcome', () => {
  const now = clock();
  const t = createRunTracker({ now, maxCycles: 2 });
  const top = { type: 'harperEDD', cmd: 'eval', targetReqId: 'REQ-2', fix: { hint: '' } };
  const tok = t.begin(top, { executor: 'Codex' });
  assert.equal(tok.started, true);
  now.add(60000);
  // the eval handler has its report, then runs the auto-eval loop from inside itself
  top.__report = { status: 'FAIL', counts: { passed: 10, failed: 2, warnings: 1 } };
  const repair = { type: 'harperRun', cmd: 'kit', targetReqId: 'REQ-2', autoEvalRepair: { cycle: 1 } };
  const rTok = t.begin(repair);
  let snap = t.snapshot();
  assert.deepEqual(snap.steps.map((s) => [s.label, s.state]), [['EVAL 1', 'failed'], ['REPAIR 1', 'running']]);
  assert.equal(snap.current.label, 'REPAIR 1');
  assert.deepEqual(snap.fix, { cycle: 1, maxCycles: 2, extraCycles: 3 });
  now.add(120000);
  repair.__result = 'ok';
  t.end(rTok, repair);
  const again = { type: 'harperEDD', cmd: 'eval', targetReqId: 'REQ-2', fix: { cycle: 1 } };
  const eTok = t.begin(again);
  now.add(30000);
  again.__report = { status: 'PASS', counts: { passed: 12, failed: 0, warnings: 1 } };
  assert.equal(t.end(eTok, again), false, 'the run goes on until the top-level handler returns');
  assert.equal(t.end(tok, top), true);
  snap = t.snapshot();
  assert.deepEqual(snap.steps.map((s) => [s.label, s.state]), [['EVAL 1', 'failed'], ['REPAIR 1', 'ok'], ['EVAL 2', 'ok']]);
  assert.deepEqual(snap.steps[2].counts, { passed: 12, failed: 0, warnings: 1 });
  assert.equal(snap.ended.outcome, 'ok', 'the outcome is the last step');
  assert.equal(snap.title, '/eval REQ-2 --fix');
  assert.equal(t.durations()['eval:REQ-2'], 30000, 'EVAL 1 is timed without the loop it started');
  // the next run of the same step knows how long it took
  const next = t.begin({ type: 'harperEDD', cmd: 'eval', targetReqId: 'REQ-2' });
  assert.equal(next.step.eta_ms, 30000);
  assert.equal(t.durations()['repair:REQ-2'], 120000);
});

test('Cancel, live text, eval progress, steps outside a run', () => {
  const now = clock();
  const t = createRunTracker({ now });
  assert.equal(t.begin({ type: 'uiChanged' }).step, null);
  t.end({ depth: 1, step: null }, {});
  assert.equal(t.snapshot(), null);
  const msg = { type: 'harperEDD', cmd: 'gate', targetReqId: 'REQ-3' };
  const tok = t.begin(msg);
  assert.equal(t.live('▶ GATE REQ-3 in the CLike eval sandbox…\nmore'), true);
  assert.equal(t.snapshot().live, '▶ GATE REQ-3 in the CLike eval sandbox…');
  assert.equal(t.evalProgress({ state: 'running', phase: 'checks', checks_done: 3, checks_total: 9 }), true);
  assert.equal(t.snapshot().evalProgress.checks_done, 3);
  t.evalProgress({ state: 'unknown' });
  assert.equal(t.snapshot().evalProgress, null);
  t.end(tok, msg, { cancelled: true });
  const snap = t.snapshot();
  assert.equal(snap.steps[0].state, 'cancelled');
  assert.equal(snap.ended.outcome, 'cancelled');
  assert.equal(t.durations()['gate:REQ-3'], undefined, 'a cancelled step is no estimate');
  assert.equal(t.live('late'), false);
});

test('autopilot: one run, the steps of every REQ', () => {
  const t = createRunTracker({ now: clock() });
  const ap = { type: 'autopilot', action: 'start' };
  const tok = t.begin(ap);
  for (const [msg, res] of [
    [{ type: 'harperRun', cmd: 'kit', targetReqId: 'REQ-1' }, { __result: 'ok' }],
    [{ type: 'harperEDD', cmd: 'eval', targetReqId: 'REQ-1', fix: { hint: '' } }, { __report: { status: 'PASS' } }],
    [{ type: 'harperEDD', cmd: 'gate', targetReqId: 'REQ-1' }, { __report: { status: 'PASS' } }],
  ]) {
    const s = t.begin(msg);
    Object.assign(msg, res);
    t.end(s, msg);
  }
  const snap = t.snapshot();
  assert.equal(snap.kind, 'autopilot');
  assert.deepEqual(snap.steps.map((s) => `${s.label} ${s.req} ${s.state}`), ['KIT REQ-1 ok', 'EVAL 1 REQ-1 ok', 'GATE REQ-1 ok']);
  assert.equal(snap.ended, null);
  t.end(tok, ap);
  assert.ok(t.snapshot().ended);
});

test('a step that ends with an error message and no outcome failed', () => {
  const t = createRunTracker({ now: clock() });
  const msg = { type: 'harperRun', cmd: 'kit', targetReqId: 'REQ-1' };
  const tok = t.begin(msg);
  t.error('[harperRun][agent] LOCAL_AGENT_REQUIRED_OUTPUTS_MISSING: phase=kit req_id=REQ-1');
  t.end(tok, msg);
  assert.equal(t.snapshot().steps[0].state, 'failed');
  assert.equal(t.snapshot().ended.outcome, 'failed');
});
