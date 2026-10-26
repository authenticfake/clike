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
