'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');

const { specUseCases, useCaseCoverage, useCaseCoverageMessage } = require('../use-case-coverage');

const SPEC = `# SPEC — Demo

## Key Workflows
- not a use case UC-99.1

## Use Cases

### UC-01 — Sign in and see my clients
- UC-01.1 The user opens the console → the system redirects to the identity provider.
- UC-01.2 The user signs in → the system creates a session and shows the clients list.
- UC-01.3 The session expires → the system asks to sign in again.

### UC-02 — Export the reviewed leads
- UC-02.1 The user requests an export → the system queues it.
- UC-02.2 The export completes → the system offers an authorized download.

### UC-03 — Audit trail
Prerequisites: in scope.

## Security & Compliance
- UC-77.1 outside the section
`;

test('the SPEC use cases and their steps, only from the Use Cases section', () => {
  assert.deepEqual(specUseCases(SPEC), {
    'UC-01': ['UC-01.1', 'UC-01.2', 'UC-01.3'],
    'UC-02': ['UC-02.1', 'UC-02.2'],
    'UC-03': [],
  });
  assert.equal(specUseCases('# SPEC\n\n## Goals\n- x\n'), null);
});

test('a step no REQ covers is listed (B2B lesson: an authenticated API with no sign-in REQ)', () => {
  const plan = { reqs: [
    { id: 'REQ-001', covers: ['UC-01.1', 'UC-01.2'] },
    { id: 'REQ-002', covers: ['UC-02'] },
    { id: 'REQ-003', covers: ['uc-05.1'] },
    { id: 'REQ-004' },
  ] };
  const coverage = useCaseCoverage(SPEC, plan);
  assert.deepEqual(coverage.uncovered, ['UC-01.3', 'UC-03']);
  assert.deepEqual(coverage.unknown, ['UC-05.1']);
  assert.deepEqual(coverage.reqsWithoutCovers, ['REQ-004']);
  assert.equal(coverage.useCases, 3);
  assert.equal(coverage.steps, 5);
  const message = useCaseCoverageMessage(coverage);
  assert.match(message, /^⚠ USE CASES: 2 step\(s\)/);
  assert.match(message, /UC-01\.3, UC-03/);
  const full = useCaseCoverage(SPEC, { reqs: [{ id: 'REQ-001', covers: ['UC-01', 'UC-02', 'UC-03'] }] });
  assert.deepEqual(full.uncovered, []);
  assert.match(useCaseCoverageMessage(full), /^✔ USE CASES: every step is covered/);
  // a SPEC planned before the section: nothing to check
  assert.equal(useCaseCoverage('# SPEC\n## Goals\n', plan), null);
});

// Journey scenarios: the SPEC includes or excludes each scenario, every included one has a REQ.
const { specScenarios, scenarioCoverage, scenarioCoverageMessage } = require('../use-case-coverage');

const SPEC_SCENARIOS = `# SPEC

## Scenarios
- IAM-02 — included — sign-in to the console
- IAM-03 — included — one generic message on wrong credentials
- IAM-05 — excluded — delegated to the identity provider (link on the login page)
- **IAM-01**: excluded (registration is by invitation only)
- UI-03 — included — every data page shows an actionable error
- IAM-09 — excluded

## Assumptions
- IAM-99 not a scenario line of the section
`;

test('the SPEC scenarios section is read with included and excluded ids and reasons', () => {
  const s = specScenarios(SPEC_SCENARIOS);
  assert.deepEqual(s.included, ['IAM-02', 'IAM-03', 'UI-03']);
  assert.deepEqual(s.excluded.map((e) => e.id), ['IAM-05', 'IAM-01', 'IAM-09']);
  assert.match(s.excluded[0].reason, /identity provider/);
  assert.match(s.excluded[1].reason, /invitation only/);
  assert.equal(s.excluded[2].reason, '');
  assert.equal(specScenarios('# SPEC\n## Use Cases\n'), null);
});

test('every included scenario must be owned by a REQ', () => {
  const plan = { reqs: [
    { id: 'REQ-001', scenarios: ['IAM-02', { id: 'UI-03' }] },
    { id: 'REQ-002', scenarios: ['UI-03', 'API-01'] },
  ] };
  const c = scenarioCoverage(SPEC_SCENARIOS, plan);
  assert.deepEqual(c.unassigned, ['IAM-03']);
  assert.deepEqual(c.unexpected, ['API-01']);
  assert.deepEqual(c.noReason, ['IAM-09']);
  assert.deepEqual(c.shared, ['UI-03']);
  const message = scenarioCoverageMessage(c);
  assert.match(message, /^⚠ SCENARIOS: 1 included scenario\(s\) no REQ owns/);
  assert.match(message, /excluded without a reason: IAM-09/);
  const full = scenarioCoverage(SPEC_SCENARIOS, { reqs: [{ id: 'REQ-001', scenarios: ['IAM-02', 'IAM-03', 'UI-03'] }] });
  assert.match(scenarioCoverageMessage(full), /^✔ SCENARIOS/);
  assert.equal(scenarioCoverage('# SPEC', { reqs: [] }), null);
});
