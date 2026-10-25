'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('fs');
const os = require('os');
const path = require('path');
const { execFile } = require('child_process');

const { agentArgsForEvalCheck, agentTimeoutMinutes, compactResult, startEvalCheckBridge, CHANNEL_DIR, HELPER_PATH } = require('../eval-check-bridge');

function runHelper(root, args) {
  return new Promise((resolve) => {
    execFile(process.execPath, [path.join(root, HELPER_PATH), ...args], { cwd: root }, (error, stdout, stderr) => {
      resolve({ code: error ? error.code : 0, stdout, stderr });
    });
  });
}

test('the agent re-runs checks through the helper and reads their errors', async () => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'clike-evalcheck-'));
  const asked = [];
  const bridge = startEvalCheckBridge({
    workspaceRoot: root,
    pollMs: 50,
    maxRuns: 2,
    runChecks: async (checks) => {
      asked.push(checks);
      return { cases: [
        { name: 'env::npm-install', passed: true },
        { name: 'test:unit', passed: false, code: 1, excerpt: 'FAIL a.test.ts\nAssertionError: 1 !== 2' },
      ] };
    },
  });
  try {
    const first = await runHelper(root, ['test:unit', 'bad;name$(x)']);
    assert.equal(first.code, 1);
    assert.match(first.stdout, /FAIL test:unit \(exit 1\)/);
    assert.match(first.stdout, / {4}AssertionError: 1 !== 2/);
    assert.doesNotMatch(first.stdout, /npm-install/);
    assert.deepEqual(asked, [['test:unit']]);  // unsafe names dropped
    await runHelper(root, ['test:unit']);
    const limited = await runHelper(root, ['test:unit']);
    assert.match(limited.stdout, /LIMIT: eval-check run limit reached \(2\)/);
    assert.equal(asked.length, 2);
  } finally {
    bridge.stop();
  }
  assert.ok(!fs.existsSync(path.join(root, CHANNEL_DIR)) && !fs.existsSync(path.join(root, HELPER_PATH)));
  fs.rmSync(root, { recursive: true, force: true });
});

test('the helper exits at once when CLike is not serving checks', async () => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'clike-evalcheck-'));
  const bridge = startEvalCheckBridge({ workspaceRoot: root, runChecks: async () => ({}) });
  const helperSource = fs.readFileSync(path.join(root, HELPER_PATH), 'utf8');
  bridge.stop();
  fs.mkdirSync(path.dirname(path.join(root, HELPER_PATH)), { recursive: true });
  fs.writeFileSync(path.join(root, HELPER_PATH), helperSource);
  const res = await runHelper(root, ['test:unit']);
  assert.equal(res.code, 2);
  assert.match(res.stderr, /not serving eval checks/);
  fs.rmSync(root, { recursive: true, force: true });
});

test('result: PASS only when every requested check passed', () => {
  assert.equal(compactResult({ cases: [{ name: 'lint', passed: true }] }).status, 'PASS');
  assert.equal(compactResult({ cases: [] }).status, 'FAIL');
  assert.equal(compactResult({ cases: [{ name: 'env::provision::X', passed: false, code: 1, stderr: 'no db' }] }).status, 'FAIL');
  const exhausted = compactResult({ reason_code: 'EVAL_SANDBOX_EXHAUSTED', cases: [{ name: 'test:e2e', passed: false, code: 1, excerpt: 'spawn EAGAIN' }] });
  assert.equal(exhausted.status, 'BLOCKED');
  assert.match(exhausted.error, /Do not change code/);
});

test('agent args: Claude Code allows the helper before its other options, Codex unchanged', () => {
  assert.deepEqual(agentArgsForEvalCheck('claude_code', ['-p', '--permission-mode', 'acceptEdits']),
    ['--allowedTools', 'Bash(node .clike/bin/eval-check.mjs:*)', '-p', '--permission-mode', 'acceptEdits']);
  assert.deepEqual(agentArgsForEvalCheck('gpt_codex', ['exec', '--sandbox', 'workspace-write']), ['exec', '--sandbox', 'workspace-write']);
});

