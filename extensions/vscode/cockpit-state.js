'use strict';
// The cockpit layout of the chat (clike.chat.theme = cockpit): the project state its side panel
// shows, read from what the repository holds (plan.json, the Harper documents, the eval and gate
// reports). No VS Code API: unit-tested.

const fs = require('fs');
const path = require('path');
const { nextActionFromPlan } = require('./extension-mcp');
const { resumeStep } = require('./autopilot');
const { inputsFingerprint } = require('./auto-eval');

const PHASES = ['idea', 'spec', 'plan', 'kit', 'finalize'];
const PASSING = new Set(['PASS', 'PASS_WITH_WARNINGS']);
// what the cockpit run card shows for each Harper command
const RUN_LABELS = {
  idea: 'IDEA', spec: 'SPEC', plan: 'PLAN', extend: 'EXTEND', kit: 'KIT', eval: 'EVAL', gate: 'GATE', finalize: 'FINALIZE',
};

const upper = (v) => String(v || '').trim().toUpperCase();
const status = (r) => String(r?.status || 'open').trim().toLowerCase();
const exists = (root, rel) => fs.existsSync(path.join(root, ...rel.split('/')));

function readJson(file) {
  try { return JSON.parse(fs.readFileSync(file, 'utf8')); } catch { return null; }
}

/** Report files of a REQ for a phase (runs/<phase>/<REQ>/report_<REQ>_<ts>.json), newest first. */
function reportFiles(root, phase, reqId) {
  const dir = path.join(root, 'runs', phase, reqId);
  let names = [];
  try { names = fs.readdirSync(dir).filter((n) => /^report_.*_\d+\.json$/.test(n)); } catch { return []; }
  return names
    .map((name) => ({ file: path.join(dir, name), ts: Number(name.match(/_(\d+)\.json$/)[1]) }))
    .sort((a, b) => b.ts - a.ts);
}

/** Counts of a report: the fields when present, else the summary line (passed=…, failed=…, warnings=…). */
function reportCounts(rep) {
  const summary = String(rep?.summary || '');
  const fromSummary = (key) => {
    const m = summary.match(new RegExp(`${key}=(\\d+)`));
    return m ? Number(m[1]) : null;
  };
  const num = (v) => (Number.isFinite(Number(v)) && typeof v !== 'boolean' ? Number(v) : null);
  const failed = Array.isArray(rep?.failed) ? rep.failed.length : num(rep?.failed);
  return {
    passed: num(rep?.passed_count) ?? fromSummary('passed') ?? 0,
    failed: failed ?? fromSummary('failed') ?? 0,
    warnings: num(rep?.warning_count) ?? fromSummary('warnings') ?? 0,
    blocked: num(rep?.blocked_count) ?? fromSummary('blocked') ?? 0,
  };
}

function reportSummary(phase, reqId, entry) {
  const rep = readJson(entry.file);
  if (!rep) return null;
  return {
    phase, req_id: reqId, ts: entry.ts, status: upper(rep.status || (rep.passed === true ? 'PASS' : 'FAIL')),
    inputs: rep.inputs_fingerprint || null, ...reportCounts(rep),
  };
}

/** The releases of the project (docs/inputs/vN), oldest first. */
function releases(root) {
  let names = [];
  try { names = fs.readdirSync(path.join(root, 'docs', 'inputs')); } catch { return []; }
  return names.map((n) => (n.match(/^v(\d+)$/) || [])[1]).filter(Boolean).map(Number).sort((a, b) => a - b).map((n) => `v${n}`);
}

/** The highest docs/inputs/vN of the project (the release in progress), or ''. */
function currentRelease(root) {
  return releases(root).pop() || '';
}

/** Phase pills: done, active (the first one not done) or todo. */
function phaseStates(root, reqs) {
  const total = reqs.length;
  const done = reqs.filter((r) => ['done', 'deferred'].includes(status(r))).length;
  const doneOf = {
    idea: exists(root, 'docs/harper/IDEA.md'),
    spec: exists(root, 'docs/harper/SPEC.md'),
    plan: total > 0,
    kit: total > 0 && done === total,
    // a FINALIZE_REPORT of an earlier release does not finalize the REQs added since
    finalize: total > 0 && done === total && exists(root, 'docs/harper/FINALIZE_REPORT.md'),
  };
  let activeSet = false;
  return PHASES.map((id) => {
    let state = doneOf[id] ? 'done' : 'todo';
    if (state === 'todo' && !activeSet) { state = 'active'; activeSet = true; }
    return { id, label: RUN_LABELS[id] || upper(id), state };
  });
}

