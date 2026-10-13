'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('fs');
const os = require('os');
const path = require('path');

const { annotateIntermittentFailures, collectRepairFailures, collectRepairFiles, nextAutoEvalStep, nextAutoGateStep, readEarlierReports, repairNotesMarkdown, writeRepairNotes } = require('../auto-eval');
const { parseSlash } = require('../slash-parser');

const failing = (names) => ({
  status: 'FAIL',
  passed: false,
  cases: [
    { name: 'lint', passed: true },
    ...names.map((name) => ({ name, passed: false, code: 1, cmd: `run ${name}`, stderr: `${name} broke`, blocking: true })),
  ],
});

test('/eval and /gate --fix carry the hint', () => {
  const withHint = parseSlash('/eval REQ-001 --fix "use the repository layer"').args;
  assert.deepEqual([withHint.targets, withHint.fix, withHint.hint], [['REQ-001'], true, 'use the repository layer']);
  const bare = parseSlash('/eval REQ-001 --fix').args;
  assert.deepEqual([bare.targets, bare.fix, bare.hint], [['REQ-001'], true, '']);
  assert.equal(parseSlash('/eval REQ-001').args.fix, undefined);
  assert.equal(parseSlash('/eval REQ-001 manual pass').args.testMode, 'manual');
  const gate = parseSlash('/gate REQ-001 --no-promote --fix "keep the worker order"').args;
  assert.deepEqual([gate.targets, gate.fix, gate.hint, gate.promote], [['REQ-001'], true, 'keep the worker order', 'off']);
  assert.equal(parseSlash('/gate REQ-001').args.fix, undefined);
});

test('failures carry name, command, exit code and output for the repair prompt', () => {
  assert.deepEqual(collectRepairFailures(failing(['unit'])), [
    { name: 'unit', code: 1, command: 'run unit', blocking: true, fingerprint: '', output: 'unit broke\n' },
  ]);
});

test('failures: runner excerpt, same errors not repeated, regression warnings of other REQs left out', () => {
  const report = { status: 'FAIL', cases: [
    { name: 'test:unit', passed: false, code: 1, cmd: 'u', stdout: 'tail only', excerpt: 'FAIL a.test.ts\nAssertionError', fingerprint: 'f1' },
    { name: 'test:coverage', passed: false, code: 1, cmd: 'c', stdout: 'x', excerpt: 'FAIL a.test.ts\nAssertionError', fingerprint: 'f1' },
    { name: 'regression::REQ-001::test:integration', passed: false, blocking: false, code: 1, excerpt: 'coverage 54 < 80', fingerprint: 'f2' },
    { name: 'regression::REQ-002::test:unit', passed: false, blocking: true, code: 1, excerpt: 'broken by this REQ', fingerprint: 'f3' },
  ] };
  const failures = collectRepairFailures(report);
  assert.deepEqual(failures.map((f) => f.name), ['test:unit', 'test:coverage', 'regression::REQ-002::test:unit']);
  assert.equal(failures[0].output, 'FAIL a.test.ts\nAssertionError');
  assert.match(failures[1].output, /Same errors as the check test:unit/);
});

test('loop: the same check failing with different errors is progress', () => {
  const base = { cycle: 0, maxCycles: 3, hint: '' };
  const report = (fp) => ({ status: 'FAIL', cases: [{ name: 'test:unit', passed: false, code: 1, excerpt: fp, fingerprint: fp }] });
  const first = nextAutoEvalStep(base, report('a'));
  assert.equal(nextAutoEvalStep({ ...base, cycle: 1, lastSignature: first.signature }, report('b')).action, 'repair');
  assert.match(nextAutoEvalStep({ ...base, cycle: 1, lastSignature: first.signature }, report('a')).reason, /no progress/);
});

