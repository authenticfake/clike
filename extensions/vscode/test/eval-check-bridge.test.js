'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('fs');
const os = require('os');
const path = require('path');
const { execFile } = require('child_process');

const { agentArgsForEvalCheck, compactResult, startEvalCheckBridge, CHANNEL_DIR, HELPER_PATH } = require('../eval-check-bridge');

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