/**
 * The cockpit state of a Harper project at `root`: release progress, phases, REQs with what each
 * waits for, the next action (same rules as /autopilot), the last eval or gate.
 * `opts.fingerprint(reqId)` overrides the inputs fingerprint (tests).
 */
function buildCockpitState(root, opts = {}) {
  const plan = readJson(path.join(root, 'docs', 'harper', 'plan.json'));
  const reqs = (Array.isArray(plan?.reqs) ? plan.reqs : []).filter((r) => r && r.id);
  const byId = new Map(reqs.map((r) => [upper(r.id), r]));
  const fingerprint = opts.fingerprint || ((reqId) => inputsFingerprint(root, reqId));
  const lastOf = (phase, reqId) => {
    const [entry] = reportFiles(root, phase, reqId);
    return entry ? reportSummary(phase, reqId, entry) : null;
  };
  const counts = { total: reqs.length, done: 0, in_progress: 0, open: 0, deferred: 0 };
  let lastRun = null;
  const rows = reqs.map((r) => {
    const id = upper(r.id);
    const st = status(r);
    counts[st] = (counts[st] || 0) + 1;
    const evalRep = lastOf('eval', id);
    const gateRep = lastOf('gate', id);
    for (const rep of [evalRep, gateRep]) if (rep && (!lastRun || rep.ts > lastRun.ts)) lastRun = rep;
    const waiting = (Array.isArray(r.dependsOn) ? r.dependsOn : []).map(upper)
      .filter((d) => d && status(byId.get(d) || {}) !== 'done');
    let note;
    if (st === 'done') note = gateRep && PASSING.has(gateRep.status) ? 'gate PASS' : 'done';
    else if (st === 'deferred') note = 'deferred';
    else if (st === 'in_progress') {
      const step = resumeStep({
        hasKit: exists(root, `runs/kit/${id}/ci/LTC.json`),
        lastEval: evalRep ? { status: evalRep.status, inputs: evalRep.inputs } : null,
        fingerprint: evalRep && PASSING.has(evalRep.status) ? fingerprint(id) : '',
      });
      note = `next: /${step}`;
    } else note = waiting.length ? `waits ${waiting[0]}${waiting.length > 1 ? ` +${waiting.length - 1}` : ''}` : 'ready';
    return {
      id, title: String(r.title || ''), status: st, note, waiting, has_kit: exists(root, `runs/kit/${id}/ci/LTC.json`),
      last_eval: evalRep ? { status: evalRep.status, failed: evalRep.failed } : null,
    };
  });

  let next = null;
  if (reqs.length) {
    const action = nextActionFromPlan(reqs);
    if (action.action === 'run_req') {
      const row = rows.find((x) => x.id === action.req_id);
      const step = row && row.status === 'in_progress' ? row.note.replace(/^next: \//, '') : 'kit';
      const command = step === 'eval' ? `/eval ${action.req_id} --fix` : `/${step} ${action.req_id}`;
      next = { command, message: action.message };
    } else if (action.action === 'finalize_only') {
      next = { command: exists(root, 'docs/harper/FINALIZE_REPORT.md') ? '' : '/finalize', message: action.message };
    } else {
      next = { command: '', message: action.message };
    }
  } else if (!exists(root, 'docs/harper/IDEA.md')) {
    next = { command: '/idea', message: 'No IDEA yet: describe the product (attach your documents) and run /idea.' };
  } else if (!exists(root, 'docs/harper/SPEC.md')) {
    next = { command: '/spec', message: 'IDEA is ready: generate the SPEC.' };
  } else {
    next = { command: '/plan', message: 'SPEC is ready: generate the PLAN.' };
  }

  return {
    harper: exists(root, 'docs/harper'),
    project: String(plan?.project || path.basename(root)),
    release: currentRelease(root),
    releases: releases(root),
    counts,
    progress_pct: counts.total ? Math.round((counts.done / counts.total) * 100) : 0,
    phases: phaseStates(root, reqs),
    reqs: rows,
    next,
    last_run: lastRun,
  };
}

module.exports = { buildCockpitState, reportCounts, phaseStates, currentRelease, releases, RUN_LABELS };