test('loop: repair, then stop on pass, no progress, exhausted cycles or a failed KIT', () => {
  const base = { cycle: 0, maxCycles: 2, hint: '' };
  const first = nextAutoEvalStep(base, failing(['unit']));
  assert.equal(first.action, 'repair');

  assert.equal(nextAutoEvalStep({ ...base, cycle: 1 }, { status: 'PASS', passed: true, cases: [] }).action, 'pass');
  assert.match(nextAutoEvalStep({ ...base, cycle: 1, lastSignature: first.signature }, failing(['unit'])).reason, /no progress/);
  assert.equal(nextAutoEvalStep({ ...base, cycle: 1, lastSignature: first.signature }, failing(['lint-2'])).action, 'repair');
  assert.match(nextAutoEvalStep({ ...base, cycle: 2 }, failing(['unit'])).reason, /after 2 repair cycle/);
  assert.match(nextAutoEvalStep({ ...base, cycle: 1, lastKitOk: false }, failing(['x'])).reason, /KIT repair request failed/);
  assert.match(nextAutoEvalStep(base, { status: 'FAIL', integrity: { ok: false }, cases: [] }).reason, /acceptance surface/);
});

test('repair files: text files of runs/kit/<REQ>, workspace-relative, caches skipped', () => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'clike-autoeval-'));
  const kit = path.join(root, 'runs', 'kit', 'REQ-001');
  fs.mkdirSync(path.join(kit, 'src', '__pycache__'), { recursive: true });
  fs.writeFileSync(path.join(kit, 'src', 'app.py'), 'print(1)\n');
  fs.writeFileSync(path.join(kit, 'src', '__pycache__', 'app.pyc'), 'x');
  fs.writeFileSync(path.join(kit, 'src', 'logo.bin'), Buffer.from([0, 1, 2]));
  assert.deepEqual(collectRepairFiles(root, 'REQ-001'), [{ path: 'runs/kit/REQ-001/src/app.py', content: 'print(1)\n' }]);
  fs.rmSync(root, { recursive: true, force: true });
});

test('acceptance surface: snapshot, changes and restore of a repair', () => {
  const { acceptanceChanges, restoreAcceptanceFiles, snapshotAcceptanceSurface } = require('../auto-eval');
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'clike-acceptance-'));
  const kit = path.join(root, 'runs', 'kit', 'REQ-001');
  for (const dir of ['src', 'test', 'ci']) fs.mkdirSync(path.join(kit, dir), { recursive: true });
  fs.writeFileSync(path.join(kit, 'src', 'app.py'), 'x = 1\n');
  fs.writeFileSync(path.join(kit, 'test', 'test_app.py'), 'assert True\n');
  fs.writeFileSync(path.join(kit, 'test', 'test_other.py'), 'assert 1\n');
  fs.writeFileSync(path.join(kit, 'ci', 'LTC.json'), '{}');
  const before = snapshotAcceptanceSurface(root, 'REQ-001');
  assert.deepEqual(Object.keys(before).sort(), ['ci/LTC.json', 'test/test_app.py', 'test/test_other.py']);

  // The agent edits a test, deletes another, adds a new one and changes the source.
  fs.writeFileSync(path.join(kit, 'test', 'test_app.py'), 'pass\n');
  fs.rmSync(path.join(kit, 'test', 'test_other.py'));
  fs.writeFileSync(path.join(kit, 'test', 'test_new.py'), 'assert 2\n');
  fs.writeFileSync(path.join(kit, 'src', 'app.py'), 'x = 2\n');
  const changes = acceptanceChanges(before, snapshotAcceptanceSurface(root, 'REQ-001'));
  assert.deepEqual(changes, { modified: { 'test/test_app.py': 'pass\n' }, deleted: ['test/test_other.py'] });

  restoreAcceptanceFiles(root, 'REQ-001', before, ['test/test_app.py', 'test/test_other.py']);
  assert.equal(fs.readFileSync(path.join(kit, 'test', 'test_app.py'), 'utf8'), 'assert True\n');
  assert.equal(fs.readFileSync(path.join(kit, 'test', 'test_other.py'), 'utf8'), 'assert 1\n');
  assert.equal(fs.readFileSync(path.join(kit, 'src', 'app.py'), 'utf8'), 'x = 2\n');
  fs.rmSync(root, { recursive: true, force: true });
});

test('/agent-model shows or sets the local agent model', () => {
  assert.deepEqual(parseSlash('/agent-model claude sonnet').args, { agent: 'claude', model: 'sonnet' });
  assert.deepEqual(parseSlash('/agent-model codex gpt-5.5-codex').args, { agent: 'codex', model: 'gpt-5.5-codex' });
  assert.deepEqual(parseSlash('/agent-model').args, { agent: '', model: '' });
});

