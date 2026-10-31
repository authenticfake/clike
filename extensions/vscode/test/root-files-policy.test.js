'use strict';
// B2B REQ-037/038: the env examples, .gitignore, the solution eval profile and the runbooks had no
// legal place under root/, so the KITs staged them under ci/shared/ (never promoted).
const test = require('node:test');
const assert = require('node:assert/strict');
const { isAllowedRootPath, DEFAULT_ROOT_FOLDERS, DEFAULT_ROOT_FILES } = require('../root-files-policy');

const policy = { folders: DEFAULT_ROOT_FOLDERS, files: DEFAULT_ROOT_FILES };

test('root/ delivers env examples, ignore files, the solution profile and project docs', () => {
  for (const p of ['.env.example', '.env.oidc.example', '.env.live.example', '.gitignore', '.dockerignore',
    'ci/SOLUTION_LTC.json', 'docs/LOCAL_LIVE.md', 'docs/ops/RUNBOOK.md', 'scripts/setup_local.sh', 'Dockerfile']) {
    assert.equal(isAllowedRootPath(p, policy), true, p);
  }
});

test('root/ never delivers secrets, Harper documents, inputs, code roots or other ci files', () => {
  for (const p of ['.env', '.env.local', '.env.live', 'id_rsa', 'cert.pem', 'docs/harper/plan.json', 'docs/inputs/v3/a.md',
    'docs/reference/x.md', 'ci/check.py', 'src/app.py', 'test/x.py', 'runs/kit/x', '../etc/passwd', '/abs']) {
    assert.equal(isAllowedRootPath(p, policy), false, p);
  }
});

test('areas of .clike/project.json are repository folders a KIT delivers through root/', () => {
  const fs = require('fs');
  const os = require('os');
  const path = require('path');
  const { rootPolicy, areaTestRoots } = require('../root-files-policy');
  const ws = fs.mkdtempSync(path.join(os.tmpdir(), 'clike-areas-'));
  fs.mkdirSync(path.join(ws, '.clike'));
  fs.writeFileSync(path.join(ws, '.clike', 'project.json'), JSON.stringify({ areas: [
    { name: 'gateway', root: 'aigateway', source: ['aigateway/src'], tests: ['aigateway/tests'] },
    { name: 'portal', root: 'portal', source: ['portal/apps/portal', 'portal/packages'], tests: ['portal/e2e'] },
    { root: '../outside' }, { root: 'docs' }, { root: 'src' },
  ] }));
  const p = rootPolicy(ws);
  assert.deepEqual(p.areas.map((a) => a.root), ['aigateway', 'portal']);
  for (const rel of ['aigateway/src/aigateway/routes.py', 'aigateway/tests/test_routes.py', 'portal/apps/portal/page.tsx']) {
    assert.equal(isAllowedRootPath(rel, p), true, rel);
  }
  assert.equal(isAllowedRootPath('aigateway/.env', p), false);
  assert.deepEqual(areaTestRoots(ws), ['aigateway/tests', 'portal/e2e']);
  // a project without areas: the policy is as before
  assert.deepEqual(rootPolicy(fs.mkdtempSync(path.join(os.tmpdir(), 'clike-plain-'))).areas, []);
  fs.rmSync(ws, { recursive: true, force: true });
});
