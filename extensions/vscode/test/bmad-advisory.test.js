const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const {
  attachBmadQaAdvisory,
  buildEffectiveEvalMethodologyContext,
} = require('../bmad-advisory');
const { parseSlash } = require('../slash-parser');

function canonicalFailingReport() {
  return {
    req_id: 'REQ-001',
    status: 'FAIL',
    passed: false,
    promotable: false,
    failed: 1,
    blocking_failures: 1,
    gate: 'block',
    gate_status: 'blocked',
    blocked_count: 0,
    warning_count: 1,
    summary: 'Typecheck failed for candidate implementation.',
    errors: ['TypeScript type error in candidate code'],
    warnings: ['Missing edge-case coverage'],
    cases: [
      {
        name: 'typecheck',
        passed: false,
        blocking: true,
        cmd: 'npm run typecheck',
        stderr: 'runs/kit/REQ-001/src/example.ts:4:1 type error',
      },
      {
        name: 'unit',
        status: 'failed',
        cmd: 'npm test',
        stdout: 'Expected candidate behavior was not observed',
        stderr: 'runs/kit/REQ-001/test/example.test.js failed',
      },
    ],
  };
}

test('/eval REQ-001 --methodology bmad --agent qa attaches advisory after canonical eval data exists', () => {
  const canonicalReport = canonicalFailingReport();
  const parsed = parseSlash('/eval REQ-001 --methodology bmad --agent qa');
  const context = buildEffectiveEvalMethodologyContext(parsed.args.methodology_context);

  const report = attachBmadQaAdvisory(canonicalReport, 'REQ-001', {
    ...context,
  });

  assert.equal(report.status, canonicalReport.status);
  assert.equal(report.passed, canonicalReport.passed);
  assert.equal(report.promotable, canonicalReport.promotable);
  assert.equal(report.failed, canonicalReport.failed);
  assert.equal(report.blocking_failures, canonicalReport.blocking_failures);
  assert.equal(report.gate, canonicalReport.gate);
  assert.equal(report.gate_status, canonicalReport.gate_status);
  assert.equal(report.bmad_advisory.agent, 'qa');
  assert.equal(report.bmad_advisory.can_decide_pass_fail, false);
  assert.equal(report.bmad_advisory.can_change_promotable_status, false);
  assert.equal(report.bmad_advisory.can_affect_gate, false);
  assert.equal(report.bmad_advisory.suggested_next_command, '/kit REQ-001 --repair --methodology bmad --agent developer');
  assert.match(report.bmad_advisory.root_cause_hypothesis, /Canonical CLike eval reported/);
  assert.ok(report.bmad_advisory.failed_checks.length >= 2);
  assert.ok(report.bmad_advisory.files_to_inspect.includes('runs/kit/REQ-001/ci/LTC.json'));
  assert.ok(report.bmad_advisory.files_to_inspect.includes('runs/kit/REQ-001/test/example.test.js'));
  assert.ok(report.bmad_advisory.files_to_inspect.includes('runs/kit/REQ-001/src/example.ts'));
  assert.ok(report.bmad_advisory.recommended_repair_strategy.length > 0);
  assert.ok(report.bmad_advisory.checks_to_rerun.includes('npm run typecheck'));
  assert.ok(report.bmad_advisory.checks_to_rerun.includes('npm test'));
  assert.ok(report.bmad_advisory.diagnostic_classifications.includes('typecheck_failure'));
});

test('/eval REQ-001 --methodology bmad defaults to QA advisory', () => {
  const parsed = parseSlash('/eval REQ-001 --methodology bmad');
  const context = buildEffectiveEvalMethodologyContext(parsed.args.methodology_context);
  const report = attachBmadQaAdvisory(canonicalFailingReport(), 'REQ-001', context);

  assert.equal(context.phase, 'eval');
  assert.equal(context.agent, 'qa');
  assert.equal(context.advisory_only, true);
  assert.equal(report.bmad_advisory.agent, 'qa');
  assert.equal(report.bmad_advisory.advisory_type, 'qa_advisory');
});

test('/eval REQ-001 --methodology bmad --agent developer attaches developer repair advisory', () => {
  const parsed = parseSlash('/eval REQ-001 --methodology bmad --agent developer');
  const context = buildEffectiveEvalMethodologyContext(parsed.args.methodology_context);
  const report = attachBmadQaAdvisory(canonicalFailingReport(), 'REQ-001', context);

  assert.equal(context.phase, 'eval');
  assert.equal(context.agent, 'developer');
  assert.equal(context.advisory_only, true);
  assert.equal(report.bmad_advisory.agent, 'developer');
  assert.equal(report.bmad_advisory.advisory_type, 'developer_repair_advisory');
  assert.equal(report.status, 'FAIL');
  assert.equal(report.promotable, false);
  assert.match(report.bmad_advisory.recommended_repair_strategy.join('\n'), /candidate repair advisory/);
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
  const contextIndex = source.indexOf('const evalMethodologyContext = buildEffectiveEvalMethodologyContext(');
  const advisoryIndex = source.indexOf('report = attachBmadQaAdvisory(report, targets, evalMethodologyContext);');

  assert.notEqual(handleEvalIndex, -1);
  assert.notEqual(contextIndex, -1);
  assert.notEqual(advisoryIndex, -1);
  assert.ok(handleEvalIndex < advisoryIndex);
  assert.ok(contextIndex < advisoryIndex);
});

test('advisory classifies malformed LTC, missing files, environment blockers, contract gaps, missing tests, security, and typecheck signals', () => {
  const report = attachBmadQaAdvisory(
    {
      req_id: 'REQ-001',
      status: 'FAIL',
      passed: false,
      failed: 1,
      blocked_count: 1,
      warning_count: 1,
      summary: 'Malformed LTC.json contract and missing tests',
      errors: [
        'No such file runs/kit/REQ-001/src/missing.ts',
        'security vulnerability found',
        'command not found',
      ],
      cases: [
        {
          name: 'schema',
          status: 'failed',
          run: 'node validate-ltc.js',
          stderr: 'Invalid JSON schema in LTC.json contract',
        },
      ],
    },
    'REQ-001',
    { methodology: 'bmad', phase: 'eval', agent: 'qa' }
  );

  const classes = report.bmad_advisory.diagnostic_classifications;
  assert.ok(classes.includes('missing_candidate_files'));
  assert.ok(classes.includes('malformed_ltc_or_contract_gap'));
  assert.ok(classes.includes('environment_blocker'));
  assert.ok(classes.includes('missing_tests'));
  assert.ok(classes.includes('security_failure'));
});
