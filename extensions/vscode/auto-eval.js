'use strict';
// Auto-eval (roadmap §3): eval → KIT repair from the real failures → eval, a bounded number of
// cycles. The extension drives the loop (it is the only workspace writer); the orchestrator
// builds the repair prompt and governs changes to the acceptance surface (tests stay locked).
const crypto = require('crypto');
const fs = require('fs');
const path = require('path');
const { KIT_ROOT_DIR, rootPolicy } = require('./root-files-policy');

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
// Prefix of the eval runner's note naming the files of a promoted REQ the candidate replaced.
const SHARED_FILES_NOTE = '[CLike EvalRunner] Shared files changed';

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
      ...(c.blocked ? { blocked: true } : {}),
      ...(output.startsWith(SHARED_FILES_NOTE) ? { sharedFiles: true } : {}),
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

// The eval sandbox ran out of processes, threads, memory or disk (spawn EAGAIN, pthread_create):
// every check fails with errors that look like code defects and are not. A repair would change
// correct code to chase them, so the loop stops and says how to recover.
const SANDBOX_EXHAUSTED_STOP =
  'the eval sandbox ran out of resources (processes, threads, memory or disk): the failures are not defects of the code, ' +
  'nothing to repair. Restart the sandbox (`podman restart docker_eval-sandbox_1`, or docker/rebuild.sh) and run again.';

// Checks stopped on native programs the sandbox still lacks (not installed: declined, no answer,
// or not installable): a repair cannot add a program, so the loop stops and says how.
function missingTools(report) {
  const names = Array.isArray(report?.missing_tools) ? report.missing_tools.filter(Boolean) : [];
  if (!names.length) return null;
  return `the eval sandbox lacks ${names.join(', ')}: the code is not at fault, nothing to repair. ` +
    `Install ${names.length > 1 ? 'them' : 'it'} with \`/tools add ${names.join(' ')}\` (or answer Install when asked) and run again.`;
}

// CLike could not compose the eval workspace (copying the KIT and the canonical tree): no check
// ran, so there is nothing for a repair to see; the cause is outside the code.
function workspaceNotPrepared(report) {
  const c = (Array.isArray(report?.cases) ? report.cases : []).find((x) => x && !x.passed && x.name === 'env::prepare-workspace');
  if (!c) return null;
  return 'CLike could not prepare the eval workspace (no check ran, nothing to repair): ' +
    `${String(c.stderr || '').split('\n')[0].slice(0, 400)}. Check that nothing is writing into runs/kit/ and run again.`;
}

function sandboxExhausted(report) {
  const code = String(report?.reason_code || '');
  return report?.sandbox_exhausted === true || code === 'EVAL_SANDBOX_EXHAUSTED' || code === 'GATE_BLOCKED_SANDBOX_EXHAUSTED';
}

/**
 * Decide the next step after an eval of an auto-eval run.
 * state: { cycle, maxCycles, hint, lastSignature }
 * → { action: 'pass' | 'stop' | 'repair', reason, failures?, signature? }
 */
function nextAutoEvalStep(state, report) {
  if (evalPassed(report)) return { action: 'pass', reason: `eval PASS after ${state.cycle} repair cycle(s)` };
  if (sandboxExhausted(report)) return { action: 'stop', reason: SANDBOX_EXHAUSTED_STOP };
  const tools = missingTools(report);
  if (tools) return { action: 'stop', reason: tools };
  const workspace = workspaceNotPrepared(report);
  if (workspace) return { action: 'stop', reason: workspace };
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
    return { action: 'stop', reason: acceptanceChangedReason(report) };
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
        out.push({ phase, ts, inputs: rep.inputs_fingerprint || null, cases: Array.isArray(rep.cases) ? rep.cases : [] });
      } catch { /* unreadable report: ignore */ }
    }
  }
  return out.sort((a, b) => a.ts - b.ts);
}

