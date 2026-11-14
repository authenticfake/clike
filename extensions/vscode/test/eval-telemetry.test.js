'use strict';
// Eval and gate runs reach .clike/telemetry: their time and outcome, no model.
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
      Uri: { joinPath: (u, ...parts) => ({ fsPath: path.join(u.fsPath, ...parts), scheme: 'file' }) },
      workspace: {
        getConfiguration: () => ({ get: (_k, d) => d }),
        fs: {
          createDirectory: async (u) => fs.mkdirSync(u.fsPath, { recursive: true }),
          stat: async (u) => fs.statSync(u.fsPath),
          readFile: async (u) => fs.readFileSync(u.fsPath),
          writeFile: async (u, buf) => fs.writeFileSync(u.fsPath, buf),
        },
      },
      window: { showWarningMessage() {}, createOutputChannel: () => ({ appendLine() {} }) },
    };
  }
  return originalLoad.call(this, request, parent, isMain);
};
const { persistTelemetryVSCode, sandboxRunTelemetry } = require('../telemetry');
test.after(() => { Module._load = originalLoad; });

test('an eval run is a telemetry row with its time, REQ and outcome, no model', async () => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'clike-telemetry-'));
  const result = { req_id: 'REQ-009', status: 'PASS_WITH_WARNINGS', passed_count: 98, failed: 0, blocked_count: 0, warning_count: 1,
    regression: true, timings: { checks_s: 43.9, regression_s: 111.4, regression_workers: 3 } };
  const fields = sandboxRunTelemetry(result, Date.now() - 1500, 'full');
  assert.ok(fields.duration_ms >= 1500);
  await persistTelemetryVSCode({ fsPath: root, scheme: 'file' }, 'cdl-pipeline', null, 'eval', fields);
  await persistTelemetryVSCode({ fsPath: root, scheme: 'file' }, 'cdl-pipeline', null, 'gate',
    sandboxRunTelemetry({ req_id: 'REQ-009', gate: 'PASS', status: 'PASS', reused_eval_at: 't' }, Date.now(), 'gate'));
  const dir = path.join(root, '.clike', 'telemetry', 'cdl-pipeline');
  const rows = fs.readFileSync(path.join(dir, fs.readdirSync(dir)[0]), 'utf8').trim().split('\n').map((l) => JSON.parse(l));
  assert.deepEqual(rows.map((r) => [r.phase, r.req_id, r.execution, r.model]), [['eval', 'REQ-009', 'eval_sandbox', null], ['gate', 'REQ-009', 'eval_sandbox', null]]);
  assert.deepEqual(rows[0].outcome, { scope: 'full', status: 'PASS_WITH_WARNINGS', passed: 98, failed: 0, blocked: 0, warnings: 1,
    regression: true, checks_s: 43.9, regression_s: 111.4, regression_workers: 3, reused: false });
  assert.deepEqual([rows[1].outcome.status, rows[1].outcome.reused], ['PASS', true]);
  fs.rmSync(root, { recursive: true, force: true });
});
