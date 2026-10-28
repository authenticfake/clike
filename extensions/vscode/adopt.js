'use strict';
// /adopt, first part (deterministic, no model): a project CLike did not create, surveyed as it is.
// What it finds — areas (the services of a monorepo), their stack, roots, commands and runtime
// versions, the CI, the documentation and the agent context files, the git history — becomes the
// areas of .clike/project.json, a baseline profile that runs each area's own checks in the eval
// sandbox, the documents indexed into the project memory, and the report docs/harper/ADOPT_<date>.md.
// Nothing of the project is written: only CLike's own files (.clike/project.json, runs/adopt/, the report).
const fs = require('fs');
const path = require('path');
const { execFileSync } = require('child_process');

const BASELINE_PROFILE = 'runs/adopt/ci/LTC.json';
const BASELINE_ID = 'ADOPT';

// a manifest marks a project (an area); the first found names its stack
const MANIFESTS = [
  ['pyproject.toml', 'python'], ['setup.py', 'python'], ['setup.cfg', 'python'],
  ['package.json', 'node'], ['go.mod', 'go'], ['pom.xml', 'java'], ['build.gradle', 'java'],
  ['build.gradle.kts', 'kotlin'], ['Cargo.toml', 'rust'], ['composer.json', 'php'], ['Gemfile', 'ruby'],
  ['requirements.txt', 'python'],
];
// never an area, never walked: CLike, git, editors, generated and dependency folders
const SKIP = new Set(['.git', '.clike', 'runs', 'node_modules', '.venv', 'venv', '__pycache__', '.next', 'dist',
  'build', 'coverage', '.cache', '.mypy_cache', '.pytest_cache', '.ruff_cache', 'target', '.idea', '.vscode',
  '.github', 'images', '.turbo', '.import_linter_cache', 'test-results']);
const DOC_SUFFIXES = new Set(['.md', '.mdx', '.txt', '.rst', '.adoc']);
const MAX_DOC_BYTES = 512 * 1024;

const exists = (...p) => fs.existsSync(path.join(...p));
const read = (...p) => { try { return fs.readFileSync(path.join(...p), 'utf8'); } catch { return ''; } };
const dirs = (dir) => { try { return fs.readdirSync(dir, { withFileTypes: true }).filter((e) => e.isDirectory() && !SKIP.has(e.name) && !e.name.startsWith('.')).map((e) => e.name).sort(); } catch { return []; } };
const stackOf = (dir) => {
  for (const [file, stack] of MANIFESTS) if (exists(dir, file)) return { file, stack };
  try { if (fs.readdirSync(dir).some((n) => /\.(csproj|sln)$/i.test(n))) return { file: '*.csproj', stack: 'dotnet' }; } catch { /* none */ }
  return null;
};

/** Make targets of a Makefile (the ones a team runs: check, test, lint, typecheck…). */
function makeTargets(text) {
  return [...new Set([...String(text || '').matchAll(/^([A-Za-z][\w-]*)\s*:(?!=)/gm)].map((m) => m[1]))];
}

/** The commands an area's team runs, in the order CLike prefers them: check, test, lint, typecheck. */
function areaCommands(dir, stack) {
  const cmds = {};
  const targets = makeTargets(read(dir, 'Makefile'));
  let scripts = {};
  try { scripts = JSON.parse(read(dir, 'package.json') || '{}').scripts || {}; } catch { /* no scripts */ }
  for (const name of ['check', 'test', 'lint', 'typecheck']) {
    if (targets.includes(name)) cmds[name] = `make ${name}`;
    else if (scripts[name]) cmds[name] = `npm run ${name}`;
  }
  if (exists(dir, 'uv.lock')) cmds.setup = 'uv sync';
  else if (exists(dir, 'poetry.lock')) cmds.setup = 'poetry install';
  else if (exists(dir, 'package-lock.json')) cmds.setup = 'npm ci';
  else if (exists(dir, 'pnpm-lock.yaml')) cmds.setup = 'pnpm install --frozen-lockfile';
  else if (exists(dir, 'yarn.lock')) cmds.setup = 'yarn install --frozen-lockfile';
  else if (exists(dir, 'package.json')) cmds.setup = 'npm install';
  else if (stack === 'python' && exists(dir, 'requirements.txt')) cmds.setup = 'pip install -r requirements.txt';
  if (!cmds.check && !cmds.test) {
    if (stack === 'python' && (exists(dir, 'tests') || exists(dir, 'test'))) cmds.test = exists(dir, 'uv.lock') ? 'uv run pytest' : 'python -m pytest';
    else if (stack === 'go') cmds.test = 'go test ./...';
    else if (stack === 'rust') cmds.test = 'cargo test';
    else if (stack === 'java' && exists(dir, 'pom.xml')) cmds.test = 'mvn -q test';
    else if (stack === 'java' || stack === 'kotlin') cmds.test = './gradlew test';
  }
  return cmds;
}

