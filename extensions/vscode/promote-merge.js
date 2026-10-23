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
const { KIT_ROOT_DIR, rootPolicy, isAllowedRootPath } = require('./root-files-policy');

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

/**
 * Candidate files to promote: [{ kitRel, rel }] — kitRel inside the KIT, rel in the repository.
 * src/, test/, tests/ keep their path; root/<path> (repository-root deliverables: scripts/,
 * deploy/, root manifests…) is promoted to <path> when the root policy allows it, otherwise it
 * is listed with `rejected` (never written).
 */
function promotableEntries(kitRoot, policy) {
  const entries = promotableFiles(kitRoot).map((rel) => ({ kitRel: rel, rel }));
  const prefix = `${KIT_ROOT_DIR}/`;
  for (const kitRel of walkFiles(path.join(kitRoot, KIT_ROOT_DIR), KIT_ROOT_DIR)) {
    const rel = kitRel.slice(prefix.length);
    entries.push(isAllowedRootPath(rel, policy) ? { kitRel, rel } : { kitRel, rel, rejected: true });
  }
  return entries;
}

function walkFiles(dir, rel) {
  const out = [];
  let entries = [];
  try { entries = fs.readdirSync(dir, { withFileTypes: true }); } catch { return out; }
  for (const e of entries.sort((a, b) => a.name.localeCompare(b.name))) {
    const childRel = `${rel}/${e.name}`;
    if (e.isDirectory()) {
      if (!SCRATCH_DIRS.has(e.name) && !e.name.endsWith('.egg-info')) out.push(...walkFiles(path.join(dir, e.name), childRel));
    } else if (e.isFile() && !SCRATCH_FILE_RE.test(e.name)) {
      out.push(childRel);
    }
  }
  return out;
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
function baseContent(workspaceRoot, rev, rel, dependencies = [], kitRel = rel) {
  for (const dep of [...dependencies].reverse()) {
    const candidate = path.join(workspaceRoot, 'runs', 'kit', dep, kitRel);
    if (fs.existsSync(candidate)) return { content: fs.readFileSync(candidate), from: dep };
  }
  if (!rev) return null;
  // cat-file, not show: for a path with [ ] (Next.js dynamic routes such as app/runs/[run_id]/)
  // that is not in rev, `git show rev:path` exits 0 with no output, i.e. an empty base file.
  const r = git(workspaceRoot, ['cat-file', 'blob', `${rev}:${rel}`]);
  return r.code === 0 ? { content: r.stdout, from: 'git' } : null;
}

/** git merge-file: {text, conflicts} (conflicts = number of conflict hunks). */
function mergeThreeWay(ours, base, theirs, reqId, tested = false) {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'clike-merge-'));
  try {
    const [o, b, t] = ['ours', 'base', 'theirs'].map((n) => path.join(dir, n));
    fs.writeFileSync(o, ours); fs.writeFileSync(b, base); fs.writeFileSync(t, theirs);
    const r = spawnSync('git', ['merge-file', '-p', '--diff3', '-L', 'canonical', '-L', 'base', '-L', reqId, o, b, t], { encoding: 'buffer' });
    if (r.status == null || r.status < 0) throw new Error(`git merge-file failed: ${String(r.stderr || r.error || '')}`);
    if (r.status === 0) return { text: r.stdout, conflicts: 0, unions: 0, contained: 0, already: 0, rewritten: 0, rewrites: [] };
    return resolveHunks(r.stdout, r.status, reqId, tested, theirs.toString('utf8'));
  } finally {
    fs.rmSync(dir, { recursive: true, force: true });
  }
}

/** Split git merge-file --diff3 output into context lines and conflict hunks, in order. */
function parseConflictHunks(text, reqId) {
  const lines = text.split('\n');
  const parts = [];
  let i = 0;
  let canonicalLine = 1;
  while (i < lines.length) {
    if (!lines[i].startsWith('<<<<<<< canonical')) { parts.push(lines[i]); canonicalLine += 1; i += 1; continue; }
    const hunk = { ours: [], base: null, theirs: [], line: canonicalLine };
    let part = hunk.ours; i += 1;
    while (i < lines.length && !lines[i].startsWith(`>>>>>>> ${reqId}`)) {
      if (lines[i].startsWith('||||||| base')) { hunk.base = []; part = hunk.base; }
      else if (lines[i] === '=======') part = hunk.theirs;
      else part.push(lines[i]);
      i += 1;
    }
    i += 1; // closing marker
    canonicalLine += hunk.ours.length;
    parts.push(hunk);
  }
  return parts;
}

