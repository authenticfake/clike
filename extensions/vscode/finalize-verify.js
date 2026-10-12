'use strict';
// /finalize verification (no flag): after /finalize, CLike runs ci/SOLUTION_LTC.json — the eval
// profile of the whole solution — in the eval sandbox against the canonical tree; when it fails,
// /finalize runs again with the errors, a bounded number of cycles (same loop rules as auto-eval).
// This module gathers what the finalize model needs and writes the evidence.
const fs = require('fs');
const path = require('path');

const SOLUTION_PROFILE = 'ci/SOLUTION_LTC.json';
const SOLUTION_EVAL_ID = 'SOLUTION';
const EVIDENCE_PATH = 'docs/harper/SOLUTION_EVAL.md';

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
  'README.md', 'docs/harper/HOWTO_RUN.md', 'docs/harper/SANITY_CHECKS.md', EVIDENCE_PATH, '.env.example',
  'package.json', 'pyproject.toml', 'requirements.txt', 'docker-compose.yml', 'Dockerfile', 'Makefile',
];

/** Eval profiles of the REQs (runs/kit/<REQ>/ci/LTC.json): checks, environment, services. */
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
    'write it (install, the promoted test suites on the canonical tree, build, the solution started as services, e2e).';
  return {
    status: 'FAIL',
    passed: false,
    cases: [{ name: 'structure::solution-profile', passed: false, code: 1, blocking: true, stderr: message, excerpt: message, fingerprint: 'missing-solution-profile' }],
  };
}

/** docs/harper/SOLUTION_EVAL.md: what CLike verified, from the eval report (truthful evidence). */
function solutionEvalMarkdown(report, { cycle = 0, when = new Date() } = {}) {
  const cases = Array.isArray(report?.cases) ? report.cases : [];
  const status = String(report?.status || (report?.passed ? 'PASS' : 'FAIL'));
  const rows = cases
    .filter((c) => c && !(String(c.name || '').startsWith('env::provision::') && c.passed))
    .map((c) => `| ${String(c.name).replace(/\|/g, '/')} | ${c.passed ? 'PASS' : c.blocked ? 'BLOCKED' : c.blocking === false ? 'WARN' : 'FAIL'} |`);
  return [
    '# Solution eval',
    '',
    `CLike ran \`${SOLUTION_PROFILE}\` in its eval sandbox against the canonical tree (the sources and tests promoted ` +
      'by the gates), after `/finalize`.',
    '',
    `- Result: **${status}**`,
    `- Date: ${when.toISOString()}`,
    `- Repair cycles: ${cycle}`,
    '',
    '| Check | Result |',
    '|---|---|',
    ...rows,
    '',
  ].join('\n');
}

module.exports = {
  EVIDENCE_PATH,
  SOLUTION_EVAL_ID,
  SOLUTION_PROFILE,
  collectReqEvalProfiles,
  collectSolutionFiles,
  missingProfileReport,
  solutionEvalMarkdown,
};
