const test = require('node:test');
const assert = require('node:assert/strict');

const {
  nextAutopilotReq, resumeStep, isQuotaFailure, transientFailure, keptParked, stepOutcome, executorState, methodologyFields,
  autopilotReportMarkdown,
} = require('../autopilot');
const { parseSlash } = require('../slash-parser');

const plan = [
  { id: 'REQ-001', status: 'done' },
  { id: 'REQ-002', status: 'in_progress', dependsOn: ['REQ-001'] },
  { id: 'REQ-003', status: 'open', dependsOn: ['REQ-002'] },
  { id: 'REQ-004', status: 'open', dependsOn: ['REQ-001'] },
];

test('the in-progress REQ resumes where the repository says it is', () => {
  assert.deepEqual(nextAutopilotReq(plan, new Set(), () => 'gate'), { action: 'run', req_id: 'REQ-002', step: 'gate' });
  assert.deepEqual(nextAutopilotReq(plan, new Set()), { action: 'run', req_id: 'REQ-002', step: 'kit' });
  // an open REQ always starts from its KIT
  assert.deepEqual(nextAutopilotReq(plan, new Set(['REQ-002']), () => 'gate'), { action: 'run', req_id: 'REQ-004', step: 'kit' });

  assert.equal(resumeStep({ hasKit: false, lastEval: { status: 'PASS', inputs: 'a' }, fingerprint: 'a' }), 'kit');
  assert.equal(resumeStep({ hasKit: true, lastEval: null, fingerprint: 'a' }), 'eval');
  assert.equal(resumeStep({ hasKit: true, lastEval: { status: 'PASS_WITH_WARNINGS', inputs: 'a' }, fingerprint: 'a' }), 'gate');
  assert.equal(resumeStep({ hasKit: true, lastEval: { status: 'PASS', inputs: 'a' }, fingerprint: 'b' }), 'eval', 'files changed since the eval');
  assert.equal(resumeStep({ hasKit: true, lastEval: { status: 'FAIL', inputs: 'a' }, fingerprint: 'a' }), 'eval');
});

test('a REQ parked by an earlier run stays parked until its files change', () => {
  const previous = { 'REQ-002': { step: 'eval', fingerprint: 'f1' }, 'REQ-004': { step: 'gate', fingerprint: 'f2' }, 'REQ-005': { step: 'kit' } };
  const now = { 'REQ-002': 'f1', 'REQ-004': 'changed', 'REQ-005': 'x' };
  const { kept, released } = keptParked(previous, (id) => now[id]);
  assert.deepEqual(Object.keys(kept), ['REQ-002']);
  assert.deepEqual(released, ['REQ-004', 'REQ-005']);
  assert.deepEqual(keptParked(undefined, () => ''), { kept: {}, released: [] });
});

test('a parked REQ is retried when the environment changed (CLike version, sandbox tools)', () => {
  // B2B REQ-037: parked on `pwsh: not found`; PowerShell installed, its files unchanged
  const previous = { 'REQ-037': { step: 'eval', fingerprint: 'f1', env: '1.6.3|shellcheck' }, 'REQ-040': { step: 'eval', fingerprint: 'f2' } };
  const same = (id) => ({ 'REQ-037': 'f1', 'REQ-040': 'f2' }[id]);
  assert.deepEqual(keptParked(previous, same, '1.6.3|shellcheck').released, ['REQ-040']);  // parked before env was recorded
  assert.deepEqual(keptParked(previous, same, '1.6.3|powershell,shellcheck').released, ['REQ-037', 'REQ-040']);
  assert.deepEqual(Object.keys(keptParked(previous, same, '').kept), ['REQ-037', 'REQ-040']);  // tools unknown: inputs only
});

test('a parked REQ is skipped and its dependants wait; the independent ones go on', () => {
  assert.deepEqual(nextAutopilotReq(plan, new Set(['REQ-002'])), { action: 'run', req_id: 'REQ-004', step: 'kit' });
  const blocked = nextAutopilotReq(plan, new Set(['REQ-002', 'REQ-004']));
  assert.equal(blocked.action, 'blocked');
  assert.deepEqual(blocked.waiting.find((w) => w.req_id === 'REQ-003'), { req_id: 'REQ-003', parked: false, waiting_for: ['REQ-002'] });
  assert.deepEqual(nextAutopilotReq([{ id: 'REQ-001', status: 'done' }, { id: 'REQ-002', status: 'deferred' }]), { action: 'finalize_only' });
});