// Words, numbers and single punctuation marks; whitespace does not count.
const tokens = (lines) => lines.join('\n').match(/[A-Za-z0-9_]+|[^\sA-Za-z0-9_]/g) || [];

/** True when every token of `small`, in order, is also in `big` (big only inserts). */
function containsInOrder(big, small) {
  let j = 0;
  for (let k = 0; k < big.length && j < small.length; k += 1) if (big[k] === small[j]) j += 1;
  return j === small.length;
}

// A line that identifies code (not a brace, a blank or a short keyword): what a repeated merge
// would duplicate.
const significant = (line) => line.trim().length >= 12 && /[A-Za-z0-9]/.test(line);

/** Share of the tokens of `line` (as a multiset) that `other` has too. */
function tokenOverlap(line, other) {
  const want = tokens([line]);
  if (!want.length) return 1;
  const have = new Map();
  for (const t of tokens([other])) have.set(t, (have.get(t) || 0) + 1);
  let hit = 0;
  for (const t of want) {
    const n = have.get(t) || 0;
    if (n) { hit += 1; have.set(t, n - 1); }
  }
  return hit / want.length;
}

const REWRITE_OVERLAP = 0.6;

const words = (line) => String(line).match(/[A-Za-z0-9_]+/g) || [];

/**
 * The lines of one spot, read as a developer would: src/ lines the candidate rewrote (paired with
 * their new form: most of their words are still there, and none of their words is gone from the
 * candidate file — a renamed expression is defined elsewhere in it), src/ lines the candidate drops
 * or loses part of (`missing`: their words the candidate file no longer has), and its new lines.
 * `theirsText`: the whole candidate file (default: the spot).
 */
function classifyHunk(ours, theirs, theirsText = theirs.join('\n')) {
  const present = new Set(words(theirsText));
  const diff = hunkDiff(ours, theirs);
  const removed = diff.filter((l) => l.startsWith('-')).map((l) => l.slice(1));
  const added = diff.filter((l) => l.startsWith('+')).map((l) => l.slice(1));
  const used = new Set();
  const rewritten = [];
  const dropped = [];
  for (const line of removed) {
    if (!significant(line)) continue;
    let best = -1; let score = 0;
    added.forEach((cand, k) => {
      const v = tokenOverlap(line, cand);
      if (v > score) { score = v; best = k; }
    });
    const missing = [...new Set(words(line).filter((w) => !present.has(w)))];
    if (best >= 0 && score >= REWRITE_OVERLAP && !missing.length) { rewritten.push({ from: line, to: added[best] }); used.add(best); }
    else {
      if (best >= 0 && score >= REWRITE_OVERLAP) used.add(best);
      dropped.push({ line, missing });
    }
  }
  const fresh = added.filter((l, k) => !used.has(k) && l.trim());
  return { rewritten, dropped, added: fresh };
}

/**
 * How one conflict hunk resolves without a human, or null:
 * - both sides only ADDED lines at the same place (empty base, e.g. new entries at the end of
 *   .env.example): the side that already contains the other wins (a REQ promoted again, or a KIT
 *   whose base is older than src/, adds lines src/ already has: keeping both repeated them at
 *   every gate); additions that share lines without one containing the other are a conflict;
 *   otherwise keep both, canonical first;
 * - the candidate holds the whole canonical side plus its own additions (a later KIT rewrote the
 *   same line from the code an earlier REQ had already promoted): keep the candidate. Nothing of
 *   src/ is lost and the candidate is exactly what the gate tested (the KIT file wins in the
 *   eval workspace). The opposite (canonical contains the candidate) stays a conflict: keeping
 *   src/ would promote code the gate did not test.
 */
