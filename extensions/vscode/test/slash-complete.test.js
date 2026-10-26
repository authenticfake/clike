const test = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');

const { completeSlash, acceptCompletion, buildBrowserSlashCompleteSource } = require('../slash-complete');
const { parseSlash } = require('../slash-parser');

const reqs = [
  { id: 'REQ-001', title: 'Schema', status: 'done', note: 'gate PASS', waiting: [], has_kit: true },
  { id: 'REQ-002', title: 'API', status: 'in_progress', note: 'next: /gate', waiting: [], has_kit: true },
  { id: 'REQ-003', title: 'UI', status: 'open', note: 'waits REQ-002', waiting: ['REQ-002'], has_kit: false },
  { id: 'REQ-004', title: 'Export', status: 'open', note: 'ready', waiting: [], has_kit: false },
];
const ctx = { mode: 'harper', reqs, next: { command: '/gate REQ-002' }, releases: ['v1', 'v2'], tools: ['kcat', 'kubectl', 'jdk@17'], models: { claude: ['opus', 'sonnet'], codex: ['gpt-5.5'] } };
const complete = (text, c = ctx) => completeSlash(text, text.length, c, parseSlash);
const labels = (res) => res.items.map((i) => i.insert);

test('command names: prefix first, the next action of the project on top', () => {
  const res = complete('/ev');
  assert.deepEqual(labels(res), ['/eval']);
  assert.equal(res.items[0].detail, 'Acceptance checks of the REQ in the sandbox (+ regression)');
  const g = complete('/g');
  assert.equal(g.items[0].kind, 'next');
  assert.equal(g.items[0].insert, '/gate REQ-002');
  assert.equal(labels(g)[1], '/gate');
  assert.ok(labels(complete('/')).length >= 10);
});

test('a next action with a placeholder is inserted up to it', () => {
  const res = complete('/in', { ...ctx, next: { command: '/init <name>' } });
  assert.equal(res.items[0].kind, 'next');
  assert.deepEqual(acceptCompletion('/in', 3, res.replaceFrom, res.items[0]), { text: '/init ', caret: 6 });
  assert.ok(labels(complete('/')).includes('/init'));
});

test('Harper commands are offered only in Harper mode; the others everywhere', () => {
  const free = { ...ctx, mode: 'free' };
  assert.deepEqual(labels(complete('/ev', free)), []);
  assert.deepEqual(labels(complete('/agent-d', free)), ['/agent-default']);
  assert.match(complete('/eval REQ-002', free).error, /only in Harper mode/);
});

test('REQs are ranked for the command, with a warning when they cannot run', () => {
  assert.deepEqual(labels(complete('/kit ')).slice(0, 2), ['REQ-002', 'REQ-004']);
  assert.deepEqual(labels(complete('/gate ')).slice(0, 1), ['REQ-002']);
  const ev = complete('/eval R');
  assert.equal(ev.items[0].insert, 'REQ-002');
  assert.equal(ev.items.find((i) => i.insert === 'REQ-004').warn, '⚠ /kit first');
  assert.equal(complete('/kit ').items.find((i) => i.insert === 'REQ-003').warn, '⚠ waits REQ-002');
  // by number or title too
  assert.deepEqual(labels(complete('/kit 4')), ['REQ-004']);
  assert.deepEqual(labels(complete('/kit REQ-00')).length, 4);
});

test('flags: not repeated, exclusive ones hidden, --agent only after --methodology', () => {
  assert.deepEqual(labels(complete('/eval REQ-002 --')), ['--fix', '--accept', '--supersede', '--methodology']);
  assert.deepEqual(labels(complete('/eval REQ-002 --fix --')), ['--supersede', '--methodology']);
  assert.deepEqual(labels(complete('/eval REQ-002 --methodology bmad --')), ['--fix', '--accept', '--supersede', '--agent']);
  assert.deepEqual(labels(complete('/gate REQ-002 --ask --')), ['--fix']);
  assert.deepEqual(labels(complete('/eval REQ-002 ')), ['--fix', '--accept', '--supersede', '--methodology']);
});

test('values: methodology, BMAD roles of the phase, executor, release, phases, tools, models', () => {
  assert.deepEqual(labels(complete('/spec --methodology ')), ['bmad']);
  assert.deepEqual(labels(complete('/spec --methodology bmad --agent ')), ['pm', 'ux']);
  assert.deepEqual(labels(complete('/eval REQ-002 --methodology bmad --agent ')), ['qa', 'developer']);
  assert.deepEqual(labels(complete('/idea --extend --methodology bmad --agent ')), ['pm', 'analyst', 'architect', 'ux']);
  assert.deepEqual(labels(complete('/autopilot --executor c')), ['cloud', 'codex', 'claude']);
  assert.deepEqual(labels(complete('/idea --extend --release ')), ['v1', 'v2']);
  assert.deepEqual(labels(complete('/kit REQ-002 --phases=integrity_eval,pro')), ['--phases=integrity_eval,promotion_hardener', '--phases=integrity_eval,promotion_eval']);
  assert.deepEqual(labels(complete('/tools add ku')), ['kubectl']);
  assert.deepEqual(labels(complete('/agent-model claude ')), ['opus', 'sonnet']);
  assert.deepEqual(labels(complete('/agent-model ')), ['list', 'claude', 'codex']);
  assert.deepEqual(labels(complete('/autopilot s')), ['stop', 'status']);
});

