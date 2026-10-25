'use strict';
// A repair's rejected change to a locked test is saved as a patch for the developer (test project
// REQ-002: the agent found three fixture defects, the lock restored the test, the work was lost).
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('fs');
const os = require('os');
const path = require('path');
const { execFileSync } = require('child_process');

const { saveRejectedTestFix, rejectedTestFixMessage } = require('../rejected-test-fix');

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
  execFileSync('git', ['apply', saved.patch], { cwd: root });
  assert.equal(fs.readFileSync(path.join(root, rel), 'utf8'), after);
  assert.match(rejectedTestFixMessage('REQ-002', saved), /--accept "<why>" \(audited\)/);
});

test('nothing is saved when no test change was rejected', () => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'clike-rtf-'));
  assert.equal(saveRejectedTestFix(root, 'REQ-002', 1, [{ rel: 'ci/LTC.json', before: '', after: '{}' }]), null);
  assert.equal(saveRejectedTestFix(root, 'REQ-002', 1, []), null);
});
