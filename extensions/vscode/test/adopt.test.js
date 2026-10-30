'use strict';
// /adopt, survey part: an existing monorepo surveyed as it is (foundation-like: Python areas with uv and
// make, a Node workspace on Node 24, CI per area, documentation, git) — nothing of it written.
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('fs');
const os = require('os');
const path = require('path');
const { execFileSync } = require('child_process');
const a = require('../adopt');

function repo() {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'clike-adopt-'));
  const put = (rel, text) => { fs.mkdirSync(path.dirname(path.join(root, rel)), { recursive: true }); fs.writeFileSync(path.join(root, rel), text); };
  put('README.md', '# Foundation\n');
  put('docs/README.md', '# Docs\n');
  put('docs/harper/IDEA.md', '# template\n');
  put('gateway/pyproject.toml', '[project]\nname = "gateway"\nrequires-python = ">=3.14"\n');
  put('gateway/uv.lock', '');
  put('gateway/Makefile', 'check: lint test ## all\n\tuv run pytest\nlint:\n\truff check\ntest:\n\tpytest\nUV ?= uv\n');
  put('gateway/src/gateway/__init__.py', '');
  put('gateway/tests/test_x.py', '');
  put('gateway/AGENTS.md', '# conventions\n');
  put('gateway/docs/adr/0001.md', '# ADR\n');
  put('gateway/docs/reference/openapi.json', '{}');
  put('gateway/.venv/lib/x.py', '');
  put('gateway/.venv/lib/README.md', '# a dependency\n');
  put('gateway/examples/agents/helper/prompt.md', '# prompt\n');
  put('deploy/README.md', '# deploy\n');
  put('portal/package.json', JSON.stringify({ scripts: { test: 'vitest', lint: 'eslint', typecheck: 'tsc' }, engines: { node: '>=24' } }));
  put('portal/package-lock.json', '{}');
  put('portal/apps/portal/page.tsx', '');
  put('portal/packages/sdk/index.ts', '');
  put('portal/e2e/login.spec.ts', '');
  put('portal/node_modules/x/package.json', '{}');
  put('deploy/compose.yaml', 'services: {}\n');
  put('.github/workflows/gateway-ci.yml', 'jobs:\n  t:\n    steps:\n      - run: uv sync --frozen --all-extras\n      - run: make check\n');
  execFileSync('git', ['init', '-q'], { cwd: root });
  execFileSync('git', ['add', '.'], { cwd: root });
  execFileSync('git', ['-c', 'user.email=a@b', '-c', 'user.name=t', 'commit', '-qm', 'first'], { cwd: root });
  return root;
}

test('adopt: areas, stacks, roots, commands from make / scripts / CI, runtimes, docs, git', () => {
  const root = repo();
  const s = a.survey(root);
  const gw = s.areas.find((x) => x.root === 'gateway');
  const portal = s.areas.find((x) => x.root === 'portal');
  assert.deepEqual(s.areas.map((x) => x.root), ['gateway', 'portal']);  // deploy/ has no manifest: not an area
  assert.equal(gw.stack, 'python');
  assert.deepEqual(gw.source, ['gateway/src']);
  assert.deepEqual(gw.tests, ['gateway/tests']);
  assert.equal(gw.commands.check, 'make check');
  assert.equal(gw.commands.setup, 'uv sync --frozen --all-extras');  // the CI's own setup
  assert.deepEqual(gw.runtime, { python: '>=3.14' });
  assert.deepEqual(gw.agentContext, ['gateway/AGENTS.md']);
  assert.deepEqual(portal.source, ['portal/apps/portal', 'portal/packages/sdk']);
  assert.deepEqual(portal.tests, ['portal/e2e']);
  assert.equal(portal.commands.test, 'npm run test');
  assert.equal(portal.commands.setup, 'npm ci');
  assert.deepEqual(portal.runtime, { node: '>=24' });
  for (const doc of ['README.md', 'docs/README.md', 'gateway/AGENTS.md', 'gateway/docs/adr/0001.md', 'gateway/docs/reference/openapi.json',
    'gateway/examples/agents/helper/prompt.md', 'deploy/README.md']) {
    assert.ok(s.docs.includes(doc), doc);
  }
  assert.ok(!s.docs.some((d) => d.startsWith('docs/harper/')), 'the Harper documents are not re-indexed');
  assert.ok(!s.docs.some((d) => d.includes('.venv/')), 'dependency folders are not documents');
  assert.equal(s.git.commits, 1);
  assert.equal(s.ci[0].file, '.github/workflows/gateway-ci.yml');
  fs.rmSync(root, { recursive: true, force: true });
});

