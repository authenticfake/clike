'use strict';
// /finalize verification (no flag): after /finalize, CLike runs ci/SOLUTION_LTC.json — the eval
// profile of the whole solution: install, build, configure, start, smoke; the REQs' test suites are
// not run again, every REQ passed them at its gate — in the eval sandbox against the canonical
// tree; when it fails, /finalize runs again with the errors, a bounded number of cycles (same loop
// rules as auto-eval). This module gathers what the finalize model needs and writes the evidence.
const fs = require('fs');
const path = require('path');

const SOLUTION_PROFILE = 'ci/SOLUTION_LTC.json';
const SOLUTION_EVAL_ID = 'SOLUTION';
const EVIDENCE_PATH = 'docs/harper/SOLUTION_EVAL.md';
const REPORT_PATH = 'docs/harper/FINALIZE_REPORT.md';
const CLIKE_REPO_URL = 'https://github.com/authenticfake/clike';
const PROMOTED_STATUSES = new Set(['done']);

const MAX_FILE_BYTES = 200 * 1024;
const MAX_FILES = 400;
const SKIPPED_DIRS = new Set([
  'node_modules', '.venv', 'venv', '__pycache__', '.pytest_cache', '.mypy_cache', '.ruff_cache', '.next',
  'dist', 'build', 'coverage', 'reports', '.tmp', 'tmp', '.cache', '.npm-cache', 'local-eval-workspaces', '.git',
]);
// What a solution repair may need to read: the canonical code and tests, scripts, the profile,
// run docs and root manifests (runs/, .clike/ and private docs are not the solution).
const SOLUTION_ROOTS = ['src', 'test', 'tests', 'scripts', 'ci', 'infra', 'deploy', 'config', 'configs'];
const SOLUTION_FILES = [
  'README.md', 'docs/harper/HOWTO_RUN.md', 'docs/harper/SANITY_CHECKS.md', EVIDENCE_PATH, REPORT_PATH, '.env.example',
  'package.json', 'pyproject.toml', 'requirements.txt', 'pom.xml', 'build.gradle', 'go.mod', 'Cargo.toml',
  'docker-compose.yml', 'docker-compose.yaml', 'compose.yml', 'compose.yaml', 'Dockerfile', 'Makefile',
];

// The developer's working-tree changes before the first /finalize of a round, {path: sha1}: kept
// until a /finalize commit succeeds, so the work of a run that ended before its commit is not
// mistaken for the developer's at the next run (runs/ is never committed).
const BASELINE_PATH = 'runs/finalize/DIRTY_BEFORE.json';

function fileSha1(absPath) {
  try { return require('crypto').createHash('sha1').update(fs.readFileSync(absPath)).digest('hex'); } catch { return 'missing'; }
}

function ensureDirtyBaseline(workspaceRoot) {
  const full = path.join(workspaceRoot, ...BASELINE_PATH.split('/'));
  if (fs.existsSync(full)) return readDirtyBaseline(workspaceRoot);
  let raw = '';
  try {
    raw = require('child_process').execFileSync('git', ['status', '--porcelain', '--untracked-files=all'], {
      cwd: workspaceRoot, encoding: 'utf8', stdio: ['ignore', 'pipe', 'ignore'],
    });
  } catch {
    return null;
  }
  const files = {};
  for (const line of raw.split(/\r?\n/).map((l) => l.trimEnd()).filter(Boolean)) {
    const p = line.slice(3).trim();
    const rel = (p.includes(' -> ') ? p.split(' -> ').pop() : p).replace(/^"(.*)"$/, '$1');
    if (!rel.startsWith('runs/')) files[rel] = fileSha1(path.join(workspaceRoot, rel));
  }
  fs.mkdirSync(path.dirname(full), { recursive: true });
  fs.writeFileSync(full, JSON.stringify({ created_at: new Date().toISOString(), files }, null, 1));
  return files;
}

function readDirtyBaseline(workspaceRoot) {
  try {
    return JSON.parse(fs.readFileSync(path.join(workspaceRoot, ...BASELINE_PATH.split('/')), 'utf8')).files || null;
  } catch {
    return null;
  }
}

function clearDirtyBaseline(workspaceRoot) {
  try { fs.rmSync(path.join(workspaceRoot, ...BASELINE_PATH.split('/')), { force: true }); } catch { /* best effort */ }
}

function readPlanReqs(workspaceRoot) {
  try {
    const plan = JSON.parse(fs.readFileSync(path.join(workspaceRoot, 'docs', 'harper', 'plan.json'), 'utf8'));
    return (plan.reqs || plan.req || []).filter((r) => r && typeof r === 'object' && r.id);
  } catch {
    return [];
  }
}

/** REQs of the plan not promoted yet (status other than done): /finalize asks before it runs. */
function pendingReqs(workspaceRoot) {
  return readPlanReqs(workspaceRoot)
    .filter((r) => !PROMOTED_STATUSES.has(String(r.status || '').trim().toLowerCase()))
    .map((r) => ({ id: String(r.id), status: String(r.status || 'open') }));
}

