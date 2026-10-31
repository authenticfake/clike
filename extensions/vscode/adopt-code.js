'use strict';
// /adopt: what the code and git say, with no model (the same for cloud and local agents).
// - sourceFiles: the code, tests, contracts and configuration of an area (git-tracked when there is
//   git), for the project memory: every later phase and the Memory panel cite them;
// - codeMap: the complete inventory of an area — modules and their public symbols, entry points,
//   HTTP routes, tools, CLI commands, event and API contracts, tests — written to docs/harper/CODEMAP.md.
//   A capability the map does not show is not in the code;
// - keyFiles: the files a cloud model reads whole (entry points, routes, contracts, settings), within a budget;
// - history: what git says each area did (commits by kind, the latest features and fixes, tags).
// Language-agnostic by patterns; a language the patterns do not know still gets its files and tests listed.
const fs = require('fs');
const path = require('path');
const { execFileSync } = require('child_process');

const CODE_EXT = new Set(['.py', '.ts', '.tsx', '.js', '.jsx', '.mjs', '.cjs', '.go', '.rs', '.java', '.kt', '.cs',
  '.rb', '.php', '.scala', '.swift', '.sql', '.proto', '.graphql', '.gql', '.avsc', '.sh', '.ps1']);
const CONFIG_EXT = new Set(['.toml', '.yaml', '.yml', '.json', '.ini', '.cfg', '.env']);
const SKIP_DIRS = new Set(['.git', '.clike', 'runs', 'node_modules', '.venv', 'venv', '__pycache__', '.next', 'dist',
  'build', 'coverage', '.cache', '.mypy_cache', '.pytest_cache', '.ruff_cache', 'target', '.idea', '.vscode',
  '.turbo', '.import_linter_cache', 'test-results', 'vendor', 'bin', 'obj']);
const SKIP_FILE = /(^|\/)(package-lock\.json|pnpm-lock\.yaml|yarn\.lock|uv\.lock|poetry\.lock|Cargo\.lock|go\.sum|composer\.lock|Gemfile\.lock)$|\.(min\.js|map|snap)$/;
const MAX_FILE_BYTES = 256 * 1024;

const git = (root, args) => execFileSync('git', args, { cwd: root, encoding: 'utf8', stdio: ['ignore', 'pipe', 'ignore'], maxBuffer: 64 * 1024 * 1024 });
const isGit = (root) => { try { git(root, ['rev-parse', '--is-inside-work-tree']); return true; } catch { return false; } };
const read = (root, rel) => { try { return fs.readFileSync(path.join(root, ...rel.split('/')), 'utf8'); } catch { return ''; } };

function walk(root, rel, out) {
  let entries = [];
  try { entries = fs.readdirSync(path.join(root, ...rel.split('/')), { withFileTypes: true }); } catch { return; }
  for (const e of entries.sort((a, b) => a.name.localeCompare(b.name))) {
    const child = rel ? `${rel}/${e.name}` : e.name;
    if (e.isDirectory()) { if (!SKIP_DIRS.has(e.name) && !e.name.startsWith('.')) walk(root, child, out); } else if (e.isFile()) out.push(child);
  }
}

/** The files of an area that say what it does: code, tests, contracts, configuration (no docs: surveyDocs has them). */
function sourceFiles(root, area) {
  let all = [];
  if (isGit(root)) {
    try { all = git(root, ['ls-files', '-z', '--', area.root]).split('\0').filter(Boolean); } catch { all = []; }
  }
  if (!all.length) walk(root, area.root, all);
  return all.filter((rel) => {
    if (SKIP_FILE.test(rel) || rel.split('/').some((p) => SKIP_DIRS.has(p))) return false;
    const ext = path.extname(rel).toLowerCase();
    const base = path.basename(rel);
    const envExample = /^\.env\.[\w.-]*(example|sample|template)$/i.test(base);
    if (!(CODE_EXT.has(ext) || CONFIG_EXT.has(ext) || envExample || /^(Makefile|Dockerfile|Containerfile|Procfile)$/.test(base))) return false;
    if (/\.env$/.test(base) && !/example|sample|template/i.test(base)) return false;   // never a real .env
    try { const st = fs.statSync(path.join(root, ...rel.split('/'))); return st.size > 0 && st.size <= MAX_FILE_BYTES; } catch { return false; }
  });
}

