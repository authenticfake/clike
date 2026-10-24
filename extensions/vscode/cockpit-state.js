'use strict';
// The cockpit layout of the chat (clike.chat.theme = cockpit): the project state its side panel
// shows, read from what the repository holds (plan.json, the Harper documents, the eval and gate
// reports). No VS Code API: unit-tested.

const fs = require('fs');
const path = require('path');
const { nextActionFromPlan } = require('./extension-mcp');
const { resumeStep } = require('./autopilot');
const { inputsFingerprint } = require('./auto-eval');
const { detectRelease } = require('./release-extend');

const PHASES = ['idea', 'spec', 'plan', 'kit', 'finalize'];
// what /init writes: a Harper document equal to its template (placeholders aside) is not done yet
const INIT_TEMPLATES = path.join(__dirname, 'templates', 'harper-init', 'docs', 'harper');
// BMAD phases with more than one role, and what each role writes (the mandatory companion outputs
// of the methodology's artifact_policy): a role ran when one of its outputs is there.
const BMAD_ROLE_OUTPUTS = {
  spec: {
    pm: ['docs/harper/bmad/spec/PRD.md', 'docs/harper/bmad/spec/EPICS.md', 'docs/harper/bmad/spec/ACCEPTANCE_MODEL.md', 'docs/harper/bmad/spec/SCOPE_DECISIONS.md'],
    ux: ['docs/harper/ux/DESIGN.md', 'docs/harper/ux/EXPERIENCE.md', 'docs/harper/ux/USER_JOURNEYS.md', 'docs/harper/ux/INTERACTION_STATES.md', 'docs/harper/ux/SPEC_UX_APPENDIX.md'],
  },
  plan: {
    architect: ['docs/harper/bmad/architecture/ARCHITECTURE.md', 'docs/harper/bmad/architecture/DECISIONS.md', 'docs/harper/bmad/architecture/INTEGRATION_BOUNDARIES.md', 'docs/harper/bmad/architecture/RISKS.md'],
    pm: ['docs/harper/bmad/plan/STORIES.md', 'docs/harper/bmad/plan/STORY_MAP.md', 'docs/harper/bmad/plan/IMPLEMENTATION_READINESS.md'],
  },
};

/** The next release /idea --extend would build, when its inputs are there; null otherwise. */
function nextRelease(root) {
  let rel;
  try { rel = detectRelease(root); } catch { return null; }
  const target = Number(String(rel.release).slice(1));
  if (!rel.inputs.length || !rel.folders.includes(rel.release)) return null;
  const planned = Math.max(0, ...rel.folders.map((f) => Number(f.slice(1))).filter((n) => n < target));
  return { release: rel.release, message: `Release ${rel.release}: ${rel.inputs.length} input file(s) in docs/inputs/${rel.release}/` +
    ` — extend the delivered project${planned ? ` (baseline v${planned})` : ''}.` };
}

/** The BMAD roles of a phase that have not run yet. */
function missingRoles(root, phase) {
  return Object.entries(BMAD_ROLE_OUTPUTS[phase] || {})
    .filter(([, outputs]) => !outputs.some((rel) => exists(root, rel)))
    .map(([role]) => role);
}
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

/** Whether a phase command produced output: runs/<phase>/ holds files (it records every run). */
function phaseRan(root, phase) {
  const walk = (dir, depth) => {
    let entries = [];
    try { entries = fs.readdirSync(dir, { withFileTypes: true }); } catch { return false; }
    return entries.some((e) => (e.isFile() && !e.name.startsWith('.'))
      || (e.isDirectory() && depth < 3 && walk(path.join(dir, e.name), depth + 1)));
  };
  return walk(path.join(root, 'runs', phase), 0);
}

/** Whether `text` is still the /init template `template` (its ${…} placeholders match anything). */
function isInitTemplate(text, template) {
  const norm = (t) => String(t || '').replace(/\r\n/g, '\n').trim().replace(/[ \t]+$/gm, '');
  const parts = norm(template).split(/\$\{[^}]*\}/);
  const pattern = parts.map((p) => p.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')).join('[\\s\\S]*?');
  try { return new RegExp(`^${pattern}$`).test(norm(text)); } catch { return false; }
}

