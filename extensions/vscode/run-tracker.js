'use strict';
// The command running in the chat as the run card and the status bar show it: the steps it goes
// through (KIT, EVAL, REPAIR, GATE…, nested handler calls of the auto-eval, auto-gate, finalize
// verification and autopilot), each with its outcome and duration, the cycle of a --fix loop, an
// estimate from the same step's earlier durations, what is happening now. Built from the same
// messages the chat handlers run; no VS Code API: unit-tested.

const PHASE_CMDS = new Set(['idea', 'spec', 'plan', 'extend', 'kit', 'finalize']);
const PASSING = new Set(['PASS', 'PASS_WITH_WARNINGS']);
const MAX_STEPS = 60;

const upper = (v) => String(v || '').trim().toUpperCase();
const reqOf = (msg) => upper(msg.targetReqId || (Array.isArray(msg.targets) ? msg.targets[0] : msg.targets) || msg.argument || '');

/** The step a chat message is, or null when it is not one the run card follows. */
function stepOf(msg) {
  if (!msg || typeof msg !== 'object') return null;
  if (msg.type === 'harperRun') {
    const cmd = String(msg.cmd || '').toLowerCase();
    if (!PHASE_CMDS.has(cmd)) return null;
    const req = cmd === 'kit' ? reqOf(msg) : '';
    if (msg.autoEvalRepair) return { kind: 'repair', label: `REPAIR ${msg.autoEvalRepair.cycle || ''}`.trim(), req, cycle: Number(msg.autoEvalRepair.cycle) || 0 };
    if (msg.finalizeRepair) return { kind: 'repair', label: `REPAIR ${msg.finalizeRepair.cycle || ''}`.trim(), req: 'SOLUTION', cycle: Number(msg.finalizeRepair.cycle) || 0 };
    if (msg.acceptanceStage) return { kind: 'kit', label: 'KIT tests', req };
    return { kind: cmd, label: cmd === 'extend' && msg.extendMode === 'cascade' ? 'EXTEND' : cmd.toUpperCase(), req };
  }
  if (msg.type === 'harperEDD') {
    const cmd = String(msg.cmd || '').toLowerCase();
    if (cmd !== 'eval' && cmd !== 'gate') return null;
    const cycle = msg.fix ? Number(msg.fix.cycle || 0) : 0;
    const n = cycle + 1;
    const targeted = Array.isArray(msg.regressionReqs) && msg.regressionReqs.length > 0;
    return { kind: cmd, label: `${cmd.toUpperCase()}${msg.fix ? ` ${n}` : ''}${targeted ? ' (targeted)' : ''}`, req: reqOf(msg), cycle, targeted };
  }
  if (msg.type === 'autopilot' && String(msg.action || 'start') === 'start') return { kind: 'autopilot', label: 'AUTOPILOT', req: '' };
  return null;
}

/** The command line the run card shows for the message that started the run. */
function titleOf(msg) {
  if (msg.rawCommand) return String(msg.rawCommand);
  const step = stepOf(msg) || {};
  if (msg.type === 'autopilot') {
    return ['/autopilot', msg.max ? String(msg.max) : '', msg.executor ? `--executor ${msg.executor}` : '', msg.methodology ? `--methodology ${msg.methodology}` : '']
      .filter(Boolean).join(' ');
  }
  const cmd = String(msg.cmd || step.kind || '').toLowerCase();
  const flags = [msg.fix ? '--fix' : '', msg.methodology ? `--methodology ${msg.methodology}` : '', msg.agent ? `--agent ${msg.agent}` : ''].filter(Boolean);
  return [`/${cmd}`, step.req, ...flags].filter(Boolean).join(' ');
}

/** ok | failed | cancelled | done: what the step's message carries when its handler returns. */
function outcomeOf(msg, step, { cancelled = false } = {}) {
  const result = String(msg.__result || '').toLowerCase();
  if (cancelled || result === 'cancelled') return 'cancelled';
  if (step.kind === 'eval' || step.kind === 'gate') {
    const status = upper(msg.__report && msg.__report.status);
    if (PASSING.has(status)) return 'ok';
    if (status) return 'failed';
    return result === 'failed' ? 'failed' : 'done';
  }
  if (result === 'ok') return 'ok';
  if (result === 'failed' || msg.__refused || step.errored) return 'failed';
  return 'done';
}

function countsOf(msg) {
  const r = msg.__report || {};
  const c = r.counts || null;
  if (!c) return null;
  return { passed: Number(c.passed) || 0, failed: Number(c.failed) || 0, warnings: Number(c.warnings) || 0 };
}

