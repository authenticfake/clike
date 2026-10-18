'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('fs');
const os = require('os');
const path = require('path');

const { buildDependencySurface, buildSolutionSurface, dependencyClosure } = require('../dependency-surface');

function project() {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'clike-surface-'));
  const put = (rel, text) => { fs.mkdirSync(path.dirname(path.join(root, rel)), { recursive: true }); fs.writeFileSync(path.join(root, rel), text); };
  put('docs/harper/plan.json', JSON.stringify({ reqs: [
    { id: 'REQ-001', title: 'Config', status: 'done', dependsOn: [] },
    { id: 'REQ-002', title: 'Discovery', status: 'done', dependsOn: ['REQ-001'] },
    { id: 'REQ-003', title: 'Login', status: 'open', dependsOn: ['REQ-002'] },
  ] }));
  // REQ-001 promoted: canonical content (edited after promotion) is what counts
  put('runs/kit/REQ-001/promotion/2026-10-01T00-00-00Z/report.json', JSON.stringify({ results: [
    { path: 'src/app/config.py', outcome: 'added' }, { path: 'test/test_config.py', outcome: 'added' },
    { path: 'src/app/big.lock', outcome: 'added' }, { path: 'scripts/run.sh', outcome: 'added' },
  ] }));
  put('src/app/config.py', 'SETTINGS = "canonical"\n');
  put('scripts/run.sh', 'echo run\n');
  put('pyproject.toml', '[project]\nname = "app"\n');
  put('runs/kit/REQ-001/ci/HOWTO.md', '# HOWTO REQ-001\nrun pytest');
  // REQ-002 not promoted yet: its KIT copy
  put('runs/kit/REQ-002/src/app/discovery/contracts.py', `class SearchPort: ...\n${'#'.repeat(900)}\n`);
  return { root, put };
}

test('dependency closure is transitive, nearest first', () => {
  const { root } = project();
  const reqs = JSON.parse(fs.readFileSync(path.join(root, 'docs/harper/plan.json'), 'utf8')).reqs;
  assert.deepEqual(dependencyClosure(reqs, 'REQ-003').map((r) => r.id), ['REQ-002', 'REQ-001']);
  fs.rmSync(root, { recursive: true, force: true });
});

test('the dependency surface carries promoted canonical code, KIT code not promoted yet and HOWTOs', () => {
  const { root } = project();
  const md = buildDependencySurface(root, 'REQ-003');
  assert.match(md, /### REQ-002 — Discovery \[done\] \(KIT files, not promoted yet\)/);
  assert.match(md, /class SearchPort/);
  assert.match(md, /SETTINGS = "canonical"/);           // canonical file, not the KIT copy
  assert.match(md, /#### scripts\/run\.sh/);              // root deliverable
  assert.match(md, /run pytest/);                         // ci/HOWTO.md
  assert.doesNotMatch(md, /test_config\.py|big\.lock/);   // tests and lockfiles are not surface
  assert.ok(md.indexOf('REQ-002') < md.indexOf('REQ-001'));
  assert.equal(buildDependencySurface(root, 'REQ-001'), '');
  const tiny = buildDependencySurface(root, 'REQ-003', { maxTotal: 1000, maxEach: 900 });
  assert.match(tiny, /Not shown \(budget\)/);
  fs.rmSync(root, { recursive: true, force: true });
});

test('the solution surface covers every delivered REQ', () => {
  const { root } = project();
  const md = buildSolutionSurface(root);
  assert.match(md, /SETTINGS = "canonical"/);
  assert.match(md, /class SearchPort/);
  fs.rmSync(root, { recursive: true, force: true });
});
