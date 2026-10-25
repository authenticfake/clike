'use strict';
// /idea --extend: the release cascade of an existing project (IDEA → SPEC → PLAN delta).
// Deterministic side of the command: which release is targeted, whether the baseline is delivered,
// whether the agent merged the documents instead of rewriting them, and the verification section
// CLike appends to the EXTEND report. The agent rules live in orchestrator/services/extend_cascade.py.
const fs = require('fs');
const path = require('path');
const crypto = require('crypto');
const { execFileSync } = require('child_process');

const RELEASE_RE = /^v(\d+)$/i;
const DOC_FILES = { idea: 'docs/harper/IDEA.md', spec: 'docs/harper/SPEC.md', tech: 'docs/harper/TECH_CONSTRAINTS.yaml' };
const PLAN_FILES = { plan: 'docs/harper/plan.json', planMd: 'docs/harper/PLAN.md' };
const CHANGE_TYPES = new Set(['ADDED', 'MODIFIED', 'REMOVED']);

const releaseNumber = (name) => Number((String(name || '').trim().match(RELEASE_RE) || [])[1] || 0);
const read = (root, rel) => { try { return fs.readFileSync(path.join(root, ...rel.split('/')), 'utf8'); } catch { return null; } };

/** The docs/inputs|reference/vN releases that hold files (an empty folder made in advance is no release). */
function releaseFolders(root) {
  const found = new Set();
  for (const base of ['inputs', 'reference']) {
    let entries = [];
    try { entries = fs.readdirSync(path.join(root, 'docs', base), { withFileTypes: true }); } catch { continue; }
    for (const e of entries) {
      if (e.isDirectory() && RELEASE_RE.test(e.name) && filesUnder(path.join(root, 'docs', base, e.name)).length) {
        found.add(releaseNumber(e.name));
      }
    }
  }
  return [...found].sort((a, b) => a - b);
}

function filesUnder(dir) {
  const out = [];
  const walk = (d) => {
    let entries = [];
    try { entries = fs.readdirSync(d, { withFileTypes: true }); } catch { return; }
    for (const e of entries) {
      if (e.name.startsWith('.')) continue;
      const p = path.join(d, e.name);
      if (e.isDirectory()) walk(p); else out.push(p);
    }
  };
  walk(dir);
  return out;
}

/** Highest `release` already in plan.json (REQs without one belong to v1). */
function planRelease(planText) {
  let reqs = [];
  try { const p = JSON.parse(planText || ''); reqs = Array.isArray(p.reqs) ? p.reqs : Array.isArray(p.req) ? p.req : []; } catch { return 0; }
  if (!reqs.length) return 0;
  return Math.max(1, ...reqs.map((r) => releaseNumber(r && r.release)));
}

/**
 * The release this cascade targets and its inputs. Explicit `--release vN` wins; otherwise the
 * highest docs/inputs|reference/vN folder above what the plan already holds; otherwise the next one.
 */
function detectRelease(root, { release = '', planText = null } = {}) {
  const delivered = planRelease(planText ?? read(root, PLAN_FILES.plan));
  const folders = releaseFolders(root);
  const explicit = releaseNumber(release);
  const highest = folders.length ? folders[folders.length - 1] : 0;
  const target = explicit || (highest > delivered ? highest : Math.max(delivered, 1) + 1);
  const rel = (p) => path.relative(root, p).split(path.sep).join('/');
  return {
    release: `v${target}`,
    baseline: `v${Math.max(1, Math.min(delivered || 1, target - 1))}`,
    inputs: filesUnder(path.join(root, 'docs', 'inputs', `v${target}`)).map(rel),
    references: filesUnder(path.join(root, 'docs', 'reference', `v${target}`)).map(rel),
    folders: folders.map((n) => `v${n}`),
  };
}

/**
 * The release needs its own input: files in docs/inputs/<release>/ or attachments of the run (as
 * /idea needs an attachment). The text of the command adds to them, it does not replace them.
 */
function cascadeInputCheck(rel, attachmentCount) {
  if (rel.inputs.length || Number(attachmentCount) > 0) return { ok: true };
  return {
    ok: false,
    message: `no input for ${rel.release}: put the new requirements in docs/inputs/${rel.release}/ ` +
      `(background in docs/reference/${rel.release}/) or attach them.`,
  };
}

