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

test('REQs not promoted, gate evidence and verification cycles in the solution evidence', () => {
  const root = project();
  const put = (rel, text) => {
    fs.mkdirSync(path.dirname(path.join(root, rel)), { recursive: true });
    fs.writeFileSync(path.join(root, rel), text);
  };
  put('docs/harper/plan.json', JSON.stringify({ reqs: [{ id: 'REQ-001', status: 'done' }, { id: 'REQ-002', status: 'in_progress' }] }));
  put('runs/gate/REQ-001/report_REQ-001_1.json', JSON.stringify({ gate: 'PASS', cases: [{}, {}] }));
  assert.deepEqual(fv.pendingReqs(root), [{ id: 'REQ-002', status: 'in_progress' }]);
  const gates = fv.gateEvidence(root);
  assert.deepEqual(gates[0], { id: 'REQ-001', status: 'done', report: 'runs/gate/REQ-001/report_REQ-001_1.json', verdict: 'PASS', cases: 2 });
  assert.deepEqual(gates[1], { id: 'REQ-002', status: 'in_progress' });
  const md = fv.solutionEvalMarkdown({ status: 'PASS', cases: [{ name: 'smoke:api', passed: true }] }, {
    cycle: 1, history: [{ cycle: 0, status: 'FAIL', failing: ['service:web'] }, { cycle: 1, status: 'PASS', failing: [] }], gates,
  });
  assert.match(md, /test suites are not run again/);
  assert.match(md, /\| 0 \| FAIL \| service:web \|/);
  assert.match(md, /\| REQ-001 \| done \| PASS \| 2 \| `runs\/gate\/REQ-001\/report_REQ-001_1.json` \|/);
  assert.match(md, /\| REQ-002 \| in_progress \| no gate \| - \| - \|/);
  assert.match(md, /docs\/harper\/FINALIZE_REPORT.md/);
  fs.rmSync(root, { recursive: true, force: true });
});

test('a missing developer report is a repairable failure of the verification', () => {
  const root = project();
  const checked = fv.withReportCheck(root, { status: 'PASS', passed: true, cases: [{ name: 'smoke', passed: true }] });
  assert.equal(checked.passed, false);
  const step = nextAutoEvalStep({ cycle: 0, maxCycles: 3, hint: '' }, checked);
  assert.equal(step.action, 'repair');
  assert.deepEqual(step.failures.map((f) => f.name), ['structure::finalize-report']);
  fs.mkdirSync(path.join(root, 'docs', 'harper'), { recursive: true });
  fs.writeFileSync(path.join(root, 'docs', 'harper', 'FINALIZE_REPORT.md'), '# Report\n');
  assert.equal(fv.withReportCheck(root, { status: 'PASS', passed: true, cases: [] }).passed, true);
  fs.rmSync(root, { recursive: true, force: true });
});

test('REQ branches not merged into the default branch are found', () => {
  const { execFileSync } = require('child_process');
  const dir = fs.realpathSync(fs.mkdtempSync(path.join(os.tmpdir(), 'clike-finalize-git-')));
  const git = (...args) => execFileSync('git', args, { cwd: dir, encoding: 'utf8' });
  git('init', '-q', '-b', 'main');
  git('-c', 'user.email=t@t', '-c', 'user.name=t', 'commit', '-q', '--allow-empty', '-m', 'base');
  git('branch', 'feature/req-001');
  git('switch', '-q', '-c', 'feature/req-002');
  git('-c', 'user.email=t@t', '-c', 'user.name=t', 'commit', '-q', '--allow-empty', '-m', 'req-002');
  git('switch', '-q', '-c', 'other');
  git('-c', 'user.email=t@t', '-c', 'user.name=t', 'commit', '-q', '--allow-empty', '-m', 'other');
  assert.deepEqual(fv.unmergedReqBranches(dir, 'main', 'feature'), ['feature/req-002']);
  assert.deepEqual(fv.unmergedReqBranches(path.join(dir, 'missing'), 'main', 'feature'), []);
  fs.rmSync(dir, { recursive: true, force: true });
});