const isTest = (rel) => /(^|\/)(tests?|__tests__|e2e|spec)(\/|$)|(^|\/)test_[^/]+$|_test\.[a-z]+$|\.(test|spec)\.[a-z]+$/i.test(rel);
const isContract = (rel) => /(^|\/)(contracts?|schemas|proto|protos)(\/|$)|(openapi|asyncapi)[^/]*\.(json|ya?ml)$|\.(proto|avsc|graphql|gql)$/i.test(rel);
const isEntry = (rel, text) => /(^|\/)(main|__main__|app|server|index|cli|program|wsgi|asgi)\.[a-z]+$/i.test(rel) ||
  /if __name__ == ["']__main__["']|func main\(\)|static void Main\(|createServer\(|\.listen\(\d|uvicorn\.run\(|FastAPI\(|Flask\(__name__\)|express\(\)/.test(text);
const isSettings = (rel) => /(^|\/)(settings|config|configuration)\.[a-z]+$|(^|\/)config\//i.test(rel) && !isTest(rel);

// HTTP routes, tools, CLI commands and events, by the patterns of the common frameworks
const ROUTE_PATTERNS = [
  /@\w+(?:\.\w+)*\.(get|post|put|patch|delete|websocket|api_route)\(\s*["'`]([^"'`]*)["'`]/g,           // FastAPI / Flask / Starlette
  /\b(?:app|router|server|fastify)\.(get|post|put|patch|delete|all)\(\s*["'`](\/[^"'`]*)["'`]/g,          // Express / Hono / Fastify
  /@(Get|Post|Put|Patch|Delete|Request)Mapping\(\s*(?:value\s*=\s*)?["']([^"']*)["']/g,                 // Spring
  /\[(Http(?:Get|Post|Put|Patch|Delete)|Route)\(\s*"([^"]*)"/g,                                          // ASP.NET
];
const GO_ROUTE = /\.(HandleFunc|Handle|GET|POST|PUT|PATCH|DELETE)\(\s*"(\/[^"]*)"/g;
// calls to other services' HTTP APIs: how the areas talk to each other
const CALL_PATTERNS = [
  /\b(?:api|client|http|axios|fetcher|httpx|requests|session|\w+Client|\w+_client|\w+Api)\.(get|post|put|patch|delete)\(\s*[f]?["'`]([^"'`]*\/v\d+\/[^"'`?]*)["'`]/g,
  /\b(?:\w+\.)?(\w+)\.(GET|POST|PUT|PATCH|DELETE)\(\s*["'`](\/[^"'`]+)["'`]/g,                             // typed clients (openapi-fetch)
  /\bfetch\(\s*`[^`]*?(\/v\d+\/[^`?]*)`(?:[\s\S]{0,160}?method:\s*["'`](\w+)["'`])?/g,
];
const TOOL_PATTERN = /@(?:\w+\.)?tool\b(?:\([^)]*\))?\s*\n\s*(?:async\s+)?def\s+(\w+)|server\.tool\(\s*["'](\w+)["']|registerTool\(\s*["'](\w+)["']/g;
const CLI_PATTERN = /@(?:\w+\.)?command\([^)]*\)\s*\n\s*(?:async\s+)?def\s+(\w+)|\.command\(\s*["']([\w:-]+)["']/g;
const EVENT_PATTERN = /\b(?:publish|emit|produce|send_event|subscribe|consume)\w*\(\s*["'`]([\w.:/-]{3,})["'`]/g;

/** Public symbols of a file: classes and functions at module level (and methods of public classes). */
function symbols(rel, text) {
  const ext = path.extname(rel).toLowerCase();
  const out = [];
  const push = (m) => { if (m && !m.startsWith('_') && !out.includes(m)) out.push(m); };
  if (ext === '.py') {
    for (const m of text.matchAll(/^(?:class\s+(\w+)|(?:async\s+)?def\s+(\w+))/gm)) push(m[1] ? `class ${m[1]}` : `${m[2]}()`);
  } else if (['.ts', '.tsx', '.js', '.jsx', '.mjs', '.cjs'].includes(ext)) {
    for (const m of text.matchAll(/^export\s+(?:default\s+)?(?:async\s+)?(?:(function|class|interface|type|enum|const)\s+)(\w+)/gm)) push(m[1] === 'function' ? `${m[2]}()` : `${m[1]} ${m[2]}`);
  } else if (ext === '.go') {
    for (const m of text.matchAll(/^(?:func\s+(?:\([^)]*\)\s*)?([A-Z]\w*)|type\s+([A-Z]\w*))/gm)) push(m[1] ? `${m[1]}()` : `type ${m[2]}`);
  } else if (['.java', '.kt', '.cs', '.scala', '.swift'].includes(ext)) {
    for (const m of text.matchAll(/\bpublic\s+(?:static\s+|abstract\s+|sealed\s+|partial\s+|final\s+)*(class|interface|record|enum)\s+(\w+)/g)) push(`${m[1]} ${m[2]}`);
  } else if (ext === '.rs') {
    for (const m of text.matchAll(/^pub\s+(?:async\s+)?(fn|struct|enum|trait)\s+(\w+)/gm)) push(m[1] === 'fn' ? `${m[2]}()` : `${m[1]} ${m[2]}`);
  }
  return out;
}

function firstDoc(rel, text) {
  const py = /^\s*(?:#[^\n]*\n|\s)*(?:"""|''')\s*([^\n]+)/.exec(text);
  if (path.extname(rel) === '.py' && py) return py[1].replace(/("""|''')\s*$/, '').trim();
  const js = /^\s*\/\*\*?\s*\n?\s*\*?\s*([^\n*][^\n]*)/.exec(text);
  if (js) return js[1].trim();
  const line = /^\s*(?:\/\/|#)\s*([^\n!][^\n]{8,})/.exec(text);
  return line ? line[1].trim() : '';
}

function testNames(rel, text) {
  const out = [];
  for (const m of text.matchAll(/^\s*(?:async\s+)?def\s+(test_\w+)/gm)) out.push(m[1]);
  for (const m of text.matchAll(/\b(?:it|test)\(\s*(["'`])(.+?)\1/g)) out.push(m[2]);
  for (const m of text.matchAll(/\bfunc\s+(Test\w+)\(/g)) out.push(m[1]);
  for (const m of text.matchAll(/\[(?:Fact|Test|TestMethod)\][\s\S]{0,80}?\bvoid\s+(\w+)/g)) out.push(m[1]);
  return out;
}

/** The inventory of an area, from its files: entry points, routes, tools, CLI, events, contracts, modules, tests. */
function codeMap(root, area, files, others = []) {
  // how this area names the others (code, configuration, *_URL variables): the edges between areas
  const variants = (name) => [...new Set([name, name.replace(/-/g, '_'), name.replace(/[-_]/g, ''), name.replace(/-/g, ' ')])];
  const refRes = others.filter((o) => o.name !== area.name)
    .map((o) => ({ area: o.name, re: new RegExp(`(?:${variants(o.name).map((v) => v.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')).join('|')})`, 'i') }));
  const map = { area: area.name, root: area.root, files: files.length, entries: [], routes: [], tools: [], cli: [], events: [],
    calls: [], refs: {}, contracts: [], settings: [], modules: [], tests: { files: 0, cases: 0, byFile: [] } };
  for (const rel of files) {
    const text = read(root, rel);
    if (!text) continue;
    const local = rel.slice(area.root.length + 1);
    for (const r of refRes) {
      if (!r.re.test(text)) continue;
      const ref = map.refs[r.area] || (map.refs[r.area] = { files: 0, examples: [] });
      ref.files += 1;
      if (ref.examples.length < 6 && !isTest(rel)) ref.examples.push(local);
    }
    if (isTest(rel)) {
      const names = testNames(rel, text);
      map.tests.files += 1;
      map.tests.cases += names.length;
      if (names.length) map.tests.byFile.push({ file: local, names });
      continue;
    }
    if (isContract(rel)) map.contracts.push(local);
    if (isSettings(rel)) map.settings.push(local);
    if (CODE_EXT.has(path.extname(rel).toLowerCase()) && isEntry(rel, text)) map.entries.push(local);
    // a router's prefix (FastAPI APIRouter(prefix=…), Spring/ASP.NET class-level route) goes before its paths
    const prefix = (/(?:APIRouter|Blueprint)\([^)]*?(?:url_)?prefix\s*=\s*["'`]([^"'`]+)["'`]/.exec(text) || [])[1] || '';
    for (const re of [...ROUTE_PATTERNS, ...(path.extname(rel) === '.go' ? [GO_ROUTE] : [])]) {
      for (const m of text.matchAll(re)) {
        const route = { method: m[1].toUpperCase(), path: `${prefix}${m[2] === '/' && prefix ? '' : m[2] || ''}` || '/', file: local };
        if (!map.routes.some((r) => r.method === route.method && r.path === route.path && r.file === route.file)) map.routes.push(route);
      }
    }
    for (const [i, re] of CALL_PATTERNS.entries()) {
      for (const m of text.matchAll(re)) {
        const call = i === 0 ? { method: m[1].toUpperCase(), path: m[2].replace(/^.*?(\/v\d+\/)/, '$1') }
          : i === 1 ? { method: m[2], path: m[3], target: m[1] } : { method: (m[2] || 'GET').toUpperCase(), path: m[1] };
        call.path = call.path.replace(/\$\{[^}]*\}/g, '{}').replace(/\{[^}]*\}/g, '{}');
        if (!map.calls.some((c) => c.method === call.method && c.path === call.path && c.target === call.target)) map.calls.push({ ...call, file: local });
      }
    }
    for (const m of text.matchAll(TOOL_PATTERN)) map.tools.push({ name: m[1] || m[2] || m[3], file: local });
    for (const m of text.matchAll(CLI_PATTERN)) map.cli.push({ name: m[1] || m[2], file: local });
    for (const m of text.matchAll(EVENT_PATTERN)) if (!map.events.some((e) => e.name === m[1])) map.events.push({ name: m[1], file: local });
    const syms = symbols(rel, text);
    if (syms.length || CODE_EXT.has(path.extname(rel).toLowerCase())) map.modules.push({ file: local, doc: firstDoc(rel, text), symbols: syms });
  }
  // a Next.js / file-system router: the routes are the folders
  for (const rel of files) {
    const m = /(?:^|\/)app\/(.*?)\/?(page|route)\.(tsx?|jsx?)$/.exec(rel);
    if (m) map.routes.push({ method: m[2] === 'page' ? 'PAGE' : 'API', path: `/${m[1].replace(/\([^)]*\)\/?/g, '')}`, file: rel.slice(area.root.length + 1) });
  }
  return map;
}

const cell = (v) => String(v ?? '').replace(/\|/g, '\\|').replace(/\n/g, ' ');

/** docs/harper/CODEMAP.md section of one area, cut at `max` characters (the modules list goes last). */
function codeMapMarkdown(map, max = 40000) {
  const L = [`## ${map.area} (\`${map.root}\`)`, '',
    `${map.files} file(s) · ${map.modules.length} module(s) · ${map.routes.length} route(s) · ${map.calls.length} call(s) to other services · ${map.tools.length} tool(s) · ` +
    `${map.events.length} event name(s) · ${map.contracts.length} contract file(s) · ${map.tests.files} test file(s), ${map.tests.cases} test case(s)`, ''];
  const list = (title, items) => { if (items.length) L.push(`### ${title}`, '', ...items, ''); };
  list('Entry points', map.entries.map((e) => `- \`${cell(e)}\``));
  if (map.routes.length) {
    L.push('### Routes', '', '| Method | Path | File |', '|---|---|---|');
    for (const r of map.routes) L.push(`| ${r.method} | \`${cell(r.path)}\` | \`${cell(r.file)}\` |`);
    L.push('');
  }
  if (Object.keys(map.refs).length) {
    L.push('### Other areas it refers to', '', '| Area | Files | Where (examples) |', '|---|---|---|');
    for (const [name, r] of Object.entries(map.refs).sort((a, b) => b[1].files - a[1].files)) L.push(`| ${cell(name)} | ${r.files} | ${r.examples.map((e) => `\`${cell(e)}\``).join(', ')} |`);
    L.push('');
  }
  if (map.calls.length) {
    L.push('### Calls to other services (HTTP)', '', '| Method | Path | Client | From |', '|---|---|---|---|');
    for (const c of map.calls) L.push(`| ${c.method} | \`${cell(c.path)}\` | ${cell(c.target || '—')} | \`${cell(c.file)}\` |`);
    L.push('');
  }
  list('Tools', map.tools.map((t) => `- \`${cell(t.name)}\` — \`${cell(t.file)}\``));
  list('CLI commands', map.cli.map((t) => `- \`${cell(t.name)}\` — \`${cell(t.file)}\``));
  list('Events (names in the code)', map.events.map((t) => `- \`${cell(t.name)}\` — \`${cell(t.file)}\``));
  list('Contracts and schemas', map.contracts.map((c) => `- \`${cell(c)}\``));
  list('Configuration', map.settings.map((c) => `- \`${cell(c)}\``));
  list('Tests (the behaviour they check)', map.tests.byFile.map((t) => `- \`${cell(t.file)}\`: ${t.names.slice(0, 25).map(cell).join('; ')}${t.names.length > 25 ? ` … (+${t.names.length - 25})` : ''}`));
  L.push('### Modules', '');
  const head = L.join('\n');
  const rows = [];
  let used = head.length;
  for (const m of map.modules) {
    const row = `- \`${cell(m.file)}\`${m.doc ? ` — ${cell(m.doc).slice(0, 140)}` : ''}${m.symbols.length ? `: ${m.symbols.slice(0, 20).map(cell).join(', ')}${m.symbols.length > 20 ? ' …' : ''}` : ''}`;
    if (used + row.length > max) { rows.push(`- … ${map.modules.length - rows.length} more module(s): see the project memory`); break; }
    rows.push(row);
    used += row.length + 1;
  }
  return `${head}\n${rows.join('\n')}\n`;
}

/** The files a cloud model reads whole: entry points, route files, contracts, settings — up to `budget` characters. */
function keyFiles(root, map, budget = 120000) {
  const ranked = [...new Set([...map.entries, ...map.routes.map((r) => r.file), ...map.tools.map((t) => t.file), ...map.calls.map((c) => c.file),
    ...map.contracts, ...map.settings])];
  const out = [];
  let used = 0;
  for (const local of ranked) {
    const rel = `${map.root}/${local}`;
    const text = read(root, rel);
    if (!text.trim() || used + text.length > budget) continue;
    out.push({ path: rel, text });
    used += text.length;
  }
  return out;
}

const KINDS = ['feat', 'fix', 'perf', 'refactor', 'docs', 'test', 'build', 'ci', 'chore', 'revert', 'security'];

/** What git says an area did: commits by kind, the latest features and fixes, its first and last day. null without git. */
function history(root, area, limit = 400) {
  if (!isGit(root)) return null;
  let lines = [];
  try { lines = git(root, ['log', '--no-merges', `-n${limit}`, '--format=%h%x09%cs%x09%s', '--', area.root]).split('\n').filter(Boolean); } catch { return null; }
  let total = 0;
  try { total = Number(git(root, ['rev-list', '--count', 'HEAD', '--', area.root]).trim()) || lines.length; } catch { total = lines.length; }
  const commits = lines.map((l) => { const [hash, day, ...s] = l.split('\t'); return { hash, day, subject: s.join('\t') }; });
  const byKind = {};
  for (const c of commits) {
    const k = (/^(\w+)(?:\([^)]*\))?!?:/.exec(c.subject) || [])[1]?.toLowerCase();
    const kind = KINDS.includes(k) ? k : 'other';
    byKind[kind] = (byKind[kind] || 0) + 1;
  }
  return {
    area: area.name, total, first: commits[commits.length - 1]?.day || '', last: commits[0]?.day || '', byKind,
    features: commits.filter((c) => /^feat/i.test(c.subject)).slice(0, 40),
    fixes: commits.filter((c) => /^fix/i.test(c.subject)).slice(0, 20),
    recent: commits.slice(0, 15),
  };
}

function tagsWithDates(root) {
  if (!isGit(root)) return [];
  try {
    return git(root, ['for-each-ref', 'refs/tags', '--sort=-creatordate', '--format=%(refname:short)%09%(creatordate:short)'])
      .split('\n').filter(Boolean).slice(0, 20).map((l) => { const [name, day] = l.split('\t'); return { name, day }; });
  } catch { return []; }
}

function historyMarkdown(h) {
  if (!h) return '';
  const kinds = Object.entries(h.byKind).sort((a, b) => b[1] - a[1]).map(([k, n]) => `${k} ${n}`).join(', ');
  const L = [`### ${h.area}`, '', `${h.total} commit(s), ${h.first} → ${h.last}${kinds ? ` (last ${Object.values(h.byKind).reduce((a, b) => a + b, 0)}: ${kinds})` : ''}`, ''];
  const list = (title, items) => { if (items.length) L.push(`${title}:`, '', ...items.map((c) => `- ${c.day} \`${c.hash}\` ${cell(c.subject)}`), ''); };
  list('Features', h.features);
  list('Fixes', h.fixes);
  if (!h.features.length && !h.fixes.length) list('Latest commits', h.recent);
  return L.join('\n');
}

module.exports = { sourceFiles, codeMap, codeMapMarkdown, keyFiles, history, historyMarkdown, tagsWithDates, isTest, symbols, testNames };