/** Runtime versions the area itself requires (requires-python, .python-version, engines.node, .nvmrc). */
function areaRuntime(dir) {
  const runtime = {};
  const py = /requires-python\s*=\s*["']([^"']+)["']/.exec(read(dir, 'pyproject.toml'));
  const pyFile = read(dir, '.python-version').trim();
  if (py) runtime.python = py[1].trim();
  else if (pyFile) runtime.python = pyFile;
  let engines = '';
  try { engines = JSON.parse(read(dir, 'package.json') || '{}').engines?.node || ''; } catch { /* none */ }
  const nvm = read(dir, '.nvmrc').trim();
  if (engines) runtime.node = engines;
  else if (nvm) runtime.node = nvm;
  return runtime;
}

function areaOf(root, rel, stack) {
  const dir = path.join(root, ...rel.split('/'));
  const source = ['src', 'app', 'lib'].filter((d) => exists(dir, d)).map((d) => `${rel}/${d}`);
  for (const group of ['apps', 'packages', 'services']) for (const sub of dirs(path.join(dir, group))) source.push(`${rel}/${group}/${sub}`);
  const tests = ['tests', 'test', 'e2e', '__tests__', 'spec'].filter((d) => exists(dir, d)).map((d) => `${rel}/${d}`);
  return {
    name: rel.split('/').pop(), root: rel, stack: stack.stack, manifest: stack.file,
    source: source.length ? source : [rel], tests,
    commands: areaCommands(dir, stack.stack), runtime: areaRuntime(dir),
    agentContext: ['AGENTS.md', 'CLAUDE.md'].filter((f) => exists(dir, f)).map((f) => `${rel}/${f}`),
  };
}

/** The areas of the repository: each top-level folder with a manifest, or with sub-folders that have one. */
function surveyAreas(root) {
  const areas = [];
  for (const top of dirs(root)) {
    if (top === 'docs') continue;
    const stack = stackOf(path.join(root, top));
    if (stack) { areas.push(areaOf(root, top, stack)); continue; }
    for (const sub of dirs(path.join(root, top))) {
      const inner = stackOf(path.join(root, top, sub));
      if (inner) areas.push(areaOf(root, `${top}/${sub}`, inner));
    }
  }
  return areas;
}

/** Documents for the project memory: docs/ and the READMEs, agent context files and changelogs of root and areas. */
function surveyDocs(root, areas) {
  const out = [];
  const add = (rel) => {
    const full = path.join(root, ...rel.split('/'));
    try { if (fs.statSync(full).size <= MAX_DOC_BYTES && !out.includes(rel)) out.push(rel); } catch { /* gone */ }
  };
  const walk = (rel) => {
    let entries = [];
    try { entries = fs.readdirSync(path.join(root, ...rel.split('/')), { withFileTypes: true }); } catch { return; }
    for (const e of entries.sort((a, b) => a.name.localeCompare(b.name))) {
      const child = `${rel}/${e.name}`;
      if (e.isDirectory()) {
        if (!SKIP.has(e.name) && !(rel === 'docs' && e.name === 'harper')) walk(child);
      } else if (DOC_SUFFIXES.has(path.extname(e.name).toLowerCase()) || /^(openapi|asyncapi)[\w.-]*\.(json|ya?ml)$/i.test(e.name)) add(child);
    }
  };
  for (const base of ['', ...areas.map((a) => a.root)]) {
    const prefix = base ? `${base}/` : '';
    for (const name of ['README.md', 'AGENTS.md', 'CLAUDE.md', 'CHANGELOG.md', 'ARCHITECTURE.md', 'CONTRIBUTING.md', 'SECURITY.md']) {
      if (exists(root, ...`${prefix}${name}`.split('/'))) add(`${prefix}${name}`);
    }
    walk(`${prefix}docs`);
  }
  return out;
}

