'use strict';
// The release a passing /finalize delivers, in git and on the code host: the finalize commit names
// the release and its REQs, an annotated tag vN marks it, and the release notes (title, REQs with
// their gate merges, what /finalize changed, how to start, verification, missing information,
// limitations, full changelog) are built from the project documents, not written by an agent.
// Publishing the GitHub Release is the developer's choice (extension.js asks first).
const fs = require('fs');
const path = require('path');
const { execFileSync } = require('child_process');

const RELEASE_RE = /^v(\d+)$/i;
const NOTES_DIR = 'runs/finalize';
const ASSETS = ['docs/harper/FINALIZE_REPORT.md', 'docs/harper/RELEASE_NOTES.md', 'docs/harper/SOLUTION_EVAL.md'];
const MAX_SECTION = 6000;

const releaseNumber = (name) => Number((String(name || '').trim().match(RELEASE_RE) || [])[1] || 0);
const read = (root, rel) => { try { return fs.readFileSync(path.join(root, ...rel.split('/')), 'utf8'); } catch { return ''; } };

function gitIn(root) {
  return (...args) => execFileSync('git', args, { cwd: root, encoding: 'utf8', stdio: ['ignore', 'pipe', 'ignore'] }).trim();
}

/**
 * The `## ` sections of a markdown document, newest first as the documents keep them: a title seen
 * again further down (an earlier finalize run kept as evidence) is skipped, the headings that only
 * mark a run ("Current verification run — …", "Earlier finalize runs — …") are not sections, a `##`
 * inside a code block is code. A document with no `## ` section is one section: its text under the
 * title. Headings lose their "1." numbering.
 */
