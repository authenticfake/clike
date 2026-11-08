'use strict';
// Use-case coverage after /plan (and /idea --extend): every step of every SPEC use case
// (`### UC-01 — …`, steps `UC-01.1`…) must be covered by at least one REQ (`reqs[].covers` in
// plan.json, a step id or a whole use case). Deterministic and the same for every executor: the
// cloud model and the local agents both leave SPEC.md and plan.json on disk, CLike reads them here.
// A SPEC without a `## Use Cases` section (projects planned before it) is not checked.
const fs = require('fs');
const path = require('path');

const UC_ID = /\bUC-(\d{2,})\b(?!\.\d)/g;
const STEP_ID = /\bUC-(\d{2,})\.(\d+)\b/g;

/** The `## Use Cases` section of a SPEC, or null when it has none. */
function useCasesSection(specText) {
  const text = String(specText || '');
  const start = text.search(/^##\s+Use Cases\s*$/m);
  if (start < 0) return null;
  const rest = text.slice(start).split('\n').slice(1).join('\n');
  const end = rest.search(/^##\s+\S/m);
  return end < 0 ? rest : rest.slice(0, end);
}

/** { 'UC-01': ['UC-01.1', …], … } in SPEC order; a use case without numbered steps maps to []. */
function specUseCases(specText) {
  const section = useCasesSection(specText);
  if (section === null) return null;
  const cases = {};
  for (const line of section.split('\n')) {
    const heading = /^###\s+(UC-\d{2,})\b/.exec(line);
    if (heading && !cases[heading[1]]) cases[heading[1]] = [];
    for (const m of line.matchAll(STEP_ID)) {
      const uc = `UC-${m[1]}`;
      const step = `${uc}.${m[2]}`;
      if (!cases[uc]) cases[uc] = [];
      if (!cases[uc].includes(step)) cases[uc].push(step);
    }
  }
  return cases;
}

/** What plan.json covers: step ids and whole use cases, upper-cased. */
function planCovers(plan) {
  const covered = new Map(); // id -> [REQ ids]
  for (const req of (plan && Array.isArray(plan.reqs) ? plan.reqs : [])) {
    const ids = Array.isArray(req?.covers) ? req.covers : (req?.covers ? [req.covers] : []);
    for (const raw of ids) {
      const id = String(raw || '').trim().toUpperCase();
      if (!/^UC-\d{2,}(\.\d+)?$/.test(id)) continue;
      covered.set(id, [...(covered.get(id) || []), String(req.id || '?')]);
    }
  }
  return covered;
}

/**
 * Coverage of the SPEC use cases by the plan: null when the SPEC has no Use Cases section;
 * otherwise { useCases, steps, uncovered: [step or UC ids], unknown: [ids the plan cites that the
 * SPEC does not have], reqsWithoutCovers: [REQ ids] }.
 */
function useCaseCoverage(specText, plan) {
  const cases = specUseCases(specText);
  if (cases === null) return null;
  const covered = planCovers(plan);
  const uncovered = [];
  let steps = 0;
  for (const [uc, ucSteps] of Object.entries(cases)) {
    if (!ucSteps.length) {
      if (!covered.has(uc)) uncovered.push(uc);
      continue;
    }
    for (const step of ucSteps) {
      steps += 1;
      if (!covered.has(step) && !covered.has(uc)) uncovered.push(step);
    }
  }
  const known = new Set([...Object.keys(cases), ...Object.values(cases).flat()]);
  const unknown = [...covered.keys()].filter((id) => !known.has(id)).sort();
  const reqsWithoutCovers = (plan && Array.isArray(plan.reqs) ? plan.reqs : [])
    .filter((r) => !(Array.isArray(r?.covers) ? r.covers.length : r?.covers))
    .map((r) => String(r.id || '?'));
  return { useCases: Object.keys(cases).length, steps, uncovered, unknown, reqsWithoutCovers };
}

/** The coverage of the project on disk (docs/harper/SPEC.md and plan.json), or null. */
function projectUseCaseCoverage(workspaceRoot) {
  const harper = path.join(workspaceRoot, 'docs', 'harper');
  let spec = '';
  let plan = null;
  try { spec = fs.readFileSync(path.join(harper, 'SPEC.md'), 'utf8'); } catch { return null; }
  try { plan = JSON.parse(fs.readFileSync(path.join(harper, 'plan.json'), 'utf8')); } catch { return null; }
  return useCaseCoverage(spec, plan);
}

/** One chat line for the developer. */
function useCaseCoverageMessage(coverage) {
  if (!coverage) return '';
  const head = `${coverage.useCases} use case(s), ${coverage.steps} step(s)`;
  const notes = [];
  if (coverage.unknown.length) notes.push(`plan cites ids the SPEC does not have: ${coverage.unknown.slice(0, 10).join(', ')}`);
  if (coverage.reqsWithoutCovers.length) notes.push(`REQs covering no use case: ${coverage.reqsWithoutCovers.slice(0, 10).join(', ')}`);
  if (!coverage.uncovered.length) {
    return `✔ USE CASES: every step is covered by a REQ (${head}).` + (notes.length ? ` Note: ${notes.join('; ')}.` : '');
  }
  const listed = coverage.uncovered.slice(0, 20).join(', ') + (coverage.uncovered.length > 20 ? ` … (+${coverage.uncovered.length - 20})` : '');
  return `⚠ USE CASES: ${coverage.uncovered.length} step(s) of the SPEC no REQ covers (${head}): ${listed}. ` +
    'The solution would miss them: run /plan again (or add REQs with /idea --extend) so that every step is in a REQ\'s covers.' +
    (notes.length ? ` Also: ${notes.join('; ')}.` : '');
}

// Journey scenarios (the journey skills of .clike/skills, orchestrator/services/quality_context.py):
// the SPEC `## Scenarios` section includes or excludes each scenario a use case implies
// (`- IAM-03 — included — …`, `- IAM-03 — excluded — <reason>`), and every included scenario is
// owned by a REQ (`reqs[].scenarios`). The eval then blocks a REQ whose scenario has no proof.
const SCENARIO_ID = /\b([A-Z]{2,6}-\d{2,3})\b/;

function scenariosSection(specText) {
  const text = String(specText || '');
  const start = text.search(/^##\s+Scenarios\s*$/m);
  if (start < 0) return null;
  const rest = text.slice(start).split('\n').slice(1).join('\n');
  const end = rest.search(/^##\s+\S/m);
  return end < 0 ? rest : rest.slice(0, end);
}

/** { included: [ids], excluded: [{ id, reason }] } of the SPEC, or null without the section. */
function specScenarios(specText) {
  const section = scenariosSection(specText);
  if (section === null) return null;
  const included = [];
  const excluded = [];
  for (const line of section.split('\n')) {
    const m = SCENARIO_ID.exec(line.toUpperCase());
    if (!m || /^\s*#/.test(line)) continue;
    const id = m[1];
    const tail = line.slice(line.toUpperCase().indexOf(id) + id.length);
    const parts = tail.split(/\s+[—–|-]\s+|\s*[—–|]\s*/).map((p) => p.trim()).filter(Boolean);
    const first = (parts[0] || '').replace(/^[\s:*`(]+/, '');
    const decision = /^(excluded|out of scope|not applicable)\b/i.exec(first);
    if (decision) {
      const inline = first.slice(decision[0].length).replace(/^[\s:)*`,(]+/, '').replace(/[)*`]+$/, '').trim();
      const reason = [inline, ...parts.slice(1)].filter(Boolean).join(' — ');
      if (!excluded.some((e) => e.id === id)) excluded.push({ id, reason });
    } else if (!included.includes(id)) {
      included.push(id);
    }
  }
  return { included, excluded };
}

/** Map scenario id -> [REQ ids] from plan.json `reqs[].scenarios` (ids or { id }). */
function planScenarios(plan) {
  const owned = new Map();
  for (const req of (plan && Array.isArray(plan.reqs) ? plan.reqs : [])) {
    const list = Array.isArray(req?.scenarios) ? req.scenarios : [];
    for (const raw of list) {
      const m = SCENARIO_ID.exec(String(raw && typeof raw === 'object' ? raw.id : raw || '').toUpperCase());
      if (m) owned.set(m[1], [...(owned.get(m[1]) || []), String(req.id || '?')]);
    }
  }
  return owned;
}

/**
 * Scenario coverage: null when the SPEC has no `## Scenarios` section; otherwise { included,
 * excluded, unassigned: [included ids no REQ owns], unexpected: [ids a REQ owns the SPEC does not
 * include], noReason: [excluded ids without a reason], shared: [ids owned by more than one REQ] }.
 */
function scenarioCoverage(specText, plan) {
  const spec = specScenarios(specText);
  if (spec === null) return null;
  const owned = planScenarios(plan);
  return {
    included: spec.included.length,
    excluded: spec.excluded.length,
    unassigned: spec.included.filter((id) => !owned.has(id)),
    unexpected: [...owned.keys()].filter((id) => !spec.included.includes(id)).sort(),
    noReason: spec.excluded.filter((e) => !e.reason).map((e) => e.id),
    shared: [...owned.entries()].filter(([, reqs]) => reqs.length > 1).map(([id]) => id).sort(),
  };
}

function projectScenarioCoverage(workspaceRoot) {
  const harper = path.join(workspaceRoot, 'docs', 'harper');
  let spec = '';
  let plan = null;
  try { spec = fs.readFileSync(path.join(harper, 'SPEC.md'), 'utf8'); } catch { return null; }
  try { plan = JSON.parse(fs.readFileSync(path.join(harper, 'plan.json'), 'utf8')); } catch { return null; }
  return scenarioCoverage(spec, plan);
}

function scenarioCoverageMessage(coverage) {
  if (!coverage) return '';
  const head = `${coverage.included} included, ${coverage.excluded} excluded`;
  const notes = [];
  if (coverage.unexpected.length) notes.push(`REQs own scenarios the SPEC does not include: ${coverage.unexpected.slice(0, 10).join(', ')}`);
  if (coverage.noReason.length) notes.push(`excluded without a reason: ${coverage.noReason.slice(0, 10).join(', ')}`);
  if (coverage.shared.length) notes.push(`owned by more than one REQ: ${coverage.shared.slice(0, 10).join(', ')}`);
  if (!coverage.unassigned.length) {
    return `✔ SCENARIOS: every included journey scenario is owned by a REQ (${head}).` + (notes.length ? ` Note: ${notes.join('; ')}.` : '');
  }
  const listed = coverage.unassigned.slice(0, 20).join(', ') + (coverage.unassigned.length > 20 ? ` … (+${coverage.unassigned.length - 20})` : '');
  return `⚠ SCENARIOS: ${coverage.unassigned.length} included scenario(s) no REQ owns (${head}): ${listed}. ` +
    'Their corner cases would never be built or proved: run /plan again so that each is in a REQ\'s scenarios.' +
    (notes.length ? ` Also: ${notes.join('; ')}.` : '');
}

module.exports = {
  useCasesSection, specUseCases, useCaseCoverage, projectUseCaseCoverage, useCaseCoverageMessage,
  specScenarios, scenarioCoverage, projectScenarioCoverage, scenarioCoverageMessage,
};