function resolveHunk(hunk, { tested = false, theirsText } = {}) {
  if (hunk.base && hunk.base.every((l) => l.trim() === '')) {
    const oursTokens = tokens(hunk.ours);
    const theirsTokens = tokens(hunk.theirs);
    if (!theirsTokens.length || containsInOrder(oursTokens, theirsTokens)) return { lines: hunk.ours, how: 'already' };
    if (!oursTokens.length || containsInOrder(theirsTokens, oursTokens)) return { lines: hunk.theirs, how: 'contains' };
    const ourLines = new Set(hunk.ours.filter(significant).map((l) => l.trim()));
    if (!hunk.theirs.some((l) => significant(l) && ourLines.has(l.trim()))) return { lines: [...hunk.ours, ...hunk.theirs], how: 'union' };
    return rewrittenByCandidate(hunk, tested, theirsText);
  }
  const ours = tokens(hunk.ours);
  if (ours.length && containsInOrder(tokens(hunk.theirs), ours)) return { lines: hunk.theirs, how: 'contains' };
  return rewrittenByCandidate(hunk, tested, theirsText);
}

/**
 * The candidate rewrote src/ lines without dropping any (each src/ line left out has its new form
 * there) and the gate ran this very candidate with the regression of the promoted REQs (`tested`):
 * keep the candidate; the rewritten pairs go to the report for review. Otherwise null.
 */
function rewrittenByCandidate(hunk, tested, theirsText) {
  if (!tested || !hunk.theirs.length) return null;
  const c = classifyHunk(hunk.ours, hunk.theirs, theirsText);
  return !c.dropped.length && c.rewritten.length ? { lines: hunk.theirs, how: 'rewritten', rewrites: c.rewritten } : null;
}

