'use strict';
// /autopilot: the REQs of the plan one after the other, unattended — /kit, /eval --fix, /gate, the
// same governed chat flow a developer runs (same executor: cloud model, Codex or Claude Code; same
// lock, gate and audit). No model decides the loop: these rules do. A REQ that needs the developer
// is parked with its reason and the loop goes on with the REQs that do not depend on it.

const STEPS = ['kit', 'eval', 'gate'];
// The run's state in the project (not committed): what a restart resumes from.
const STATE_REL = 'runs/autopilot/state.json';
const REPORT_REL = 'runs/autopilot/report.md';

const status = (r) => String(r?.status || 'open').trim().toLowerCase();
const upper = (v) => String(v || '').trim().toUpperCase();

/**
 * Where an in-progress REQ resumes, from what the repository holds: no KIT → kit; the last eval
 * passed on exactly the current inputs (same fingerprint) → gate; otherwise → eval.
 */
function resumeStep({ hasKit, lastEval, fingerprint }) {
  if (!hasKit) return 'kit';
  const passed = lastEval && ['PASS', 'PASS_WITH_WARNINGS'].includes(String(lastEval.status || '').toUpperCase());
  return passed && lastEval.inputs && lastEval.inputs === fingerprint ? 'gate' : 'eval';
}

/**
 * The next REQ to run and its first step, skipping the parked ones: an in-progress REQ first
 * (resumed at stepOf(reqId), see resumeStep), else the first open REQ whose dependencies are done.
 */
function nextAutopilotReq(reqs, parked = new Set(), stepOf = () => 'kit') {
  const list = (Array.isArray(reqs) ? reqs : []).filter((r) => r && r.id);
  const byId = new Map(list.map((r) => [upper(r.id), r]));
  const deps = (r) => (Array.isArray(r.dependsOn) ? r.dependsOn : []).map(upper).filter(Boolean);
  const isParked = (id) => parked.has(upper(id));
  const ready = (r) => deps(r).every((d) => status(byId.get(d) || {}) === 'done');
  const candidates = [
    ...list.filter((r) => status(r) === 'in_progress'),
    ...list.filter((r) => status(r) === 'open'),
  ].filter((r) => !isParked(r.id));
  const pick = candidates.find(ready);
  if (pick) {
    const reqId = upper(pick.id);
    const step = status(pick) === 'in_progress' ? stepOf(reqId) : 'kit';
    return { action: 'run', req_id: reqId, step };
  }
  const pending = list.filter((r) => status(r) !== 'done' && status(r) !== 'deferred');
  if (!pending.length) return { action: 'finalize_only' };
  return {
    action: 'blocked',
    waiting: pending.map((r) => ({
      req_id: upper(r.id),
      parked: isParked(r.id),
      waiting_for: deps(r).filter((d) => status(byId.get(d) || {}) !== 'done'),
    })),
  };
}

// A provider out of quota or rate limited: wait and retry the same step, do not park the REQ.
const QUOTA_RE = /\b429\b|rate[ _-]?limit|too many requests|quota|usage limit|insufficient_quota|limit reached|try again (?:later|in)|at capacity|overloaded/i;

function isQuotaFailure(text) {
  return QUOTA_RE.test(String(text || ''));
}

// CLike's own services not answering (restarting, sandbox out of resources): wait, do not park.
const SERVICE_RE = /ECONNREFUSED|ECONNRESET|ETIMEDOUT|fetch failed|socket hang up|\b50[234]\b|Service Unavailable|Bad Gateway|EVAL_SANDBOX_EXHAUSTED/i;

/** 'quota' | 'service' when the failure is transient (wait and retry the step), else null. */
function transientFailure(text) {
  if (isQuotaFailure(text)) return 'quota';
  return SERVICE_RE.test(String(text || '')) ? 'service' : null;
}

/**
 * Parked REQs of an earlier run that stay parked: those whose inputs did not change since (nobody
 * fixed them yet). A REQ the developer changed is released and retried.
 */
function keptParked(previous, fingerprintOf) {
  const kept = {};
  const released = [];
  for (const [reqId, info] of Object.entries(previous || {})) {
    if (info && info.fingerprint && info.fingerprint === fingerprintOf(reqId)) kept[reqId] = info;
    else released.push(reqId);
  }
  return { kept, released };
}