// CLike's promotion leftovers and generated files: never inputs of an eval.
const SCRATCH_INPUT_RE = /(\.pyc|\.pyo|\.log)$|^\.DS_Store$|\.(incoming|conflict)-REQ-|\.bak-\d/;

/**
 * Fingerprint of what an eval/gate of the REQ runs on: the canonical roots and the KIT
 * (src/, test/, tests/, plus the KIT's ci/). Stored in each report, so a check that passed
 * earlier is called nondeterministic only when it passed on the same code.
 */
function inputsFingerprint(workspaceRoot, reqId) {
  const hash = crypto.createHash('sha256');
  // repository-root deliverables (scripts/, deploy/, root manifests) are inputs too
  const policy = rootPolicy(workspaceRoot);
  const roots = [
    ...['src', 'test', 'tests'].map((r) => r),
    ...policy.folders,
    ...['src', 'test', 'tests', 'ci', KIT_ROOT_DIR].map((r) => `runs/kit/${reqId}/${r}`),
  ];
  const walk = (rel) => {
    let entries = [];
    try { entries = fs.readdirSync(path.join(workspaceRoot, rel), { withFileTypes: true }); } catch { return; }
    for (const e of entries.sort((a, b) => (a.name < b.name ? -1 : a.name > b.name ? 1 : 0))) {
      const child = `${rel}/${e.name}`;
      if (e.isDirectory()) {
        if (!SKIPPED_DIRS.has(e.name) && !e.name.endsWith('.egg-info')) walk(child);
      } else if (e.isFile() && !SCRATCH_INPUT_RE.test(e.name)) {
        try { hash.update(`${child}\0`).update(fs.readFileSync(path.join(workspaceRoot, child))).update('\0'); } catch { /* vanished */ }
      }
    }
  };
  roots.forEach(walk);
  for (const name of policy.files) {
    try { hash.update(`${name}\0`).update(fs.readFileSync(path.join(workspaceRoot, name))).update('\0'); } catch { /* absent */ }
  }
  return hash.digest('hex').slice(0, 16);
}

/**
 * Mark the failures that passed in earlier runs of the same REQ, derived from CLike's own
 * reports (no developer hint needed). With `currentInputs` (the inputsFingerprint of this run):
 * - passed earlier on the same code → nondeterministic: the repair makes the code deterministic
 *   instead of chasing the asserted value;
 * - passed earlier only on other code → not flaky: the failure comes from what changed since.
 * Reports without a fingerprint count as other code. A test-level match is preferred.
 */