test('adopt: project.json keeps what the developer corrected; the baseline runs each area as its team does', () => {
  const root = repo();
  const s = a.survey(root);
  const meta = a.mergeProjectAreas({ project_id: 'f', areas: [{ name: 'gw', root: 'gateway', source: ['gateway/src'], tests: ['gateway/tests'], commands: { check: 'make ci' } }] }, s.areas);
  assert.equal(meta.project_id, 'f');
  assert.equal(meta.areas.find((x) => x.root === 'gateway').commands.check, 'make ci');
  assert.ok(meta.areas.find((x) => x.root === 'portal'));
  const profile = a.baselineProfile(s.areas);
  assert.deepEqual(profile.environment, { python: '>=3.14', node: '>=24' });
  assert.deepEqual(profile.setup.map((x) => [x.cwd, x.command]), [['gateway', 'uv sync --frozen --all-extras'], ['portal', 'npm ci']]);
  assert.deepEqual(profile.checks.map((x) => [x.id, x.cwd, x.command]), [['gateway::check', 'gateway', 'make check'], ['portal::test', 'portal', 'npm run test']]);
  const report = a.reportMarkdown(s, { baseline: { status: 'PASS', cases: [{ name: 'gateway::check', passed: true }] }, indexed: 5 });
  assert.match(report, /\| `gateway` \| python \(pyproject\.toml\)/);
  assert.match(report, /Baseline: \*\*PASS\*\*/);
  assert.match(report, /indexed: 5/);
  assert.equal(a.memoryItems(root, ['README.md', 'missing.md']).length, 1);
  fs.rmSync(root, { recursive: true, force: true });
});

test('adopt: make targets and a repository without git', () => {
  assert.deepEqual(a.makeTargets('check: lint ## x\nlint:\nUV ?= uv\nX := 1\n'), ['check', 'lint']);
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'clike-adopt-nogit-'));
  assert.equal(a.surveyGit(root), null);
  fs.rmSync(root, { recursive: true, force: true });
});

test('/adopt is parsed with its area and dry run', () => {
  const { parseSlash } = require('../slash-parser');
  assert.deepEqual(parseSlash('/adopt --area aigateway').args, { area: 'aigateway', dryRun: false });
  assert.deepEqual(parseSlash('/adopt --dry-run').args, { area: '', dryRun: true });
});

// ---- the analysis (G3b): baseline REQs, the check of the model's plan, area by area

const { validateExtendPlan } = require('../extend-guard');
const gw = { name: 'gateway', root: 'gateway', stack: 'python', runtime: { python: '>=3.14' }, commands: { setup: 'uv sync', check: 'make check' } };
const portal = { name: 'portal', root: 'portal', stack: 'node', runtime: {}, commands: { setup: 'npm ci', test: 'npm test' } };

test('baselineReqs: one done REQ per area, its LTC runs the team checks; a failing check is non-blocking', () => {
  const base = a.baselineReqs([gw, portal], { cases: [{ name: 'gateway::check', passed: true }, { name: 'portal::test', passed: false }] });
  assert.deepEqual(base.reqs.map((r) => [r.id, r.area, r.status, r.origin]), [['REQ-001', 'gateway', 'done', 'adopted'], ['REQ-002', 'portal', 'done', 'adopted']]);
  assert.equal(base.ltcs['REQ-001'].checks[0].blocking, true);
  assert.deepEqual(base.ltcs['REQ-001'].environment, { python: '>=3.14' });
  assert.equal(base.ltcs['REQ-001'].checks[0].cwd, 'gateway');
  assert.equal(base.ltcs['REQ-002'].checks[0].blocking, false);
  assert.deepEqual(base.reqs[1].failing_at_adoption, ['portal::test']);
  // area by area: numbering continues after the REQs already adopted
  assert.equal(a.baselineReqs([portal], null, base.reqs.slice(0, 1).concat([{ id: 'REQ-004' }])).reqs[0].id, 'REQ-005');
});

