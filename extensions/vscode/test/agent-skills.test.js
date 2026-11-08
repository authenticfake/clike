'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('fs');
const os = require('os');
const path = require('path');
const { spawnSync } = require('child_process');

const {
  syncAgentSkills, toNativeSkill, parseSkill, lockedRootsEnv, upsertBlock, BLOCK_BEGIN, BLOCK_END,
} = require('../agent-skills');

const TEMPLATE_CLIKE = path.join(__dirname, '..', 'templates', 'harper-init', '.clike');

function project() {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'clike-skills-'));
  fs.cpSync(TEMPLATE_CLIKE, path.join(root, '.clike'), { recursive: true });
  return root;
}

// Agent Skills specification (agentskills.io): name 1–64 lowercase/hyphen matching the folder,
// description 1–1024, only the standard top-level keys, metadata a map of string values.
function assertSpecCompliant(dir) {
  const text = fs.readFileSync(path.join(dir, 'SKILL.md'), 'utf8');
  const m = /^---\n([\s\S]*?)\n---\n/.exec(text);
  assert.ok(m, `${dir}: frontmatter`);
  const top = {};
  const metadata = {};
  let inMeta = false;
  for (const line of m[1].split('\n')) {
    if (/^\s{2}\S/.test(line)) {
      assert.ok(inMeta, `${dir}: nested key outside metadata: ${line}`);
      const kv = /^\s{2}([a-z0-9_-]+): (".*")$/.exec(line);
      assert.ok(kv, `${dir}: metadata value must be a string: ${line}`);
      metadata[kv[1]] = JSON.parse(kv[2]);
      continue;
    }
    const kv = /^([a-z-]+):(.*)$/.exec(line);
    assert.ok(kv, `${dir}: bad line ${line}`);
    top[kv[1]] = kv[2].trim();
    inMeta = kv[1] === 'metadata';
  }
  const allowed = new Set(['name', 'description', 'license', 'compatibility', 'metadata', 'allowed-tools']);
  for (const key of Object.keys(top)) assert.ok(allowed.has(key), `${dir}: non-standard key ${key}`);
  assert.equal(top.name, path.basename(dir));
  assert.match(top.name, /^[a-z0-9]+(-[a-z0-9]+)*$/);
  assert.ok(top.name.length <= 64);
  const description = JSON.parse(top.description);
  assert.ok(description.length >= 1 && description.length <= 1024, `${dir}: description length`);
  assert.ok(Object.values(metadata).every((v) => typeof v === 'string'));
}