/** What the baseline is: REQs not delivered and the last solution verification. */
function baselineStatus(root) {
  let reqs = [];
  try { const p = JSON.parse(read(root, PLAN_FILES.plan) || ''); reqs = Array.isArray(p.reqs) ? p.reqs : p.req || []; } catch { /* no plan */ }
  const notDone = reqs.filter((r) => r && String(r.status || 'open').toLowerCase() !== 'done').map((r) => `${r.id} (${r.status || 'open'})`);
  const evidence = read(root, 'docs/harper/SOLUTION_EVAL.md');
  const solution = evidence ? ((evidence.match(/\b(PASS|FAIL)\b/) || [])[1] || 'unknown') : 'not run';
  return { hasPlan: reqs.length > 0, total: reqs.length, notDone, solution };
}

/** The documents the cascade may change, as they are before the run. */
function snapshotDocs(root) {
  return Object.fromEntries(Object.entries({ ...DOC_FILES, ...PLAN_FILES }).map(([k, rel]) => [k, read(root, rel)]));
}

function sections(markdown) {
  const out = new Map();
  let current = '(preamble)';
  let body = [];
  const flush = () => out.set(current, crypto.createHash('sha1').update(body.join('\n').trim()).digest('hex'));
  for (const line of String(markdown || '').split(/\r?\n/)) {
    const m = line.match(/^(#{1,3})\s+(.+?)\s*$/);
    if (m) { flush(); current = `${m[1]} ${m[2]}`; body = []; } else body.push(line);
  }
  flush();
  return out;
}

/**
 * Merge check of one Markdown document: every heading of the earlier release must still be there.
 * Returns { ok, missing, added, changed }.
 */
function compareMarkdown(before, after) {
  if (before == null) return { ok: true, missing: [], added: [], changed: [] };
  if (after == null) return { ok: false, missing: ['(the whole document)'], added: [], changed: [] };
  const a = sections(before);
  const b = sections(after);
  const missing = [...a.keys()].filter((h) => h !== '(preamble)' && !b.has(h));
  const added = [...b.keys()].filter((h) => !a.has(h));
  const changed = [...a.keys()].filter((h) => b.has(h) && a.get(h) !== b.get(h));
  return { ok: missing.length === 0, missing, added, changed };
}

/** TECH_CONSTRAINTS changes only by addition: every earlier non-empty line is still there. */
function compareAdditive(before, after) {
  if (before == null) return { ok: true, missing: [] };
  if (after == null) return { ok: false, missing: ['(the whole file)'] };
  const kept = new Set(String(after).split(/\r?\n/).map((l) => l.trimEnd()));
  const missing = String(before).split(/\r?\n/).map((l) => l.trimEnd()).filter((l) => l.trim() && !l.trim().startsWith('#') && !kept.has(l));
  return { ok: missing.length === 0, missing };
}

/**
 * Delta rules on the new REQs of the cascade (existing REQs are checked by validateExtendPlan).
 * `ltcChecks(reqId)` returns the check ids of runs/kit/<REQ>/ci/LTC.json (or null when unknown).
 * Missing `release` is filled in (returned in `planText`); the rest are errors or warnings.
 */
function validateDelta({ beforeText, planText, release, ltcChecks = () => null }) {
  const errors = [];
  const warnings = [];
  let plan;
  try { plan = JSON.parse(planText); } catch (e) { return { ok: false, errors: [`plan.json is not valid JSON: ${e.message}`], warnings, planText, delta: [] }; }
  const key = Array.isArray(plan.reqs) ? 'reqs' : 'req';
  const reqs = Array.isArray(plan[key]) ? plan[key] : [];
  let before = [];
  try { const p = JSON.parse(beforeText || ''); before = Array.isArray(p.reqs) ? p.reqs : p.req || []; } catch { /* nothing before */ }
  const byId = new Map(before.map((r) => [String(r.id), r]));
  const delta = reqs.filter((r) => r && !byId.has(String(r.id)));
  let filled = false;
  for (const r of delta) {
    const id = r.id;
    if (!r.release) { r.release = release; filled = true; }
    else if (r.release !== release) errors.push(`${id}: release is ${r.release}, this cascade is ${release}`);
    const change = String(r.change || '').toUpperCase();
    if (!CHANGE_TYPES.has(change)) { errors.push(`${id}: change must be ADDED, MODIFIED or REMOVED`); continue; }
    if (r.change !== change) { r.change = change; filled = true; }
    const targets = (field) => (Array.isArray(r[field]) ? r[field].map(String) : []);
    for (const field of ['amends', 'retires']) {
      for (const t of targets(field)) {
        const target = byId.get(t);
        if (!target) errors.push(`${id}: ${field} ${t}, which is not a delivered REQ`);
        else if (String(target.status || '').toLowerCase() === 'in_progress') errors.push(`${id}: ${field} ${t}, which is in progress (re-plan it instead)`);
      }
    }
    if (change === 'MODIFIED' && !targets('amends').length) errors.push(`${id}: MODIFIED needs amends: ["REQ-x"]`);
    if (change === 'REMOVED' && !targets('retires').length) errors.push(`${id}: REMOVED needs retires: ["REQ-x"]`);
    if (change === 'ADDED' && (targets('amends').length || targets('retires').length)) warnings.push(`${id}: ADDED with amends/retires — should it be MODIFIED or REMOVED?`);
    for (const s of Array.isArray(r.supersedes) ? r.supersedes : []) {
      const ref = String((s && s.check) || s || '');
      const m = ref.match(/^(REQ-\d+)#(.+)$/);
      if (!m) { errors.push(`${id}: supersedes "${ref}" is not REQ-x#<check or test id>`); continue; }
      if (!targets('amends').includes(m[1])) errors.push(`${id}: supersedes a check of ${m[1]}, which it does not amend`);
      const known = ltcChecks(m[1]);
      if (Array.isArray(known) && !known.includes(m[2]) && !/[/:.]/.test(m[2])) {
        errors.push(`${id}: supersedes ${ref}, but ${m[1]}'s LTC has no check "${m[2]}" (checks: ${known.join(', ') || 'none'})`);
      }
      if (!s || !s.reason) warnings.push(`${id}: supersedes ${ref} without a reason`);
    }
    if (change === 'MODIFIED' && !(Array.isArray(r.supersedes) && r.supersedes.length)) {
      warnings.push(`${id}: MODIFIED without supersedes — the regression of ${targets('amends').join(', ')} will keep every check`);
    }
  }
  if (!delta.length) errors.push('the cascade added no REQ');
  return { ok: errors.length === 0, errors, warnings, delta, planText: filled ? `${JSON.stringify(plan, null, 2)}\n` : planText };
}

/** Check ids of a REQ's eval profile (runs/kit/<REQ>/ci/LTC.json), or null when there is none. */
function ltcCheckIds(root, reqId) {
  try {
    const ltc = JSON.parse(fs.readFileSync(path.join(root, 'runs', 'kit', reqId, 'ci', 'LTC.json'), 'utf8'));
    return [...(ltc.setup || []), ...(ltc.checks || [])].map((c) => String(c.id || '')).filter(Boolean);
  } catch { return null; }
}

/** The section CLike appends to the EXTEND report: facts it checked itself. */
function verificationMarkdown({ release, baseline, inputs = [], references = [], attachments = [], baselineInfo, docs = {}, delta = [], restored = [], warnings = [], dryRun = false, tag = '' }) {
  const cell = (v) => String(v ?? '').replace(/\|/g, '/').replace(/\n/g, ' ');
  const list = (v) => (Array.isArray(v) && v.length ? v.map((x) => (x && x.check) || x).join(', ') : '—');
  const docLine = (label, d) => (!d ? `- ${label}: unchanged` : d.missing && d.missing.length
    ? `- ${label}: **restored** (the run dropped: ${d.missing.join('; ')})`
    : `- ${label}: ${d.added?.length || 0} section(s) added, ${d.changed?.length || 0} changed${d.added?.length ? ` — new: ${d.added.join('; ')}` : ''}`);
  return [
    '',
    `## CLike verification (${new Date().toISOString().slice(0, 10)})`,
    '',
    dryRun ? '**Dry run:** only this report was kept; IDEA, SPEC, PLAN and plan.json are unchanged.\n' : null,
    `- Release: **${release}**, from baseline ${baseline}${tag ? ` (tag \`${tag}\`)` : ''}`,
    baselineInfo ? `- Baseline: ${baselineInfo.total} REQ(s), ${baselineInfo.notDone.length ? `not delivered: ${baselineInfo.notDone.join(', ')}` : 'all delivered'}; last solution verification: ${baselineInfo.solution}` : null,
    `- Release inputs: ${[...attachments.map((a) => `${a} (attachment)`), ...inputs, ...references].join(', ') || 'none'}`,
    docLine('IDEA.md', docs.idea),
    docLine('SPEC.md', docs.spec),
    docs.tech ? (docs.tech.missing?.length ? `- TECH_CONSTRAINTS.yaml: **restored** (lines removed: ${docs.tech.missing.length})` : '- TECH_CONSTRAINTS.yaml: extended') : '- TECH_CONSTRAINTS.yaml: unchanged',
    restored.length ? `- Existing REQs restored (read-only): ${restored.join('; ')}` : '- Existing REQs: unchanged',
    '',
    '| REQ | Change | Title | Amends / retires | Supersedes | Depends on |',
    '|---|---|---|---|---|---|',
    ...delta.map((r) => `| ${cell(r.id)} | ${cell(r.change)} | ${cell(r.title)} | ${cell(list([...(r.amends || []), ...(r.retires || [])]))} | ${cell(list(r.supersedes))} | ${cell(list(r.dependsOn))} |`),
    '',
    ...(warnings.length ? ['Warnings:', '', ...warnings.map((w) => `- ${w}`), ''] : []),
    'Next: review this report, then `/kit` the new REQs in order; `/eval --fix` and `/gate` as usual, `/finalize` at the end of the release.',
    '',
  ].filter((l) => l !== null).join('\n');
}

/**
 * PLAN.md sections that index every REQ must list the new ones too, wherever the agent put their
 * detail: the REQ-IDs table (rebuilt from plan.json, as CLike does on every status change), the
 * dependency graph (`- REQ-x <- deps`), and the per-REQ bullet sections (`**REQ-x** — ...`), which
 * get a pointer to the REQ's own subsection. Returns { text, added: ["section: REQ-x", ...] }.
 */
function syncPlanMd(md, planText) {
  let reqs = [];
  try { const p = JSON.parse(planText || ''); reqs = Array.isArray(p.reqs) ? p.reqs : p.req || []; } catch { return { text: md, added: [] }; }
  if (md == null || !reqs.length) return { text: md, added: [] };
  const added = [];
  const lines = String(md).split('\n');
  const sections = [];
  lines.forEach((l, i) => { if (/^## /.test(l)) sections.push(i); });
  const bounds = (start) => { const next = sections.find((i) => i > start); return [start, next === undefined ? lines.length : next]; };
  const cell = (v) => String(v ?? '').replace(/\|/g, '/').replace(/\n/g, ' ');
  const edits = [];
  for (const start of sections) {
    const heading = lines[start].replace(/^##\s+/, '').trim();
    const [, end] = bounds(start);
    const body = lines.slice(start + 1, end);
    const has = (id) => body.some((l) => l.includes(id));
    if (/^REQ[- ]IDs table$/i.test(heading)) {
      const tableEnd = body.findIndex((l, i) => i > 0 && !l.startsWith('|') && body[i - 1].startsWith('|'));
      const tableStart = body.findIndex((l) => l.startsWith('|'));
      if (tableStart < 0) continue;
      const rows = reqs.map((r) => `| ${cell(r.id)} | ${cell(r.title)} | ${cell((Array.isArray(r.acceptance) ? r.acceptance.map((a) => String(a).trim()) : [r.acceptance || '']).join('<br/>'))} | ${cell((r.dependsOn || []).join(', '))} | ${cell(r.track)} | ${cell(r.status)} |`);
      const missing = reqs.filter((r) => !has(`| ${r.id} |`)).map((r) => r.id);
      if (!missing.length) continue;
      const stop = tableEnd < 0 ? body.length : tableEnd;
      edits.push({ from: start + 1 + tableStart + 2, to: start + 1 + stop, insert: rows });
      missing.forEach((id) => added.push(`${heading}: ${id}`));
      continue;
    }
    if (body.some((l) => /^- REQ-\d+ <- /.test(l))) {
      const last = start + 1 + body.map((l) => /^- REQ-\d+ <- /.test(l)).lastIndexOf(true);
      const missing = reqs.filter((r) => !body.some((l) => l.startsWith(`- ${r.id} <- `)));
      if (missing.length) {
        edits.push({ from: last + 1, to: last + 1, insert: missing.map((r) => `- ${r.id} <- ${(r.dependsOn || []).join(', ') || 'none'}`) });
        missing.forEach((r) => added.push(`${heading}: ${r.id}`));
      }
      continue;
    }
    const bulletIds = body.filter((l) => /^\*\*REQ-\d+\*\*/.test(l)).length;
    if (bulletIds >= 2) {
      const missing = reqs.filter((r) => !body.some((l) => l.startsWith(`**${r.id}**`)));
      if (!missing.length) continue;
      const prefix = heading.replace(/\s*\(.*\)\s*$/, '');
      let insertAt = end;
      while (insertAt > start + 1 && !lines[insertAt - 1].trim()) insertAt -= 1;
      const pointer = (r) => {
        const sub = `### ${prefix} — ${r.id}`;
        const where = lines.includes(sub) ? `\`${sub}\`` : `the ${r.id} section`;
        return ['', `**${r.id}** — see ${where}${r.release ? ` (Release ${r.release})` : ''}.`];
      };
      edits.push({ from: insertAt, to: insertAt, insert: missing.flatMap(pointer) });
      missing.forEach((r) => added.push(`${heading}: ${r.id}`));
    }
  }
  edits.sort((a, b) => b.from - a.from).forEach((e) => lines.splice(e.from, e.to - e.from, ...e.insert));
  return { text: lines.join('\n'), added };
}

const norm = (p) => String(p || '').replace(/\\/g, '/').replace(/^\.?\//, '');

/**
 * Check the result of an extend run against the documents as they were, and repair or reject it.
 * `files`: the files the run returned (cloud: CLike writes them; local agent: already on disk).
 * mode 'plan' (/extend): only TECH_CONSTRAINTS is protected (not an /extend output).
 * mode 'cascade' (/idea --extend): plan rules (validateExtendPlan + validateDelta), merged IDEA/SPEC,
 * additive TECH_CONSTRAINTS, dry run, and CLike's verification section in the EXTEND report.
 * Returns { ok, errors, warnings, delta, restored, docs, report } and updates `files` / the disk.
 */
function reconcileExtend({ root, before, files, isAgent, mode = 'plan', cascade = {}, validateExtendPlan, startedAt = 0 }) {
  const find = (rel) => files.find((f) => norm(f && f.path) === rel);
  const keyOf = Object.fromEntries(Object.entries({ ...DOC_FILES, ...PLAN_FILES }).map(([k, rel]) => [rel, k]));
  // what the run leaves for `rel`: the returned file, else the disk (local agent) or the unchanged original (cloud)
  const current = (rel) => {
    const f = find(rel);
    if (f && typeof f.content === 'string') return f.content;
    if (isAgent) return read(root, rel);
    return rel in keyOf ? before[keyOf[rel]] : null;
  };
  const put = (rel, text) => {
    const f = find(rel);
    if (f) f.content = text;
    if (isAgent) {
      if (text == null) { try { fs.unlinkSync(path.join(root, ...rel.split('/'))); } catch { /* absent */ } }
      else fs.writeFileSync(path.join(root, ...rel.split('/')), text, 'utf8');
    }
  };
  const restoreAll = () => {
    for (const [k, rel] of Object.entries({ ...DOC_FILES, ...PLAN_FILES })) {
      if (current(rel) !== before[k]) put(rel, before[k]);
    }
    for (let i = files.length - 1; i >= 0; i -= 1) if (!/^docs\/harper\/EXTEND_[^/]+\.md$/.test(norm(files[i] && files[i].path))) files.splice(i, 1);
  };
  const warnings = [];
  const tech = compareAdditive(before.tech, current(DOC_FILES.tech) ?? before.tech);
  if (mode !== 'cascade') {
    if (current(DOC_FILES.tech) !== before.tech) {
      put(DOC_FILES.tech, before.tech);
      warnings.push('TECH_CONSTRAINTS.yaml is not an /extend output: restored (use /idea --extend for a new release)');
    }
    return { ok: true, errors: [], warnings, delta: [], restored: [], docs: {}, report: null };
  }

  const verdict = validateExtendPlan({ beforeText: before.plan, afterText: current(PLAN_FILES.plan) });
  const delta = verdict.ok
    ? validateDelta({ beforeText: before.plan, planText: verdict.planText, release: cascade.release, ltcChecks: (id) => ltcCheckIds(root, id) })
    : { ok: false, errors: [], warnings: [], delta: [], planText: null };
  const errors = [...verdict.errors, ...delta.errors];
  warnings.push(...verdict.warnings, ...delta.warnings);
  if (errors.length) { restoreAll(); return { ok: false, errors, warnings, delta: [], restored: verdict.restored, docs: {}, report: null }; }
  if (delta.planText !== current(PLAN_FILES.plan)) put(PLAN_FILES.plan, delta.planText);

  const docs = {};
  for (const key of ['idea', 'spec']) {
    const rel = DOC_FILES[key];
    const after = current(rel);
    if (after == null || after === before[key]) continue;
    docs[key] = compareMarkdown(before[key], after);
    if (!docs[key].ok) {
      put(rel, before[key]);
      warnings.push(`${rel} dropped sections of the earlier release (${docs[key].missing.join('; ')}): restored — merge, never rewrite`);
    }
  }
  if (current(DOC_FILES.tech) !== before.tech) {
    docs.tech = tech;
    if (!tech.ok) {
      put(DOC_FILES.tech, before.tech);
      warnings.push(`${DOC_FILES.tech} removed earlier lines: restored — it changes only by addition`);
    }
  }
  if (!cascade.dryRun) {
    const synced = syncPlanMd(current(PLAN_FILES.planMd), current(PLAN_FILES.plan));
    if (synced.added.length) {
      put(PLAN_FILES.planMd, synced.text);
      if (!find(PLAN_FILES.planMd) && !isAgent) files.push({ path: PLAN_FILES.planMd, content: synced.text });
      warnings.push(`PLAN.md index sections did not list the new REQs: CLike added ${synced.added.length} entr${synced.added.length === 1 ? 'y' : 'ies'} (${[...new Set(synced.added.map((a) => a.split(':')[0]))].join('; ')})`);
    }
  }
  if (cascade.dryRun) restoreAll();

  // the EXTEND report of this run: returned (cloud) or the newest on disk (local agent)
  let report = files.map((f) => norm(f && f.path)).find((p) => /^docs\/harper\/EXTEND_[^/]+\.md$/.test(p)) || null;
  if (!report && isAgent) {
    const dir = path.join(root, 'docs', 'harper');
    let names = [];
    try { names = fs.readdirSync(dir).filter((n) => /^EXTEND_.+\.md$/.test(n)); } catch { /* none */ }
    const fresh = names.map((n) => ({ n, t: fs.statSync(path.join(dir, n)).mtimeMs })).filter((x) => x.t >= startedAt).sort((a, b) => b.t - a.t);
    if (fresh.length) report = `docs/harper/${fresh[0].n}`;
  }
  const ids = delta.delta.map((r) => r.id);
  if (!report) {
    report = `docs/harper/EXTEND_${new Date().toISOString().slice(0, 10)}_${ids[0] || 'NONE'}_${ids[ids.length - 1] || 'NONE'}.md`;
    files.push({ path: report, content: `# EXTEND ${cascade.release}\n\nThe run returned no report; CLike wrote its verification.\n` });
    warnings.push('the run returned no EXTEND report: CLike wrote one with its verification only');
  }
  const section = verificationMarkdown({ ...cascade, docs, delta: delta.delta, restored: verdict.restored, warnings });
  const text = current(report) ?? (find(report) || {}).content ?? '';
  const merged = `${String(text).replace(/\s+$/, '')}\n${section}`;
  if (find(report)) find(report).content = merged; else files.push({ path: report, content: merged });
  if (isAgent) fs.writeFileSync(path.join(root, ...report.split('/')), merged, 'utf8');
  return { ok: true, errors: [], warnings, delta: delta.delta, restored: verdict.restored, docs, report };
}

/** Annotated tag on HEAD marking the delivered baseline (`harper/v1`), once; '' when not a git repo. */
function tagBaseline(root, baseline) {
  const tag = `harper/${baseline}`;
  const git = (...args) => execFileSync('git', args, { cwd: root, encoding: 'utf8', stdio: ['ignore', 'pipe', 'ignore'] }).trim();
  try {
    git('rev-parse', '--verify', 'HEAD');
    try { git('rev-parse', '--verify', `refs/tags/${tag}`); return tag; } catch { /* not there yet */ }
    try {
      git('tag', '-a', tag, '-m', `Harper baseline ${baseline}: delivered before the next release cascade`);
    } catch {
      git('tag', tag); // no committer identity configured: a lightweight tag still marks the baseline
    }
    return tag;
  } catch { return ''; }
}

module.exports = {
  reconcileExtend,
  syncPlanMd,
  tagBaseline,
  DOC_FILES,
  PLAN_FILES,
  releaseNumber,
  detectRelease,
  baselineStatus,
  cascadeInputCheck,
  snapshotDocs,
  compareMarkdown,
  compareAdditive,
  validateDelta,
  ltcCheckIds,
  verificationMarkdown,
};
