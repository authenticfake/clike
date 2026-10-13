'use strict';
// Gate auto-merge promotion: promote a passing REQ candidate (runs/kit/<REQ>/{src,test,tests})
// into the canonical roots with a per-file 3-way merge, without prompts, and write a report.
//
// base   = the canonical file before the KIT of this REQ (git: parent of the first commit that
//          added runs/kit/<REQ>/), so changes made to src/ after the KIT are preserved;
// ours   = the canonical file now;  theirs = the candidate.
// A file that cannot be merged cleanly is never touched: its merge with conflict markers is
// written next to it as <name>.conflict-<REQ>-<ts> and the REQ is reported as not promoted.
const fs = require('fs');
const os = require('os');
const path = require('path');
const { spawnSync } = require('child_process');

const PROMOTED_ROOTS = ['src', 'test', 'tests'];
// Generated or installed content, never source (names a real package could use are not listed).
const SCRATCH_DIRS = new Set([
  '__pycache__', 'node_modules', '.venv', '.pytest_cache', '.mypy_cache', '.ruff_cache',
  '.tmp', '.cache', '.npm-cache', '.next', '.turbo', 'local-eval-workspaces',
]);
const SCRATCH_FILE_RE = /(\.pyc|\.pyo|\.log)$|^\.DS_Store$|\.(incoming|conflict)-REQ-|\.bak-\d/;

function git(cwd, args, input) {
  const r = spawnSync('git', args, { cwd, input, encoding: 'buffer', maxBuffer: 64 * 1024 * 1024 });
  return { code: r.status, stdout: r.stdout || Buffer.alloc(0), stderr: String(r.stderr || '') };
}

function isBinary(buf) {
  return !!buf && buf.subarray(0, 8000).includes(0);
}

/** Candidate files to promote, KIT-relative (src/…, test/…), scratch excluded. */
function promotableFiles(kitRoot) {
  const out = [];
  const walk = (dir, rel) => {
    let entries = [];
    try { entries = fs.readdirSync(dir, { withFileTypes: true }); } catch { return; }
    for (const e of entries.sort((a, b) => a.name.localeCompare(b.name))) {
      const childRel = rel ? `${rel}/${e.name}` : e.name;
      if (e.isDirectory()) {
        if (!SCRATCH_DIRS.has(e.name) && !e.name.endsWith('.egg-info')) walk(path.join(dir, e.name), childRel);
      } else if (e.isFile() && !SCRATCH_FILE_RE.test(e.name)) {
        out.push(childRel);
      }
    }
  };
  for (const root of PROMOTED_ROOTS) {
    if (fs.existsSync(path.join(kitRoot, root))) walk(path.join(kitRoot, root), root);
  }
  return out;
}

/** When the KIT was generated: the oldest file CLike wrote for it (docs/ and ci/). */
function kitCreatedAt(kitRoot) {
  let oldest = null;
  for (const sub of ['docs', 'ci']) {
    let entries = [];
    try { entries = fs.readdirSync(path.join(kitRoot, sub), { withFileTypes: true }); } catch { continue; }
    for (const e of entries) {
      if (!e.isFile()) continue;
      try {
        const t = fs.statSync(path.join(kitRoot, sub, e.name)).mtimeMs;
        if (oldest == null || t < oldest) oldest = t;
      } catch { /* ignore */ }
    }
  }
  return oldest;
}

/**
 * The commit whose tree is the canonical state the KIT started from:
 * - the parent of the first commit that added runs/kit/<REQ> (the KIT phase commit), else
 * - the last commit before the KIT was generated (KIT never committed), else null.
 * Returns { rev, how } or null.
 */
function kitBaseRevision(workspaceRoot, reqId) {
  const top = git(workspaceRoot, ['rev-parse', '--show-toplevel']);
  if (top.code !== 0) return null;
  const log = git(workspaceRoot, ['log', '--diff-filter=A', '--format=%H', '--', `runs/kit/${reqId}`]);
  const shas = String(log.stdout).trim().split('\n').filter(Boolean);
  if (shas.length) {
    const first = shas[shas.length - 1];
    const parent = git(workspaceRoot, ['rev-parse', '--verify', '--quiet', `${first}^`]);
    if (parent.code === 0) return { rev: String(parent.stdout).trim(), how: 'parent of the KIT commit' };
  }
  const created = kitCreatedAt(path.join(workspaceRoot, 'runs', 'kit', reqId));
  if (created == null) return null;
  const before = git(workspaceRoot, ['rev-list', '-1', `--before=${Math.floor(created / 1000)}`, 'HEAD']);
  const rev = String(before.stdout).trim();
  return before.code === 0 && rev ? { rev, how: 'last commit before the KIT was generated (KIT not committed)' } : null;
}

