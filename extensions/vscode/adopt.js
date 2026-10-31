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
const code = require('./adopt-code');

const BASELINE_PROFILE = 'runs/adopt/ci/LTC.json';
const BASELINE_ID = 'ADOPT';
const CODEMAP = 'docs/harper/CODEMAP.md';

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

const areaName = (rel) => rel.split('/').join('-');

function areaOf(root, rel, stack) {
  const dir = path.join(root, ...rel.split('/'));
  const source = ['src', 'app', 'lib'].filter((d) => exists(dir, d)).map((d) => `${rel}/${d}`);
  for (const group of ['apps', 'packages', 'services']) for (const sub of dirs(path.join(dir, group))) source.push(`${rel}/${group}/${sub}`);
  const tests = ['tests', 'test', 'e2e', '__tests__', 'spec'].filter((d) => exists(dir, d)).map((d) => `${rel}/${d}`);
  return {
    // a nested area is named by its path (events/python → events-python): its folder alone says too little
    name: areaName(rel), root: rel, stack: stack.stack, manifest: stack.file,
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

/** Documents for the project memory: every document of the repository (Markdown, text, reStructuredText,
 * AsciiDoc, OpenAPI/AsyncAPI) — the READMEs, agent context files and changelogs of root and areas first.
 * Tracked and untracked files the project does not ignore (a folder without git: walked); never
 * docs/harper/ (CLike writes it), .clike/, runs/ or dependency and build folders. */
function surveyDocs(root, areas) {
  const out = [];
  const isDoc = (name) => DOC_SUFFIXES.has(path.extname(name).toLowerCase()) || /^(openapi|asyncapi)[\w.-]*\.(json|ya?ml)$/i.test(name);
  const add = (rel) => {
    if (out.includes(rel) || rel.startsWith('docs/harper/') || rel.split('/').slice(0, -1).some((p) => SKIP.has(p))) return;
    const full = path.join(root, ...rel.split('/'));
    try { const st = fs.statSync(full); if (st.isFile() && st.size <= MAX_DOC_BYTES) out.push(rel); } catch { /* gone */ }
  };
  for (const base of ['', ...areas.map((a) => a.root)]) {
    const prefix = base ? `${base}/` : '';
    for (const name of ['README.md', 'AGENTS.md', 'CLAUDE.md', 'CHANGELOG.md', 'ARCHITECTURE.md', 'CONTRIBUTING.md', 'SECURITY.md']) {
      if (exists(root, ...`${prefix}${name}`.split('/'))) add(`${prefix}${name}`);
    }
  }
  let files = null;
  try {
    files = execFileSync('git', ['ls-files', '-z', '--cached', '--others', '--exclude-standard'],
      { cwd: root, encoding: 'utf8', stdio: ['ignore', 'pipe', 'ignore'], maxBuffer: 64 * 1024 * 1024 }).split('\0').filter(Boolean);
  } catch { files = null; }
  if (!files) {
    files = [];
    const walk = (rel) => {
      let entries = [];
      try { entries = fs.readdirSync(rel ? path.join(root, ...rel.split('/')) : root, { withFileTypes: true }); } catch { return; }
      for (const e of entries) {
        const child = rel ? `${rel}/${e.name}` : e.name;
        if (e.isDirectory()) { if (!SKIP.has(e.name)) walk(child); } else files.push(child);
      }
    };
    walk('');
  }
  for (const rel of files.filter((f) => isDoc(path.basename(f))).sort((a, b) => a.localeCompare(b))) add(rel);
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
    // what git says each area did (null without git: the code alone)
    history: areas.map((a) => code.history(root, a)).filter(Boolean),
    tags: code.tagsWithDates(root),
    agentContext: ['AGENTS.md', 'CLAUDE.md'].filter((f) => exists(root, f)),
  };
}

/** .clike/project.json with the areas of the survey (merged: what the developer corrected stays). */
function mergeProjectAreas(meta, areas) {
  const keep = new Map((Array.isArray(meta?.areas) ? meta.areas : []).map((a) => [String(a.root || ''), a]));
  // the name an earlier survey gave a nested area (its last folder) becomes its path name; a name the developer chose stays
  for (const [root, a] of keep) if (root.includes('/') && a.name === root.split('/').pop()) keep.set(root, { ...a, name: areaName(root) });
  const merged = areas.map((a) => keep.get(a.root) || {
    name: a.name, root: a.root, source: a.source, tests: a.tests, commands: a.commands,
    ...(Object.keys(a.runtime).length ? { runtime: a.runtime } : {}),
  });
  for (const [root, a] of keep) if (!areas.some((x) => x.root === root)) merged.push(a);
  return { ...(meta || {}), areas: merged };
}

/**
 * The areas /adopt works on: those of .clike/project.json after the merge (a root, command or name the
 * developer corrected, an area declared by hand), with what the survey found for each (stack, agent
 * context files, runtimes). An area declared by hand that the survey did not find comes as declared.
 */
function effectiveAreas(surveyed, merged) {
  const by = new Map((surveyed || []).map((a) => [a.root, a]));
  return (merged || []).filter((m) => m && m.root).map((m) => {
    const s = by.get(m.root) || { stack: 'unknown', source: [m.root], tests: [], commands: {}, runtime: {}, agentContext: [] };
    return {
      ...s, name: m.name || s.name || areaName(m.root), root: m.root,
      source: Array.isArray(m.source) && m.source.length ? m.source : s.source,
      tests: Array.isArray(m.tests) ? m.tests : s.tests,
      commands: { ...(s.commands || {}), ...(m.commands || {}) },
      runtime: { ...(s.runtime || {}), ...(m.runtime || {}) },
      stack: m.stack || s.stack, agentContext: s.agentContext || [],
    };
  });
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
  if ((found.tags || []).length) lines.push(`- Tags: ${found.tags.map((t) => `\`${cell(t.name)}\` ${t.day}`).join(', ')}`);
  if ((found.history || []).length) {
    lines.push('', '### History per area (git: what was built and fixed, and when)', '');
    for (const h of found.history) lines.push(code.historyMarkdown(h));
  }
  lines.push(`- Code map (every module, entry point, route, call to another area, contract and test, per area): \`${CODEMAP}\``);
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
    dryRun ? '- Run `/adopt` (without --dry-run) for the baseline, the project memory and the analysis.'
      : '- The analysis follows: IDEA, SPEC, PLAN with the adopted REQs (protected by the tests above), TECH_CONSTRAINTS, lane guides, HOWTO_RUN and the README — its report is the EXTEND report of this run.', '');
  return lines.filter((l) => l !== null).join('\n');
}