test('loop: a missing eval environment stops at once, without a repair', () => {
  const report = {
    status: 'BLOCKED',
    reason_code: 'EVAL_ENVIRONMENT_MISSING',
    passed: false,
    cases: [{ name: 'env::required-variables', passed: false, blocked: true, blocking: true, stderr: '  - APP_TEST_DATABASE_URL: real PostgreSQL' }],
  };
  const step = nextAutoEvalStep({ cycle: 0, maxCycles: 2, hint: '' }, report);
  assert.equal(step.action, 'stop');
  assert.match(step.reason, /nothing to repair/);
  assert.match(step.reason, /APP_TEST_DATABASE_URL/);
});

test('acceptance snapshot leaves out ci/HOWTO.md (documentation, editable by hand)', () => {
  const { snapshotAcceptanceSurface } = require('../auto-eval');
  const ws = fs.mkdtempSync(path.join(os.tmpdir(), 'clike-howto-'));
  const kit = path.join(ws, 'runs', 'kit', 'REQ-001');
  fs.mkdirSync(path.join(kit, 'ci'), { recursive: true });
  fs.writeFileSync(path.join(kit, 'ci', 'LTC.json'), '{}');
  fs.writeFileSync(path.join(kit, 'ci', 'HOWTO.md'), '# how');
  const snap = snapshotAcceptanceSurface(ws, 'REQ-001');
  assert.ok('ci/LTC.json' in snap);
  assert.ok(!('ci/HOWTO.md' in snap));
});

test('loop: a missing environment a repair can declare is repaired, not stopped', () => {
  const report = {
    status: 'BLOCKED',
    reason_code: 'EVAL_ENVIRONMENT_MISSING',
    environment_repairable: true,
    passed: false,
    cases: [{ name: 'env::required-variables', passed: false, blocked: true, blocking: true, code: 78, stderr: '  - APP_TEST_API_URL' }],
  };
  const step = nextAutoEvalStep({ cycle: 0, maxCycles: 2, hint: '' }, report);
  assert.equal(step.action, 'repair');
  assert.equal(step.failures[0].name, 'env::required-variables');
});

test('loop: extra cycles while the failures decrease, bounded', () => {
  const base = { cycle: 2, maxCycles: 2, hint: '', extraCycles: 2, lastKitOk: true };
  assert.equal(nextAutoEvalStep({ ...base, lastFailureCount: 3 }, failing(['integration'])).action, 'repair');
  assert.equal(nextAutoEvalStep({ ...base, lastFailureCount: 1 }, failing(['integration'])).action, 'stop');
  assert.equal(nextAutoEvalStep({ ...base, cycle: 4, lastFailureCount: 3 }, failing(['integration'])).action, 'stop');
  assert.equal(nextAutoEvalStep({ ...base, extraCycles: 0, lastFailureCount: 3 }, failing(['integration'])).action, 'stop');
});

test('/gate promotion flags', () => {
  assert.equal(parseSlash('/gate REQ-003 --ask').args.promote, 'ask');
  assert.equal(parseSlash('/gate REQ-003 --no-promote').args.promote, 'off');
  assert.equal(parseSlash('/gate REQ-003').args.promote, undefined);
  assert.deepEqual(parseSlash('/gate REQ-003 --ask').args.targets, ['REQ-003']);
});

test('/gate --auto-merge forces the auto-merge promotion', () => {
  assert.equal(parseSlash('/gate REQ-003 --auto-merge').args.promote, 'merge');
});