/** Direct dependencies of the REQ in plan.json (dependsOn), in plan order. */
function planDependencies(workspaceRoot, reqId) {
  try {
    const plan = JSON.parse(fs.readFileSync(path.join(workspaceRoot, 'docs', 'harper', 'plan.json'), 'utf8'));
    const req = (plan.reqs || plan.req || []).find((r) => r && String(r.id) === String(reqId));
    return Array.isArray(req?.dependsOn) ? req.dependsOn.map(String).filter((d) => /^REQ-[\w.-]+$/.test(d)) : [];
  } catch {
    return [];
  }
}

/**
 * What the KIT started from for one file, the same composition the eval uses: the canonical
 * root overlaid by the direct dependency KITs in plan order. So the base is the file of the last
 * dependency KIT that has it, else the canonical file at the merge-base commit.
 */
function baseContent(workspaceRoot, rev, rel, dependencies = []) {
  for (const dep of [...dependencies].reverse()) {
    const candidate = path.join(workspaceRoot, 'runs', 'kit', dep, rel);
    if (fs.existsSync(candidate)) return { content: fs.readFileSync(candidate), from: dep };
  }
  if (!rev) return null;
  // cat-file, not show: for a path with [ ] (Next.js dynamic routes such as app/runs/[run_id]/)
  // that is not in rev, `git show rev:path` exits 0 with no output, i.e. an empty base file.
  const r = git(workspaceRoot, ['cat-file', 'blob', `${rev}:${rel}`]);
  return r.code === 0 ? { content: r.stdout, from: 'git' } : null;
}

/** git merge-file: {text, conflicts} (conflicts = number of conflict hunks). */
function mergeThreeWay(ours, base, theirs, reqId) {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'clike-merge-'));
  try {
    const [o, b, t] = ['ours', 'base', 'theirs'].map((n) => path.join(dir, n));
    fs.writeFileSync(o, ours); fs.writeFileSync(b, base); fs.writeFileSync(t, theirs);
    const r = spawnSync('git', ['merge-file', '-p', '--diff3', '-L', 'canonical', '-L', 'base', '-L', reqId, o, b, t], { encoding: 'buffer' });
    if (r.status == null || r.status < 0) throw new Error(`git merge-file failed: ${String(r.stderr || r.error || '')}`);
    if (r.status === 0) return { text: r.stdout, conflicts: 0, unions: 0 };
    return resolveAdditionOnlyHunks(r.stdout, r.status, reqId);
  } finally {
    fs.rmSync(dir, { recursive: true, force: true });
  }
}

/**
 * A conflict hunk whose base part is empty means both sides only ADDED lines at the same place
 * (e.g. new entries at the end of .env.example): keep both, canonical first. Any hunk where both
 * sides changed existing lines stays a conflict and the file is not written.
 */
function resolveAdditionOnlyHunks(buf, conflicts, reqId) {
  const lines = buf.toString('utf8').split('\n');
  const out = [];
  let i = 0;
  let unions = 0;
  while (i < lines.length) {
    if (!lines[i].startsWith('<<<<<<< canonical')) { out.push(lines[i]); i += 1; continue; }
    const ours = []; const base = []; const theirs = [];
    let part = ours; i += 1;
    while (i < lines.length && !lines[i].startsWith(`>>>>>>> ${reqId}`)) {
      if (lines[i].startsWith('||||||| base')) part = base;
      else if (lines[i] === '=======') part = theirs;
      else part.push(lines[i]);
      i += 1;
    }
    i += 1; // closing marker
    if (base.some((l) => l.trim() !== '')) return { text: buf, conflicts, unions: 0 };
    out.push(...ours, ...theirs);
    unions += 1;
  }
  return { text: Buffer.from(out.join('\n'), 'utf8'), conflicts: 0, unions };
}

/** Unified diff of one file (before → after), paths relative to the workspace. */
function unifiedDiff(rel, before, after) {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'clike-diff-'));
  try {
    const a = path.join(dir, 'a'); const b = path.join(dir, 'b');
    fs.writeFileSync(a, before || Buffer.alloc(0)); fs.writeFileSync(b, after || Buffer.alloc(0));
    const r = spawnSync('git', ['diff', '--no-index', '--no-color', '--', a, b], { encoding: 'utf8' });
    const text = String(r.stdout || '');
    if (!text) return '';
    const header = `diff --git a/${rel} b/${rel}\n` + (before ? '' : 'new file mode 100644\n');
    const body = text.split('\n').slice(1).filter((l) => !/^(new file mode|index )/.test(l)).join('\n')
      .replace(/^--- .*$/m, before ? `--- a/${rel}` : '--- /dev/null')
      .replace(/^\+\+\+ .*$/m, `+++ b/${rel}`);
    return header + body;
  } finally {
    fs.rmSync(dir, { recursive: true, force: true });
  }
}