test('step outcomes follow the governed flow: kit result, auto-eval outcome, gate verdict and promotion', () => {
  assert.equal(stepOutcome('kit', { __result: 'ok' }).ok, true);
  assert.equal(stepOutcome('kit', { __result: 'failed' }).ok, false);
  assert.deepEqual(stepOutcome('eval', { __report: { auto_eval: { outcome: 'pass', cycles: 2 } } }), { ok: true, cycles: 2 });
  const stopped = stepOutcome('eval', { __report: { status: 'FAIL', auto_eval: { outcome: 'stopped', cycles: 2, reason: '2 failing check(s)' } } });
  assert.equal(stopped.ok, false);
  assert.match(stopped.reason, /stopped: 2 failing/);
  assert.equal(stepOutcome('eval', {}).ok, false);
  assert.deepEqual(stepOutcome('gate', { __report: { gate: 'pass', status: 'PASS_WITH_WARNINGS', review_required: true } }), { ok: true, review_required: true });
  assert.equal(stepOutcome('gate', { __report: { gate: 'pass', status: 'FAIL' } }).ok, false);
  assert.equal(stepOutcome('gate', { __report: { gate: 'fail', status: 'FAIL' } }).ok, false);
  assert.match(stepOutcome('gate', { __report: { gate: 'pass', status: 'PASS', promotion: { promoted: false, summary: 'conflicts' } } }).reason, /promotion not done: conflicts/);
});

test('provider quota and rate limits are recognised, other failures are not', () => {
  for (const text of ['HTTP 429 Too Many Requests', 'rate_limit_exceeded', 'You have reached your usage limit', 'insufficient_quota']) {
    assert.equal(isQuotaFailure(text), true, text);
  }
  for (const text of ['✖ AUTO-EVAL REQ-024 stopped: 2 failing check(s)', 'typecheck failed']) {
    assert.equal(isQuotaFailure(text), false, text);
    assert.equal(transientFailure(text), null, text);
  }
  assert.equal(transientFailure('HTTP 429'), 'quota');
  for (const text of ['fetch failed', 'connect ECONNREFUSED 127.0.0.1:8080', 'HTTP 503 Service Unavailable', 'EVAL_SANDBOX_EXHAUSTED']) {
    assert.equal(transientFailure(text), 'service', text);
  }
});

test('the report lists promoted and parked REQs with the reason and what to review', () => {
  const md = autopilotReportMarkdown({
    startedAt: 0, endedAt: 3_900_000, outcome: 'no REQ can go on', next: 'REQ-003 needs you',
    reqs: [
      { req_id: 'REQ-002', result: 'promoted', cycles: 1, ms: 1_800_000, review_required: true },
      { req_id: 'REQ-004', result: 'parked', step: 'eval', reason: 'eval --fix stopped: x | y', messages: ['✖ stopped'] },
    ],
    waits: [{ req_id: 'REQ-002', step: 'kit', minutes: 30, reason: '429' }],
  });
  assert.match(md, /1 h 5 min/);
  assert.match(md, /\| REQ-002 \| 1 \| 30 min \| review the test fixes/);
  assert.match(md, /\| REQ-004 \| eval \| eval --fix stopped: x \\\| y \|/);
  assert.match(md, /REQ-002 kit: waited 30 min/);
});

test('executor and methodology of a run map to the chat state and to the step messages', () => {
  assert.equal(executorState(''), null);
  assert.deepEqual(executorState('cloud'), { executionPreference: 'cloud_only' });
  assert.deepEqual(executorState('Codex'), { executionPreference: 'local_agent_only', localAgentExecutor: 'gpt_codex' });
  assert.deepEqual(executorState('claude'), { executionPreference: 'local_agent_only', localAgentExecutor: 'claude_code' });
  assert.throws(() => executorState('gemini'), /cloud, codex or claude/);
  assert.deepEqual(methodologyFields('bmad', 'kit'), { methodology: 'bmad', agent: 'developer' });
  assert.deepEqual(methodologyFields('bmad', 'eval'), { methodology: 'bmad', agent: 'qa' });
  assert.deepEqual(methodologyFields('bmad', 'gate'), {});
  assert.deepEqual(methodologyFields('', 'kit'), {});
  assert.throws(() => methodologyFields('scrum', 'kit'), /bmad/);
});

test('/autopilot parses N, executor, methodology, stop and status', () => {
  assert.deepEqual(parseSlash('/autopilot').args, { action: 'start', max: 0, executor: '', methodology: '' });
  assert.deepEqual(parseSlash('/autopilot 3').args, { action: 'start', max: 3, executor: '', methodology: '' });
  const bmad = parseSlash('/autopilot 2 --executor claude --methodology bmad').args;
  assert.deepEqual([bmad.action, bmad.max, bmad.executor, bmad.methodology], ['start', 2, 'claude', 'bmad']);
  assert.deepEqual(parseSlash('/autopilot --executor=codex').args, { action: 'start', max: 0, executor: 'codex', methodology: '' });
  assert.deepEqual(parseSlash('/autopilot stop').args, { action: 'stop' });
  assert.deepEqual(parseSlash('/autopilot status').args, { action: 'status' });
});