test('checkAdoptedPlan: baseline kept, done only when covered, open otherwise, area and acceptance required', () => {
  const base = a.baselineReqs([gw], null);
  const beforeText = JSON.stringify({ reqs: base.reqs });
  const after = (extra) => JSON.stringify({ reqs: [...base.reqs, ...extra] });
  const ok = a.checkAdoptedPlan({ beforeText, afterText: after([
    { id: 'REQ-002', title: 'routing', area: 'gateway', status: 'done', acceptance: ['(observed) routes'] },
    { id: 'REQ-003', title: 'quota', area: 'gateway', status: 'planned', acceptance: ['(declared) quota'] },
  ]), areas: [gw], baselineIds: ['REQ-001'], validateExtendPlan });
  assert.equal(ok.ok, true, ok.errors.join('; '));
  const plan = JSON.parse(ok.planText);
  assert.equal(plan.reqs.find((r) => r.id === 'REQ-002').covered_by, 'REQ-001');
  assert.equal(plan.reqs.find((r) => r.id === 'REQ-003').status, 'open');
  assert.deepEqual(ok.summary.map((s) => s.id), ['REQ-002', 'REQ-003']);
  const bad = a.checkAdoptedPlan({ beforeText, afterText: after([{ id: 'REQ-002', title: 'x', status: 'done' }]),
    areas: [gw], baselineIds: ['REQ-001'], validateExtendPlan });
  assert.equal(bad.ok, false);
  assert.ok(bad.errors.some((e) => /no acceptance/.test(e)) && bad.errors.some((e) => /no area/.test(e)));
  // a REQ of an area adopted before is not this run's
  const second = a.checkAdoptedPlan({ beforeText: after([{ id: 'REQ-002', title: 'r', area: 'gateway', status: 'done', acceptance: ['a'] }]),
    afterText: after([{ id: 'REQ-002', title: 'r', area: 'gateway', status: 'done', acceptance: ['a'] }]),
    areas: [portal], baselineIds: ['REQ-003'], validateExtendPlan });
  assert.deepEqual(second.summary, []);
});

test('checkAdoptedPlan: a journey across areas may name the areas of the project not adopted yet', () => {
  const gw = { name: 'agent-platform', root: 'agent-platform', stack: 'python', runtime: {}, commands: { check: 'make check' } };
  const base = a.baselineReqs([gw]).reqs;
  const plan = JSON.stringify({ reqs: [...base, { id: 'REQ-002', title: 'Portal to MCP', areas: ['agent-platform', 'portal'], status: 'open', acceptance: ['(declared) x'] },
    { id: 'REQ-003', title: 'Elsewhere', area: 'nowhere', status: 'open', acceptance: ['(declared) y'] }] });
  const { validateExtendPlan } = require('../extend-guard');
  const out = a.checkAdoptedPlan({ beforeText: JSON.stringify({ reqs: base }), afterText: plan, areas: [gw], baselineIds: ['REQ-001'], validateExtendPlan,
    projectAreas: [{ name: 'agent-platform' }, { name: 'portal' }] });
  assert.equal(out.ok, true, out.errors.join('; '));
  assert.deepEqual(out.warnings.filter((w) => /is not an area/.test(w)), ['REQ-003: area nowhere is not an area of .clike/project.json']);
});

test('adoptablePlan: a new plan, or adopted area by area without the same area twice', () => {
  const base = a.baselineReqs([gw], null);
  assert.equal(a.adoptablePlan({}, [gw]), '');
  assert.equal(a.adoptablePlan({ reqs: base.reqs }, [portal]), '');
  const analysed = [...base.reqs, { id: 'REQ-002', area: 'gateway', origin: 'adopted', title: 'Routing' }];
  assert.match(a.adoptablePlan({ reqs: analysed }, [gw]), /already adopted: gateway/);
  assert.match(a.adoptablePlan({ reqs: [{ id: 'REQ-001', origin: 'harper' }] }, [gw]), /did not adopt/);
});

test('contextDocuments: the README and the run guide whole (they are returned integrated), the other documents cut', () => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'clike-adopt-docs-'));
  fs.mkdirSync(path.join(root, 'gateway'), { recursive: true });
  fs.mkdirSync(path.join(root, 'docs', 'harper'), { recursive: true });
  fs.writeFileSync(path.join(root, 'README.md'), 'r'.repeat(100));
  fs.writeFileSync(path.join(root, 'docs', 'harper', 'HOWTO_RUN.md'), 'h'.repeat(100));
  fs.writeFileSync(path.join(root, 'gateway', 'README.md'), 'g'.repeat(100));
  fs.writeFileSync(path.join(root, 'gateway', 'AGENTS.md'), '# rules');
  const docs = a.contextDocuments(root, { agentContext: [] }, [{ ...gw, agentContext: ['gateway/AGENTS.md'] }], 'docs/harper/ADOPT_x.md', 50);
  assert.deepEqual(docs.map((d) => d.path), ['README.md', 'docs/harper/HOWTO_RUN.md', 'gateway/AGENTS.md', 'gateway/README.md']);
  assert.deepEqual(docs.filter((d) => d.integrate).map((d) => d.text.length), [100, 100]);
  assert.match(docs[3].text, /cut: the rest is in the project memory/);
});