/** Resolve what resolveHunk can; the rest stays as conflict markers (fewer to resolve by hand). */
function resolveHunks(buf, conflicts, reqId, tested = false, theirsText) {
  const out = [];
  const counts = { union: 0, contains: 0, already: 0, rewritten: 0 };
  const rewrites = [];
  let left = 0;
  for (const part of parseConflictHunks(buf.toString('utf8'), reqId)) {
    if (typeof part === 'string') { out.push(part); continue; }
    const r = resolveHunk(part, { tested, theirsText });
    if (r) {
      out.push(...r.lines); counts[r.how] += 1;
      if (r.rewrites) rewrites.push({ line: part.line, pairs: r.rewrites });
      continue;
    }
    left += 1;
    out.push('<<<<<<< canonical', ...part.ours);
    if (part.base) out.push('||||||| base', ...part.base);
    out.push('=======', ...part.theirs, `>>>>>>> ${reqId}`);
  }
  return {
    text: Buffer.from(out.join('\n'), 'utf8'), conflicts: left, unions: counts.union, contained: counts.contains, already: counts.already,
    rewritten: counts.rewritten, rewrites,
  };
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

const FENCE_LANG = { ts: 'ts', tsx: 'tsx', js: 'js', mjs: 'js', cjs: 'js', jsx: 'jsx', py: 'python', json: 'json', css: 'css', md: 'md', yml: 'yaml', yaml: 'yaml', toml: 'toml', sh: 'sh', sql: 'sql', html: 'html' };

function fenced(lines, lang = '') {
  const body = lines.join('\n');
  const fence = body.includes('```') ? '~~~~' : '```';
  return [`${fence}${lang}`, ...(lines.length ? lines : ['(nothing: this side has no lines here)']), fence];
}

/** Line diff of one hunk, canonical → candidate, without file headers. */
function hunkDiff(ours, theirs) {
  const diff = unifiedDiff('x', Buffer.from(`${ours.join('\n')}\n`), Buffer.from(`${theirs.join('\n')}\n`));
  return diff.split('\n').filter((l) => !/^(diff --git|--- |\+\+\+ |@@ )/.test(l) && l !== '');
}

/**
 * conflicts.md: every spot still in conflict, read for the developer: what src/ has now, what the
 * REQ wants, the diff, and line by line what the REQ rewrote, what it would drop and what it adds;
 * then what to do, with the commands.
 */
/** The merge with every remaining conflict spot taken from the candidate (the rest as merged). */
function takeCandidateSpots(markers, reqId) {
  return parseConflictHunks(markers.toString('utf8'), reqId).flatMap((p) => (typeof p === 'string' ? [p] : p.theirs)).join('\n');
}

function renderConflicts({ reqId, ts, conflicts }) {
  const lines = [
    `# ${reqId} — conflicts to resolve (${ts})`,
    '',
    `Nothing of these files was written: src/ is as before. ${reqId} was tested by the gate with **its own version** of`,
    'each file (in the eval the KIT file replaces src/, and the regression of the promoted REQs ran with it).',
    '',
    'For each spot below:',
    '',
    `1. **Rewritten by ${reqId}** — a src/ line ${reqId} changed into a new form: its meaning is kept, check the new form.`,
    `2. **Only in src/** — lines ${reqId} would drop: an earlier REQ put them there. Keep them, unless ${reqId} removes them on purpose.`,
    `3. **Only in ${reqId}** — its additions.`,
    '',
    `When a file has nothing under *Only in src/*, ${reqId}'s version keeps everything: take it (the command is given).`,
    `Otherwise start from ${reqId}'s version and put back the *Only in src/* lines, adapted. Then delete the`,
    `\`.conflict-…\` file and run \`/gate ${reqId}\` again (it promotes every other file too).`,
    '',
  ];
  const commands = [];
  for (const r of conflicts) {
    const lang = FENCE_LANG[path.extname(r.path).slice(1).toLowerCase()] || '';
    const hunks = r.markers ? parseConflictHunks(r.markers.toString('utf8'), reqId).filter((p) => typeof p !== 'string') : [];
    const kitPath = `runs/kit/${reqId}/${r.kit_path || r.path}`;
    lines.push(`## \`${r.path}\``, '', `${r.reason}${r.conflictFile ? ` — markers in \`${r.conflictFile}\`` : ''}`, '');
    if (!hunks.length) {
      lines.push('No text to compare (binary, or removed from src/ after the KIT): decide by hand which file to keep.', '');
      continue;
    }
    let dropsAny = false;
    hunks.forEach((h, n) => {
      const c = classifyHunk(h.ours, h.theirs, r.theirs ? r.theirs.toString('utf8') : undefined);
      if (c.dropped.length) dropsAny = true;
      lines.push(`### Spot ${n + 1} of ${hunks.length} — line ${h.line} of src/`, '');
      if (c.rewritten.length) {
        lines.push(`**1. Rewritten by ${reqId}** (${c.rewritten.length})`, '', '```diff',
          ...c.rewritten.flatMap((p) => [`- ${p.from.trim()}`, `+ ${p.to.trim()}`]), '```', '');
      }
      lines.push(`**2. Only in src/** (${c.dropped.length})`, '');
      lines.push(...(c.dropped.length ? fenced(c.dropped.map((d) => d.line.trim()), lang) : ['None: nothing of src/ is lost here.']), '');
      const lost = [...new Set(c.dropped.flatMap((d) => d.missing))];
      if (lost.length) lines.push(`${reqId}'s file no longer has: ${lost.map((w) => `\`${w}\``).join(', ')}.`, '');
      lines.push(`**3. Only in ${reqId}** (${c.added.length})`, '');
      lines.push(...(c.added.length ? fenced(c.added.map((l) => l.trim()), lang) : ['None.']), '');
      lines.push('<details><summary>Both versions in full, the diff and the base</summary>', '');
      lines.push('**src/ now**', '', ...fenced(h.ours, lang), '');
      lines.push(`**${reqId} wants**`, '', ...fenced(h.theirs, lang), '');
      lines.push(`**src/ → ${reqId}** (\`-\` only in src/, \`+\` only in ${reqId})`, '', ...fenced(hunkDiff(h.ours, h.theirs), 'diff'), '');
      if (h.base) lines.push('**base** (what the KIT started from)', '', ...fenced(h.base, lang), '');
      lines.push('</details>', '');
      const theirsInOurs = h.theirs.length && containsInOrder(tokens(h.ours), tokens(h.theirs));
      lines.push(theirsInOurs
        ? `**What to do:** src/ already holds everything ${reqId} adds here, plus more: keeping src/ is likely right, but ${reqId} was tested with its own version, so run \`/gate ${reqId}\` and check its tests.`
        : c.dropped.length
          ? `**What to do:** keep the ${c.dropped.length} line(s) under *Only in src/* and add what ${reqId} needs (rewritten lines and its additions).`
          : `**What to do:** nothing of src/ is lost here: ${reqId}'s version is right for this spot.`, '');
    });
    const sameAsCandidate = r.theirs && takeCandidateSpots(r.markers, reqId).replace(/\n+$/, '') === r.theirs.toString('utf8').replace(/\n+$/, '');
    if (!dropsAny && sameAsCandidate) {
      lines.push(`**This file:** ${reqId}'s version keeps every line of src/ (rewritten or unchanged): take it whole.`, '',
        '```bash', `cp ${kitPath} ${r.path}`, ...(r.conflictFile ? [`rm ${r.conflictFile}`] : []), '```', '');
      commands.push(`cp ${kitPath} ${r.path}`);
    } else if (!dropsAny) {
      lines.push(`**This file:** take ${reqId}'s side of every spot, but not the whole ${kitPath}: elsewhere src/ has changes`,
        `${reqId} lacks (merged cleanly). In \`${r.conflictFile}\` keep, in each marker block, only the lines between`,
        `\`=======\` and \`>>>>>>> ${reqId}\`, delete the markers, and save it as \`${r.path}\`.`, '');
      commands.push(`# ${r.path}: in ${r.conflictFile} keep the ${reqId} side of each block, remove the markers, save as ${r.path}`);
    } else {
      lines.push(`**This file:** write it by hand: start from \`${kitPath}\` and put back the *Only in src/* lines above.`, '');
      commands.push(`# ${r.path}: edit by hand (start from ${kitPath})`);
    }
    if (r.conflictFile) commands.push(`rm ${r.conflictFile}`);
  }
  lines.push('## Commands', '', 'From the project root, on the REQ branch:', '', '```bash', ...commands, '```', '',
    `Then \`/gate ${reqId}\` in the CLike chat.`, '');
  return lines.join('\n');
}

