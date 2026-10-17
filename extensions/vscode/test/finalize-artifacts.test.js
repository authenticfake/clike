'use strict';
// /finalize artifacts: the solution profile and smoke scripts are collected (and committed); a file
// the developer modified before the run and the run did not touch is left out.
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('fs');
const os = require('os');
const path = require('path');
const Module = require('module');
const { execFileSync } = require('child_process');

const originalLoad = Module._load;
Module._load = function (request, parent, isMain) {
  if (request === 'vscode') {
    return {
      FileType: { File: 1, Directory: 2 },
      Uri: { file: (p) => ({ fsPath: p }) },
      workspace: {
        getConfiguration: () => ({ get: (_k, d) => d }),
        fs: {
          stat: async (uri) => { const st = fs.statSync(uri.fsPath); return { type: st.isFile() ? 1 : 2, size: st.size }; },
          readFile: async (uri) => fs.readFileSync(uri.fsPath),
        },
      },
      window: { createOutputChannel: () => ({ appendLine() {} }) },
    };
  }
  return originalLoad.call(this, request, parent, isMain);
};
const { collectFinalizeCandidateFileArtifacts } = require('../utility');
Module._load = originalLoad;

const git = (cwd, ...args) => execFileSync('git', args, { cwd, encoding: 'utf8' });

test('finalize collects its work, also in new directories and from an uncommitted earlier run, not the developer\'s changes', async () => {
  const fv = require('../finalize-verify');
  const root = fs.realpathSync(fs.mkdtempSync(path.join(os.tmpdir(), 'clike-finalize-art-')));
  const put = (rel, text) => {
    fs.mkdirSync(path.dirname(path.join(root, rel)), { recursive: true });
    fs.writeFileSync(path.join(root, rel), text);
  };
  git(root, 'init', '-q', '-b', 'main');
  put('src/pkg/__init__.py', 'A = 1\n');
  put('src/runtime/compose.yaml', 'services: {}\n');
  git(root, 'add', '.');
  git(root, '-c', 'user.email=t@t', '-c', 'user.name=t', 'commit', '-qm', 'init');
  put('src/pkg/__init__.py', 'A = 2\n'); // the developer's own change, before /finalize
  fv.ensureDirtyBaseline(root);
  // a first /finalize run writes, then ends before its commit
  put('src/runtime/compose.yaml', 'services: {app: {}}\n');
  put('scripts/solution_local.py', 'print(1)\n'); // scripts/ is a new, untracked directory
  // the next run: the baseline of the round is kept
  fv.ensureDirtyBaseline(root);
  put('ci/SOLUTION_LTC.json', '{"req_id":"SOLUTION","checks":[]}\n');
  put('ci/solution/smoke.mjs', 'console.log(1)\n');
  put('docs/harper/FINALIZE_REPORT.md', '# Report\n');

  const paths = (await collectFinalizeCandidateFileArtifacts({ fsPath: root }, { baseline: fv.readDirtyBaseline(root) })).map((a) => a.path);
  for (const rel of ['ci/SOLUTION_LTC.json', 'ci/solution/smoke.mjs', 'docs/harper/FINALIZE_REPORT.md',
    'src/runtime/compose.yaml', 'scripts/solution_local.py']) {
    assert.ok(paths.includes(rel), `${rel} collected`);
  }
  assert.ok(!paths.includes('src/pkg/__init__.py'), 'the developer\'s untouched change left out');
  put('src/pkg/__init__.py', 'A = 3\n'); // finalize changed it too: now it is finalize's
  const again = (await collectFinalizeCandidateFileArtifacts({ fsPath: root }, { baseline: fv.readDirtyBaseline(root) })).map((a) => a.path);
  assert.ok(again.includes('src/pkg/__init__.py'));
  fv.clearDirtyBaseline(root);
  assert.equal(fv.readDirtyBaseline(root), null);
  fs.rmSync(root, { recursive: true, force: true });
});
