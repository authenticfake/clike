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

/** Finalized: the report is there and the last /finalize did not fail (no outcome: an earlier CLike). */
function finalizeDone(root) {
  if (!fs.existsSync(path.join(root, ...REPORT_PATH.split('/')))) return false;
  return readFinalizeOutcome(root)?.status !== 'failed';
}

module.exports = { OUTCOME_PATH, writeFinalizeOutcome, readFinalizeOutcome, finalizeDone };
