'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('fs');
const os = require('os');
const path = require('path');

const { copyTemplateTree, mergeGitignore, hasTeamProcess, teamProcessRedirect, PROPOSALS_DIR } = require('../init-merge');

const write = (root, rel, text) => { fs.mkdirSync(path.dirname(path.join(root, rel)), { recursive: true }); fs.writeFileSync(path.join(root, rel), text); };

test('init: the template never overwrites a file of an existing project', () => {
  const tpl = fs.mkdtempSync(path.join(os.tmpdir(), 'clike-tpl-'));
  const ws = fs.mkdtempSync(path.join(os.tmpdir(), 'clike-ws-'));
  write(tpl, 'README.md', '# ${project.name}\n');
  write(tpl, 'docs/harper/IDEA.md', 'idea of ${project.name}\n');
  write(tpl, '.clike/project.json', '{"project_id":"${project.id}"}\n');
  write(ws, 'README.md', '# My existing project\n');
  write(ws, 'backend/app/main.py', 'app = 1\n');
  const r = copyTemplateTree(tpl, ws, { vars: { '${project.name}': 'Portal', '${project.id}': 'portal' } });
  assert.deepEqual(r.kept, ['README.md']);
  assert.deepEqual(r.created.sort(), ['.clike/project.json', 'docs/harper/IDEA.md']);
  assert.equal(fs.readFileSync(path.join(ws, 'README.md'), 'utf8'), '# My existing project\n');
  assert.equal(fs.readFileSync(path.join(ws, 'docs/harper/IDEA.md'), 'utf8'), 'idea of Portal\n');
  assert.equal(fs.readFileSync(path.join(ws, '.clike/project.json'), 'utf8'), '{"project_id":"portal"}\n');
  assert.equal(fs.readFileSync(path.join(ws, 'backend/app/main.py'), 'utf8'), 'app = 1\n');
});

test('init: .gitignore keeps its rules and gets only the CLike rules it lacks', () => {
  const rules = ['node_modules/', 'runs/eval/', '.clike/sessions/'];
  assert.deepEqual(mergeGitignore(null, rules), { text: 'node_modules/\nruns/eval/\n.clike/sessions/\n', added: rules });
  const merged = mergeGitignore('# mine\nnode_modules/\n*.pyc', rules);
  assert.equal(merged.text, '# mine\nnode_modules/\n*.pyc\n\n# CLike\nruns/eval/\n.clike/sessions/\n');
  assert.deepEqual(merged.added, ['runs/eval/', '.clike/sessions/']);
  const again = mergeGitignore(merged.text, rules);
  assert.equal(again.text, merged.text);
  assert.deepEqual(again.added, []);
});

test('init: a repository with its own review / PR / CI process gets CLike\'s as proposals only', () => {
  // foundation: six workflows of its own; a new CODEOWNERS would change who must approve its PRs
  const tpl = fs.mkdtempSync(path.join(os.tmpdir(), 'clike-tpl-'));
  write(tpl, '.github/CODEOWNERS', '* @owner\n');
  write(tpl, '.github/pull_request_template.md', '## Summary\n');
  write(tpl, '.github/workflows/clike-ci.yaml', 'name: clike\n');
  write(tpl, '.clike/project.json', '{}\n');
  const team = fs.mkdtempSync(path.join(os.tmpdir(), 'clike-ws-'));
  write(team, '.github/workflows/aigateway-ci.yml', 'name: aigateway\n');
  assert.equal(hasTeamProcess(team), true);
  const r = copyTemplateTree(tpl, team, { redirect: teamProcessRedirect(team) });
  assert.deepEqual(r.proposed.sort(), ['.github/CODEOWNERS', '.github/pull_request_template.md', '.github/workflows/clike-ci.yaml']);
  assert.deepEqual(r.created, ['.clike/project.json']);
  for (const rel of r.proposed) {
    assert.equal(fs.existsSync(path.join(team, rel)), false, rel);
    assert.equal(fs.existsSync(path.join(team, PROPOSALS_DIR, rel)), true, rel);
  }
  assert.deepEqual(fs.readdirSync(path.join(team, '.github/workflows')), ['aigateway-ci.yml']);
  // a new folder (or one without a process) gets them as before
  const fresh = fs.mkdtempSync(path.join(os.tmpdir(), 'clike-ws-'));
  write(fresh, 'src/app.py', 'x = 1\n');
  assert.equal(hasTeamProcess(fresh), false);
  const n = copyTemplateTree(tpl, fresh, { redirect: teamProcessRedirect(fresh) });
  assert.deepEqual(n.proposed, []);
  assert.equal(fs.existsSync(path.join(fresh, '.github/CODEOWNERS')), true);
  assert.equal(fs.existsSync(path.join(fresh, PROPOSALS_DIR)), false);
});

test('init: a CODEOWNERS or a PR template anywhere GitHub reads them counts as a process', () => {
  for (const rel of ['CODEOWNERS', 'docs/CODEOWNERS', '.github/CODEOWNERS', 'PULL_REQUEST_TEMPLATE.md',
    '.github/pull_request_template.md', '.github/PULL_REQUEST_TEMPLATE/feature.md']) {
    const ws = fs.mkdtempSync(path.join(os.tmpdir(), 'clike-ws-'));
    write(ws, rel, 'x\n');
    assert.equal(hasTeamProcess(ws), true, rel);
  }
  const ws = fs.mkdtempSync(path.join(os.tmpdir(), 'clike-ws-'));
  write(ws, '.github/workflows/README.md', 'notes\n');
  assert.equal(hasTeamProcess(ws), false, 'a folder of notes is not a workflow');
});