/** Two-way conflict markers (no merge base): the whole canonical file against the candidate. */
/**
 * Significant lines a merge would repeat: added by BOTH sides (since the base) and present in the
 * result more often than in either side. A clean 3-way merge does this when the candidate adds,
 * at another place, lines src/ already received from an earlier REQ. Promoting must be idempotent.
 */
function repeatedLines(ours, base, theirs, merged) {
  const count = (buf) => {
    const m = new Map();
    for (const l of buf.toString('utf8').split('\n')) if (significant(l)) m.set(l.trim(), (m.get(l.trim()) || 0) + 1);
    return m;
  };
  const [o, b, t, r] = [ours, base, theirs, merged].map(count);
  const out = [];
  for (const [line, n] of r) {
    const inOurs = o.get(line) || 0;
    const inTheirs = t.get(line) || 0;
    const inBase = b.get(line) || 0;
    if (inOurs > inBase && inTheirs > inBase && n > Math.max(inOurs, inTheirs)) out.push(line);
  }
  return out;
}

/**
 * Why merged content (new text, which the gate never ran) is not valid for its language, or null.
 * Python compiles, JSON parses, JS/MJS pass `node --check`; a tool that is not installed checks
 * nothing (null). The KIT's own files are not checked: the gate ran them.
 */
function invalidSource(rel, content) {
  const ext = path.extname(rel).toLowerCase();
  const text = content.toString('utf8');
  if (ext === '.json') {
    try { JSON.parse(text); return null; } catch (e) { return `not valid JSON (${String(e.message).slice(0, 120)})`; }
  }
  const run = (cmds, args, input, file) => {
    for (const cmd of cmds) {
      const r = spawnSync(cmd, file ? [...args, file] : args, { input, encoding: 'utf8', timeout: 30000 });
      if (r.error && r.error.code === 'ENOENT') continue;
      if (r.status === 0) return null;
      if (r.status == null) return null;  // timed out: no verdict
      return String(r.stderr || r.stdout || '').split(/\r?\n/).map((l) => l.trim()).filter(Boolean).slice(-2).join(' ').slice(0, 200);
    }
    return null;
  };
  if (ext === '.py') {
    const err = run(['python3', 'python'], ['-c', 'import sys; compile(sys.stdin.read(), sys.argv[1], "exec")', rel], text);
    return err ? `not valid Python (${err})` : null;
  }
  if (['.js', '.mjs', '.cjs'].includes(ext)) {
    const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'clike-check-'));
    try {
      const file = path.join(dir, `check${ext}`);
      fs.writeFileSync(file, content);
      const err = run(['node'], ['--check'], undefined, file);
      return err ? `not valid JavaScript (${err})` : null;
    } finally {
      fs.rmSync(dir, { recursive: true, force: true });
    }
  }
  return null;
}