function annotateIntermittentFailures(failures, earlierReports, currentInputs) {
  return (failures || []).map((f) => {
    // An environment-blocked check failed for the sandbox, not for the code: no history note.
    if (f.blocked) return f;
    const runs = (earlierReports || [])
      .map((r) => ({ inputs: r.inputs, c: (r.cases || []).find((c) => c && c.name === f.name) }))
      .filter((r) => r.c);
    const passedRuns = runs.filter((r) => r.c.passed);
    if (!passedRuns.length) return f;
    const tests = failedTestIds(f.output);
    const subjectOf = (passed) => {
      const passedTests = tests.filter((t) =>
        passed.some((r) => new RegExp(`${t.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}\\b[^\\n]*PASSED`).test(String(r.c.stdout || '')))
      );
      return passedTests.length ? passedTests.join(', ') : `the check ${f.name}`;
    };
    if (currentInputs) {
      const same = runs.filter((r) => r.inputs === currentInputs);
      const passedSame = same.filter((r) => r.c.passed);
      if (!passedSame.length) {
        const note =
          `CLike note: ${subjectOf(passedRuns)} passed in ${passedRuns.length} earlier eval/gate run(s) of this REQ, ` +
          'but src/, test/ or the KIT changed since then: the failure most likely comes from that change. ' +
          'Read the error and fix its cause; it is not a nondeterministic failure.';
        return { ...f, changedSince: true, output: `${note}\n\n${f.output || ''}` };
      }
      const note =
        `CLike note: ${subjectOf(passedSame)} passed in ${passedSame.length} of ${same.length} earlier eval/gate run(s) of this REQ ` +
        'on the same code (src/, test/ and the KIT unchanged), so the failure is nondeterministic (order of rows or jobs by ' +
        'random ids, timing, concurrency, unseeded randomness): make the behavior deterministic in src/, do not adjust the asserted value.';
      return { ...f, intermittent: true, output: `${note}\n\n${f.output || ''}` };
    }
    const note =
      `CLike note: ${subjectOf(passedRuns)} passed in ${passedRuns.length} of ${runs.length} earlier eval/gate run(s) of this REQ. ` +
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
  const notes = (failures || []).filter((f) => f.intermittent || f.changedSince || f.sharedFiles);
  if (notes.length) {
    for (const f of notes) {
      const note = String(f.output || '').split('\n\n')[0].split('\n');
      // shared files: the explanation and the replaced files, not their diffs (in the report)
      const shown = f.sharedFiles ? [note[0], ...note.slice(1).filter((l) => l.startsWith('- '))] : note;
      lines.push(`- \`${f.name}\`: ${shown.join('\n  ')}`);
    }
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
 * Stop reason for a changed acceptance surface: which REQ (the candidate or a promoted REQ its
 * regression runs), which files, and the two ways out.
 */
function acceptanceChangedReason(report) {
  const req = String(report?.integrity_req_id || report?.req_id || '').trim() || 'the REQ';
  const anomalies = Array.isArray(report?.integrity?.anomalies) ? report.integrity.anomalies : [];
  const files = anomalies.slice(0, 5).map((a) => `${a.path} ${a.kind}${a.details?.length ? ` (${[].concat(a.details).join('; ')})` : ''}`);
  const weakening = anomalies.some((a) => a.kind !== 'modified');
  return `the acceptance surface (test/ or ci/) of ${req} changed after the lock` +
    (files.length ? `: ${files.join(', ')}` : '') +
    (weakening
      ? `; restore it or re-run /kit ${req} to re-baseline`
      : `; if you changed it on purpose run /eval ${req} --accept "<why>" (audited), otherwise restore it`);
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
  if (sandboxExhausted(report)) return { action: 'stop', reason: SANDBOX_EXHAUSTED_STOP };
  const tools = missingTools(report);
  if (tools) return { action: 'stop', reason: tools };
  const workspace = workspaceNotPrepared(report);
  if (workspace) return { action: 'stop', reason: workspace };
  if (reasonCode === 'GATE_MANUAL_OVERRIDE') return { action: 'stop', reason: 'manual gate override: nothing to repair' };
  if (reasonCode === 'GATE_BLOCKED_ACCEPTANCE_TAMPERED') {
    return { action: 'stop', reason: acceptanceChangedReason(report) };
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

/**
 * A manual `/kit <REQ> --repair`: the same repair request as auto-eval, from the latest eval or
 * gate report of the REQ, so the cloud model receives the failures and the candidate files (a
 * local agent reads the reports itself). null when there is no failing report.
 */
function manualRepairRequest(workspaceRoot, reqId, hint = '') {
  const reports = readEarlierReports(workspaceRoot, reqId);
  const latest = reports[reports.length - 1];
  if (!latest) return null;
  const failures = collectRepairFailures({ cases: latest.cases });
  if (!failures.length) return null;
  return { cycle: 1, max_cycles: 1, failures, files: collectRepairFiles(workspaceRoot, reqId), hint: String(hint || ''), source: `${latest.phase} report ${latest.ts}` };
}

module.exports = {
  manualRepairRequest,
  acceptanceChanges,
  annotateIntermittentFailures,
  inputsFingerprint,
  readEarlierReports,
  collectRepairFailures,
  collectRepairFiles,
  evalPassed,
  missingTools,
  sandboxExhausted,
  workspaceNotPrepared,
  failureSignature,
  nextAutoEvalStep,
  nextAutoGateStep,
  repairNotesMarkdown,
  restoreAcceptanceFiles,
  snapshotAcceptanceSurface,
  writeRepairNotes,
};
