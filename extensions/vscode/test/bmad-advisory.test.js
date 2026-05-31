const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const { attachBmadQaAdvisory } = require('../bmad-advisory');

test('BMAD QA advisory does not change canonical eval verdict fields', () => {
  const canonicalReport = {
    req_id: 'REQ-001',
    status: 'FAIL',
    passed: false,
    promotable: false,
    failed: 1,
    passed_count: 0,
    blocked_count: 0,
    warning_count: 0,
    cases: [
      {
        name: 'unit',
        passed: false,
        blocking: true,
        cmd: 'npm test',
        stderr: 'runs/kit/REQ-001/test/example.test.js failed',
      },
    ],
  };

  const report = attachBmadQaAdvisory(canonicalReport, 'REQ-001', {
    methodology: 'bmad',
    agent: 'qa',
    phase: 'eval',
  });

  assert.equal(report.status, canonicalReport.status);
  assert.equal(report.passed, canonicalReport.passed);
  assert.equal(report.promotable, canonicalReport.promotable);
  assert.equal(report.failed, canonicalReport.failed);
  assert.equal(report.bmad_advisory.can_decide_pass_fail, false);
  assert.equal(report.bmad_advisory.can_change_promotable_status, false);
  assert.equal(report.bmad_advisory.can_affect_gate, false);
  assert.match(report.bmad_advisory.suggested_next_command, /\/kit REQ-001 --repair --methodology bmad --agent developer/);
  assert.ok(report.bmad_advisory.files_to_inspect.includes('runs/kit/REQ-001/ci/LTC.json'));
  assert.ok(report.bmad_advisory.files_to_inspect.includes('runs/kit/REQ-001/test/example.test.js'));
});

test('BMAD advisory is absent when methodology is omitted', () => {
  const canonicalReport = { req_id: 'REQ-001', status: 'PASS', passed: true };
  const report = attachBmadQaAdvisory(canonicalReport, 'REQ-001', null);

  assert.equal(report, canonicalReport);
  assert.equal(report.bmad_advisory, undefined);
});

test('extension eval path calls canonical handleEval before BMAD advisory attachment', () => {
  const source = fs.readFileSync(path.join(__dirname, '..', 'extension.js'), 'utf8');
  const handleEvalIndex = source.indexOf('report = await handleEval(path_ltc_json, ws_root, targets, mode, modeContent);');
  const advisoryIndex = source.indexOf('report = attachBmadQaAdvisory(report, targets, msg.methodology_context);');

  assert.notEqual(handleEvalIndex, -1);
  assert.notEqual(advisoryIndex, -1);
  assert.ok(handleEvalIndex < advisoryIndex);
});