/** Did the step succeed? msg is the chat message after the handler ran (its __result/__report). */
function stepOutcome(step, msg) {
  const report = msg?.__report || {};
  if (step === 'kit') {
    return msg?.__result === 'ok' ? { ok: true } : { ok: false, reason: 'the KIT did not complete' };
  }
  if (step === 'eval') {
    const auto = report.auto_eval;
    if (auto && auto.outcome === 'pass') return { ok: true, cycles: auto.cycles };
    if (auto) return { ok: false, reason: `eval --fix ${auto.outcome}: ${auto.reason}`, cycles: auto.cycles };
    return { ok: false, reason: report.status ? `eval ${report.status}` : 'the eval did not run' };
  }
  // as the promotion decides it: verdict pass and status PASS / PASS_WITH_WARNINGS
  const verdict = String(report.gate || '').toUpperCase();
  const gateStatus = String(report.status || '').toUpperCase();
  if (verdict !== 'PASS' || !['PASS', 'PASS_WITH_WARNINGS'].includes(gateStatus)) {
    return { ok: false, reason: verdict || gateStatus ? `gate ${verdict || '?'} (${gateStatus || '?'})` : 'the gate did not run' };
  }
  if (report.promotion && report.promotion.promoted === false) {
    return { ok: false, reason: `gate PASS, promotion not done: ${report.promotion.summary || 'see the promotion report'}` };
  }
  return { ok: true, review_required: !!report.review_required };
}

/**
 * The chat execution state for an executor chosen for the run (cloud | codex | claude), or null to
 * keep the configured one. Kit, repairs and eval pre-passes read it, as when set in the chat.
 */
function executorState(executor) {
  const raw = String(executor || '').trim().toLowerCase();
  if (!raw) return null;
  if (raw === 'cloud') return { executionPreference: 'cloud_only' };
  if (raw === 'codex') return { executionPreference: 'local_agent_only', localAgentExecutor: 'gpt_codex' };
  if (raw === 'claude') return { executionPreference: 'local_agent_only', localAgentExecutor: 'claude_code' };
  throw new Error(`executor must be cloud, codex or claude (got ${executor})`);
}

/** Methodology fields of a step's message: BMAD developer for the KIT, QA (advisory) for the eval; the gate is CLike's. */
function methodologyFields(methodology, step) {
  const raw = String(methodology || '').trim().toLowerCase();
  if (!raw) return {};
  if (raw !== 'bmad') throw new Error(`methodology must be bmad (got ${methodology})`);
  if (step === 'kit') return { methodology: 'bmad', agent: 'developer' };
  if (step === 'eval') return { methodology: 'bmad', agent: 'qa' };
  return {};
}

function duration(ms) {
  const min = Math.round(Math.max(0, ms) / 60000);
  return min >= 60 ? `${Math.floor(min / 60)} h ${min % 60} min` : `${min} min`;
}

/** The report the developer reads afterwards (runs/autopilot/report.md, not committed). */
function autopilotReportMarkdown(run) {
  const lines = [
    '# Autopilot report', '',
    `Started ${new Date(run.startedAt).toISOString()}, ${run.endedAt ? `ended ${new Date(run.endedAt).toISOString()}` : 'running'}` +
      ` (${duration((run.endedAt || Date.now()) - run.startedAt)}). Executor: ${run.executor || 'as configured'}; methodology: ${run.methodology || 'none'}.`,
    ...(run.resumed ? ['', 'Resumed an interrupted run (same options; each REQ from where the repository says it is).'] : []),
    '', `Outcome: ${run.outcome || 'running'}`, '',
    '## Promoted', '',
  ];
  const promoted = run.reqs.filter((r) => r.result === 'promoted');
  lines.push(...(promoted.length
    ? ['| REQ | Repair cycles | Duration | Review |', '|---|---|---|---|',
      ...promoted.map((r) => `| ${r.req_id} | ${r.cycles ?? 0} | ${duration(r.ms)} | ${r.review_required ? 'review the test fixes (gate REVIEW)' : '—'} |`)]
    : ['None.']));
  lines.push('', '## Parked (need you)', '');
  const parked = run.reqs.filter((r) => r.result === 'parked');
  lines.push(...(parked.length
    ? ['| REQ | Step | Why | Last messages |', '|---|---|---|---|',
      ...parked.map((r) => `| ${r.req_id} | ${r.step} | ${String(r.reason || '').replace(/\|/g, '\\|')} | ${(r.messages || []).slice(-2).join(' / ').replace(/\|/g, '\\|').slice(0, 400)} |`)]
    : ['None.']));
  if (run.released && run.released.length) {
    lines.push('', '## Retried', '', `Parked earlier and changed since: ${run.released.join(', ')}.`);
  }
  if (run.waits && run.waits.length) {
    lines.push('', '## Waits (quota, services)', '', ...run.waits.map((w) => `- ${w.req_id} ${w.step}: waited ${w.minutes} min (${w.reason})`));
  }
  lines.push('', '## Next', '', run.next || '—', '');
  return lines.join('\n');
}

module.exports = {
  STEPS, STATE_REL, REPORT_REL, resumeStep, nextAutopilotReq, isQuotaFailure, transientFailure, keptParked, stepOutcome,
  executorState, methodologyFields, autopilotReportMarkdown,
};
