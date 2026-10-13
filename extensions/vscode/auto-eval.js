'use strict';
// Auto-eval (roadmap §3): eval → KIT repair from the real failures → eval, a bounded number of
// cycles. The extension drives the loop (it is the only workspace writer); the orchestrator
// builds the repair prompt and governs changes to the acceptance surface (tests stay locked).
const fs = require('fs');
const path = require('path');

const MAX_FILE_BYTES = 200 * 1024;
const SKIPPED_DIRS = new Set([
  '__pycache__', '.venv', 'venv', 'node_modules', '.pytest_cache', '.mypy_cache', '.ruff_cache', 'reports',
  '.tmp', 'tmp', '.cache', '.npm-cache', '.next', 'coverage', 'local-eval-workspaces',
]);

function evalPassed(report) {
  const status = String(report?.status || '').toUpperCase();
  return report?.passed === true || status === 'PASS';
}

/**
 * Failed checks in the shape the KIT repair prompt reads.
 * - output: the error blocks of the whole output (report `excerpt`, built by the eval runner),
 *   else stderr head + stdout tail;
 * - a check with the same errors as one already listed (unit and coverage run the same tests)
 *   points to it instead of repeating them;
 * - non-blocking failures of the regression of other REQs (their coverage, warnings) are not
 *   this REQ's to repair: left out (the eval is not failed by them).
 */
function collectRepairFailures(report) {
  const seen = new Map();
  const out = [];
  for (const c of (Array.isArray(report?.cases) ? report.cases : [])) {
    if (!c || c.passed) continue;
    if (c.blocking === false && String(c.name || '').startsWith('regression::')) continue;
    const output = c.excerpt
      ? String(c.excerpt)
      : `${String(c.stderr || '').slice(0, 1500)}\n${String(c.stdout || '').slice(-2500)}`;
    const fingerprint = String(c.fingerprint || '');
    const same = fingerprint ? seen.get(fingerprint) : undefined;
    if (fingerprint && !same) seen.set(fingerprint, c.name);
    out.push({
      name: c.name,
      code: c.code,
      command: c.cmd || '',
      blocking: c.blocking !== false,
      fingerprint,
      output: same ? `Same errors as the check ${same} above.` : output,
    });
  }
  return out;
}

