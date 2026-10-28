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
  for (const doc of ['README.md', 'docs/README.md', 'gateway/AGENTS.md', 'gateway/docs/adr/0001.md', 'gateway/docs/reference/openapi.json']) {
    assert.ok(s.docs.includes(doc), doc);
  }
  assert.ok(!s.docs.some((d) => d.startsWith('docs/harper/')), 'the Harper documents are not re-indexed');
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

test('adoptablePlan: a new plan, or adopted area by area without the same area twice', () => {
  const base = a.baselineReqs([gw], null);
  assert.equal(a.adoptablePlan({}, [gw]), '');
  assert.equal(a.adoptablePlan({ reqs: base.reqs }, [portal]), '');
  assert.match(a.adoptablePlan({ reqs: base.reqs }, [gw]), /already adopted: gateway/);
  assert.match(a.adoptablePlan({ reqs: [{ id: 'REQ-001', origin: 'harper' }] }, [gw]), /did not adopt/);
});

test('contextDocuments: the survey report, the agent context files and the READMEs, cut', () => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'clike-adopt-docs-'));
  fs.mkdirSync(path.join(root, 'gateway'), { recursive: true });
  fs.writeFileSync(path.join(root, 'README.md'), 'r'.repeat(100));
  fs.writeFileSync(path.join(root, 'gateway', 'README.md'), '# gw');
  fs.writeFileSync(path.join(root, 'gateway', 'AGENTS.md'), '# rules');
  const docs = a.contextDocuments(root, { agentContext: [] }, [{ ...gw, agentContext: ['gateway/AGENTS.md'] }], 'docs/harper/ADOPT_x.md', 50);
  assert.deepEqual(docs.map((d) => d.path), ['README.md', 'gateway/AGENTS.md', 'gateway/README.md']);
  assert.match(docs[0].text, /cut: the rest is in the project memory/);
});
