'use strict';
// The outcome of the last /finalize, written by CLike. A local agent writes FINALIZE_REPORT.md in the
// workspace before CLike accepts its result, so the report alone does not mean the finalize passed
// (test project: the orchestrator rejected the result, the cockpit showed FINALIZE done).

const fs = require('fs');
const path = require('path');

const OUTCOME_PATH = 'runs/finalize/LAST_OUTCOME.json';
const REPORT_PATH = 'docs/harper/FINALIZE_REPORT.md';

function writeFinalizeOutcome(root, status, reason = '', now = new Date()) {
  const file = path.join(root, ...OUTCOME_PATH.split('/'));
  fs.mkdirSync(path.dirname(file), { recursive: true });
  const outcome = { status, reason: String(reason || '').split('\n')[0].slice(0, 500), at: now.toISOString() };
  fs.writeFileSync(file, `${JSON.stringify(outcome, null, 2)}\n`);
  return outcome;
}

function readFinalizeOutcome(root) {
  try {
    const out = JSON.parse(fs.readFileSync(path.join(root, ...OUTCOME_PATH.split('/')), 'utf8'));
    return out && typeof out === 'object' ? out : null;
  } catch {
    return null;
  }
}

/** When the last gate promoted a REQ (ms; 0 if none): the newest passing runs/gate/<REQ>/report_<REQ>_<ts>.json. */
function lastPromotionAt(root) {
  const gateDir = path.join(root, 'runs', 'gate');
  let reqs = [];
  try { reqs = fs.readdirSync(gateDir); } catch { return 0; }
  let last = 0;
  for (const req of reqs) {
    let names = [];
    try { names = fs.readdirSync(path.join(gateDir, req)).filter((n) => /^report_.*_\d+\.json$/.test(n)); } catch { continue; }
    const reports = names.map((n) => ({ n, ts: Number(n.match(/_(\d+)\.json$/)[1]) })).sort((a, b) => b.ts - a.ts);
    for (const { n, ts } of reports) {
      if (ts <= last) break;
      let rep = null;
      try { rep = JSON.parse(fs.readFileSync(path.join(gateDir, req, n), 'utf8')); } catch { continue; }
      const st = String(rep?.status || (rep?.passed === true ? 'PASS' : '')).toUpperCase();
      if (st === 'PASS' || st === 'PASS_WITH_WARNINGS') { last = ts; break; }
    }
  }
  return last;
}

/**
 * Finalized: the report is there, the last /finalize did not fail (no outcome: an earlier CLike) and
 * no gate promoted a REQ after it. A FINALIZE_REPORT of an earlier release does not finalize the REQs
 * promoted since (test project: v1 report, v2 REQs all done, the cockpit showed FINALIZE done).
 */
function finalizeDone(root) {
  const report = path.join(root, ...REPORT_PATH.split('/'));
  let reportAt;
  try { reportAt = fs.statSync(report).mtimeMs; } catch { return false; }
  const outcome = readFinalizeOutcome(root);
  if (outcome?.status === 'failed') return false;
  const outcomeAt = Date.parse(outcome?.at || '');
  const finalizedAt = Number.isFinite(outcomeAt) ? Math.max(outcomeAt, reportAt) : reportAt;
  return finalizedAt >= lastPromotionAt(root);
}

module.exports = { OUTCOME_PATH, writeFinalizeOutcome, readFinalizeOutcome, finalizeDone, lastPromotionAt };