function lineStats(diff) {
  let added = 0; let removed = 0;
  for (const l of String(diff).split('\n')) {
    if (l.startsWith('+') && !l.startsWith('+++')) added += 1;
    else if (l.startsWith('-') && !l.startsWith('---')) removed += 1;
  }
  return { added, removed };
}

/** Two-way conflict markers (no merge base): the whole canonical file against the candidate. */
function twoWayMarkers(ours, theirs, reqId) {
  const nl = (b) => (b.length && b[b.length - 1] !== 10 ? Buffer.concat([b, Buffer.from('\n')]) : b);
  return Buffer.concat([
    Buffer.from('<<<<<<< canonical\n'), nl(ours), Buffer.from('=======\n'), nl(theirs), Buffer.from(`>>>>>>> ${reqId}\n`),
  ]);
}

/** Decide the outcome of one file (pure: no writes). Every conflict carries a marker file. */
function decide({ ours, base, theirs, reqId }) {
  const d = decideRaw({ ours, base, theirs, reqId });
  if (d.outcome === 'conflict' && !d.markers && ours && theirs && !isBinary(ours) && !isBinary(theirs)) {
    d.markers = twoWayMarkers(ours, theirs, reqId);
  }
  return d;
}

function decideRaw({ ours, base, theirs, reqId }) {
  if (ours == null) return base == null ? { outcome: 'added', content: theirs } : { outcome: 'conflict', reason: 'removed from the canonical root after the KIT' };
  if (ours.equals(theirs)) return { outcome: 'unchanged' };
  if (base != null && ours.equals(base)) return { outcome: 'updated', content: theirs };
  if (base != null && theirs.equals(base)) return { outcome: 'kept_canonical' };
  if (base == null) return { outcome: 'conflict', reason: 'exists in the canonical root with different content and no merge base' };
  if (isBinary(ours) || isBinary(base) || isBinary(theirs)) return { outcome: 'conflict', reason: 'binary file changed on both sides' };
  const merged = mergeThreeWay(ours, base, theirs, reqId);
  if (merged.conflicts === 0) {
    return merged.unions
      ? { outcome: 'merged', content: merged.text, reason: `${merged.unions} place(s) where both sides only added lines: both kept` }
      : { outcome: 'merged', content: merged.text };
  }
  return { outcome: 'conflict', reason: `${merged.conflicts} overlapping change(s)`, markers: merged.text };
}

