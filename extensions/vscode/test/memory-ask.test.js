'use strict';
// Ask in the Memory panel: an answer only from numbered sources, steps with exact commands, how sure
// it is, the next questions; "NOW" questions from the project's state.
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('fs');
const os = require('os');
const path = require('path');

const { pickSources, buildAskPrompt, parseAskAnswer, pendingTestPatches, nowSuggestions, stateContext, lastRunFailures } = require('../memory-ask');

const hits = {
  project: [
    { path: 'runs/kit/REQ-032/docs/KIT_REQ-032.md', chunk: 0, score: 0.6, text: 'Playwright only routes the first URL in a redirect chain' },
    { path: 'runs/kit/REQ-032/docs/KIT_REQ-032.md', chunk: 0, score: 0.59, text: 'duplicate chunk' },
    { path: 'runs/kit/REQ-016/src/Login.tsx', chunk: 2, score: 0.4, text: 'login form' },
  ],
  guide: [{ path: 'commands.md', chunk: 3, score: 0.61, text: '### /eval <REQ-ID> --accept "reason"' }],
};

test('sources: best chunks of each memory, no duplicates, numbered by relevance', () => {
  const s = pickSources(hits, { project: 5, guide: 4 });
  assert.deepEqual(s.map((x) => [x.n, x.collection, x.path]), [
    [1, 'guide', 'commands.md'],
    [2, 'project', 'runs/kit/REQ-032/docs/KIT_REQ-032.md'],
    [3, 'project', 'runs/kit/REQ-016/src/Login.tsx'],
  ]);
  assert.equal(pickSources({ project: hits.project }, { project: 1 }).length, 1);
});

test('the prompt holds the rules, the numbered sources, the state and the question', () => {
  const s = pickSources(hits);
  const p = buildAskPrompt('come funziona --accept?', s, 'Next action: /eval REQ-032 --fix');
  assert.match(p, /ONLY the numbered sources/);
  assert.match(p, /Answer in the language of the question/);
  assert.match(p, /Never invent a command/);
  assert.match(p, /\[1\] CLike guide · commands\.md/);
  assert.match(p, /\[2\] Project · runs\/kit\/REQ-032/);
  assert.match(p, /Project state now:\nNext action: \/eval REQ-032 --fix/);
  assert.match(p, /Question: come funziona --accept\?$/);
});

test('a JSON reply is validated: unknown sources dropped, steps and follow-ups bounded', () => {
  const s = pickSources(hits);
  const reply = 'Here it is:\n```json\n' + JSON.stringify({
    answer: 'It applies the patch [1].',
    steps: [{ text: 'Accept it', command: '/eval REQ-032 --accept "why"' }, 'Then gate', { text: '' }],
    confidence: 'high', confidence_reason: '2 sources agree', sources_used: [1, 2, 9],
    followups: ['a', 'b', 'c', 'd'], not_in_memory: false,
  }) + '\n```';
  const a = parseAskAnswer(reply, s);
  assert.equal(a.answer, 'It applies the patch [1].');
  assert.deepEqual(a.steps, [{ text: 'Accept it', command: '/eval REQ-032 --accept "why"' }, { text: 'Then gate', command: '' }]);
  assert.deepEqual(a.sources_used, [1, 2]);
  assert.equal(a.followups.length, 3);
  assert.equal(a.confidence, 'high');
});

test('a reply that is not JSON is shown as it is, with low confidence', () => {
  const a = parseAskAnswer('Plain text answer', []);
  assert.equal(a.answer, 'Plain text answer');
  assert.equal(a.confidence, 'low');
  assert.equal(parseAskAnswer('{"answer": "x", "confidence": "certain"}', []).confidence, 'low');
});

test('NOW questions: the test patch to review first, then the failed run, the next action, the guide', () => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'clike-now-'));
  fs.mkdirSync(path.join(root, 'runs/eval/REQ-032'), { recursive: true });
  fs.writeFileSync(path.join(root, 'runs/eval/REQ-032/proposed_test_fix_10.patch'), '');
  fs.writeFileSync(path.join(root, 'runs/eval/REQ-032/proposed_test_fix_20.patch'), '');
  fs.mkdirSync(path.join(root, 'runs/eval/REQ-031'), { recursive: true });
  fs.writeFileSync(path.join(root, 'runs/eval/REQ-031/proposed_test_fix_5.applied.patch'), '');
  const patches = pendingTestPatches(root);
  assert.deepEqual(patches, [{ req: 'REQ-032', file: 'runs/eval/REQ-032/proposed_test_fix_20.patch' }]);

  const state = {
    last_run: { phase: 'eval', req_id: 'REQ-032', status: 'FAIL', failed: 1 },
    next: { command: '/eval REQ-032 --fix', message: 'repair' },
    reqs: [], counts: { done: 31, total: 36 },
  };
  const now = nowSuggestions(state, patches);
  assert.deepEqual(now.map((s) => s.label), [
    'Review the test patch proposed for REQ-032', 'What does --accept do?',
    'Why did the last eval of REQ-032 fail?', 'What does /eval REQ-032 --fix do here?',
  ]);
  assert.match(stateContext(state, patches), /Test patch waiting for review: runs\/eval\/REQ-032\/proposed_test_fix_20\.patch/);
  // a quiet project still gets a question about CLike
  assert.deepEqual(nowSuggestions(null, []).map((s) => s.label), ['How does the autopilot work?']);
  assert.deepEqual(pendingTestPatches(path.join(root, 'none')), []);
});

test('the state of now beats older sources: live blocking failures, file dates, CLike commands only', () => {
  // real case: an answer from old KIT notes about the e2e while the last eval failed on the regression
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'clike-state-'));
  fs.mkdirSync(path.join(root, 'runs/eval/REQ-032'), { recursive: true });
  fs.writeFileSync(path.join(root, 'runs/eval/REQ-032/report_2.json'), JSON.stringify({ cases: [
    { name: 'regression::REQ-008::test:unit', passed: false, blocking: true, excerpt: 'line\nexpected 3 facets, got 2' },
    { name: 'regression::REQ-001::test:integration', passed: false, blocking: false, excerpt: 'already failing' },
    { name: 'e2e', passed: true },
  ] }));
  const run = { phase: 'eval', req_id: 'REQ-032', status: 'FAIL', failed: 1 };
  const failures = lastRunFailures(root, run);
  assert.deepEqual(failures, [{ name: 'regression::REQ-008::test:unit', error: 'line | expected 3 facets, got 2' }]);
  const ctx = stateContext({ last_run: run, next: { command: '/eval REQ-032 --fix', message: '' } }, [], failures);
  assert.match(ctx, /blocking failure regression::REQ-008::test:unit: line \| expected 3 facets, got 2/);
  assert.deepEqual(lastRunFailures(root, { phase: 'kit', req_id: 'REQ-032' }), []);

  const p = buildAskPrompt('what now?', [{ n: 1, collection: 'project', path: 'runs/kit/REQ-032/docs/KIT.md', modified: '2026-10-25 09:10', text: 'old e2e notes' }], ctx);
  assert.match(p, /\[1\] Project · runs\/kit\/REQ-032\/docs\/KIT\.md \(modified 2026-10-25 09:10\)/);
  assert.match(p, /follow the state and the newest source/);
  assert.match(p, /never give tools an agent uses internally/);
});