function twoWayMarkers(ours, theirs, reqId) {
  const nl = (b) => (b.length && b[b.length - 1] !== 10 ? Buffer.concat([b, Buffer.from('\n')]) : b);
  return Buffer.concat([
    Buffer.from('<<<<<<< canonical\n'), nl(ours), Buffer.from('=======\n'), nl(theirs), Buffer.from(`>>>>>>> ${reqId}\n`),
  ]);
}

/** Decide the outcome of one file (pure: no writes). Every conflict carries a marker file. */
function decide({ ours, base, theirs, reqId, tested = false }) {
  const d = decideRaw({ ours, base, theirs, reqId, tested });
  if (d.outcome === 'conflict' && !d.markers && ours && theirs && !isBinary(ours) && !isBinary(theirs)) {
    d.markers = twoWayMarkers(ours, theirs, reqId);
  }
  return d;
}

function decideRaw({ ours, base, theirs, reqId, tested = false }) {
  if (ours == null) return base == null ? { outcome: 'added', content: theirs } : { outcome: 'conflict', reason: 'removed from the canonical root after the KIT' };
  if (ours.equals(theirs)) return { outcome: 'unchanged' };
  if (base != null && ours.equals(base)) return { outcome: 'updated', content: theirs };
  if (base != null && theirs.equals(base)) return { outcome: 'kept_canonical' };
  if (isBinary(ours) || isBinary(theirs) || (base != null && isBinary(base))) {
    return { outcome: 'conflict', reason: base == null ? 'exists in the canonical root with different content and no merge base' : 'binary file changed on both sides' };
  }
  if (base == null) {
    const r = resolveHunk({ ours: ours.toString('utf8').split('\n'), base: null, theirs: theirs.toString('utf8').split('\n') }, { tested, theirsText: theirs.toString('utf8') });
    if (r && r.how === 'rewritten') {
      return { outcome: 'merged', content: theirs, rewrites: [{ line: 1, pairs: r.rewrites }],
        reason: `no merge base; ${reqId} rewrote ${r.rewrites.length} line(s) of src/ without dropping any and the gate tested it with the regression: ${reqId} kept — review the rewritten lines` };
    }
    return r
      ? { outcome: 'merged', content: theirs, reason: `no merge base, but ${reqId} contains the whole canonical file plus its own additions: ${reqId} kept` }
      : { outcome: 'conflict', reason: 'exists in the canonical root with different content and no merge base' };
  }
  const merged = mergeThreeWay(ours, base, theirs, reqId, tested);
  const repeated = merged.conflicts === 0 ? repeatedLines(ours, base, theirs, merged.text) : [];
  if (repeated.length) {
    return {
      outcome: 'conflict',
      reason: `the merge would repeat ${repeated.length} line(s) both sides added (e.g. \`${repeated[0].slice(0, 80)}\`): ` +
        'src/ already has them; write the file once by hand',
    };
  }
  const auto = [
    merged.unions ? `${merged.unions} place(s) where both sides only added lines: both kept` : '',
    merged.contained ? `${merged.contained} place(s) where ${reqId} contains src/ plus its own additions: ${reqId} kept` : '',
    merged.already ? `${merged.already} place(s) where src/ already has what ${reqId} adds: src/ kept` : '',
    merged.rewritten ? `${merged.rewritten} place(s) where ${reqId} rewrote src/ lines without dropping any, tested by the gate with the regression: ${reqId} kept — review the rewritten lines` : '',
  ].filter(Boolean).join('; ');
  const rewrites = merged.rewrites && merged.rewrites.length ? { rewrites: merged.rewrites } : {};
  if (merged.conflicts === 0) return auto ? { outcome: 'merged', content: merged.text, reason: auto, ...rewrites } : { outcome: 'merged', content: merged.text };
  return { outcome: 'conflict', reason: [`${merged.conflicts} overlapping change(s)`, auto].filter(Boolean).join('; '), markers: merged.text, ...rewrites };
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
      'compared. **`conflicts.md`** (next to this report) shows every spot side by side with its diff.',
      'Write the right content into the canonical file, delete the `.conflict-…` file and run',
      '`/gate ' + `${reqId}\` again: the REQ becomes done when no conflict is left.`,
      '',
      ...conflicts.map((r) => `- \`${r.path}\`: ${r.reason}${r.conflictFile ? ` → \`${r.conflictFile}\`` : ''}`),
      '',
    );
  }
  const reviewed = results.filter((r) => r.rewrites && r.rewrites.length);
  if (reviewed.length) {
    lines.push('## Rewritten lines kept from ' + reqId + ' (review)', '',
      `${reqId} rewrote these lines of src/ (each src/ line has its new form, none dropped) and the gate ran this version with`,
      'the regression of the promoted REQs, so it was promoted. Check that each rewrite keeps what the earlier REQ meant.', '');
    for (const r of reviewed) {
      lines.push(`### \`${r.path}\``, '');
      for (const spot of r.rewrites) {
        for (const pair of spot.pairs) lines.push('```diff', `- ${pair.from.trim()}`, `+ ${pair.to.trim()}`, '```');
      }
      lines.push('');
    }
  }
  lines.push('Outcomes: `added` new file · `updated` canonical unchanged since the KIT, candidate written · `merged` both changed, merged cleanly · `kept_canonical` only the canonical side changed · `unchanged` identical · `conflict` overlapping changes, not written · `rejected` a root/ file outside the repository-root policy, not written.', '');
  return lines.join('\n');
}