test('every shipped skill becomes a standard native skill for both agents, and a second sync writes nothing', () => {
  const root = project();
  const first = syncAgentSkills(root);
  assert.ok(first.skills.includes('journey-identity-access'));
  assert.ok(first.skills.includes('bmad-acceptance-modeling'), 'vendored skills are installed with their vendor prefix');
  for (const target of ['.claude/skills', '.agents/skills']) {
    for (const name of first.skills) assertSpecCompliant(path.join(root, target, name));
    const refs = path.join(root, target, 'journey-identity-access', 'references', 'test-idioms.md');
    assert.ok(fs.existsSync(refs), 'skill resources are installed with the skill');
  }
  const native = fs.readFileSync(path.join(root, '.claude/skills/journey-identity-access/SKILL.md'), 'utf8');
  assert.match(native, /## Scenario catalog/);
  assert.match(native, /\*\*IAM-05\*\* \(required\) Password reset/);
  assert.match(native, /clike-scenarios: "IAM-01, IAM-02/);
  assert.deepEqual(syncAgentSkills(root).written, []);
});

test('CLAUDE.md and AGENTS.md get the CLike block, and the rest of the file is kept', () => {
  const root = project();
  fs.writeFileSync(path.join(root, 'AGENTS.md'), '# Team rules\n\nUse tabs.\n');
  syncAgentSkills(root);
  const agents = fs.readFileSync(path.join(root, 'AGENTS.md'), 'utf8');
  assert.match(agents, /^# Team rules\n\nUse tabs\.\n\n<!-- CLIKE:BEGIN/);
  assert.match(agents, /Never stop at the happy path/);
  assert.match(agents, /Journey catalogs \(skills\): journey-api-contract/);
  assert.match(fs.readFileSync(path.join(root, 'CLAUDE.md'), 'utf8'), /During \/eval the acceptance surface is locked/);
  // the block is replaced in place, never duplicated
  const file = path.join(root, 'AGENTS.md');
  upsertBlock(file, `${BLOCK_BEGIN}\nnew\n${BLOCK_END}`);
  const again = fs.readFileSync(file, 'utf8');
  assert.equal(again.split(BLOCK_BEGIN).length, 2);
  assert.match(again, /Use tabs\.\n\n<!-- CLIKE:BEGIN[^\n]*\nnew\n<!-- CLIKE:END -->\n$/);
});

test('a skill CLike does not manage is never overwritten, and a removed source skill is uninstalled', () => {
  const root = project();
  const own = path.join(root, '.claude', 'skills', 'journey-ui-states');
  fs.mkdirSync(own, { recursive: true });
  fs.writeFileSync(path.join(own, 'SKILL.md'), '---\nname: journey-ui-states\ndescription: mine\n---\n');
  const r = syncAgentSkills(root);
  assert.deepEqual(r.skipped.map((s) => `${s.target}/${s.name}`), ['.claude/skills/journey-ui-states']);
  assert.match(fs.readFileSync(path.join(own, 'SKILL.md'), 'utf8'), /description: mine/);
  fs.rmSync(path.join(root, '.clike', 'skills', 'figma-fidelity'), { recursive: true });
  const after = syncAgentSkills(root);
  assert.ok(after.removed.includes('.agents/skills/figma-fidelity'));
  assert.ok(!fs.existsSync(path.join(root, '.agents', 'skills', 'figma-fidelity')));
});

test('the guard hook is added once to settings.json, which keeps its other settings', () => {
  const root = project();
  fs.mkdirSync(path.join(root, '.claude'), { recursive: true });
  fs.writeFileSync(path.join(root, '.claude', 'settings.json'), JSON.stringify({ model: 'x', hooks: { Stop: [] } }));
  syncAgentSkills(root);
  syncAgentSkills(root);
  const settings = JSON.parse(fs.readFileSync(path.join(root, '.claude', 'settings.json'), 'utf8'));
  assert.equal(settings.model, 'x');
  assert.deepEqual(settings.hooks.Stop, []);
  assert.equal(settings.hooks.PreToolUse.length, 1);
  assert.match(settings.hooks.PreToolUse[0].hooks[0].command, /clike-guard\.cjs/);
});

test('during /eval the guard refuses writes to the tests and CI of the REQ, and nothing else', () => {
  const root = project();
  syncAgentSkills(root);
  const guard = path.join(root, '.claude', 'hooks', 'clike-guard.cjs');
  const run = (file, env) => spawnSync(process.execPath, [guard], {
    input: JSON.stringify({ tool_input: { file_path: file } }),
    env: { ...process.env, CLAUDE_PROJECT_DIR: root, ...env },
    encoding: 'utf8',
  });
  const locked = lockedRootsEnv('eval', 'REQ-004');
  assert.deepEqual(locked, { CLIKE_LOCKED_ROOTS: 'runs/kit/REQ-004/test:runs/kit/REQ-004/ci' });
  const denied = run(path.join(root, 'runs/kit/REQ-004/test/test_login.py'), locked);
  assert.equal(denied.status, 2);
  assert.match(denied.stderr, /locked acceptance surface/);
  assert.equal(run('runs/kit/REQ-004/ci/LTC.json', locked).status, 2);
  assert.equal(run('runs/kit/REQ-004/ci/HOWTO.md', locked).status, 0);
  assert.equal(run('runs/kit/REQ-004/src/app/login.py', locked).status, 0);
  assert.equal(run('runs/kit/REQ-004/test/test_login.py', {}).status, 0, 'without the env (KIT, chat) nothing is refused');
  assert.deepEqual(lockedRootsEnv('kit', 'REQ-004'), {});
  assert.deepEqual(lockedRootsEnv('eval', '../x'), {});
});

test('the CLike frontmatter maps to string metadata', () => {
  const text = '---\nname: x\ndescription: d\nphases: ["kit", "eval"]\ngate_required: true\n---\n# X\n';
  assert.deepEqual(parseSkill(text).meta, { name: 'x', description: 'd', phases: ['kit', 'eval'], gate_required: 'true' });
  const native = toNativeSkill('x', text, '.clike/skills/x');
  assert.match(native, /^---\nname: x\ndescription: "d"\nmetadata:\n {2}clike-source: "\.clike\/skills\/x"\n {2}clike-phases: "kit, eval"\n {2}clike-gate_required: "true"\n---\n# X\n$/);
});