/** IDEA / SPEC done: its command ran, or the document is no longer what /init wrote. */
function documentDone(root, phase, file, templatesDir) {
  if (phaseRan(root, phase)) return true;
  let text;
  try { text = fs.readFileSync(path.join(root, 'docs', 'harper', file), 'utf8'); } catch { return false; }
  let template = null;
  try { template = fs.readFileSync(path.join(templatesDir, file), 'utf8'); } catch { /* no template known */ }
  return template === null ? text.trim().length > 0 : !isInitTemplate(text, template);
}

/** Phase pills: done, active (the first one not done) or todo. */
function phaseStates(root, reqs, templatesDir = INIT_TEMPLATES) {
  const total = reqs.length;
  const done = reqs.filter((r) => ['done', 'deferred'].includes(status(r))).length;
  const doneOf = {
    idea: documentDone(root, 'idea', 'IDEA.md', templatesDir),
    spec: documentDone(root, 'spec', 'SPEC.md', templatesDir),
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

  const phases = phaseStates(root, reqs, opts.templatesDir || INIT_TEMPLATES);
  let next = null;
  let extendAlternative = null;
  if (reqs.length) {
    const action = nextActionFromPlan(reqs);
    if (action.action === 'run_req') {
      const row = rows.find((x) => x.id === action.req_id);
      const step = row && row.status === 'in_progress' ? row.note.replace(/^next: \//, '') : 'kit';
      const command = step === 'eval' ? `/eval ${action.req_id} --fix` : `/${step} ${action.req_id}`;
      next = { command, message: action.message };
    } else if (action.action === 'finalize_only') {
      // every REQ is done: /finalize, then the next release when its inputs are there (the same
      // detection /idea --extend runs: a docs/inputs/vN above the plan's release, with files)
      const finalized = exists(root, 'docs/harper/FINALIZE_REPORT.md');
      const rel = nextRelease(root);
      if (!finalized) next = { command: '/finalize', message: action.message };
      else if (rel) next = { command: '/idea --extend', message: rel.message };
      else {
        const target = detectRelease(root).release;
        next = { command: '', message: `Delivered. For the next release put its requirements in docs/inputs/${target}/ ` +
          `(background in docs/reference/${target}/): /idea --extend becomes the next action.` };
      }
      if (!finalized && rel) extendAlternative = { command: '/idea --extend', message: rel.message };
    } else {
      next = { command: '', message: action.message };
    }
  } else if (!exists(root, 'docs/harper')) {
    next = { command: '/init <name>', message: 'No Harper project in this workspace: /init <name> creates it (existing files are kept with --force).' };
  } else if (!phases[0] || phases[0].state !== 'done') {
    next = { command: '/idea', message: 'IDEA.md is still the /init template: describe the product (put your documents in docs/inputs/ or attach them) and run /idea.' };
  } else if (phases[1].state !== 'done') {
    next = { command: '/spec', message: 'IDEA is ready: generate the SPEC (with its Use Cases).' };
  } else {
    next = { command: '/plan', message: 'SPEC is ready: generate the PLAN (the REQs).' };
  }

  // With BMAD, a phase whose roles have not all run stays open next to the next step (SPEC by pm
  // and ux, PLAN by architect and pm) until the KIT starts: the developer chooses.
  const alternatives = extendAlternative ? [extendAlternative] : [];
  const kitStarted = counts.done > 0 || counts.in_progress > 0;
  if (opts.methodology === 'bmad' && next && !kitStarted) {
    const doneOf = Object.fromEntries(phases.map((ph) => [ph.id, ph.state === 'done']));
    for (const phase of ['spec', 'plan']) {
      if (!doneOf[phase]) continue;
      for (const role of missingRoles(root, phase)) {
        const command = `/${phase} --methodology bmad --agent ${role}`;
        if (command !== next.command) alternatives.push({ command, message: `${phase.toUpperCase()} by the ${role} role has not run yet` });
      }
    }
  }

  return {
    harper: exists(root, 'docs/harper'),
    project: String(plan?.project || path.basename(root)),
    release: currentRelease(root),
    releases: releases(root),
    counts,
    progress_pct: counts.total ? Math.round((counts.done / counts.total) * 100) : 0,
    phases,
    reqs: rows,
    next,
    alternatives,
    last_run: lastRun,
  };
}

module.exports = { buildCockpitState, reportCounts, phaseStates, isInitTemplate, currentRelease, releases, RUN_LABELS };