// ---- the analysis (G3b): the baseline REQs CLike writes, the context the model gets, the check of its plan

const reqId = (n) => `REQ-${String(n).padStart(3, '0')}`;

/**
 * One adopted baseline REQ per area (REQ-001…), status done: its LTC runs the area's own setup and
 * check, as the team runs them; a check already failing at adoption is non-blocking (reported until
 * a REQ fixes it). The model adds the capability REQs after them (covered_by: the baseline REQ).
 * `existing`: the REQs of a plan already adopted for other areas (`/adopt --area`, one at a time).
 */
function baselineReqs(areas, baseline = null, existing = []) {
  const last = Math.max(0, ...existing.map((r) => Number(String(r?.id || '').match(/^REQ-(\d+)$/)?.[1] || 0)));
  const passedCase = (id) => (baseline?.cases || []).some((c) => c.name === id && c.passed);
  const reqs = [];
  const ltcs = {};
  areas.forEach((a, i) => {
    const id = reqId(last + i + 1);
    const checkId = `${a.name}::${a.commands.check ? 'check' : 'test'}`;
    const cmd = a.commands.check || a.commands.test;
    const failingAtAdoption = Boolean(baseline) && Boolean(cmd) && !passedCase(checkId);
    reqs.push({
      id, title: `${a.name} — existing behaviour (adopted baseline)`, status: 'done', origin: 'adopted', release: 'v1',
      area: a.name, lane: a.stack, dependsOn: [],
      acceptance: [cmd
        ? `${id}-A01: (observed) the checks the ${a.name} team runs pass: \`${cmd}\` in ${a.root}${failingAtAdoption ? ' (failing at adoption: reported, not blocking, until a REQ fixes it)' : ''}`
        : `${id}-A01: (open) ${a.name} has no test command CLike could find: characterization tests to add`],
      ...(failingAtAdoption ? { failing_at_adoption: [checkId] } : {}),
    });
    ltcs[id] = {
      req_id: id, purpose: `adopted baseline of ${a.name}: the checks its team already runs`,
      ...(Object.keys(a.runtime).length ? { environment: { ...a.runtime } } : {}),
      setup: a.commands.setup ? [{ id: 'setup', command: a.commands.setup, cwd: a.root, timeout: 1200 }] : [],
      checks: cmd ? [{ id: 'baseline', command: cmd, cwd: a.root, blocking: !failingAtAdoption, timeout: 1800 }] : [],
    };
  });
  return { reqs, ltcs };
}