/** Identity of a set of failures: the checks and their errors (a different error is progress). */
function failureSignature(failures) {
  return (failures || []).map((f) => `${String(f.name || '')}#${String(f.fingerprint || '')}`).sort().join('|');
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

/** Text content of the REQ's acceptance surface (runs/kit/<REQ>/{test,ci}/**), KIT-relative. */
function snapshotAcceptanceSurface(workspaceRoot, reqId) {
  const snapshot = {};
  for (const file of collectRepairFiles(workspaceRoot, reqId)) {
    const rel = file.path.slice(`runs/kit/${reqId}/`.length);
    // Markdown (ci/HOWTO.md) documents how to run the checks: not acceptance, freely editable.
    if ((rel.startsWith('test/') || rel.startsWith('ci/')) && !rel.toLowerCase().endsWith('.md')) snapshot[rel] = file.content;
  }
  return snapshot;
}

/**
 * What a repair changed in the acceptance surface: files modified (submitted for governance)
 * and files deleted (always restored). New files are left alone (they do not weaken the lock).
 */
function acceptanceChanges(before, after) {
  const modified = {};
  const deleted = [];
  for (const [rel, content] of Object.entries(before)) {
    if (!(rel in after)) deleted.push(rel);
    else if (after[rel] !== content) modified[rel] = after[rel];
  }
  return { modified, deleted };
}

/** Write back the pre-repair content of the given KIT-relative files. */
function restoreAcceptanceFiles(workspaceRoot, reqId, before, rels) {
  for (const rel of rels) {
    if (!(rel in before)) continue;
    const full = path.join(workspaceRoot, 'runs', 'kit', reqId, ...rel.split('/'));
    fs.mkdirSync(path.dirname(full), { recursive: true });
    fs.writeFileSync(full, before[rel], 'utf8');
  }
}

/**
 * Decide the next step after an eval of an auto-eval run.
 * state: { cycle, maxCycles, hint, lastSignature }
 * → { action: 'pass' | 'stop' | 'repair', reason, failures?, signature? }
 */
function nextAutoEvalStep(state, report) {
  if (evalPassed(report)) return { action: 'pass', reason: `eval PASS after ${state.cycle} repair cycle(s)` };
  if (report?.reason_code === 'EVAL_ENVIRONMENT_MISSING' && !report.environment_repairable) {
    // Only the developer can give these values (external ones, the database server URL).
    const env = (report.cases || []).find(c => c.name === 'env::required-variables');
    return {
      action: 'stop',
      reason: 'the eval environment lacks values only you can give (the code is not at fault, nothing to repair)' +
        (env?.stderr ? `:\n${env.stderr}` : ''),
    };
  }
  // A repairable missing environment falls through: the repair declares in ci/LTC.json how CLike
  // provisions the variables (generated values, test databases, services of other REQs).
  if (report?.integrity && report.integrity.ok === false) {
    return { action: 'stop', reason: 'the acceptance surface (test/ or ci/) changed after the lock; re-run /kit to re-baseline' };
  }
  const failures = collectRepairFailures(report);
  if (!failures.length) return { action: 'stop', reason: 'eval failed without failing checks to repair (see the eval report)' };
  const signature = failureSignature(failures);
  if (state.cycle >= state.maxCycles) {
    // Still improving (fewer failing checks than before the last repair): extra cycles, bounded.
    const extra = Math.max(0, Number(state.extraCycles ?? 3));
    const improving = Number.isFinite(state.lastFailureCount) && failures.length < state.lastFailureCount;
    if (!improving || state.cycle >= state.maxCycles + extra) {
      return { action: 'stop', reason: `still failing after ${state.cycle} repair cycle(s)`, failures, signature };
    }
    if (state.lastKitOk !== false) {
      return {
        action: 'repair',
        reason: `${failures.length} failing check(s), down from ${state.lastFailureCount}: extra cycle ${state.cycle + 1 - state.maxCycles}/${extra}`,
        failures,
        signature,
      };
    }
  }
  if (state.lastKitOk === false) {
    return { action: 'stop', reason: 'the KIT repair request failed (see the chat for the error)', failures, signature };
  }
  if (state.cycle > 0 && state.lastSignature === signature) {
    return { action: 'stop', reason: 'no progress: the same checks still fail', failures, signature };
  }
  return { action: 'repair', reason: `${failures.length} failing check(s)`, failures, signature };
}

const _FAILED_TEST_RE = /^FAILED\s+(\S+?)(?:\s+-\s|\s*$)/gm;

/** Test ids of a pytest-style output that failed ("FAILED path::test - ..."). */
function failedTestIds(output) {
  return [...String(output || '').matchAll(_FAILED_TEST_RE)].map((m) => m[1].split('::').pop());
}

/**
 * Earlier eval/gate reports of the REQ (runs/{eval,gate}/<REQ>/report_*.json), oldest first,
 * reduced to what the flakiness check needs: per check, passed or not, and its output.
 */
function readEarlierReports(workspaceRoot, reqId) {
  const out = [];
  for (const phase of ['eval', 'gate']) {
    const dir = path.join(workspaceRoot, 'runs', phase, reqId);
    let names = [];
    try { names = fs.readdirSync(dir).filter((n) => /^report_.*\.json$/.test(n)); } catch { continue; }
    for (const name of names) {
      try {
        const rep = JSON.parse(fs.readFileSync(path.join(dir, name), 'utf8'));
        const ts = Number((name.match(/_(\d+)\.json$/) || [])[1] || 0);
        out.push({ phase, ts, cases: Array.isArray(rep.cases) ? rep.cases : [] });
      } catch { /* unreadable report: ignore */ }
    }
  }
  return out.sort((a, b) => a.ts - b.ts);
}

/**
 * Mark the failures that passed in earlier runs of the same REQ: the repair is told that the
 * failure is likely nondeterministic (ordering, timing, random ids) so it makes the code
 * deterministic instead of chasing the asserted value. Derived from CLike's own reports: no
 * developer hint needed. A test-level match (the failing test id PASSED earlier) is preferred.
 */
function annotateIntermittentFailures(failures, earlierReports) {
  return (failures || []).map((f) => {
    const runs = (earlierReports || [])
      .map((r) => (r.cases || []).find((c) => c && c.name === f.name))
      .filter(Boolean);
    const passedRuns = runs.filter((c) => c.passed);
    if (!passedRuns.length) return f;
    const tests = failedTestIds(f.output);
    const passedTests = tests.filter((t) =>
      passedRuns.some((c) => new RegExp(`${t.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}\\b[^\\n]*PASSED`).test(String(c.stdout || '')))
    );
    const subject = passedTests.length ? passedTests.join(', ') : `the check ${f.name}`;
    const note =
      `CLike note: ${subject} passed in ${passedRuns.length} of ${runs.length} earlier eval/gate run(s) of this REQ. ` +
      'If the code did not change in between, the failure is nondeterministic (order of rows or jobs by random ids, ' +
      'timing, concurrency, unseeded randomness): make the behavior deterministic in src/, do not adjust the asserted value.';
    return { ...f, intermittent: true, output: `${note}\n\n${f.output || ''}` };
  });
}

/**
 * What a repair cycle was given, readable next to the eval/gate report that started it: the
 * developer hint (optional) and CLike's own diagnosis (the notes derived from earlier runs).
 */
function repairNotesMarkdown({ reqId, phase, cycle, maxCycles, reason, hint, failures }) {
  const lines = [
    `# ${phase === 'gate' ? 'AUTO-GATE' : 'AUTO-EVAL'} ${reqId} — repair cycle ${cycle}/${maxCycles}`,
    '',
    `- **Why:** ${reason}`,
    `- **Developer hint:** ${hint ? hint : 'none (optional: `--fix "<hint>"`)'}`,
    '',
    '## CLike diagnosis',
    '',
  ];
  const notes = (failures || []).filter((f) => f.intermittent);
  if (notes.length) {
    for (const f of notes) lines.push(`- \`${f.name}\`: ${String(f.output || '').split('\n\n')[0]}`);
  } else {
    lines.push('- No failing check passed in earlier runs of this REQ: the failures are treated as steady.');
  }
  lines.push('', '## Failing checks given to the repair', '');
  for (const f of failures || []) lines.push(`- \`${f.name}\`${f.command ? ` (\`${f.command}\`)` : ''}`);
  return lines.join('\n') + '\n';
}

/** Write the notes as runs/<phase>/<REQ>/repair_<REQ>_<ts>.md; returns the workspace-relative path. */
function writeRepairNotes(workspaceRoot, phase, reqId, markdown) {
  const rel = ['runs', phase, reqId, `repair_${reqId}_${Date.now()}.md`];
  const full = path.join(workspaceRoot, ...rel);
  fs.mkdirSync(path.dirname(full), { recursive: true });
  fs.writeFileSync(full, markdown, 'utf8');
  return rel.join('/');
}

/**
 * Decide the next step after a gate of `/gate REQ --fix`: the same repair loop as /eval --fix
 * (same locked tests, same cycle bounds, same stop rules), driven by the gate verdict. A gate
 * PASS ends the loop even when the promotion left conflicts: those are merges of the canonical
 * tree, not defects of the candidate, and a KIT repair cannot resolve them.
 */
function nextAutoGateStep(state, report) {
  if (String(report?.gate || '').toUpperCase() === 'PASS') {
    return { action: 'pass', reason: `gate PASS after ${state.cycle} repair cycle(s)` };
  }
  const reasonCode = String(report?.reason_code || '');
  if (reasonCode === 'GATE_MANUAL_OVERRIDE') return { action: 'stop', reason: 'manual gate override: nothing to repair' };
  if (reasonCode === 'GATE_BLOCKED_ACCEPTANCE_TAMPERED') {
    return { action: 'stop', reason: 'the acceptance surface (test/ or ci/) changed after the lock; restore it or re-run /kit to re-baseline' };
  }
  // Missing required outputs are not checks: hand them to the repair as failures of their own.
  const blockers = (Array.isArray(report?.structural_blockers) ? report.structural_blockers : []).map((b) => ({
    name: `required-output::${String(b?.role || 'unknown')}`,
    passed: false,
    code: 1,
    blocking: true,
    excerpt: String(b?.reason || 'required output missing'),
    fingerprint: `required-output::${String(b?.role || 'unknown')}`,
  }));
  const failedReport = { ...(report || {}), status: 'FAIL', passed: false, cases: [...(report?.cases || []), ...blockers] };
  const step = nextAutoEvalStep(state, failedReport);
  if (step.action === 'pass') return { action: 'stop', reason: 'gate failed without failing checks to repair (see the gate report)' };
  return step.reason.startsWith('eval failed')
    ? { ...step, reason: step.reason.replace('eval failed', 'gate failed').replace('the eval report', 'the gate report') }
    : step;
}

module.exports = {
  acceptanceChanges,
  annotateIntermittentFailures,
  readEarlierReports,
  collectRepairFailures,
  collectRepairFiles,
  evalPassed,
  failureSignature,
  nextAutoEvalStep,
  nextAutoGateStep,
  repairNotesMarkdown,
  restoreAcceptanceFiles,
  snapshotAcceptanceSurface,
  writeRepairNotes,
};
