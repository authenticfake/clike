'use strict';
// /adopt: what the code and git say — sources for the project memory, the code map, the key files, the history.
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('fs');
const os = require('os');
const path = require('path');
const { execFileSync } = require('child_process');
const c = require('../adopt-code');
const adopt = require('../adopt');

function repo({ withGit = true } = {}) {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'clike-adopt-code-'));
  const put = (rel, text) => { fs.mkdirSync(path.dirname(path.join(root, rel)), { recursive: true }); fs.writeFileSync(path.join(root, rel), text); };
  put('gateway/pyproject.toml', '[project]\nname = "gateway"\n');
  put('gateway/src/gateway/app.py', '"""The HTTP surface of the gateway."""\nfrom fastapi import FastAPI\napp = FastAPI()\n');
  put('gateway/src/gateway/routes/models.py', 'router = APIRouter(prefix="/v1")\n\n@router.post("/chat/completions")\nasync def chat():\n    ...\n\n@router.get("/models")\ndef models():\n    ...\n\nclass ModelCatalog:\n    pass\n\ndef _private():\n    pass\n');
  put('gateway/src/gateway/config/settings.py', 'KNOWLEDGE_URL = "http://knowledge"\n');
  put('gateway/src/gateway/tools.py', '@mcp.tool()\ndef search_docs(q):\n    ...\n');
  put('gateway/tests/test_models.py', 'def test_chat_answers():\n    pass\n\ndef test_models_list():\n    pass\n');
  put('gateway/uv.lock', 'x');
  put('gateway/.env', 'SECRET=1\n');
  put('gateway/.env.example', 'SECRET=\n');
  put('portal/package.json', '{"name":"portal"}');
  put('portal/src/app/(shell)/agents/page.tsx', 'export default function Agents() {}\n');
  put('portal/src/lib/data.ts', 'export async function load() {\n  return clients.gateway.GET("/v1/models", {});\n}\nexport const x = await clients.gateway.POST("/v1/chat/completions", {});\n');
  put('portal/src/lib/data.test.ts', "it('loads the models', () => {});\n");
  if (withGit) {
    const g = (...args) => execFileSync('git', args, { cwd: root, stdio: 'ignore' });
    g('init', '-q'); g('config', 'user.email', 't@t'); g('config', 'user.name', 't');
    g('add', '-A'); g('commit', '-qm', 'feat(gateway): chat completions and the model catalogue');
    fs.appendFileSync(path.join(root, 'gateway/src/gateway/app.py'), '# fix\n');
    g('commit', '-qam', 'fix: the model list is sorted'); g('tag', 'v1');
  }
  return root;
}

const areas = [{ name: 'gateway', root: 'gateway' }, { name: 'portal', root: 'portal' }];

test('sourceFiles: code, tests, contracts and config of an area; no locks, no real .env', () => {
  const root = repo();
  const files = c.sourceFiles(root, areas[0]);
  assert.ok(files.includes('gateway/src/gateway/routes/models.py') && files.includes('gateway/tests/test_models.py'));
  assert.ok(files.includes('gateway/.env.example'));
  assert.ok(!files.includes('gateway/.env') && !files.includes('gateway/uv.lock'));
  // without git: the folder is walked
  const plain = repo({ withGit: false });
  assert.deepEqual(c.sourceFiles(plain, areas[0]).sort(), files.sort());
});