/** The context a cloud model gets (a local agent reads the repository itself): the survey report, the
 * agent context files and the READMEs of the areas, each cut to `max` characters. */
function contextDocuments(root, found, areas, surveyRel, max = 6000, { maps = [], keyBudget = 160000 } = {}) {
  const cut = (text, n) => (text.length > n ? `${text.slice(0, n)}\n… (cut: the rest is in the project memory)` : text);
  const out = [];
  // what the run returns integrated: whole, first (a cut README would lose its tail and be put back) —
  // the root README, and the run guide an earlier area wrote
  for (const rel of ['README.md', 'docs/harper/HOWTO_RUN.md']) {
    const text = read(root, ...rel.split('/'));
    if (text.trim()) out.push({ path: rel, text, integrate: true });
  }
  // the survey report, and the code map: whole for the areas analysed, the others without their module list
  const report = read(root, ...surveyRel.split('/'));
  if (report.trim()) out.push({ path: surveyRel, text: cut(report, 40000) });
  if (maps.length) {
    const mine = (m) => areas.some((a) => a.name === m.area);
    out.push({ path: CODEMAP, text: maps.map((m) => code.codeMapMarkdown(m, mine(m) ? 40000 : 10000)).join('\n') });
  }
  const rels = [...found.agentContext, ...areas.flatMap((a) => [...a.agentContext, `${a.root}/README.md`])];
  for (const rel of [...new Set(rels)]) {
    const text = read(root, ...rel.split('/'));
    if (text.trim()) out.push({ path: rel, text: cut(text, max) });
  }
  // the key source files of the areas analysed (entry points, routes, calls, contracts, settings), read whole
  const mine = maps.filter((m) => areas.some((a) => a.name === m.area));
  for (const m of mine) out.push(...code.keyFiles(root, m, Math.floor(keyBudget / Math.max(1, mine.length))));
  return out;
}

/** The code maps of every area (the whole system: the contracts between areas) and docs/harper/CODEMAP.md. */
function codeMaps(root, areas) {
  const maps = areas.map((a) => code.codeMap(root, a, code.sourceFiles(root, a), areas));
  const markdown = ['# Code map', '',
    'Written by `/adopt` from the code, with no model: every module with its public symbols, entry point, route, call to',
    'another area, contract, configuration and test, per area. A capability this map does not show is not in the code.', '',
    '| Area | Files | Modules | Routes | Calls out | Tests |', '|---|---|---|---|---|---|',
    ...maps.map((m) => `| ${m.area} | ${m.files} | ${m.modules.length} | ${m.routes.length} | ${m.calls.length} | ${m.tests.cases} |`), '',
    ...maps.map((m) => code.codeMapMarkdown(m))].join('\n');
  return { maps, markdown };
}

/** The project memory: the documents, and the code of the areas adopted now (path-cited by every phase). */
function sourceItems(root, areas) {
  return areas.flatMap((a) => code.sourceFiles(root, a)).map((rel) => ({ path: rel, text: read(root, ...rel.split('/')) }))
    .filter((it) => it.text.trim() && !it.text.includes('\u0000'));
}

