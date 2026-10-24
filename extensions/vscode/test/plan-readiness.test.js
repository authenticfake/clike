'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');

const { reqBlockers, planReadiness, blockersOf, planReadinessMessage, notReadyReason } = require('../plan-readiness');

test('a REQ is KIT-ready unless the plan says it waits for the owner', () => {
  assert.deepEqual(reqBlockers({ id: 'REQ-001' }), []); // planned before kit_ready existed
  assert.deepEqual(reqBlockers({ id: 'REQ-001', kit_ready: true, blockers: ['ignored'] }), []);
  assert.deepEqual(reqBlockers({ id: 'REQ-001', kit_ready: false, blockers: ['OPEN-01 — which SSO tenant?'] }), ['OPEN-01 — which SSO tenant?']);
  assert.deepEqual(reqBlockers({ id: 'REQ-001', kit_ready: 'false', blockers: [{ id: 'OPEN-02', question: 'Retention period?' }] }), ['OPEN-02 — Retention period?']);
  assert.deepEqual(reqBlockers({ id: 'REQ-001', kit_ready: false }), ['the plan marks it not KIT-ready without saying why']);
});

test('the plan readiness lists only open REQs that wait, and says how to answer', () => {
  // ShortLink: a /plan that left the decisions of the SPEC open stopped the KIT (no src/, no test/)
  const plan = { reqs: [
    { id: 'REQ-001', status: 'open', kit_ready: false, blockers: ['D-01 URL policy', 'D-02 code policy'] },
    { id: 'REQ-002', status: 'open', kit_ready: true, blockers: [] },
    { id: 'REQ-003', status: 'done', kit_ready: false, blockers: ['old'] },
  ] };
  const readiness = planReadiness(plan);
  assert.deepEqual(readiness.notReady, [{ id: 'REQ-001', blockers: ['D-01 URL policy', 'D-02 code policy'] }]);
  const line = planReadinessMessage(readiness);
  assert.match(line, /1 REQ\(s\) wait for answers only you can give — REQ-001: D-01 URL policy; D-02 code policy/);
  assert.match(line, /Note from Harper Orchestrator/);
  assert.equal(planReadinessMessage(planReadiness({ reqs: [{ id: 'REQ-002', kit_ready: true }] })), '');
  assert.deepEqual(blockersOf(plan, 'req-001'), ['D-01 URL policy', 'D-02 code policy']);
  assert.deepEqual(blockersOf(plan, 'REQ-002'), []);
  assert.deepEqual(blockersOf(plan, 'REQ-404'), []);
  assert.match(notReadyReason(['D-01 URL policy']), /^not KIT-ready, the plan waits for your answers: D-01 URL policy/);
});
