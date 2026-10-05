'use strict';
// Auto-eval (roadmap §3): eval → KIT repair from the real failures → eval, a bounded number of
// cycles. The extension drives the loop (it is the only workspace writer); the orchestrator
// builds the repair prompt and governs changes to the acceptance surface (tests stay locked).
const fs = require('fs');
const path = require('path');

const OUTPUT_TAIL = 3000;
const MAX_FILE_BYTES = 200 * 1024;
const SKIPPED_DIRS = new Set(['__pycache__', '.venv', 'node_modules', '.pytest_cache', '.mypy_cache', '.ruff_cache', 'reports']);

function evalPassed(report) {
  const status = String(report?.status || '').toUpperCase();
  return report?.passed === true || status === 'PASS';
}

/** Failed checks in the shape the KIT repair prompt reads. */
function collectRepairFailures(report) {
  return (Array.isArray(report?.cases) ? report.cases : [])
    .filter((c) => c && !c.passed)
    .map((c) => ({
      name: c.name,
      code: c.code,
      command: c.cmd || '',
      blocking: c.blocking !== false,
      output: `${c.stderr || ''}\n${c.stdout || ''}`.slice(-OUTPUT_TAIL),
    }));
}

function failureSignature(failures) {
  return (failures || []).map((f) => String(f.name || '')).sort().join('|');
}

/** Current candidate files of the REQ (runs/kit/<REQ>/**), workspace-relative. */
function collectRepairFiles(workspaceRoot, reqId) {
  const kitRoot = path.join(workspaceRoot, 'runs', 'kit', reqId);
  const files = [];
  const walk = (dir) => {
    let entries = [];
    try {
      entries = fs.readdirSync(dir, { withFileTypes: true });
    } catch {
      return;
    }
    for (const entry of entries.sort((a, b) => a.name.localeCompare(b.name))) {
      const full = path.join(dir, entry.name);
      if (entry.isDirectory()) {
        if (!SKIPPED_DIRS.has(entry.name)) walk(full);
      } else if (entry.isFile()) {
        let size = 0;
        try { size = fs.statSync(full).size; } catch { continue; }
        if (size >= MAX_FILE_BYTES) continue;
        const content = fs.readFileSync(full);
        if (content.includes(0)) continue; // binary
        files.push({ path: path.relative(workspaceRoot, full).split(path.sep).join('/'), content: content.toString('utf8') });
      }
    }
  };
  walk(kitRoot);
  return files;
}

/**
 * Decide the next step after an eval of an auto-eval run.
 * state: { cycle, maxCycles, hint, lastSignature }
 * → { action: 'pass' | 'stop' | 'repair', reason, failures?, signature? }
 */
function nextAutoEvalStep(state, report) {
  if (evalPassed(report)) return { action: 'pass', reason: `eval PASS after ${state.cycle} repair cycle(s)` };
  if (report?.integrity && report.integrity.ok === false) {
    return { action: 'stop', reason: 'the acceptance surface (test/ or ci/) changed after the lock; re-run /kit to re-baseline' };
  }
  const failures = collectRepairFailures(report);
  if (!failures.length) return { action: 'stop', reason: 'eval failed without failing checks to repair (see the eval report)' };
  const signature = failureSignature(failures);
  if (state.cycle >= state.maxCycles) {
    return { action: 'stop', reason: `still failing after ${state.cycle} repair cycle(s)`, failures, signature };
  }
  if (state.lastKitOk === false) {
    return { action: 'stop', reason: 'the KIT repair request failed (see the chat for the error)', failures, signature };
  }
  if (state.cycle > 0 && state.lastSignature === signature) {
    return { action: 'stop', reason: 'no progress: the same checks still fail', failures, signature };
  }
  return { action: 'repair', reason: `${failures.length} failing check(s)`, failures, signature };
}

module.exports = {
  collectRepairFailures,
  collectRepairFiles,
  evalPassed,
  failureSignature,
  nextAutoEvalStep,
};