/**
 * The plan the model returned, checked: the baseline REQs unchanged (validateExtendPlan restores them),
 * every new REQ with an area and acceptance; done only with covered_by the area's baseline REQ (filled
 * in when missing), else open; origin and release set. Returns { ok, errors, warnings, planText, summary }.
 */
function checkAdoptedPlan({ beforeText, afterText, areas, baselineIds, validateExtendPlan, projectAreas = [] }) {
  const verdict = validateExtendPlan({ beforeText, afterText });
  const errors = [...verdict.errors];
  const warnings = [...verdict.warnings];
  if (!verdict.planText && !verdict.ok) return { ok: false, errors, warnings, planText: null, summary: [] };
  const plan = JSON.parse(verdict.planText || afterText);
  const reqs = Array.isArray(plan.reqs) ? plan.reqs : [];
  const byArea = new Map(areas.map((a, i) => [a.name, baselineIds[i]]));
  // the REQs of areas adopted before (validateExtendPlan keeps them): not this run's
  let before = new Set();
  try { before = new Set((JSON.parse(beforeText || '{}').reqs || []).map((r) => String(r.id))); } catch { /* none */ }
  const summary = [];
  for (const r of reqs) {
    if (baselineIds.includes(String(r.id)) || before.has(String(r.id))) continue;
    const areaNames = (Array.isArray(r.areas) ? r.areas : [r.area]).map((x) => String(x || '').trim()).filter(Boolean);
    if (!Array.isArray(r.acceptance) || !r.acceptance.length) errors.push(`${r.id}: no acceptance`);
    if (!areaNames.length) errors.push(`${r.id}: no area (one of ${areas.map((a) => a.name).join(', ')})`);
    // a journey across areas names the other areas of the project too (adopted later)
    const unknown = areaNames.filter((x) => !byArea.has(x) && !projectAreas.some((a) => a.name === x));
    if (unknown.length) warnings.push(`${r.id}: area ${unknown.join(', ')} is not an area of .clike/project.json`);
    r.origin = r.origin || 'adopted';
    r.release = r.release || 'v1';
    if (String(r.status || '').toLowerCase() === 'done') {
      const covers = areaNames.map((x) => byArea.get(x)).filter(Boolean);
      if (!covers.length) {
        r.status = 'open';
        warnings.push(`${r.id}: done without a baseline that covers it — open ("documented, not verified")`);
      } else if (!r.covered_by) r.covered_by = covers.length === 1 ? covers[0] : covers;
    } else r.status = 'open';
    summary.push({ id: r.id, title: r.title || '', areas: areaNames, status: r.status, origin: r.origin });
  }
  return { ok: errors.length === 0, errors, warnings, planText: `${JSON.stringify(plan, null, 2)}\n`, summary };
}

/** CLike's own section of the adoption analysis report. */
function adoptVerificationMarkdown({ areas, baselineIds, summary, baseline, warnings = [], docs = {} }) {
  const lines = ['', `## CLike verification (adoption, ${new Date().toISOString().slice(0, 10)})`, '',
    '| Area | Baseline REQ | Baseline | Capability REQs done | open |', '|---|---|---|---|---|'];
  areas.forEach((a, i) => {
    const mine = summary.filter((s) => s.areas.includes(a.name));
    const checkId = `${a.name}::${a.commands.check ? 'check' : 'test'}`;
    const c = (baseline?.cases || []).find((x) => x.name === checkId);
    lines.push(`| \`${cell(a.root)}\` | ${baselineIds[i]} | ${c ? (c.passed ? 'PASS' : 'FAIL (failing at adoption)') : 'not run'} | ` +
      `${mine.filter((s) => s.status === 'done').length} | ${mine.filter((s) => s.status !== 'done').length} |`);
  });
  lines.push('', '| REQ | Title | Areas | Status | Origin |', '|---|---|---|---|---|');
  for (const s of summary) lines.push(`| ${s.id} | ${cell(s.title)} | ${s.areas.join(', ')} | ${s.status} | ${cell(s.origin)} |`);
  const readme = !docs.readme ? 'not integrated'
    : docs.readme.ok ? `integrated — ${docs.readme.added.length} section(s) added, ${docs.readme.changed.length} existing section(s) extended, no existing line changed or removed`
      : `restored (the run ${docs.readme.missing?.length ? 'dropped existing sections' : `changed or dropped ${docs.readme.lost?.length || 0} existing line(s)`})`;
  lines.push('', `- README.md: ${readme}`, `- docs/harper/HOWTO_RUN.md: ${docs.howto ? 'written' : 'missing'}`);
  if (warnings.length) lines.push('', 'Warnings:', '', ...warnings.map((w) => `- ${w}`));
  lines.push('', 'Next: `/idea --extend` for the next release (the work the plan keeps open), then `/kit` → `/eval --fix` → `/gate`.', '');
  return lines.join('\n');
}

