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