test('auto-gate: same loop as auto-eval, driven by the gate verdict', () => {
  const base = { cycle: 0, maxCycles: 2, hint: '' };
  const gateFail = (names) => ({ ...failing(names), gate: 'FAIL', reason_code: 'GATE_BLOCKED_FAILED_CHECKS' });
  const first = nextAutoGateStep(base, gateFail(['test:integration']));
  assert.equal(first.action, 'repair');
  assert.deepEqual(first.failures.map((f) => f.name), ['test:integration']);
  // PASS_WITH_WARNINGS accepted by the gate ends the loop; promotion conflicts are not repaired.
  assert.equal(nextAutoGateStep({ ...base, cycle: 1 }, { gate: 'PASS', status: 'PASS_WITH_WARNINGS', passed: true, cases: [] }).action, 'pass');
  assert.match(nextAutoGateStep({ ...base, cycle: 1, lastSignature: first.signature }, gateFail(['test:integration'])).reason, /no progress/);
  assert.match(nextAutoGateStep({ ...base, cycle: 2 }, gateFail(['unit'])).reason, /after 2 repair cycle/);
  const tampered = { gate: 'FAIL', reason_code: 'GATE_BLOCKED_ACCEPTANCE_TAMPERED', integrity: { ok: false }, cases: [] };
  assert.equal(nextAutoGateStep(base, tampered).action, 'stop');
  assert.equal(nextAutoGateStep(base, { gate: 'OVERRIDE', reason_code: 'GATE_MANUAL_OVERRIDE', cases: [] }).action, 'stop');
  const missing = nextAutoGateStep(base, {
    gate: 'FAIL', status: 'FAIL', reason_code: 'GATE_BLOCKED_REQUIRED_OUTPUTS_MISSING', cases: [{ name: 'lint', passed: true }],
    structural_blockers: [{ role: 'module_launcher', reason: 'no composition root' }],
  });
  assert.equal(missing.action, 'repair');
  assert.deepEqual(missing.failures.map((f) => [f.name, f.output]), [['required-output::module_launcher', 'no composition root']]);
  assert.match(nextAutoGateStep(base, { gate: 'FAIL', status: 'FAIL', cases: [] }).reason, /gate failed without failing checks/);
});

test('intermittent failures: a check that passed in earlier runs is flagged for the repair', () => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'clike-flaky-'));
  const write = (phase, ts, cases) => {
    const dir = path.join(root, 'runs', phase, 'REQ-006');
    fs.mkdirSync(dir, { recursive: true });
    fs.writeFileSync(path.join(dir, `report_REQ-006_${ts}.json`), JSON.stringify({ cases }));
  };
  write('eval', 1, [{ name: 'test:integration', passed: true, stdout: 'x.py::test_foreign_records <- y PASSED [ 91%]' }]);
  write('gate', 2, [{ name: 'test:integration', passed: false }]);
  write('gate', 3, [{ name: 'acceptance::integrity', passed: false }]);
  const reports = readEarlierReports(root, 'REQ-006');
  assert.deepEqual(reports.map((r) => r.phase), ['eval', 'gate', 'gate']);
  const failures = [
    { name: 'test:integration', output: 'E assert 1 == 3\nFAILED src/x.py::test_foreign_records - assert 1 == 3' },
    { name: 'lint', output: 'E501' },
  ];
  const [flaky, steady] = annotateIntermittentFailures(failures, reports);
  assert.equal(flaky.intermittent, true);
  assert.match(flaky.output, /^CLike note: test_foreign_records passed in 1 of 2 earlier/);
  assert.match(flaky.output, /make the behavior deterministic in src\//);
  assert.match(flaky.output, /assert 1 == 3/);
  assert.equal(steady, failures[1]);
  fs.rmSync(root, { recursive: true, force: true });
});

test('repair notes: hint and CLike diagnosis next to the report, never read back as a report', () => {
  const failures = [
    { name: 'test:integration', command: 'python ci/check.py tests', intermittent: true, output: 'CLike note: t passed in 3 of 5 earlier runs.\n\nassert 1 == 3' },
    { name: 'lint', output: 'E501' },
  ];
  const md = repairNotesMarkdown({ reqId: 'REQ-006', phase: 'gate', cycle: 1, maxCycles: 2, reason: '1 failing check(s)', hint: '', failures });
  assert.match(md, /^# AUTO-GATE REQ-006 — repair cycle 1\/2/);
  assert.match(md, /Developer hint:\*\* none/);
  assert.match(md, /`test:integration`: CLike note: t passed in 3 of 5 earlier runs\.\n/);
  assert.doesNotMatch(md, /assert 1 == 3/);
  assert.match(repairNotesMarkdown({ reqId: 'R', phase: 'eval', cycle: 1, maxCycles: 2, reason: 'x', hint: 'keep order', failures: [] }), /Developer hint:\*\* keep order/);
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'clike-notes-'));
  const rel = writeRepairNotes(root, 'gate', 'REQ-006', md);
  assert.match(rel, /^runs\/gate\/REQ-006\/repair_REQ-006_\d+\.md$/);
  assert.equal(fs.readFileSync(path.join(root, rel), 'utf8'), md);
  assert.deepEqual(readEarlierReports(root, 'REQ-006'), []);
  fs.rmSync(root, { recursive: true, force: true });
});