/**
 * REQ branches not merged into the default branch (e.g. merge-on-gate off or failed): /finalize
 * commits on the default branch, where those REQs are missing. Empty when git cannot answer.
 */
function unmergedReqBranches(workspaceRoot, defaultBranch = 'main', prefix = 'feature') {
  const git = (...args) => require('child_process').execFileSync('git', args, {
    cwd: workspaceRoot, encoding: 'utf8', stdio: ['ignore', 'pipe', 'ignore'],
  });
  try {
    return git('branch', '--format=%(refname:short)', '--no-merged', defaultBranch)
      .split(/\r?\n/).map((b) => b.trim())
      .filter((b) => b.toLowerCase().startsWith(`${String(prefix).toLowerCase()}/req-`));
  } catch {
    return [];
  }
}

/** The last gate of every REQ of the plan (runs/gate/<REQ>/report_*.json): the acceptance evidence. */
function gateEvidence(workspaceRoot) {
  return readPlanReqs(workspaceRoot).map((r) => {
    const id = String(r.id);
    const dir = path.join(workspaceRoot, 'runs', 'gate', id);
    let last = null;
    try {
      const reports = fs.readdirSync(dir).filter((n) => /^report_.*\.json$/.test(n))
        .map((n) => ({ n, t: fs.statSync(path.join(dir, n)).mtimeMs })).sort((a, b) => b.t - a.t);
      if (reports.length) {
        const data = JSON.parse(fs.readFileSync(path.join(dir, reports[0].n), 'utf8'));
        last = { report: `runs/gate/${id}/${reports[0].n}`, verdict: String(data.gate || data.status || '?'), cases: Array.isArray(data.cases) ? data.cases.length : 0 };
      }
    } catch { /* no gate yet */ }
    return { id, status: String(r.status || 'open'), ...(last || {}) };
  });
}

/** How the REQs ran (runs/kit/<REQ>/ci/LTC.json): environment and services, the checks for reference. */
function collectReqEvalProfiles(workspaceRoot) {
  const kitRoot = path.join(workspaceRoot, 'runs', 'kit');
  let reqs = [];
  try {
    reqs = fs.readdirSync(kitRoot).filter((n) => /^REQ-[\w-]+$/.test(n)).sort();
  } catch {
    return [];
  }
  const out = [];
  for (const req of reqs) {
    let ltc;
    try {
      ltc = JSON.parse(fs.readFileSync(path.join(kitRoot, req, 'ci', 'LTC.json'), 'utf8'));
    } catch {
      continue;
    }
    const checks = (Array.isArray(ltc.checks) ? ltc.checks : Array.isArray(ltc.cases) ? ltc.cases : [])
      .filter((c) => c && typeof c === 'object')
      .map((c) => ({
        id: c.id || c.name,
        command: c.command || c.run,
        ...(c.cwd ? { cwd: c.cwd } : {}),
        ...(c.blocking === false ? { blocking: false } : {}),
      }));
    out.push({
      req,
      ...(ltc.run_from || ltc.cwd ? { run_from: ltc.run_from || ltc.cwd } : {}),
      checks,
      ...(ltc.environment ? { environment: ltc.environment } : {}),
      ...(ltc.services ? { services: ltc.services } : {}),
    });
  }
  return out;
}

/** Text files of the canonical solution, workspace-relative (bounded). */
function collectSolutionFiles(workspaceRoot) {
  const files = [];
  const add = (full) => {
    if (files.length >= MAX_FILES) return;
    let size = 0;
    try { size = fs.statSync(full).size; } catch { return; }
    if (size >= MAX_FILE_BYTES) return;
    const content = fs.readFileSync(full);
    if (content.includes(0)) return;
    files.push({ path: path.relative(workspaceRoot, full).split(path.sep).join('/'), content: content.toString('utf8') });
  };
  const walk = (dir) => {
    let entries = [];
    try { entries = fs.readdirSync(dir, { withFileTypes: true }); } catch { return; }
    for (const entry of entries.sort((a, b) => a.name.localeCompare(b.name))) {
      const full = path.join(dir, entry.name);
      if (entry.isDirectory()) {
        if (!SKIPPED_DIRS.has(entry.name)) walk(full);
      } else if (entry.isFile()) {
        add(full);
      }
    }
  };
  for (const rel of SOLUTION_FILES) {
    const full = path.join(workspaceRoot, ...rel.split('/'));
    if (fs.existsSync(full)) add(full);
  }
  for (const root of SOLUTION_ROOTS) walk(path.join(workspaceRoot, root));
  return files;
}