/** The CI workflows and the commands they run (single-line `run:` steps). */
function surveyCi(root) {
  const dir = path.join(root, '.github', 'workflows');
  let names = [];
  try { names = fs.readdirSync(dir).filter((n) => /\.ya?ml$/i.test(n)).sort(); } catch { return []; }
  return names.map((n) => ({
    file: `.github/workflows/${n}`,
    runs: [...read(dir, n).matchAll(/^\s*(?:-\s*)?run:\s*([^|>\n][^\n]*)$/gm)].map((m) => m[1].trim()).slice(0, 12),
  }));
}

/** Git as the evidence of what was done: commits, tags, last commit, remote, branch. null without git. */
function surveyGit(root) {
  const git = (...args) => execFileSync('git', args, { cwd: root, encoding: 'utf8', stdio: ['ignore', 'pipe', 'ignore'] }).trim();
  try { git('rev-parse', '--is-inside-work-tree'); } catch { return null; }
  const safe = (fn) => { try { return fn(); } catch { return ''; } };
  return {
    commits: Number(safe(() => git('rev-list', '--count', 'HEAD')) || 0),
    branch: safe(() => git('rev-parse', '--abbrev-ref', 'HEAD')),
    last: safe(() => git('log', '-1', '--format=%h %ci %s')),
    tags: safe(() => git('tag', '--sort=-creatordate')).split('\n').filter(Boolean).slice(0, 10),
    remote: safe(() => git('remote', 'get-url', 'origin')),
  };
}

/** The CI is what the team runs: an area's setup command comes from its workflow when there is one. */
function withCiSetup(areas, ci) {
  for (const a of areas) {
    const wf = ci.find((w) => path.basename(w.file).toLowerCase().includes(a.name.toLowerCase()));
    const setup = wf && wf.runs.find((r) => /^(uv sync|poetry install|pip install|npm ci|pnpm install|yarn install)\b/.test(r));
    if (setup) a.commands.setup = setup;
  }
  return areas;
}

function survey(root) {
  const ci = surveyCi(root);
  const areas = withCiSetup(surveyAreas(root), ci);
  return {
    at: new Date().toISOString(),
    rootStack: stackOf(root)?.stack || '',
    areas,
    docs: surveyDocs(root, areas),
    ci,
    git: surveyGit(root),
    agentContext: ['AGENTS.md', 'CLAUDE.md'].filter((f) => exists(root, f)),
  };
}

/** .clike/project.json with the areas of the survey (merged: what the developer corrected stays). */
function mergeProjectAreas(meta, areas) {
  const keep = new Map((Array.isArray(meta?.areas) ? meta.areas : []).map((a) => [String(a.root || ''), a]));
  const merged = areas.map((a) => keep.get(a.root) || {
    name: a.name, root: a.root, source: a.source, tests: a.tests, commands: a.commands,
    ...(Object.keys(a.runtime).length ? { runtime: a.runtime } : {}),
  });
  for (const [root, a] of keep) if (!areas.some((x) => x.root === root)) merged.push(a);
  return { ...(meta || {}), areas: merged };
}

const highest = (values) => values.filter(Boolean).sort((a, b) => {
  const n = (v) => (String(v).match(/\d+(\.\d+)?/) || ['0'])[0].split('.').map(Number);
  const [x, y] = [n(a), n(b)];
  return (y[0] - x[0]) || ((y[1] || 0) - (x[1] || 0));
})[0];

/** The baseline profile: each area's own setup, then its check (or test) command, run inside the area. */
function baselineProfile(areas) {
  const setup = [];
  const checks = [];
  for (const a of areas) {
    if (a.commands.setup) setup.push({ id: `${a.name}::setup`, command: a.commands.setup, cwd: a.root, timeout: 1200 });
    const cmd = a.commands.check || a.commands.test;
    if (cmd) checks.push({ id: `${a.name}::${a.commands.check ? 'check' : 'test'}`, command: cmd, cwd: a.root, blocking: true, timeout: 1800 });
  }
  const environment = {};
  const py = highest(areas.map((a) => a.runtime.python));
  const node = highest(areas.map((a) => a.runtime.node));
  if (py) environment.python = py;
  if (node) environment.node = node;
  return { req_id: BASELINE_ID, purpose: 'adoption baseline: the tests each area already has, as its team runs them', environment, setup, checks };
}

/** Documents of the survey as project-memory items ({ path, text }). */
function memoryItems(root, docs) {
  const items = [];
  for (const rel of docs) {
    const buf = (() => { try { return fs.readFileSync(path.join(root, ...rel.split('/'))); } catch { return null; } })();
    if (!buf || buf.includes(0)) continue;
    const text = buf.toString('utf8');
    if (text.trim()) items.push({ path: rel, text });
  }
  return items;
}