function createRunTracker({ now = Date.now, durations = {}, maxCycles = 2, extraCycles = 3 } = {}) {
  let run = null;
  let depth = 0;
  let seq = 0;
  const known = { ...durations };

  function etaOf(step) {
    return known[`${step.kind}:${step.req}`] || known[step.kind] || null;
  }

  function close(entry, msg, cancelled) {
    entry.state = outcomeOf(msg || {}, entry, { cancelled });
    entry.endedAt = now();
    entry.counts = countsOf(msg || {});
    if (entry.state !== 'cancelled') {
      const ms = entry.endedAt - entry.startedAt;
      known[`${entry.kind}:${entry.req}`] = ms;
      known[entry.kind] = ms;
    }
  }

  /** A handler starts on `msg`; returns the token to give back to end(). */
  function begin(msg, { executor = '' } = {}) {
    const step = stepOf(msg);
    depth += 1;
    const token = { depth, step: null, started: false };
    if (!step) return token;
    if (!run || run.ended) {
      if (depth !== 1) return token; // a nested message of a run the card does not follow
      seq += 1;
      run = {
        id: seq, title: titleOf(msg), kind: step.kind, req: step.req, executor, startedAt: now(), ended: null,
        fix: !!msg.fix, maxCycles: Number((msg.fix && msg.fix.maxCycles) || maxCycles), extraCycles,
        steps: [], live: '', liveAt: 0, evalProgress: null,
      };
      token.started = true;
    }
    if (step.kind === 'autopilot') return token;
    // A step started from inside another handler continues the loop of that handler (the
    // auto-eval's repair after its eval, the auto-eval after a KIT): the outer step's own work is
    // done and its outcome is on its message. The acceptance-first test stage is part of its KIT.
    if (!msg.acceptanceStage) {
      for (const open of run.steps) if (open.state === 'running') close(open, open.msg, false);
    }
    const entry = { id: run.steps.length + 1, ...step, state: 'running', startedAt: now(), endedAt: null, eta_ms: etaOf(step), counts: null };
    Object.defineProperty(entry, 'msg', { value: msg, enumerable: false });
    run.steps.push(entry);
    if (run.steps.length > MAX_STEPS) run.steps.splice(0, run.steps.length - MAX_STEPS);
    run.evalProgress = null;
    token.step = entry;
    return token;
  }

  /** The handler of `token` returned; `msg` carries its outcome (__result, __report). */
  function end(token, msg, { cancelled = false } = {}) {
    depth = Math.max(0, depth - 1);
    const entry = token && token.step;
    if (entry && entry.state === 'running') close(entry, msg, cancelled);
    if (run && !run.ended && depth === 0) {
      const last = run.steps[run.steps.length - 1];
      const anyCancelled = cancelled || run.steps.some((s) => s.state === 'cancelled');
      run.ended = { at: now(), outcome: anyCancelled ? 'cancelled' : last ? last.state : outcomeOf(msg || {}, { kind: run.kind }) };
      run.evalProgress = null;
      return true;
    }
    return false;
  }

  /** What is happening now (an echo of the handlers, a tool the agent uses). */
  function live(text) {
    if (!run || run.ended) return false;
    const t = String(text || '').split('\n')[0].trim().slice(0, 220);
    if (!t) return false;
    run.live = t;
    run.liveAt = now();
    if (/^⏹/.test(t)) {
      const cur = run.steps.find((s) => s.state === 'running');
      if (cur) cur.cancelRequested = true;
    }
    return true;
  }

  /** An error message while a step runs: without an explicit outcome the step failed. */
  function error(text) {
    const cur = run && !run.ended ? run.steps.filter((s) => s.state === 'running').pop() : null;
    if (cur) cur.errored = true;
    return live(text);
  }

  function evalProgress(p) {
    if (!run || run.ended) return false;
    const cur = run.steps.find((s) => s.state === 'running');
    if (!cur || (cur.kind !== 'eval' && cur.kind !== 'gate')) return false;
    run.evalProgress = p && p.state && p.state !== 'unknown' ? p : null;
    return true;
  }

  function current() {
    return run ? run.steps.filter((s) => s.state === 'running').pop() || null : null;
  }

  function snapshot(extra = {}) {
    if (!run) return null;
    const cur = current();
    const repairs = run.steps.filter((s) => s.kind === 'repair').length;
    return {
      ...extra,
      id: run.id, title: run.title, kind: run.kind, req: run.req, executor: run.executor,
      startedAt: run.startedAt, ended: run.ended, now: now(),
      fix: run.fix ? { cycle: repairs, maxCycles: run.maxCycles, extraCycles: run.extraCycles } : null,
      steps: run.steps.slice(-12).map((s) => ({
        id: s.id, kind: s.kind, label: s.label, req: s.req, state: s.state, startedAt: s.startedAt, endedAt: s.endedAt,
        eta_ms: s.eta_ms, counts: s.counts,
      })),
      current: cur ? { kind: cur.kind, label: cur.label, req: cur.req, startedAt: cur.startedAt, eta_ms: cur.eta_ms } : null,
      live: run.live, evalProgress: run.evalProgress,
    };
  }

  return {
    begin, end, live, error, evalProgress, snapshot, current,
    active: () => !!(run && !run.ended),
    durations: () => ({ ...known }),
  };
}

module.exports = { createRunTracker, stepOf, titleOf, outcomeOf };