/** The report of a missing profile, in the eval report shape (a repair writes it). */
function missingProfileReport() {
  const message = `/finalize did not write ${SOLUTION_PROFILE}, the eval profile of the whole solution: ` +
    'write it (install, build, the solution configured and started as services, smoke checks of the running solution).';
  return {
    status: 'FAIL',
    passed: false,
    cases: [{ name: 'structure::solution-profile', passed: false, code: 1, blocking: true, stderr: message, excerpt: message, fingerprint: 'missing-solution-profile' }],
  };
}

/**
 * The verification also needs the developer's report (docs/harper/FINALIZE_REPORT.md): when
 * /finalize did not write it, a repairable failure is added, so the next repair cycle writes it.
 */
function withReportCheck(workspaceRoot, report) {
  const failures = [];
  if (!fs.existsSync(path.join(workspaceRoot, ...REPORT_PATH.split('/')))) {
    failures.push(['structure::finalize-report', 'missing-finalize-report',
      `/finalize did not write ${REPORT_PATH}, the report for the developer: write it (how to start and see ` +
      'the solution, configuration, missing information, what /finalize changed and why, problems met and how they were solved).']);
  }
  let readme = '';
  try { readme = fs.readFileSync(path.join(workspaceRoot, 'README.md'), 'utf8'); } catch { /* missing README */ }
  if (!readme.includes(CLIKE_REPO_URL)) {
    failures.push(['structure::readme-clike', 'readme-without-clike',
      `README.md does not say it is a CLike project: add the CLike badge linked to ${CLIKE_REPO_URL}, the Harper badge ` +
      `linked to ${CLIKE_REPO_URL}#harper-lifecycle, the Finalize badge linked to ${REPORT_PATH}, and a last section ` +
      `"Made with CLike" (delivered with CLike through the Harper process; links to docs/harper/, ${REPORT_PATH}, ${EVIDENCE_PATH}).`]);
  }
  if (!failures.length) return report;
  const cases = Array.isArray(report?.cases) ? report.cases : [];
  return {
    ...(report || {}),
    status: 'FAIL',
    passed: false,
    cases: [...cases, ...failures.map(([name, fingerprint, message]) =>
      ({ name, passed: false, code: 1, blocking: true, stderr: message, excerpt: message, fingerprint }))],
  };
}

/**
 * docs/harper/SOLUTION_EVAL.md: what CLike verified, from the eval reports (truthful evidence) —
 * the run of the solution, the repair cycles and the acceptance tests each REQ passed at its gate.
 */
function solutionEvalMarkdown(report, { cycle = 0, when = new Date(), history = [], gates = [] } = {}) {
  const cases = Array.isArray(report?.cases) ? report.cases : [];
  const status = String(report?.status || (report?.passed ? 'PASS' : 'FAIL'));
  const cell = (v) => String(v ?? '').replace(/\|/g, '/');
  const rows = cases
    .filter((c) => c && !(String(c.name || '').startsWith('env::provision::') && c.passed))
    .map((c) => `| ${cell(c.name)} | ${c.passed ? 'PASS' : c.blocked ? 'BLOCKED' : c.blocking === false ? 'WARN' : 'FAIL'} |`);
  const lines = [
    '# Solution eval',
    '',
    `CLike ran \`${SOLUTION_PROFILE}\` in its eval sandbox against the canonical tree after \`/finalize\`: the ` +
      'solution installed, built, configured, started and checked while running. The REQs\' test suites are not run ' +
      'again: each REQ passed them at its gate (below).',
    '',
    `- Result: **${status}**`,
    `- Date: ${when.toISOString()}`,
    `- Repair cycles: ${cycle}`,
    `- Report for the developer: \`${REPORT_PATH}\``,
    '',
    '| Check | Result |',
    '|---|---|',
    ...rows,
  ];
  if (history.length) {
    lines.push('', '## Verification cycles', '', '| Cycle | Result | Failing checks |', '|---|---|---|');
    for (const h of history) lines.push(`| ${h.cycle} | ${cell(h.status)} | ${cell((h.failing || []).join(', ') || '-')} |`);
  }
  if (gates.length) {
    lines.push('', '## Acceptance tests (passed at each REQ\'s gate, not run again)', '',
      '| REQ | Plan status | Last gate | Checks | Report |', '|---|---|---|---|---|');
    for (const g of gates) lines.push(`| ${cell(g.id)} | ${cell(g.status)} | ${cell(g.verdict || 'no gate')} | ${g.cases || '-'} | ${g.report ? `\`${g.report}\`` : '-'} |`);
  }
  lines.push('');
  return lines.join('\n');
}

module.exports = {
  EVIDENCE_PATH,
  REPORT_PATH,
  CLIKE_REPO_URL,
  gateEvidence,
  pendingReqs,
  ensureDirtyBaseline,
  readDirtyBaseline,
  clearDirtyBaseline,
  unmergedReqBranches,
  withReportCheck,
  SOLUTION_EVAL_ID,
  SOLUTION_PROFILE,
  collectReqEvalProfiles,
  collectSolutionFiles,
  missingProfileReport,
  solutionEvalMarkdown,
};