/** Whether /adopt may analyse `areas` on this plan: a plan without REQs, or one adopted area by area
 * (every REQ origin "adopted") where none of `areas` has a baseline REQ yet. Returns '' or the reason. */
function adoptablePlan(plan, areas) {
  const reqs = Array.isArray(plan?.reqs) ? plan.reqs : [];
  if (!reqs.length) return '';
  if (reqs.some((r) => !isAdoptedOrigin(r?.origin))) return 'the plan has REQs CLike did not adopt: an adopted project evolves with /idea --extend';
  // adopted = its baseline REQ and the REQs of its analysis; a baseline alone (the analysis never ended) runs again
  const isBase = (r) => /adopted baseline/.test(String(r?.title || ''));
  const have = new Set(reqs.filter(isBase).map((r) => r.area).filter((area) => reqs.some((r) => !isBase(r) && reqAreas(r).includes(area))));
  const again = areas.filter((a) => have.has(a.name)).map((a) => a.name);
  return again.length ? `already adopted: ${again.join(', ')} (pick another area with --area <name>)` : '';
}

// What /adopt writes: its own REQs, and the backlog items it imports (docs/inputs)
const isAdoptedOrigin = (o) => /^(adopted$|import:)/.test(String(o || ''));
const reqAreas = (r) => (Array.isArray(r?.areas) ? r.areas : [r?.area]).map((x) => String(x || '').trim()).filter(Boolean);

/** The areas adopted by an earlier /adopt (a baseline REQ and the REQs of its analysis): the next one adds to them. */
function adoptedAreas(plan) {
  const reqs = Array.isArray(plan?.reqs) ? plan.reqs : [];
  const isBase = (r) => /adopted baseline/.test(String(r?.title || ''));
  return [...new Set(reqs.filter(isBase).map((r) => r.area))].filter((area) => area && reqs.some((r) => !isBase(r) && reqAreas(r).includes(area)));
}

// Written by an earlier CLike (a copy of the README): still read, never written again
const ORIGINAL_README = '.clike/adopt/README.original.md';
const hasClikeSection = (text) => /^#{1,3}\s+made with clike/im.test(String(text || ''));

/**
 * The project's own README, as it was before CLike integrated it — no copy kept: the working copy when
 * CLike has not integrated it yet, else the latest version in git without CLike's "Made with CLike"
 * section (an earlier copy in .clike/adopt/ is still read). Every later /adopt keeps each of its lines
 * while CLike's own sections are updated for the new area. null when it cannot be found (no README,
 * or integrated without git): the README of the run's start is then the reference.
 */
function originalReadme(root) {
  const current = exists(root, 'README.md') ? read(root, 'README.md') : null;
  if (current != null && !hasClikeSection(current)) return current;
  const git = (...args) => execFileSync('git', args, { cwd: root, encoding: 'utf8', stdio: ['ignore', 'pipe', 'ignore'], maxBuffer: 16 * 1024 * 1024 });
  try {
    for (const sha of git('log', '--format=%H', '--', 'README.md').split('\n').filter(Boolean).slice(0, 200)) {
      let text;
      try { text = git('show', `${sha}:README.md`); } catch { continue; }   // deleted at that commit
      if (!hasClikeSection(text)) return text;
    }
  } catch { /* not a git repository */ }
  if (exists(root, ...ORIGINAL_README.split('/'))) return read(root, ...ORIGINAL_README.split('/'));
  return null;
}

