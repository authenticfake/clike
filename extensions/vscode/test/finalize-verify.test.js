'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('fs');
const os = require('os');
const path = require('path');

const fv = require('../finalize-verify');
const { nextAutoEvalStep } = require('../auto-eval');

function project() {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'clike-finalize-'));
  const put = (rel, text) => {
    fs.mkdirSync(path.dirname(path.join(root, rel)), { recursive: true });
    fs.writeFileSync(path.join(root, rel), text);
  };
  put('runs/kit/REQ-001/ci/LTC.json', JSON.stringify({ run_from: 'runs/kit/REQ-001', checks: [{ id: 'unit', command: 'pytest test', blocking: true }], environment: { required_variables: [{ name: 'DB', provision: 'postgres_database' }] } }));
  put('runs/kit/REQ-002/ci/LTC.json', '{broken');
  put('src/app.py', 'x = 1\n');
  put('src/web/node_modules/a/index.js', 'x');
  put('test/test_app.py', 'def test(): pass\n');
  put('README.md', '# app\n');
  put('docs/_private/notes.md', 'secret notes');
  put('.clike/sessions/s.jsonl', '{}');
  return root;
}

test('REQ eval profiles: checks, environment, unreadable profiles skipped', () => {
  const root = project();
  assert.deepEqual(fv.collectReqEvalProfiles(root), [{
    req: 'REQ-001', run_from: 'runs/kit/REQ-001', checks: [{ id: 'unit', command: 'pytest test' }],
    environment: { required_variables: [{ name: 'DB', provision: 'postgres_database' }] },
  }]);
  fs.rmSync(root, { recursive: true, force: true });
});

test('solution files: canonical code, tests and run docs; no deps, runs, local state or private docs', () => {
  const root = project();
  const paths = fv.collectSolutionFiles(root).map((f) => f.path);
  assert.deepEqual(paths.sort(), ['README.md', 'src/app.py', 'test/test_app.py']);
  fs.rmSync(root, { recursive: true, force: true });
});

test('a missing solution profile is a repairable failure; evidence lists the checks', () => {
  const step = nextAutoEvalStep({ cycle: 0, maxCycles: 3, hint: '' }, fv.missingProfileReport());
  assert.equal(step.action, 'repair');
  assert.match(step.failures[0].output, /did not write ci\/SOLUTION_LTC.json/);
  const md = fv.solutionEvalMarkdown({ status: 'FAIL', cases: [
    { name: 'env::provision::DB', passed: true }, { name: 'e2e', passed: false, blocking: true }, { name: 'build', passed: true },
  ] }, { cycle: 2, when: new Date('2026-10-12T10:00:00Z') });
  assert.match(md, /Result: \*\*FAIL\*\*/);
  assert.match(md, /\| e2e \| FAIL \|/);
  assert.doesNotMatch(md, /env::provision/);
  assert.match(md, /Repair cycles: 2/);
});
