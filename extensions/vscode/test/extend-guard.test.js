'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');

const { validateExtendPlan } = require('../extend-guard');

const req = (id, extra = {}) => ({ id, title: `t ${id}`, status: 'done', dependsOn: [], acceptance: ['a'], ...extra });
const plan = (...reqs) => JSON.stringify({ snapshot: { total: reqs.length }, reqs });
const BEFORE = plan(req('REQ-001'), req('REQ-002', { dependsOn: ['REQ-001'], status: 'in_progress' }));

test('extend guard: appended REQs that continue the sequence pass untouched', () => {
  const after = plan(req('REQ-001'), req('REQ-002', { dependsOn: ['REQ-001'], status: 'in_progress' }), req('REQ-003', { status: 'open', dependsOn: ['REQ-002'] }));
  const v = validateExtendPlan({ beforeText: BEFORE, afterText: after, anchorReq: 'REQ-002', explicitReq: 'REQ-003' });
  assert.deepEqual([v.ok, v.errors, v.warnings, v.added, v.restored], [true, [], [], ['REQ-003'], []]);
  assert.equal(v.planText, after);
});

test('extend guard: existing REQs changed or removed by the agent are restored, derived fields kept', () => {
  const after = plan(
    req('REQ-002', { dependsOn: ['REQ-001'], status: 'done', acceptance: ['rewritten'], capabilities: { skills: [{ id: 's' }] } }),
    req('REQ-003', { status: 'open' }),
  );
  const v = validateExtendPlan({ beforeText: BEFORE, afterText: after });
  assert.equal(v.ok, true, v.errors.join('; '));
  assert.deepEqual(v.restored, ['REQ-002 (acceptance, status)', 'REQ-001 (removed)']);
  assert.match(v.warnings[0], /existing REQs are read-only in \/extend: restored REQ-002 \(acceptance, status\); REQ-001 \(removed\)/);
  const reqs = JSON.parse(v.planText).reqs;
  assert.deepEqual(reqs.map((r) => r.id), ['REQ-001', 'REQ-002', 'REQ-003']);
  assert.deepEqual(reqs[1], { ...JSON.parse(BEFORE).reqs[1], capabilities: { skills: [{ id: 's' }] } });
  assert.match(v.warnings[1], /snapshot\.total is 2, the plan has 3 REQs/);
});

test('extend guard: what cannot be repaired is an error', () => {
  const v = (afterReqs, opts = {}) => validateExtendPlan({ beforeText: BEFORE, afterText: plan(...afterReqs), ...opts });
  assert.deepEqual(v([req('REQ-001'), req('REQ-002', { dependsOn: ['REQ-001'], status: 'in_progress' })]).errors, ['no new REQ was added']);
  assert.match(v([req('REQ-001'), req('REQ-002', { dependsOn: ['REQ-001'], status: 'in_progress' }), req('REQ-003'), req('REQ-003')]).errors[0], /duplicate REQ id REQ-003/);
  assert.match(v([req('REQ-001'), req('REQ-002', { dependsOn: ['REQ-001'], status: 'in_progress' }), req('REQ-3a')]).errors.join(), /REQ-3a is not REQ-<number>/);
  assert.match(v([req('REQ-001'), req('REQ-002', { dependsOn: ['REQ-001'], status: 'in_progress' }), req('REQ-003', { dependsOn: ['REQ-099'] })]).errors.join(), /REQ-003 depends on REQ-099/);
  assert.match(v([req('REQ-001'), req('REQ-002', { dependsOn: ['REQ-001'], status: 'in_progress' }), req('REQ-003')], { anchorReq: 'REQ-009' }).errors.join(), /anchor REQ-009 is not in the plan/);
  assert.match(v([req('REQ-001'), req('REQ-002', { dependsOn: ['REQ-001'], status: 'in_progress' }), req('REQ-003')], { explicitReq: 'REQ-004' }).errors.join(), /requested REQ-004 is not among the new REQs \(REQ-003\)/);
  const gap = v([req('REQ-001'), req('REQ-002', { dependsOn: ['REQ-001'], status: 'in_progress' }), req('REQ-005')]);
  assert.equal(gap.ok, true);
  assert.match(gap.warnings.join(), /REQ-005 leaves a gap in the sequence \(expected REQ-003\)/);
  assert.match(validateExtendPlan({ beforeText: BEFORE, afterText: '{' }).errors[0], /not valid JSON/);
});

test('extend guard: a new id below the last existing one does not continue the sequence', () => {
  const before = plan(req('REQ-001'), req('REQ-005'));
  const v = validateExtendPlan({ beforeText: before, afterText: plan(req('REQ-001'), req('REQ-005'), req('REQ-003')) });
  assert.match(v.errors.join(), /new REQ-003 does not continue the sequence \(last existing is REQ-005\)/);
});
