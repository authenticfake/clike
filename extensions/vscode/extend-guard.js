'use strict';
// /extend (alias /add-req) is append-only: existing REQs are read-only, new REQs continue the
// sequence. The phase prompt says so, and the agent returns the whole plan.json; this module is
// the deterministic check of the result, run before the plan is kept.
const fs = require('fs');
const path = require('path');
const { isDeepStrictEqual } = require('util');

// Derived by CLike from other fields (orchestrator capability enrichment), so they may differ.
const DERIVED_REQ_FIELDS = new Set(['capabilities', 'capability_exclusions']);
const REQ_ID_RE = /^REQ-(\d+)$/;

const reqsOf = (plan) => {
  const list = plan && (plan.reqs || plan.req);
  return Array.isArray(list) ? list.filter((r) => r && typeof r === 'object') : null;
};

const withoutDerived = (req) => Object.fromEntries(Object.entries(req).filter(([k]) => !DERIVED_REQ_FIELDS.has(k)));

/** Fields of an existing REQ that the extension changed (derived fields ignored). */
function changedFields(before, after) {
  const a = withoutDerived(before);
  const b = withoutDerived(after);
  return [...new Set([...Object.keys(a), ...Object.keys(b)])].filter((k) => !isDeepStrictEqual(a[k], b[k])).sort();
}

/**
 * Validate an /extend result. `beforeText`/`afterText` are plan.json contents; `anchorReq` and
 * `explicitReq` come from the command. Existing REQs the agent changed or removed are put back
 * as they were (`restored`, and `planText` is the repaired plan.json); what cannot be repaired
 * (ids, sequence, dependencies, nothing added) is an error.
 * Returns { ok, errors, warnings, added, restored, planText }.
 * Without a readable plan before the run there is nothing to preserve: only the result is checked.
 */
function validateExtendPlan({ beforeText, afterText, anchorReq = '', explicitReq = '' }) {
  const errors = [];
  const warnings = [];
  const restored = [];
  let after;
  try { after = JSON.parse(String(afterText || '')); } catch (e) {
    return { ok: false, errors: [`plan.json is not valid JSON: ${e.message}`], warnings, added: [], restored, planText: null };
  }
  const afterReqs = reqsOf(after);
  if (!afterReqs || !afterReqs.length) return { ok: false, errors: ['plan.json has no reqs'], warnings, added: [], restored, planText: null };

  let beforeReqs = [];
  if (beforeText != null) {
    try { beforeReqs = reqsOf(JSON.parse(String(beforeText))) || []; } catch { warnings.push('plan.json before the run was not readable: existing REQs not compared'); }
  }

  const ids = afterReqs.map((r) => String(r.id || ''));
  const seen = new Set();
  for (const id of ids) {
    if (!id) errors.push('a REQ has no id');
    else if (seen.has(id)) errors.push(`duplicate REQ id ${id}`);
    seen.add(id);
  }

  // Existing REQs are read-only: changed ones go back to their text, removed ones back in place.
  const beforeById = new Map(beforeReqs.map((r) => [String(r.id || ''), r]));
  const keepDerived = (original, now) => {
    const derived = Object.fromEntries(Object.entries(now || {}).filter(([k]) => DERIVED_REQ_FIELDS.has(k)));
    return { ...original, ...derived };
  };
  const reqs = afterReqs.map((r) => {
    const original = beforeById.get(String(r.id || ''));
    if (!original) return r;
    const fields = changedFields(original, r);
    if (!fields.length) return r;
    restored.push(`${original.id} (${fields.join(', ')})`);
    return keepDerived(original, r);
  });
  const present = new Set(reqs.map((r) => String(r.id || '')));
  beforeReqs.forEach((original, index) => {
    if (present.has(String(original.id || ''))) return;
    restored.push(`${original.id} (removed)`);
    reqs.splice(Math.min(index, reqs.length), 0, original);
  });
  if (restored.length) {
    warnings.push(`existing REQs are read-only in /extend: restored ${restored.join('; ')}. Check that PLAN.md does not describe the discarded change.`);
  }

  const beforeIds = new Set(beforeById.keys());
  const added = ids.filter((id) => id && !beforeIds.has(id));
  if (!added.length) errors.push('no new REQ was added');
  const maxBefore = Math.max(0, ...[...beforeIds].map((id) => Number((id.match(REQ_ID_RE) || [])[1] || 0)));
  let expected = maxBefore + 1;
  for (const id of added) {
    const m = id.match(REQ_ID_RE);
    if (!m) { errors.push(`new REQ id ${id} is not REQ-<number>`); continue; }
    const n = Number(m[1]);
    if (n <= maxBefore) errors.push(`new ${id} does not continue the sequence (last existing is REQ-${String(maxBefore).padStart(3, '0')})`);
    else if (n !== expected) warnings.push(`new ${id} leaves a gap in the sequence (expected REQ-${String(expected).padStart(3, '0')})`);
    expected = Math.max(expected, n + 1);
  }

  if (anchorReq && beforeReqs.length && !beforeIds.has(anchorReq)) errors.push(`anchor ${anchorReq} is not in the plan`);
  if (explicitReq && !added.includes(explicitReq)) errors.push(`requested ${explicitReq} is not among the new REQs (${added.join(', ') || 'none'})`);

  const allIds = new Set(reqs.map((r) => String(r.id || '')));
  for (const r of reqs.filter((x) => added.includes(String(x.id || '')))) {
    for (const dep of Array.isArray(r.dependsOn) ? r.dependsOn : []) {
      if (!allIds.has(String(dep))) errors.push(`new ${r.id} depends on ${dep}, which is not in the plan`);
    }
  }

  const snap = after.snapshot;
  if (snap && typeof snap === 'object' && Number.isInteger(snap.total) && snap.total !== reqs.length) {
    warnings.push(`snapshot.total is ${snap.total}, the plan has ${reqs.length} REQs`);
  }
  const key = Array.isArray(after.reqs) ? 'reqs' : 'req';
  const planText = restored.length ? `${JSON.stringify({ ...after, [key]: reqs }, null, 2)}\n` : String(afterText);
  return { ok: errors.length === 0, errors, warnings, added, restored, planText };
}

/** plan.json content now on disk, or null. */
function readPlanText(workspaceRoot) {
  try { return fs.readFileSync(path.join(workspaceRoot, 'docs', 'harper', 'plan.json'), 'utf8'); } catch { return null; }
}

module.exports = { validateExtendPlan, readPlanText, changedFields };