/** The REQs kept when `areas` are adopted (again): every REQ but the baseline of those areas, written anew. */
function keptReqs(plan, areas) {
  const reqs = Array.isArray(plan?.reqs) ? plan.reqs : [];
  return reqs.filter((r) => !(/adopted baseline/.test(String(r?.title || '')) && areas.some((a) => a.name === r.area)));
}

/** CLike's own files of the adoption (what /init and /adopt added, not committed yet): they go with its commit.
 * The developer's own changes elsewhere are never included. */
function clikeOwnFiles(root) {
  let out = '';
  try {
    out = execFileSync('git', ['status', '--porcelain', '-uall', '--', '.clike', 'docs/harper', 'docs/inputs', 'docs/reference', '.gitignore', 'README_1st.md', 'images/clike', BASELINE_PROFILE],
      { cwd: root, encoding: 'utf8', stdio: ['ignore', 'pipe', 'ignore'] });
  } catch { return []; }
  const entries = out.split('\n').filter(Boolean).map((l) => ({ code: l.slice(0, 2), rel: l.slice(3).replace(/^"|"$/g, '').split(' -> ').pop() }));
  return entries.filter(({ code, rel }) => {
    // CLike's local state (sessions, telemetry, the /init hand-off naming this machine's folder)
    if (/^\.clike\/(sessions|telemetry|eval-check|bin|adopt-guard|adopt)\//.test(rel) || /^\.clike\/last_init_summary[^/]*\.json$/.test(rel)) return false;
    // docs/inputs and docs/reference hold the developer's documents (/init adds empty folders only)
    if (/^docs\/(inputs|reference)\//.test(rel)) return code === '??' && /(^|\/)\.gitkeep$/.test(rel);
    // .gitignore: only when /init created it, or its change is the "# CLike" block it appended
    if (rel === '.gitignore') return code === '??' || gitignoreChangeIsClike(root);
    return true;
  }).map(({ rel }) => rel);
}

/** The .gitignore change is only the "# CLike" block /init appends (init-merge.js): no line removed, every added line in it. */
function gitignoreChangeIsClike(root) {
  let diff = '';
  try { diff = execFileSync('git', ['diff', '-U0', 'HEAD', '--', '.gitignore'], { cwd: root, encoding: 'utf8', stdio: ['ignore', 'pipe', 'ignore'] }); } catch { return false; }
  const lines = diff.split('\n').filter((l) => /^[+-]/.test(l) && !/^(\+\+\+|---) /.test(l));
  if (lines.some((l) => l.startsWith('-'))) return false;
  const text = read(root, '.gitignore').split(/\r?\n/);
  const marker = text.lastIndexOf('# CLike');
  if (marker < 0) return false;
  const block = new Set(text.slice(marker).map((l) => l.trim()));
  return lines.every((l) => !l.slice(1).trim() || block.has(l.slice(1).trim()));
}

/**
 * The files of a commit that name this machine: the project's absolute path or the home folder
 * (a customer name, a user name) — they stay out of the commit. Binary or unreadable files are skipped.
 */
function machinePathFiles(root, rels) {
  // as written, JSON-escaped (C:\\Users) and with forward slashes (C:/Users): a Windows path in any form
  const needles = [...new Set([root, require('os').homedir()]
    .map((p) => String(p || '').replace(/[\\/]+$/, '')).filter((p) => p.length > 3)
    .flatMap((p) => [p, p.replace(/\\/g, '\\\\'), p.replace(/\\/g, '/')]))];
  return (rels || []).filter((rel) => {
    const full = path.join(root, ...String(rel).split('/'));
    try {
      if (!fs.statSync(full).isFile() || fs.statSync(full).size > 8 * 1024 * 1024) return false;
      const text = fs.readFileSync(full, 'utf8');
      return needles.some((n) => text.includes(n));
    } catch { return false; }
  });
}

// What /adopt may change in the project: CLike's own files and the root README (integrated, never replaced).
const adoptWritable = (rel) => rel === 'README.md' || /^(docs\/harper|\.clike|runs)\//.test(rel);

/** The files a run returned, split into what /adopt may write and what it never writes. */
function writableFiles(files) {
  // normalized as they are written (safe-workspace.js): `docs/harper/../src/x.py` is `src/x.py`, not writable
  const rel = (f) => {
    const raw = String(f?.path || '').replace(/\\/g, '/');
    const norm = path.posix.normalize(raw.replace(/^(\.\/)+/, ''));
    return raw.startsWith('/') ? raw : norm;   // absolute, or ../ outside the project: never writable
  };
  // the survey report and the code map are CLike's own, written before the analysis
  const ok = (f) => adoptWritable(rel(f)) && !/^docs\/harper\/(ADOPT_[^/]+\.md|CODEMAP\.md)$/.test(rel(f));
  return { kept: (files || []).filter(ok), dropped: (files || []).filter((f) => !ok(f)).map(rel) };
}

/** git status of the project outside what /adopt may write: path -> status. */
function statusOutside(root) {
  const out = execFileSync('git', ['status', '--porcelain', '-z', '-uall'], { cwd: root, encoding: 'utf8', stdio: ['ignore', 'pipe', 'ignore'], maxBuffer: 64 * 1024 * 1024 });
  const parts = out.split('\0');
  const map = new Map();
  for (let i = 0; i < parts.length; i += 1) {
    const entry = parts[i];
    if (!entry) continue;
    const xy = entry.slice(0, 2);
    const rel = entry.slice(3);
    if (/[RC]/.test(xy)) i += 1;   // the original path of a rename or copy follows
    if (!adoptWritable(rel)) map.set(rel, xy);
  }
  return map;
}

/**
 * The guard of /adopt: the project as it is before the run (git: what is changed or new outside CLike's
 * files, with its content). null without git — then only the returned files are filtered.
 */
function guardSnapshot(root) {
  try {
    const saved = {};
    for (const rel of statusOutside(root).keys()) {
      const full = path.join(root, ...rel.split('/'));
      saved[rel] = fs.existsSync(full) && fs.statSync(full).isFile() ? fs.readFileSync(full).toString('base64') : null;
    }
    return { saved };
  } catch { return null; }
}

/**
 * Every file outside CLike's own the run changed, created or deleted is put back as it was (the developer's
 * uncommitted changes included); what the run left there is kept aside in `keepDir`. Returns the paths restored.
 */
/**
 * The project files that changed while /adopt ran (outside CLike's own files and the root README):
 * changed, created or deleted. Only reported, never written: they may be the developer's own work
 * (an editor, another agent working in the project) — CLike never changes a project file.
 */
function guardChanges(root, snap) {
  if (!snap) return [];
  let now;
  try { now = statusOutside(root); } catch { return []; }
  const changed = [];
  for (const rel of new Set([...now.keys(), ...Object.keys(snap.saved)])) {
    const full = path.join(root, ...rel.split('/'));
    const current = fs.existsSync(full) && fs.statSync(full).isFile() ? fs.readFileSync(full).toString('base64') : null;
    if (rel in snap.saved && current === snap.saved[rel]) continue;
    changed.push(rel);
  }
  return changed;
}

module.exports = {
  CODEMAP, ORIGINAL_README, isAdoptedOrigin, machinePathFiles, keptReqs, adoptedAreas, originalReadme, clikeOwnFiles, writableFiles, guardSnapshot, guardChanges, codeMaps, sourceItems, adoptablePlan, baselineReqs, contextDocuments, checkAdoptedPlan, adoptVerificationMarkdown,
  BASELINE_PROFILE, BASELINE_ID, survey, surveyAreas, surveyDocs, surveyCi, surveyGit, areaCommands, areaRuntime,
  makeTargets, mergeProjectAreas, effectiveAreas, baselineProfile, memoryItems, reportMarkdown,
};
