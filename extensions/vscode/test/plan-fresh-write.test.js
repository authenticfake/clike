'use strict';
// A status write at the end of /kit starts from the plan on disk, not from the copy read when the run
// started: B2B REQ-037, a supersedes entry added during a 25-minute repair was overwritten at its end.
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('fs');
const os = require('os');
const path = require('path');
const Module = require('module');

const originalLoad = Module._load;
Module._load = function (request, parent, isMain) {
  if (request === 'vscode') {
    return {
      workspace: {
        getConfiguration: () => ({ get: (_k, d) => d }),
        fs: {
          readFile: async (uri) => fs.readFileSync(uri.fsPath),
          writeFile: async (uri, data) => { fs.mkdirSync(path.dirname(uri.fsPath), { recursive: true }); fs.writeFileSync(uri.fsPath, data); },
          createDirectory: async (uri) => fs.mkdirSync(uri.fsPath, { recursive: true }),
        },
      },
      window: { createOutputChannel: () => ({ appendLine() {} }), showErrorMessage() {}, showWarningMessage() {} },
      Uri: { joinPath: (base, ...parts) => ({ fsPath: path.join(base.fsPath, ...parts) }), file: (p) => ({ fsPath: p }) },
    };
  }
  return originalLoad.call(this, request, parent, isMain);
};
const { saveKitCommand } = require('../utility');
Module._load = originalLoad;

test('the end of /kit keeps what changed in plan.json during the run', async () => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'clike-plan-'));
  const planPath = path.join(root, 'docs', 'harper', 'plan.json');
  fs.mkdirSync(path.dirname(planPath), { recursive: true });
  const atStart = { reqs: [{ id: 'REQ-001', status: 'done' }, { id: 'REQ-002', status: 'open', supersedes: [] }] };
  fs.writeFileSync(planPath, JSON.stringify(atStart));
  // during the run the developer declares a superseded test
  const during = JSON.parse(JSON.stringify(atStart));
  during.reqs[1].supersedes.push({ check: 'REQ-001#test/x.py::test_a', reason: 'declared during the run' });
  fs.writeFileSync(planPath, JSON.stringify(during));
  await saveKitCommand({ fsPath: root }, atStart, 'REQ-002', { appendLine() {} });
  const after = JSON.parse(fs.readFileSync(planPath, 'utf8')).reqs[1];
  assert.equal(after.status, 'in_progress');
  assert.deepEqual(after.supersedes, [{ check: 'REQ-001#test/x.py::test_a', reason: 'declared during the run' }]);
  fs.rmSync(root, { recursive: true, force: true });
});