/**
 * Promote reqId with a 3-way merge per file. Returns
 * { ts, promoted, results, written, reportFiles, reportPath, summary }.
 */
const sha = (buf) => require('crypto').createHash('sha256').update(buf).digest('hex');

/**
 * Conflicts of earlier promotions of this REQ the developer resolved: the conflict file was
 * deleted (what conflicts.md asks once src/ holds the right content) and the KIT file is the one
 * that conflicted (same digest, when the report recorded it). A resolved file keeps src/: without
 * this, the same 3-way merge raised the same conflict at every gate.
 * → Map<path, {ts}>
 */
function resolvedConflicts(workspaceRoot, kitRoot, theirsDigest) {
  const resolved = new Map();
  const dir = path.join(kitRoot, 'promotion');
  let stamps = [];
  try { stamps = fs.readdirSync(dir).sort(); } catch { return resolved; }
  for (const ts of stamps) {
    let report;
    try { report = JSON.parse(fs.readFileSync(path.join(dir, ts, 'report.json'), 'utf8')); } catch { continue; }
    for (const r of report.results || []) {
      if (r.outcome !== 'conflict' || !r.conflictFile || !r.path) continue;
      const stillThere = fs.existsSync(path.join(workspaceRoot, r.conflictFile));
      const sameKit = !r.theirs_sha256 || r.theirs_sha256 === theirsDigest(r.path);
      if (!stillThere && sameKit) resolved.set(r.path, { ts });
      else resolved.delete(r.path);
    }
  }
  return resolved;
}

