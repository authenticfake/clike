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

/** The commit whose tree is the canonical state the KIT started from, or null (no git/history). */
function kitBaseRevision(workspaceRoot, reqId) {
  const top = git(workspaceRoot, ['rev-parse', '--show-toplevel']);
  if (top.code !== 0) return null;
  const log = git(workspaceRoot, ['log', '--diff-filter=A', '--format=%H', '--', `runs/kit/${reqId}`]);
  const shas = String(log.stdout).trim().split('\n').filter(Boolean);
  if (!shas.length) return null;
  const first = shas[shas.length - 1];
  const parent = git(workspaceRoot, ['rev-parse', '--verify', '--quiet', `${first}^`]);
  return parent.code === 0 ? String(parent.stdout).trim() : null;
}

function baseContent(workspaceRoot, rev, rel) {
  if (!rev) return null;
  const r = git(workspaceRoot, ['show', `${rev}:${rel}`]);
  return r.code === 0 ? r.stdout : null;
}

/** git merge-file: {text, conflicts} (conflicts = number of conflict hunks). */
function mergeThreeWay(ours, base, theirs, reqId) {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'clike-merge-'));
  try {
    const [o, b, t] = ['ours', 'base', 'theirs'].map((n) => path.join(dir, n));
    fs.writeFileSync(o, ours); fs.writeFileSync(b, base); fs.writeFileSync(t, theirs);
    const r = spawnSync('git', ['merge-file', '-p', '-L', 'canonical', '-L', 'base', '-L', reqId, o, b, t], { encoding: 'buffer' });
    if (r.status == null || r.status < 0) throw new Error(`git merge-file failed: ${String(r.stderr || r.error || '')}`);
    return { text: r.stdout, conflicts: r.status };
  } finally {
    fs.rmSync(dir, { recursive: true, force: true });
  }
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

/** Decide the outcome of one file (pure: no writes). */
function decide({ ours, base, theirs, reqId }) {
  if (ours == null) return base == null ? { outcome: 'added', content: theirs } : { outcome: 'conflict', reason: 'removed from the canonical root after the KIT' };
  if (ours.equals(theirs)) return { outcome: 'unchanged' };
  if (base != null && ours.equals(base)) return { outcome: 'updated', content: theirs };
  if (base != null && theirs.equals(base)) return { outcome: 'kept_canonical' };
  if (base == null) return { outcome: 'conflict', reason: 'exists in the canonical root with different content and no merge base' };
  if (isBinary(ours) || isBinary(base) || isBinary(theirs)) return { outcome: 'conflict', reason: 'binary file changed on both sides' };
  const merged = mergeThreeWay(ours, base, theirs, reqId);
  if (merged.conflicts === 0) return { outcome: 'merged', content: merged.text };
  return { outcome: 'conflict', reason: `${merged.conflicts} overlapping change(s)`, markers: merged.text };
}

function renderReport({ reqId, ts, baseRev, results, promoted }) {
  const counts = results.reduce((acc, r) => ({ ...acc, [r.outcome]: (acc[r.outcome] || 0) + 1 }), {});
  const conflicts = results.filter((r) => r.outcome === 'conflict');
  const lines = [
    `# Promotion of ${reqId} — auto-merge`,
    '',
    `- **Result:** ${promoted ? 'PROMOTED' : `NOT PROMOTED — ${conflicts.length} conflict(s) to resolve`}`,
    `- **When:** ${ts}`,
    `- **Merge base:** ${baseRev ? `\`${baseRev.slice(0, 12)}\` (canonical roots before the KIT of ${reqId})` : 'none (no git history of the KIT): only new or identical files are promoted'}`,
    `- **Files:** ${Object.entries(counts).map(([k, v]) => `${k} ${v}`).join(', ') || 'none'}`,
    '- **Patch:** `promotion.diff` (apply/revert with `git apply [-R] runs/kit/' + `${reqId}/promotion/${ts}/promotion.diff\`)`,
    '',
    '| File | Outcome | +/- | Note |',
    '|---|---|---|---|',
    ...results.map((r) => `| \`${r.path}\` | ${r.outcome} | ${r.stats ? `+${r.stats.added} −${r.stats.removed}` : ''} | ${r.reason || r.conflictFile || ''} |`),
    '',
  ];
  if (conflicts.length) {
    lines.push(
      '## Conflicts',
      '',
      'These files were **not** changed. Next to each one, `<name>.conflict-' + `${reqId}-${ts}\` holds the merge with`,
      'conflict markers (`<<<<<<< canonical`, `=======`, `>>>>>>> ' + `${reqId}\`). Resolve them into the canonical file,`,
      'delete the `.conflict-…` file and run `/gate ' + `${reqId}\` again.`,
      '',
      ...conflicts.map((r) => `- \`${r.path}\`: ${r.reason}`),
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
  const baseRev = kitBaseRevision(workspaceRoot, reqId);
  const results = [];
  const writes = [];
  const diffs = [];
  for (const rel of promotableFiles(kitRoot)) {
    const dest = path.join(workspaceRoot, rel);
    const theirs = fs.readFileSync(path.join(kitRoot, rel));
    const ours = fs.existsSync(dest) ? fs.readFileSync(dest) : null;
    const base = baseContent(workspaceRoot, baseRev, rel);
    const d = decide({ ours, base, theirs, reqId });
    const entry = { path: rel, outcome: d.outcome };
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
  fs.writeFileSync(reportPath, renderReport({ reqId, ts, baseRev, results, promoted }));
  fs.writeFileSync(jsonPath, `${JSON.stringify({ req_id: reqId, strategy: 'auto-merge', timestamp: ts, merge_base: baseRev, promoted, results }, null, 2)}\n`);
  fs.writeFileSync(diffPath, diffs.filter(Boolean).map((d) => (d.endsWith('\n') ? d : `${d}\n`)).join(''));
  const n = (k) => results.filter((r) => r.outcome === k).length;
  const summary = promoted
    ? `${reqId} promoted by auto-merge: ${n('added')} added, ${n('updated')} updated, ${n('merged')} merged, ${n('unchanged') + n('kept_canonical')} unchanged.`
    : `${reqId} NOT promoted: ${n('conflict')} conflict(s); ${written.length} file(s) merged cleanly were written. See the report.`;
  return { ts, promoted, results, written, reportFiles: [reportPath, jsonPath, diffPath], reportPath, summary };
}

module.exports = { autoMergePromotion, decide, promotableFiles, kitBaseRevision, mergeThreeWay, unifiedDiff };