test('a helper stopped by the agent timeout resumes the same run', async () => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'clike-evalcheck-'));
  let release;
  const gate = new Promise((resolve) => { release = resolve; });
  let calls = 0;
  const bridge = startEvalCheckBridge({ workspaceRoot: root, pollMs: 50, runChecks: async () => {
    calls += 1; await gate; return { cases: [{ name: 'lint', passed: true }] };
  } });
  try {
    const killed = execFile(process.execPath, [path.join(root, HELPER_PATH), 'lint'], { cwd: root });
    await new Promise((r) => setTimeout(r, 400));
    killed.kill();
    const resumed = runHelper(root, ['lint']);
    await new Promise((r) => setTimeout(r, 300));
    release();
    const res = await resumed;
    assert.equal(res.code, 0);
    assert.match(res.stdout, /still running lint/);
    assert.equal(calls, 1);
  } finally {
    bridge.stop();
    fs.rmSync(root, { recursive: true, force: true });
  }
});

test('agent timeout: extended by the eval checks it may wait for', () => {
  assert.equal(agentTimeoutMinutes(30, null), 30);
  assert.equal(agentTimeoutMinutes(30, { max_runs: 8 }), 78);
  assert.equal(agentTimeoutMinutes(1800 / 60, { max_runs: 0 }), 30);
});

test('eval-check shows a regressed REQ\'s failures, not its passing setup steps', () => {
  const result = compactResult({ cases: [
    { name: 'regression::REQ-014::env::npm-install', passed: true },
    { name: 'regression::REQ-014::test:integration', passed: false, excerpt: 'Error: expect(locator).toContainText failed' },
    { name: 'tests', passed: true },
  ] });
  assert.deepStrictEqual(result.checks.map((c) => c.name), ['regression::REQ-014::test:integration', 'tests']);
  assert.equal(result.status, 'FAIL');
});

test('a check run with changed locked tests warns that the pass does not hold yet', async () => {
  // test project REQ-002: the agent fixed the locked test, its eval-check passed, CLike restored it
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'clike-evalcheck-'));
  const testDir = path.join(root, 'runs', 'kit', 'REQ-002', 'test');
  fs.mkdirSync(testDir, { recursive: true });
  fs.writeFileSync(path.join(testDir, 'test_ui.py'), 'def test_x():\n    assert True\n');
  const bridge = startEvalCheckBridge({
    workspaceRoot: root, pollMs: 50, testRoot: 'runs/kit/REQ-002/test',
    runChecks: async () => ({ cases: [{ name: 'test:browser', passed: true }] }),
  });
  try {
    const clean = await runHelper(root, ['test:browser']);
    assert.equal(clean.code, 0);
    assert.doesNotMatch(clean.stdout, /WARNING/);
    fs.writeFileSync(path.join(testDir, 'test_ui.py'), 'def test_x():\n    assert 1\n');
    fs.writeFileSync(path.join(testDir, 'test_new.py'), 'def test_n():\n    assert True\n');  // new: not locked
    const changed = await runHelper(root, ['test:browser']);
    assert.match(changed.stdout, /WARNING: this result uses your changes to tests that existed before this repair \(runs\/kit\/REQ-002\/test\/test_ui.py\)/);
    assert.doesNotMatch(changed.stdout, /test_new\.py/);
  } finally {
    bridge.stop();
    fs.rmSync(root, { recursive: true, force: true });
  }
});

test('a non-blocking failure does not make the result FAIL, and the repair is told when its checks pass', () => {
  // B2B REQ-032: the two unit checks given to the repair passed at its 2nd run; coverage checks the
  // eval marks non-blocking kept the result FAIL and the agent went on for 25 minutes (14.5M tokens)
  const report = { cases: [
    { name: 'regression::REQ-008::test:unit', passed: true },
    { name: 'regression::REQ-008::test:coverage', passed: false, blocking: false, excerpt: 'already failing without this candidate' },
    { name: 'regression::REQ-014::test:unit', passed: true },
  ] };
  const targets = ['regression::REQ-008::test:unit', 'regression::REQ-014::test:unit'];
  const out = compactResult(report, targets);
  assert.equal(out.status, 'PASS');
  assert.match(out.done, /the 2 check\(s\) this repair was given pass: finish now/);
  assert.equal(out.checks[1].blocking, false);
  assert.match(out.checks[1].note, /non-blocking/);
  // a target still failing: no finish signal, and a blocking failure still fails
  const failing = compactResult({ cases: [{ name: 'regression::REQ-008::test:unit', passed: false }] }, targets);
  assert.equal(failing.status, 'FAIL');
  assert.equal(failing.done, undefined);
  // a run that did not include every target does not say finish
  assert.equal(compactResult({ cases: [{ name: 'regression::REQ-008::test:unit', passed: true }] }, targets).done, undefined);
});