function renderReport({ reqId, ts, baseRev, baseHow, results, promoted }) {
  const counts = results.reduce((acc, r) => ({ ...acc, [r.outcome]: (acc[r.outcome] || 0) + 1 }), {});
  const conflicts = results.filter((r) => r.outcome === 'conflict');
  const lines = [
    `# Promotion of ${reqId} — auto-merge`,
    '',
    `- **Result:** ${promoted ? 'PROMOTED' : `NOT PROMOTED — ${conflicts.length} conflict(s) to resolve`}`,
    `- **When:** ${ts}`,
    `- **Merge base:** ${baseRev ? `\`${baseRev.slice(0, 12)}\` (${baseHow || `canonical roots before the KIT of ${reqId}`})` : 'none (no git history): only new or identical files are promoted'}`,
    `- **Files:** ${Object.entries(counts).map(([k, v]) => `${k} ${v}`).join(', ') || 'none'}`,
    '- **Patch:** `promotion.diff` (apply/revert with `git apply [-R] runs/kit/' + `${reqId}/promotion/${ts}/promotion.diff\`)`,
    '',
    '| File | Outcome | +/- | Note |',
    '|---|---|---|---|',
    ...results.map((r) => `| \`${r.path}\` | ${r.outcome} | ${r.stats ? `+${r.stats.added} −${r.stats.removed}` : ''} | ${[r.reason, r.conflictFile ? `resolve with \`${r.conflictFile}\`` : '', r.base ? `base: ${r.base} KIT` : ''].filter(Boolean).join('; ')} |`),
    '',
  ];
  if (conflicts.length) {
    lines.push(
      '## Conflicts',
      '',
      'These files were **not** changed. Next to each one (the **Note** column), `<name>.conflict-' + `${reqId}-${ts}\``,
      'holds the merge with conflict markers: `<<<<<<< canonical` (src/ now), `||||||| base` (what the KIT',
      'started from, when known), `=======`, `>>>>>>> ' + `${reqId}\` (the candidate); without a base the whole files are`,
      'compared. Write the right content into the canonical file, delete the `.conflict-…` file and run',
      '`/gate ' + `${reqId}\` again: the REQ becomes done when no conflict is left.`,
      '',
      ...conflicts.map((r) => `- \`${r.path}\`: ${r.reason}${r.conflictFile ? ` → \`${r.conflictFile}\`` : ''}`),
      '',
    );
  }
  lines.push('Outcomes: `added` new file · `updated` canonical unchanged since the KIT, candidate written · `merged` both changed, merged cleanly · `kept_canonical` only the canonical side changed · `unchanged` identical · `conflict` overlapping changes, not written.', '');
  return lines.join('\n');
}

/**
 * Promote reqId with a 3-way merge per file. Returns
 * { ts, promoted, results, written, reportFiles, reportPath, summary }.
 */
function autoMergePromotion({ workspaceRoot, reqId, now = new Date() }) {
  const ts = now.toISOString().replace(/[:.]/g, '-');
  const kitRoot = path.join(workspaceRoot, 'runs', 'kit', reqId);
  const baseInfo = kitBaseRevision(workspaceRoot, reqId);
  const baseRev = baseInfo ? baseInfo.rev : null;
  const dependencies = planDependencies(workspaceRoot, reqId);
  const results = [];
  const writes = [];
  const diffs = [];
  for (const rel of promotableFiles(kitRoot)) {
    const dest = path.join(workspaceRoot, rel);
    const theirs = fs.readFileSync(path.join(kitRoot, rel));
    const ours = fs.existsSync(dest) ? fs.readFileSync(dest) : null;
    const baseFile = baseContent(workspaceRoot, baseRev, rel, dependencies);
    const d = decide({ ours, base: baseFile ? baseFile.content : null, theirs, reqId });
    const entry = { path: rel, outcome: d.outcome };
    if (baseFile && baseFile.from !== 'git' && d.outcome !== 'added' && d.outcome !== 'unchanged') entry.base = baseFile.from;
    if (d.reason) entry.reason = d.reason;
    if (d.content) {
      const diff = isBinary(d.content) ? `Binary file ${rel} ${ours ? 'changed' : 'added'}\n` : unifiedDiff(rel, ours, d.content);
      entry.stats = lineStats(diff);
      diffs.push(diff);
      writes.push({ dest, content: d.content });
    }
    if (d.outcome === 'conflict' && d.markers) {
      entry.conflictFile = `${rel}.conflict-${reqId}-${ts}`;
      writes.push({ dest: path.join(workspaceRoot, entry.conflictFile), content: d.markers, conflict: true });
    }
    results.push(entry);
  }
  const promoted = !results.some((r) => r.outcome === 'conflict');
  // Write only when every decision is taken (no half-applied state on an exception above).
  const written = [];
  for (const w of writes) {
    fs.mkdirSync(path.dirname(w.dest), { recursive: true });
    fs.writeFileSync(w.dest, w.content);
    if (!w.conflict) written.push(w.dest);
  }
  const reportDir = path.join(kitRoot, 'promotion', ts);
  fs.mkdirSync(reportDir, { recursive: true });
  const reportPath = path.join(reportDir, 'report.md');
  const jsonPath = path.join(reportDir, 'report.json');
  const diffPath = path.join(reportDir, 'promotion.diff');
  fs.writeFileSync(reportPath, renderReport({ reqId, ts, baseRev, baseHow: baseInfo && baseInfo.how, results, promoted }));
  fs.writeFileSync(jsonPath, `${JSON.stringify({ req_id: reqId, strategy: 'auto-merge', timestamp: ts, merge_base: baseRev, merge_base_source: baseInfo && baseInfo.how, promoted, results }, null, 2)}\n`);
  fs.writeFileSync(diffPath, diffs.filter(Boolean).map((d) => (d.endsWith('\n') ? d : `${d}\n`)).join(''));
  const n = (k) => results.filter((r) => r.outcome === k).length;
  const summary = promoted
    ? `${reqId} promoted by auto-merge: ${n('added')} added, ${n('updated')} updated, ${n('merged')} merged, ${n('unchanged') + n('kept_canonical')} unchanged.`
    : `${reqId} NOT promoted: ${n('conflict')} conflict(s); ${written.length} file(s) merged cleanly were written. See the report.`;
  return { ts, promoted, results, written, reportFiles: [reportPath, jsonPath, diffPath], reportPath, summary };
}

module.exports = { autoMergePromotion, baseContent, decide, planDependencies, promotableFiles, kitBaseRevision, mergeThreeWay, unifiedDiff };
