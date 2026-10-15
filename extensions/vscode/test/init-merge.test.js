'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('fs');
const os = require('os');
const path = require('path');

const { copyTemplateTree, mergeGitignore } = require('../init-merge');

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
