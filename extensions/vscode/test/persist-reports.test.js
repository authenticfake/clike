'use strict';
// The eval report written under runs/eval/<REQ>/ keeps what the orchestrator measured.
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
      Uri: {
        file: (p) => ({ fsPath: p, scheme: 'file' }),
        joinPath: (u, ...parts) => ({ fsPath: path.join(u.fsPath, ...parts), scheme: 'file' }),
      },
      workspace: {
        getConfiguration: () => ({ get: (_k, d) => d }),
        fs: {
          createDirectory: async (u) => fs.mkdirSync(u.fsPath, { recursive: true }),
          writeFile: async (u, buf) => fs.writeFileSync(u.fsPath, buf),
        },
      },
      window: { showErrorMessage() {}, createOutputChannel: () => ({ appendLine() {} }) },
    };
  }
  return originalLoad.call(this, request, parent, isMain);
};
// persistReports requires vscode when it runs: the stub stays until the tests end
const { persistReports } = require('../utility');
test.after(() => { Module._load = originalLoad; });

test('the persisted eval report keeps the timings of the eval', async () => {
  // cdl-pipeline REQ-003: the orchestrator returned timings, the written report dropped them
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'clike-persist-'));
  const timings = { total_s: 98.1, setup_s: 5, checks_s: 30, regression_s: 60, regression_workers: 2, regression_by_req: { 'REQ-001': 55 } };
  await persistReports({ fsPath: root, scheme: 'file' }, 'eval', {
    req_id: 'REQ-003', status: 'PASS', passed: true, failed: 0, passed_count: 3, cases: [], timings,
  }, { appendLine() {} });
  const dir = path.join(root, 'runs', 'eval', 'REQ-003');
  const file = fs.readdirSync(dir).find((n) => n.endsWith('.json'));
  assert.deepEqual(JSON.parse(fs.readFileSync(path.join(dir, file), 'utf8')).timings, timings);
});