const cell = (v) => String(v ?? '').replace(/\|/g, '\\|').replace(/\n/g, ' ');

/** docs/harper/ADOPT_<date>.md: what was found and what the existing tests say, before any analysis. */
function reportMarkdown(found, { baseline = null, indexed = 0, dryRun = false, area = '' } = {}) {
  const lines = [`# Adoption report — ${found.at.slice(0, 10)}`, '',
    dryRun ? '**Dry run:** survey only; nothing written except this report.\n' : '',
    `Areas: **${found.areas.length}**${area ? ` (adopting \`${area}\` first)` : ''} · documents for the project memory: **${found.docs.length}**` +
      (indexed ? ` (indexed: ${indexed})` : '') + ` · CI workflows: **${found.ci.length}**`, ''];
  lines.push('## Areas', '', '| Area | Stack | Source | Tests | Commands | Runtime |', '|---|---|---|---|---|---|');
  for (const a of found.areas) {
    lines.push(`| \`${cell(a.root)}\` | ${cell(a.stack)} (${cell(a.manifest)}) | ${a.source.map((s) => `\`${cell(s)}\``).join(', ')} | ` +
      `${a.tests.map((s) => `\`${cell(s)}\``).join(', ') || '—'} | ${Object.entries(a.commands).map(([k, v]) => `${k}: \`${cell(v)}\``).join('<br>') || '—'} | ` +
      `${Object.entries(a.runtime).map(([k, v]) => `${k} ${cell(v)}`).join(', ') || '—'} |`);
  }
  if (!found.areas.length) lines.push('| — | the repository root is one project | | | | |');
  lines.push('', '## What exists: git and the tests', '');
  if (found.git) {
    lines.push(`- Git: ${found.git.commits} commit(s) on \`${cell(found.git.branch)}\`, last \`${cell(found.git.last)}\`` +
      `${found.git.tags.length ? `, tags ${found.git.tags.map((t) => `\`${t}\``).join(', ')}` : ''}${found.git.remote ? `, remote ${found.git.remote}` : ', no remote'}`);
  } else lines.push('- No git: what exists is read from the code alone.');
  if (baseline) {
    lines.push('', '### Baseline (the existing checks, run in the CLike eval sandbox)', '', '| Check | Result |', '|---|---|');
    for (const c of baseline.cases || []) lines.push(`| \`${cell(c.name)}\` | ${c.passed ? 'PASS' : c.blocking === false ? 'WARN' : 'FAIL'} |`);
    lines.push('', `Baseline: **${baseline.status || (baseline.passed ? 'PASS' : 'FAIL')}**. A check that already fails is recorded as failing at adoption: reported, not blocking, until a REQ fixes it.`);
  } else if (!dryRun) lines.push('- Baseline not run.');
  lines.push('', '## CI', '');
  for (const w of found.ci) lines.push(`- \`${w.file}\`: ${w.runs.map((r) => `\`${cell(r)}\``).join(' · ') || '(no single-line run steps)'}`);
  if (!found.ci.length) lines.push('- No CI workflow found.');
  lines.push('', '## Documentation and conventions', '');
  const ctx = [...found.agentContext, ...found.areas.flatMap((a) => a.agentContext)];
  lines.push(`- Agent context files (conventions → lane guides): ${ctx.map((f) => `\`${f}\``).join(', ') || 'none'}`);
  lines.push(`- Documents for the project memory: ${found.docs.length}${found.docs.length ? ` (e.g. ${found.docs.slice(0, 6).map((f) => `\`${f}\``).join(', ')}${found.docs.length > 6 ? ', …' : ''})` : ''}`);
  lines.push('', '## Next', '',
    '- Review the areas in `.clike/project.json` (correct a root or a command there: the next `/adopt` keeps it).',
    '- The analysis area by area — capabilities as they are, adopted REQs protected by the tests above, IDEA / SPEC / PLAN — is the next step of `/adopt`.', '');
  return lines.filter((l) => l !== null).join('\n');
}

module.exports = {
  BASELINE_PROFILE, BASELINE_ID, survey, surveyAreas, surveyDocs, surveyCi, surveyGit, areaCommands, areaRuntime,
  makeTargets, mergeProjectAreas, baselineProfile, memoryItems, reportMarkdown,
};