test('adopt: what a model may write is checked as it is written (normalized), origins of the import count as adopted, areas as declared', () => {
  const w = a.writableFiles([{ path: 'docs/harper/../../src/app.py' }, { path: 'runs/../setup.py' }, { path: 'docs/harper/../x.md' },
    { path: './docs/harper/SPEC.md' }, { path: '/etc/x' }, { path: 'docs/harper/../../../x' }, { path: 'README.md' }]);
  assert.deepEqual(w.kept.map((f) => f.path), ['./docs/harper/SPEC.md', 'README.md']);
  assert.deepEqual(w.dropped, ['src/app.py', 'setup.py', 'docs/x.md', '/etc/x', '../x']);
  const x = { name: 'x', root: 'x', stack: 'python', runtime: {}, commands: { check: 'make check' } };
  const reqs = [...a.baselineReqs([x]).reqs, { id: 'REQ-002', areas: ['x', 'y'], origin: 'import:backlog:W-1', title: 'W-1' }];
  assert.equal(a.adoptablePlan({ reqs }, [{ name: 'y' }]), '');                    // a backlog item does not block the next area
  assert.deepEqual(a.adoptedAreas({ reqs }), ['x']);                                 // its REQ names the area in areas[]
  assert.match(a.adoptablePlan({ reqs: [...reqs, { id: 'REQ-003', origin: 'harper' }] }, [{ name: 'y' }]), /did not adopt/);
  // the areas of .clike/project.json: a corrected command is used, an area declared by hand can be adopted
  const eff = a.effectiveAreas([{ ...x, agentContext: ['x/AGENTS.md'] }], [{ name: 'x', root: 'x', commands: { check: 'make test-all' } }, { name: 'root', root: '.' }]);
  assert.equal(eff[0].commands.check, 'make test-all');
  assert.deepEqual(eff[0].agentContext, ['x/AGENTS.md']);
  assert.deepEqual([eff[1].name, eff[1].root, eff[1].stack], ['root', '.', 'unknown']);
});

test('adopt: a nested area is named by its path; an adoption that stopped before its analysis runs again', () => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'clike-adopt-nested-'));
  fs.mkdirSync(path.join(root, 'events', 'python'), { recursive: true });
  fs.writeFileSync(path.join(root, 'events', 'python', 'pyproject.toml'), '[project]\nname = "events"\n');
  const [ev] = a.surveyAreas(root);
  assert.equal(ev.name, 'events-python');
  const merged = a.mergeProjectAreas({ areas: [{ name: 'python', root: 'events/python', commands: { test: 'pytest -q' } }] }, [ev]);
  assert.equal(merged.areas[0].name, 'events-python');
  assert.deepEqual(merged.areas[0].commands, { test: 'pytest -q' });   // the rest the developer set stays
  const gw = { name: 'gateway', root: 'gateway', stack: 'python', runtime: {}, commands: { check: 'make check' } };
  const base = a.baselineReqs([gw]);
  assert.equal(a.adoptablePlan({ reqs: base.reqs }, [gw]), '');                 // baseline only: again
  assert.deepEqual(a.keptReqs({ reqs: base.reqs }, [gw]), []);
  assert.match(a.adoptablePlan({ reqs: [...base.reqs, { id: 'REQ-002', area: 'gateway', origin: 'adopted', title: 'Routing' }] }, [gw]), /already adopted: gateway/);
  fs.rmSync(root, { recursive: true, force: true });
});

test('/adopt starts its analysis as a Harper phase run (harperRun), never through the /eval and /gate handler', () => {
  const src = fs.readFileSync(path.join(__dirname, '..', 'extension.js'), 'utf8');
  const line = src.split('\n').find((l) => l.includes("extendMode: 'adopt'"));
  assert.match(line, /type: 'harperRun', cmd: 'extend'/);
});