test('codeMap: routes with their prefix, tools, entry points, settings, tests, calls and references to other areas', () => {
  const root = repo();
  const gw = c.codeMap(root, areas[0], c.sourceFiles(root, areas[0]), areas);
  assert.deepEqual(gw.routes.map((r) => `${r.method} ${r.path}`), ['POST /v1/chat/completions', 'GET /v1/models']);
  assert.deepEqual(gw.tools.map((t) => t.name), ['search_docs']);
  assert.ok(gw.entries.includes('src/gateway/app.py'));
  assert.ok(gw.settings.includes('src/gateway/config/settings.py'));
  assert.deepEqual(gw.tests.byFile[0].names, ['test_chat_answers', 'test_models_list']);
  const mod = gw.modules.find((m) => m.file === 'src/gateway/routes/models.py');
  assert.deepEqual(mod.symbols, ['chat()', 'models()', 'class ModelCatalog']);
  assert.equal(gw.modules.find((m) => m.file === 'src/gateway/app.py').doc, 'The HTTP surface of the gateway.');

  const portal = c.codeMap(root, areas[1], c.sourceFiles(root, areas[1]), areas);
  assert.deepEqual(portal.calls.map((x) => `${x.target} ${x.method} ${x.path}`), ['gateway GET /v1/models', 'gateway POST /v1/chat/completions']);
  assert.deepEqual(portal.routes.map((r) => `${r.method} ${r.path}`), ['PAGE /agents']);
  assert.equal(portal.refs.gateway.files, 1);
  assert.equal(portal.tests.cases, 1);

  const md = c.codeMapMarkdown(portal);
  assert.match(md, /### Calls to other services \(HTTP\)/);
  assert.match(md, /\| GET \| `\/v1\/models` \| gateway \|/);
  assert.match(md, /### Other areas it refers to/);
  // cut at the budget: the module list goes last
  assert.match(c.codeMapMarkdown(gw, 300), /more module\(s\): see the project memory/);
});

test('keyFiles: entry points, routes, tools and settings, whole, within the budget', () => {
  const root = repo();
  const gw = c.codeMap(root, areas[0], c.sourceFiles(root, areas[0]), areas);
  const files = c.keyFiles(root, gw).map((f) => f.path);
  assert.ok(files.includes('gateway/src/gateway/app.py') && files.includes('gateway/src/gateway/routes/models.py'));
  assert.ok(files.includes('gateway/src/gateway/config/settings.py') && files.includes('gateway/src/gateway/tools.py'));
  assert.ok(!files.includes('gateway/tests/test_models.py'));
  assert.equal(c.keyFiles(root, gw, 10).length, 0);
});

test('history: commits of the area by kind, features and fixes; tags with their day; none without git', () => {
  const root = repo();
  const h = c.history(root, areas[0]);
  assert.equal(h.total, 2);
  assert.deepEqual(h.byKind, { fix: 1, feat: 1 });
  assert.match(h.features[0].subject, /chat completions/);
  assert.match(c.historyMarkdown(h), /Features:[\s\S]*Fixes:/);
  assert.equal(c.history(root, areas[1]).total, 1);
  assert.deepEqual(c.tagsWithDates(root).map((t) => t.name), ['v1']);
  assert.equal(c.history(repo({ withGit: false }), areas[0]), null);
});

test('adopt: the code map of every area, the sources of the areas adopted, the cloud context', () => {
  const root = repo();
  const { maps, markdown } = adopt.codeMaps(root, areas);
  assert.match(markdown, /^# Code map/);
  assert.match(markdown, /\| gateway \| \d+ \| \d+ \| 2 \| 0 \| 2 \|/);
  assert.ok(adopt.sourceItems(root, [areas[0]]).every((it) => it.path.startsWith('gateway/')));
  const docs = adopt.contextDocuments(root, { agentContext: [] }, [{ ...areas[0], agentContext: [] }], 'docs/harper/ADOPT_x.md', 6000, { maps });
  const cm = docs.find((d) => d.path === adopt.CODEMAP);
  assert.match(cm.text, /## gateway/) && assert.match(cm.text, /## portal/);
  assert.ok(docs.some((d) => d.path === 'gateway/src/gateway/routes/models.py'));
  assert.ok(!docs.some((d) => d.path.startsWith('portal/src')));
  const found = adopt.survey(root);
  assert.equal(found.history.length, 2);
  assert.match(adopt.reportMarkdown(found, {}), /Tags: `v1`[\s\S]*### History per area[\s\S]*### gateway/);
});

test('clikeOwnFiles: what /init and /adopt added goes with the adoption commit; the developer changes do not', () => {
  const root = repo();
  const put = (rel, text) => { fs.mkdirSync(path.dirname(path.join(root, rel)), { recursive: true }); fs.writeFileSync(path.join(root, rel), text); };
  put('.clike/project.json', '{}');
  put('.clike/sessions/harper.jsonl', 'x');
  put('docs/harper/PLAYBOOK.md', '# p');
  put('docs/inputs/.gitkeep', '');
  put('.gitignore', '.env\n');
  put(adopt.BASELINE_PROFILE, '{}');
  put('README_1st.md', '# first');
  put('images/clike/logo.png', 'x');
  put('foundation.code-workspace', '{}');
  put('.clike/last_init_summary.done.json', JSON.stringify({ targetDir: root }));    // names this machine's folder
  put('docs/inputs/v1/backlog.md', '# the developer backlog\n');                    // the developer's documents
  put('docs/reference/notes.md', '# notes\n');
  fs.appendFileSync(path.join(root, 'gateway/src/gateway/app.py'), '# developer work\n');
  assert.deepEqual(adopt.clikeOwnFiles(root).sort(), ['.clike/project.json', '.gitignore', 'README_1st.md', 'docs/harper/PLAYBOOK.md', 'docs/inputs/.gitkeep', 'images/clike/logo.png', 'runs/adopt/ci/LTC.json']);
  // a tracked .gitignore: only the "# CLike" block /init appends goes with the adoption
  execFileSync('git', ['add', '.gitignore'], { cwd: root }); execFileSync('git', ['commit', '-qm', 'ignore'], { cwd: root });
  fs.appendFileSync(path.join(root, '.gitignore'), '\n# CLike\n.clike/sessions/\n');
  assert.ok(adopt.clikeOwnFiles(root).includes('.gitignore'));
  fs.writeFileSync(path.join(root, '.gitignore'), 'node_modules/\n\n# CLike\n.clike/sessions/\n');   // a rule the developer removed
  assert.ok(!adopt.clikeOwnFiles(root).includes('.gitignore'));
  // a file naming this machine stays out of the commit
  assert.deepEqual(adopt.machinePathFiles(root, ['.clike/last_init_summary.done.json', '.clike/project.json', 'missing.md']), ['.clike/last_init_summary.done.json']);
});

test('the adopt guard: the project files changed while the run went are reported, never written; CLike files and the README pass', () => {
  const root = repo();
  const put = (rel, text) => { fs.mkdirSync(path.dirname(path.join(root, rel)), { recursive: true }); fs.writeFileSync(path.join(root, rel), text); };
  const app = path.join(root, 'gateway/src/gateway/app.py');
  put('gateway/src/gateway/wip.py', 'developer work\n');                       // untracked, before the run
  fs.appendFileSync(path.join(root, 'gateway/tests/test_models.py'), '# wip\n');   // uncommitted, before the run
  const snap = adopt.guardSnapshot(root);
  assert.deepEqual(adopt.guardChanges(root, snap), []);                          // what was there before is not a change
  // while the run goes (the developer's agent, or the run)
  fs.writeFileSync(app, 'rewritten\n');
  fs.writeFileSync(path.join(root, 'gateway/tests/test_models.py'), 'gone\n');
  fs.rmSync(path.join(root, 'gateway/src/gateway/wip.py'));
  put('gateway/new.py', 'new\n');
  put('docs/harper/IDEA.md', '# IDEA\n');
  put('README.md', '# integrated\n');
  put('.clike/project.json', '{}');
  assert.deepEqual(adopt.guardChanges(root, snap).sort(), ['gateway/new.py', 'gateway/src/gateway/app.py', 'gateway/src/gateway/wip.py', 'gateway/tests/test_models.py']);
  // left exactly as they are
  assert.equal(fs.readFileSync(app, 'utf8'), 'rewritten\n');
  assert.equal(fs.readFileSync(path.join(root, 'gateway/new.py'), 'utf8'), 'new\n');
  assert.equal(fs.existsSync(path.join(root, 'gateway/src/gateway/wip.py')), false);
  assert.equal(adopt.guardRestore, undefined);
  const files = adopt.writableFiles([{ path: 'README.md' }, { path: './docs/harper/SPEC.md' }, { path: 'gateway/src/x.py' }, { path: 'docs/harper/ADOPT_2026-10-30.md' }, { path: 'docs/harper/CODEMAP.md' }]);
  assert.deepEqual(files.kept.map((f) => f.path), ['README.md', './docs/harper/SPEC.md']);
  assert.deepEqual(files.dropped, ['gateway/src/x.py', 'docs/harper/ADOPT_2026-10-30.md', 'docs/harper/CODEMAP.md']);
  assert.equal(adopt.guardSnapshot(repo({ withGit: false })), null);
});
