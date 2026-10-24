'use strict';
// KIT readiness from plan.json: a REQ is KIT-ready unless the plan says it needs answers only the
// owner can give (`reqs[].kit_ready: false`, the questions in `reqs[].blockers`). Ordinary product
// choices are decided in the SPEC Assumptions and never block. Deterministic and the same for every
// executor: the cloud model and the local agents both leave plan.json on disk, CLike reads it here.
// A plan without `kit_ready` (projects planned before it) is KIT-ready. The cockpit, /kit and
// /autopilot read readiness through this module only.

/** The owner's open questions of one REQ of plan.json, [] when it is KIT-ready. */
function reqBlockers(req) {
  if (!req || typeof req !== 'object') return [];
  // `kit_ready`/`blockers` (the plan.json schema), or a `readiness` object some plans write instead
  const nested = req.readiness && typeof req.readiness === 'object' ? req.readiness : null;
  const source = 'kit_ready' in req ? req : nested || req;
  const flag = source.kit_ready;
  const notReady = flag === false || String(flag).trim().toLowerCase() === 'false';
  if (!notReady) return [];
  const raw = Array.isArray(source.blockers) ? source.blockers : (source.blockers ? [source.blockers] : []);
  const blockers = raw
    .map((b) => (b && typeof b === 'object' ? [b.id, b.question || b.subject || b.text].filter(Boolean).join(' — ') : String(b || '')))
    .map((b) => b.trim())
    .filter(Boolean);
  return blockers.length ? blockers : ['the plan marks it not KIT-ready without saying why'];
}

/** { reqs, notReady: [{ id, blockers }] } of a plan.json object. */
function planReadiness(plan) {
  const reqs = plan && Array.isArray(plan.reqs) ? plan.reqs : [];
  const notReady = reqs
    .filter((r) => !['done', 'deferred'].includes(String(r?.status || '').trim().toLowerCase()))
    .map((r) => ({ id: String(r?.id || '?').toUpperCase(), blockers: reqBlockers(r) }))
    .filter((r) => r.blockers.length);
  return { reqs: reqs.length, notReady };
}

/** The blockers of one REQ id in a plan.json object, [] when ready or absent. */
function blockersOf(plan, reqId) {
  const id = String(reqId || '').trim().toUpperCase();
  const req = (plan && Array.isArray(plan.reqs) ? plan.reqs : []).find((r) => String(r?.id || '').toUpperCase() === id);
  return reqBlockers(req);
}

const HOW_TO_ANSWER = 'answer them in the "Note from Harper Orchestrator (Super User) to be applied" section of SPEC.md, then run /spec and /plan again';

function listed(blockers, max = 8) {
  return blockers.slice(0, max).join('; ') + (blockers.length > max ? ` … (+${blockers.length - max})` : '');
}

/** One chat line after /plan: '' when every open REQ is KIT-ready. */
function planReadinessMessage(readiness) {
  if (!readiness || !readiness.notReady.length) return '';
  const lines = readiness.notReady.map((r) => `${r.id}: ${listed(r.blockers)}`);
  return `⚠ KIT READINESS: ${readiness.notReady.length} REQ(s) wait for answers only you can give — ${lines.join(' | ')}. ` +
    `To go on, ${HOW_TO_ANSWER}. /autopilot parks these REQs before /kit.`;
}

/** Why /autopilot parks a REQ before its /kit. */
function notReadyReason(blockers) {
  return `not KIT-ready, the plan waits for your answers: ${listed(blockers)} (${HOW_TO_ANSWER})`;
}

module.exports = { reqBlockers, planReadiness, blockersOf, planReadinessMessage, notReadyReason };
