'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('fs');
const os = require('os');
const path = require('path');

const { collectRepairFailures, collectRepairFiles, nextAutoEvalStep } = require('../auto-eval');
const { parseSlash } = require('../slash-parser');

const failing = (names) => ({
  status: 'FAIL',
  passed: false,
  cases: [
    { name: 'lint', passed: true },
    ...names.map((name) => ({ name, passed: false, code: 1, cmd: `run ${name}`, stderr: `${name} broke`, blocking: true })),
  ],
});

test('/eval --fix carries the hint; /gate ignores --fix', () => {
  const withHint = parseSlash('/eval REQ-001 --fix "use the repository layer"').args;
  assert.deepEqual([withHint.targets, withHint.fix, withHint.hint], [['REQ-001'], true, 'use the repository layer']);
  const bare = parseSlash('/eval REQ-001 --fix').args;
  assert.deepEqual([bare.targets, bare.fix, bare.hint], [['REQ-001'], true, '']);
  assert.equal(parseSlash('/eval REQ-001').args.fix, undefined);
  assert.equal(parseSlash('/eval REQ-001 manual pass').args.testMode, 'manual');
  assert.equal(parseSlash('/gate REQ-001 --fix').args.fix, undefined);
});

test('failures carry name, command, exit code and output for the repair prompt', () => {
  assert.deepEqual(collectRepairFailures(failing(['unit'])), [
    { name: 'unit', code: 1, command: 'run unit', blocking: true, output: 'unit broke\n' },
  ]);
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