test('signature: the part being typed is active', () => {
  const sig = complete('/eval REQ-002 --methodology bmad --ag').signature;
  assert.equal(sig.command, '/eval');
  assert.deepEqual(sig.parts.filter((p) => p.active).map((p) => p.text), ['[--agent qa|developer]]']);
  assert.deepEqual(complete('/eval ').signature.parts.filter((p) => p.active).map((p) => p.text), ['<REQ-ID>']);
});

test('errors are the parser\'s, with a fix when there is an obvious one', () => {
  const gate = complete('/gate REQ-002 --methodology bmad');
  assert.match(gate.error, /Gate is CLike-owned/);
  assert.equal(gate.fix, '/gate REQ-002');
  const role = complete('/kit REQ-002 --methodology bmad --agent qa');
  assert.match(role.error, /not allowed for phase 'kit'/);
  assert.equal(role.fix, '/kit REQ-002 --methodology bmad --agent developer');
  assert.equal(complete('/spec --agent ux ').fix, '/spec --methodology bmad --agent ux');
  assert.match(complete('/eval REQ-099 ').error, /REQ-099 is not in the plan/);
  assert.equal(complete('/eval REQ-09').error, '', 'no error while the id is being typed');
  assert.match(complete('/evil x').error, /Unknown command/);
  assert.equal(complete('/eval REQ-002 --fix').error, '');
  assert.equal(complete('/eval REQ-002 --methodology bmad --agent q').error, '', 'no error while a suggested value is typed');
  assert.match(complete('/eval REQ-002 --methodology bmad --agent q ').error, /Unsupported BMAD agent/);
  assert.deepEqual(completeSlash('plain text', 10, ctx, parseSlash).items, []);
});

test('accepting replaces the token being typed', () => {
  const text = '/eval R';
  const res = completeSlash(text, text.length, ctx, parseSlash);
  assert.deepEqual(acceptCompletion(text, text.length, res.replaceFrom, res.items[0]), { text: '/eval REQ-002 ', caret: 14 });
  const g = completeSlash('/g', 2, ctx, parseSlash);
  assert.deepEqual(acceptCompletion('/g', 2, g.replaceFrom, g.items[0]), { text: '/gate REQ-002 ', caret: 14 });
  // in the middle of the text: the rest is kept
  const mid = '/kit RE --repair';
  const m = completeSlash(mid, 7, ctx, parseSlash);
  assert.equal(acceptCompletion(mid, 7, m.replaceFrom, m.items[0]).text, '/kit REQ-002 --repair');
  const ph = '/kit REQ-002 --phases=int';
  const p = completeSlash(ph, ph.length, ctx, parseSlash);
  assert.equal(acceptCompletion(ph, ph.length, p.replaceFrom, p.items[0]).text, '/kit REQ-002 --phases=integrity_eval ');
});

test('the browser source is the same completer', () => {
  const sandbox = {};
  vm.runInNewContext(buildBrowserSlashCompleteSource() + '\nthis.C = CLIKE_SLASH_COMPLETE;', sandbox);
  const res = sandbox.C.complete('/spec --methodology bmad --agent ', 33, ctx, parseSlash);
  assert.equal(JSON.stringify(res.items.map((i) => i.insert)), '["pm","ux"]');
});

test('the methodology preference is added only where the parser accepts it', () => {
  const { withMethodology } = require('../slash-complete');
  const bmad = { methodology: 'bmad', roles: { spec: 'ux', plan: 'architect', eval: 'developer', kit: 'qa' } };
  assert.equal(withMethodology('/spec', bmad), '/spec --methodology bmad --agent ux');
  assert.equal(withMethodology('/plan', bmad), '/plan --methodology bmad', 'the default role is not repeated');
  assert.equal(withMethodology('/kit REQ-002', bmad), '/kit REQ-002 --methodology bmad', 'a role not allowed for the phase is ignored');
  assert.equal(withMethodology('/eval REQ-002 --fix "keep the API"', bmad), '/eval REQ-002 --fix "keep the API" --methodology bmad --agent developer');
  assert.equal(withMethodology('/gate REQ-002', bmad), '/gate REQ-002');
  assert.equal(withMethodology('/eval REQ-002 --accept "edited by hand"', bmad), '/eval REQ-002 --accept "edited by hand"');
  assert.equal(withMethodology('/autopilot 3', bmad), '/autopilot 3 --methodology bmad');
  assert.equal(withMethodology('/autopilot stop', bmad), '/autopilot stop');
  assert.equal(withMethodology('/spec --methodology bmad --agent pm', bmad), '/spec --methodology bmad --agent pm', 'typed flags win');
  assert.equal(withMethodology('/idea --extend', { methodology: 'bmad', roles: { extend: 'architect' } }), '/idea --extend --methodology bmad --agent architect');
  assert.equal(withMethodology('/agent-model list', bmad), '/agent-model list');
  assert.equal(withMethodology('/spec', { methodology: '' }), '/spec');
  for (const cmd of ['/spec', '/plan', '/kit REQ-002', '/eval REQ-002 --fix', '/idea --extend', '/finalize', '/extend "x"']) {
    assert.equal(parseSlash(withMethodology(cmd, bmad)).error, undefined, cmd);
  }
});