function sections(md, fallbackTitle = '') {
  const out = [];
  const seen = new Set();
  let cur = null;
  let fence = false;
  const lines = String(md || '').replace(/\r\n/g, '\n').split('\n');
  for (const line of lines) {
    if (/^\s*(```|~~~)/.test(line)) fence = !fence;
    const h = fence ? null : line.match(/^##\s+(.+?)\s*$/);
    if (!h) { if (cur) cur.body.push(line); continue; }
    const title = h[1].replace(/^\d+[.)]\s*/, '');
    const key = title.toLowerCase();
    if (/^(current|earlier|previous|latest)\b.*\b(run|runs|evidence)\b/i.test(title) || seen.has(key)) { cur = null; continue; }
    seen.add(key);
    cur = { title, body: [] };
    out.push(cur);
  }
  const found = out.map((s) => ({ title: s.title, body: s.body.join('\n').trim() })).filter((s) => s.body);
  if (found.length || !fallbackTitle) return found;
  const body = lines.filter((l, i) => !(i === lines.findIndex((x) => /^#\s/.test(x)) && /^#\s/.test(l))).join('\n').trim();
  return body ? [{ title: fallbackTitle, body }] : [];
}

const pick = (list, re) => (list.find((s) => re.test(s.title)) || {}).body || '';

function clip(text, max = MAX_SECTION) {
  const t = String(text || '').trim();
  return t.length > max ? `${t.slice(0, max).replace(/\n[^\n]*$/, '')}\n\n…` : t;
}

/** owner/repo of a GitHub remote URL (https or ssh), or ''. */
function githubRepo(url) {
  const m = String(url || '').trim().match(/github\.com[:/]+([^/\s]+)\/([^/\s]+?)(?:\.git)?\/?$/i);
  return m ? `${m[1]}/${m[2]}` : '';
}

/** The REQs of a plan grouped by release (a REQ without one belongs to v1). */
function planReleases(plan) {
  const reqs = (Array.isArray(plan?.reqs) ? plan.reqs : []).filter((r) => r && r.id);
  const byRelease = new Map();
  for (const r of reqs) {
    const n = Math.max(1, releaseNumber(r.release));
    if (!byRelease.has(n)) byRelease.set(n, []);
    byRelease.get(n).push(r);
  }
  return byRelease;
}

/** REQ id → the newest "merge: REQ-… via gate" commit on HEAD. */
function gateMerges(git) {
  const out = {};
  let log = '';
  try { log = git('log', '--format=%H%x09%s', '--grep=^merge: REQ-', 'HEAD'); } catch { return out; }
  for (const line of log.split('\n')) {
    const [sha, subject] = line.split('\t');
    const m = String(subject || '').match(/^merge:\s+(REQ-[\w-]+)\s+via gate/i);
    if (m && sha && !out[m[1].toUpperCase()]) out[m[1].toUpperCase()] = sha;
  }
  return out;
}

/**
 * Everything the release needs, read from the project: plan.json (release, REQs), git (gate merges,
 * previous release tag, remote), RELEASE_NOTES.md, FINALIZE_REPORT.md, SOLUTION_EVAL.md.
 * `opts.git` overrides the git runner (tests); `opts.status` is the solution eval verdict.
 */
function releaseInfo(root, opts = {}) {
  const git = opts.git || gitIn(root);
  let plan = null;
  try { plan = JSON.parse(read(root, 'docs/harper/plan.json')); } catch { /* no plan */ }
  const groups = planReleases(plan);
  const number = groups.size ? Math.max(...groups.keys()) : 1;
  const release = `v${number}`;
  const reqs = (groups.get(number) || []).map((r) => ({
    id: String(r.id).toUpperCase(), title: String(r.title || '').trim(),
    change: String(r.change || (number === 1 ? 'ADDED' : '')).toUpperCase(), status: String(r.status || 'open').toLowerCase(),
  }));
  const tagExists = (t) => { try { git('rev-parse', '--verify', '--quiet', `refs/tags/${t}`); return true; } catch { return false; } };
  let previousTag = '';
  for (let n = number - 1; n >= 1 && !previousTag; n -= 1) {
    previousTag = [`v${n}`, `harper/v${n}`].find(tagExists) || '';
  }
  let remoteUrl = '';
  try { remoteUrl = git('remote', 'get-url', opts.remote || 'origin'); } catch { /* no remote */ }
  const notes = sections(read(root, 'docs/harper/RELEASE_NOTES.md'), 'Release notes');
  const report = sections(read(root, 'docs/harper/FINALIZE_REPORT.md'));
  const evalMd = read(root, 'docs/harper/SOLUTION_EVAL.md');
  const status = String(opts.status || (evalMd.match(/Result:\s*\*\*([A-Z_]+)\*\*/) || [])[1] || '').toUpperCase();
  return {
    release, number, tag: release, project: String(plan?.project || path.basename(root)).trim(),
    reqs, merges: gateMerges(git), previousTag, tagExists: tagExists(release),
    repo: githubRepo(remoteUrl), remoteUrl, status,
    prerelease: status === 'PASS_WITH_WARNINGS',
    notes, report,
    assets: ASSETS.filter((rel) => fs.existsSync(path.join(root, ...rel.split('/')))),
  };
}

function changeSummary(reqs) {
  const counts = {};
  for (const r of reqs) if (r.change) counts[r.change] = (counts[r.change] || 0) + 1;
  const parts = Object.entries(counts).map(([k, n]) => `${k} ${n}`);
  return `${reqs.length} REQ${parts.length ? ` (${parts.join(', ')})` : ''}`;
}

const releaseTitle = (info) => `${info.project} ${info.release}`;

/** The finalize commit: the release, its REQs and the run, instead of a bare "chore: finalize". */
function finalizeCommitMessage(info, runId) {
  const list = info.reqs.slice(0, 60).map((r) => `- ${r.id} ${r.title}${r.change ? ` (${r.change})` : ''}`);
  if (info.reqs.length > 60) list.push(`- … ${info.reqs.length - 60} more`);
  return [
    `chore(release): finalize ${info.release} — ${info.project}`,
    '',
    `Release ${info.release}: ${changeSummary(info.reqs)}${info.previousTag ? `, since ${info.previousTag}` : ''}.`,
    ...(list.length ? ['', ...list] : []),
    '',
    `[harper:finalize] runId=${runId}`,
  ].join('\n');
}

/** The commit of the solution eval evidence after a verification. */
function evidenceCommitMessage(info, status, runId) {
  return `chore(release): ${info.release} solution evaluation ${status || 'evidence'}\n\n[harper:finalize] runId=${runId}`;
}

/** The message of the annotated tag vN. */
function tagMessage(info) {
  return [
    releaseTitle(info),
    '',
    `${changeSummary(info.reqs)}: ${info.reqs.map((r) => r.id).join(', ') || 'none'}.`,
    `Solution evaluation: ${info.status || 'not recorded'}.`,
    info.previousTag ? `Previous release: ${info.previousTag}.` : '',
    'Release notes: docs/harper/RELEASE_NOTES.md · report: docs/harper/FINALIZE_REPORT.md',
  ].filter((l) => l !== '').join('\n');
}

/** The GitHub Release body: built from the project documents, citing REQs and commits. */
function releaseNotesMarkdown(info) {
  const base = info.repo ? `https://github.com/${info.repo}` : '';
  const commit = (sha) => (sha ? (base ? `[\`${sha.slice(0, 7)}\`](${base}/commit/${sha})` : `\`${sha.slice(0, 7)}\``) : '—');
  const doc = (rel) => (base ? `[${path.basename(rel)}](${base}/blob/${info.tag}/${rel})` : `\`${rel}\``);
  const out = [];
  const scope = pick(info.notes, /scope|overview|summary|highlights/i) || pick(info.report, /solution/i);
  out.push(`## ${releaseTitle(info)}`, '');
  out.push(`${changeSummary(info.reqs)}${info.previousTag ? ` since ${info.previousTag}` : ''} · solution evaluation **${info.status || 'not recorded'}**`);
  if (scope) out.push('', clip(scope, 3000));
  if (info.reqs.length) {
    out.push('', '## Requirements delivered', '', '| REQ | Title | Change | Gate merge |', '|---|---|---|---|');
    for (const r of info.reqs) out.push(`| ${r.id} | ${r.title.replace(/\|/g, '\\|')} | ${r.change || '—'} | ${commit(info.merges[r.id])} |`);
  }
  const used = new Set();
  const add = (title, body) => { if (body) out.push('', `## ${title}`, '', clip(body)); };
  for (const s of info.notes) {
    if (/scope|overview|summary|highlights/i.test(s.title)) continue;
    used.add(s.title.toLowerCase());
    add(s.title, s.body);
  }
  const fromReport = [
    ['How to start and see it', /\bstart\b|how to run/i],
    ['Missing information', /missing/i],
    ['Problems and verification', /problem|verification/i],
    ['Remaining limitations', /limitation/i],
  ];
  for (const [title, re] of fromReport) {
    const s = info.report.find((x) => re.test(x.title));
    if (s && !used.has(s.title.toLowerCase()) && ![...used].some((u) => re.test(u))) add(title, s.body);
  }
  out.push('', '## Documents', '', ...info.assets.map((rel) => `- ${doc(rel)}`));
  if (base && info.previousTag) out.push('', `**Full changelog**: ${base}/compare/${info.previousTag}...${info.tag}`);
  return `${out.join('\n').trim()}\n`;
}

/** Writes the notes to runs/finalize/RELEASE_<vN>.md; returns the workspace-relative path. */
function writeReleaseNotes(root, info) {
  const rel = `${NOTES_DIR}/RELEASE_${info.release}.md`;
  const file = path.join(root, ...rel.split('/'));
  fs.mkdirSync(path.dirname(file), { recursive: true });
  fs.writeFileSync(file, releaseNotesMarkdown(info));
  return rel;
}

/**
 * The annotated tag vN on HEAD. Kept when it already marks HEAD; an existing vN elsewhere is never
 * moved (it may be published): { tag, created, error }.
 */
function tagRelease(root, info, opts = {}) {
  const git = opts.git || gitIn(root);
  try {
    const head = git('rev-parse', 'HEAD');
    if (info.tagExists) {
      const at = git('rev-list', '-n', '1', info.tag);
      if (at === head) return { tag: info.tag, created: false };
      return { tag: info.tag, created: false, error: `tag ${info.tag} already marks ${at.slice(0, 7)}, not HEAD ${head.slice(0, 7)}: ` +
        `it is not moved (it may be published). Delete it (git tag -d ${info.tag}) to release again.` };
    }
    try { git('tag', '-a', info.tag, '-m', tagMessage(info)); } catch { git('tag', info.tag); }
    return { tag: info.tag, created: true };
  } catch (e) {
    return { tag: '', created: false, error: `not a git repository with commits (${String(e?.message || e).split('\n')[0]})` };
  }
}

/** The gh arguments creating (or, when it exists, editing) the GitHub Release with every field. */
function ghReleaseArgs(info, notesFile, { exists = false } = {}) {
  const fields = ['--title', releaseTitle(info), '--notes-file', notesFile, '--latest'];
  if (info.prerelease) fields.push('--prerelease');
  if (exists) return [['release', 'edit', info.tag, ...fields, '--draft=false'], ...(info.assets.length ? [['release', 'upload', info.tag, ...info.assets, '--clobber']] : [])];
  return [['release', 'create', info.tag, ...fields, '--verify-tag', ...info.assets]];
}

module.exports = {
  ASSETS, sections, githubRepo, planReleases, gateMerges, releaseInfo, releaseTitle, changeSummary,
  finalizeCommitMessage, evidenceCommitMessage, tagMessage, releaseNotesMarkdown, writeReleaseNotes, tagRelease, ghReleaseArgs,
};