function autoMergePromotion({ workspaceRoot, reqId, now = new Date(), tested = false }) {
  const ts = now.toISOString().replace(/[:.]/g, '-');
  const kitRoot = path.join(workspaceRoot, 'runs', 'kit', reqId);
  const baseInfo = kitBaseRevision(workspaceRoot, reqId);
  const baseRev = baseInfo ? baseInfo.rev : null;
  const dependencies = planDependencies(workspaceRoot, reqId);
  const results = [];
  const writes = [];
  const diffs = [];
  const conflictDetails = [];
  const entries = promotableEntries(kitRoot, rootPolicy(workspaceRoot));
  const kitPathOf = new Map(entries.map((e) => [e.rel, e.kitRel]));
  const resolved = resolvedConflicts(workspaceRoot, kitRoot, (rel) => {
    try { return sha(fs.readFileSync(path.join(kitRoot, kitPathOf.get(rel) || rel))); } catch { return null; }
  });
  for (const { kitRel, rel, rejected } of entries) {
    if (rejected) {
      results.push({ path: rel, kit_path: kitRel, outcome: 'rejected', reason: 'not a repository-root path a KIT may deliver (.clike/project.json root_folders / root_files)' });
      continue;
    }
    const dest = path.join(workspaceRoot, rel);
    const theirs = fs.readFileSync(path.join(kitRoot, kitRel));
    const ours = fs.existsSync(dest) ? fs.readFileSync(dest) : null;
    const baseFile = baseContent(workspaceRoot, baseRev, rel, dependencies, kitRel);
    let d = decide({ ours, base: baseFile ? baseFile.content : null, theirs, reqId, tested });
    if (d.outcome === 'merged' && d.content && !d.content.equals(theirs)) {
      const invalid = invalidSource(rel, d.content);
      if (invalid) {
        d = { outcome: 'conflict', reason: `the merged file is ${invalid}: not written`, markers: twoWayMarkers(ours, theirs, reqId) };
      }
    }
    if (d.outcome === 'conflict' && ours && resolved.has(rel)) {
      d = { outcome: 'kept_canonical', reason: `conflict of ${resolved.get(rel).ts} resolved in src/ (its conflict file was removed): src/ kept` };
    }
    const entry = { path: rel, outcome: d.outcome };
    if (kitRel !== rel) entry.kit_path = kitRel;
    if (baseFile && baseFile.from !== 'git' && d.outcome !== 'added' && d.outcome !== 'unchanged') entry.base = baseFile.from;
    if (d.reason) entry.reason = d.reason;
    if (d.rewrites && d.outcome !== 'conflict') entry.rewrites = d.rewrites;
    if (d.content) {
      const diff = isBinary(d.content) ? `Binary file ${rel} ${ours ? 'changed' : 'added'}\n` : unifiedDiff(rel, ours, d.content);
      entry.stats = lineStats(diff);
      diffs.push(diff);
      writes.push({ dest, content: d.content });
    }
    if (d.outcome === 'conflict') entry.theirs_sha256 = sha(theirs);
    if (d.outcome === 'conflict' && d.markers) {
      entry.conflictFile = `${rel}.conflict-${reqId}-${ts}`;
      writes.push({ dest: path.join(workspaceRoot, entry.conflictFile), content: d.markers, conflict: true });
    }
    if (d.outcome === 'conflict') conflictDetails.push({ ...entry, markers: d.markers, theirs });
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
  const reportFiles = [reportPath, jsonPath, diffPath];
  if (conflictDetails.length) {
    const conflictsPath = path.join(reportDir, 'conflicts.md');
    fs.writeFileSync(conflictsPath, renderConflicts({ reqId, ts, conflicts: conflictDetails }));
    reportFiles.push(conflictsPath);
  }
  const n = (k) => results.filter((r) => r.outcome === k).length;
  const summary = promoted
    ? `${reqId} promoted by auto-merge: ${n('added')} added, ${n('updated')} updated, ${n('merged')} merged, ${n('unchanged') + n('kept_canonical')} unchanged${n('rejected') ? `, ${n('rejected')} root file(s) rejected (see the report)` : ''}.`
    : `${reqId} NOT promoted: ${n('conflict')} conflict(s); ${written.length} file(s) merged cleanly were written. Each spot to resolve, with its diff: runs/kit/${reqId}/promotion/${ts}/conflicts.md`;
  return { ts, promoted, results, written, reportFiles, reportPath, summary };
}

module.exports = { autoMergePromotion, promotableEntries, baseContent, classifyHunk, decide, invalidSource, renderConflicts, resolveHunk, planDependencies, promotableFiles, kitBaseRevision, mergeThreeWay, unifiedDiff };
