'use strict';
// A repair's rejected change to a locked test is saved as a patch for the developer (test project
// REQ-002: the agent found three fixture defects, the lock restored the test, the work was lost).
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('fs');
const os = require('os');
const path = require('path');
const { execFileSync } = require('child_process');

const { saveRejectedTestFix, rejectedTestFixMessage, applyLatestTestFix, revertAppliedTestFix } = require('../rejected-test-fix');

test('the rejected test change is saved as a patch that applies to the restored test', () => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'clike-rtf-'));
  const rel = 'runs/kit/REQ-002/test/test_ui.py';
  fs.mkdirSync(path.join(root, path.dirname(rel)), { recursive: true });
  const before = 'def test_x(page):\n    page.add_init_script("() => { hold() }")\n    assert page.state() == "L-LOADING"\n';
  const after = before.replace('"() => { hold() }"', '"(() => { hold() })()"');
  fs.writeFileSync(path.join(root, rel), before);
  const saved = saveRejectedTestFix(root, 'REQ-002', 1, [
    { rel: 'test/test_ui.py', before, after, issues: ['tests are locked (the eval does not show an error in the test itself)'] },
    { rel: 'ci/LTC.json', before: '{}', after: '{"x":1}', issues: ['check removed'] },
  ], 42);
  assert.deepEqual(saved, { patch: 'runs/eval/REQ-002/proposed_test_fix_42.patch', files: ['test/test_ui.py'] });
  const patch = fs.readFileSync(path.join(root, saved.patch), 'utf8');
  assert.match(patch, /rejected by the acceptance lock/);
  assert.match(patch, /test\/test_ui.py: tests are locked/);
  execFileSync('git', ['init', '-q'], { cwd: root });
  execFileSync('git', ['config', 'core.autocrlf', 'false'], { cwd: root });
  execFileSync('git', ['-c', 'core.autocrlf=false', 'apply', saved.patch], { cwd: root });
  assert.equal(fs.readFileSync(path.join(root, rel), 'utf8'), after);
  assert.match(rejectedTestFixMessage('REQ-002', saved), /--accept "<why>" applies it/);
});

test('nothing is saved when no test change was rejected', () => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'clike-rtf-'));
  assert.equal(saveRejectedTestFix(root, 'REQ-002', 1, [{ rel: 'ci/LTC.json', before: '', after: '{}' }]), null);
  assert.equal(saveRejectedTestFix(root, 'REQ-002', 1, []), null);
});

test('--accept applies the latest proposal once, and a refused one is undone', () => {
  // B2B REQ-032: the developer approves the repair's test change with one command
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'clike-rtf-'));
  execFileSync('git', ['init', '-q'], { cwd: root });
  execFileSync('git', ['config', 'core.autocrlf', 'false'], { cwd: root });
  const rel = 'runs/kit/REQ-032/test/test_browser.py';
  fs.mkdirSync(path.join(root, path.dirname(rel)), { recursive: true });
  const before = 'from helpers import csrf_headers, login\n\ndef test_x():\n    assert login()\n';
  const old = before.replace('login\n', 'login  # old\n');
  const after = 'from helpers import csrf_headers\nfrom support import login_loopback as login\n\ndef test_x():\n    assert login()\n';
  saveRejectedTestFix(root, 'REQ-032', 1, [{ rel: 'test/test_browser.py', before: old, after: old }], 10);
  fs.writeFileSync(path.join(root, rel), before);
  saveRejectedTestFix(root, 'REQ-032', 2, [{ rel: 'test/test_browser.py', before, after }], 20);
  assert.equal(applyLatestTestFix(root, 'REQ-999'), null);

  const res = applyLatestTestFix(root, 'REQ-032');
  assert.deepEqual(res, { applied: 'runs/eval/REQ-032/proposed_test_fix_20.applied.patch' });
  assert.equal(fs.readFileSync(path.join(root, rel), 'utf8'), after);
  // the next proposal left (cycle 1) does not apply to this test any more
  assert.deepEqual(applyLatestTestFix(root, 'REQ-032'), { stale: 'runs/eval/REQ-032/proposed_test_fix_10.patch' });

  assert.equal(revertAppliedTestFix(root, res.applied), 'runs/eval/REQ-032/proposed_test_fix_20.patch');
  assert.equal(fs.readFileSync(path.join(root, rel), 'utf8'), before);
});
