'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');

const { buildAgentChatArgs, createAgentStreamParser, newSession, sessionKey } = require('../agent-chat');
const { parseSlash } = require('../slash-parser');

test('claude: streamed JSON, session id on the first turn, resume afterwards', () => {
  const first = buildAgentChatArgs({ executorId: 'claude_code', mode: 'free', session: { id: 'abc', started: false }, modelArgs: ['--model', 'opus'] });
  assert.deepEqual(first, ['-p', '--output-format', 'stream-json', '--verbose', '--include-partial-messages', '--model', 'opus', '--session-id', 'abc']);
  const next = buildAgentChatArgs({ executorId: 'claude_code', mode: 'coding', session: { id: 'abc', started: true } });
  assert.ok(next.includes('--resume') && next.includes('acceptEdits'));
  assert.equal(newSession('claude_code').id.length, 36);
});

test('codex: read-only outside coding, resume keeps the sandbox as config', () => {
  assert.deepEqual(buildAgentChatArgs({ executorId: 'gpt_codex', mode: 'free', session: newSession('gpt_codex') }),
    ['exec', '--json', '--sandbox', 'read-only', '--skip-git-repo-check']);
  assert.deepEqual(buildAgentChatArgs({ executorId: 'gpt_codex', mode: 'coding', session: { id: 't1', started: true } }),
    ['exec', 'resume', 't1', '-', '--json', '-c', 'sandbox_mode="workspace-write"', '--skip-git-repo-check']);
  assert.equal(sessionKey('Harper', 'gpt_codex'), 'harper:gpt_codex');
});

test('claude stream events become session, text deltas, tools and the result', () => {
  const p = createAgentStreamParser('claude_code');
  const events = [
    '{"type":"system","subtype":"init","session_id":"s1","model":"claude-opus-5-5"}',
    '{"type":"stream_event","event":{"type":"content_block_delta","delta":{"type":"text_delta","text":"Hel"}}}',
    '{"type":"stream_event","event":{"type":"content_block_delta","delta":{"type":"text_delta","text":"lo"}}}',
    '{"type":"assistant","message":{"content":[{"type":"text","text":"Hello"},{"type":"tool_use","name":"Read","input":{"file_path":"src/app.py"}}]}}',
    '{"type":"result","subtype":"success","result":"Hello","session_id":"s1","total_cost_usd":0.01,"usage":{"input_tokens":3,"output_tokens":2},"modelUsage":{"claude-opus-5-5":{}}}',
  ].flatMap((line) => p.feed(line));
  assert.deepEqual(events.map((e) => e.kind), ['session', 'delta', 'delta', 'tool', 'result']);
  assert.equal(events[3].label, 'Read src/app.py');
  assert.equal(events[4].text, 'Hello');
  assert.equal(events[4].model, 'claude-opus-5-5');
});

test('codex events become session, messages, commands, file changes and the result', () => {
  const p = createAgentStreamParser('gpt_codex');
  const events = [
    '{"type":"thread.started","thread_id":"t1"}',
    '{"type":"item.started","item":{"type":"command_execution","command":"pytest -q"}}',
    '{"type":"item.completed","item":{"type":"file_change","changes":[{"path":"src/a.py"}]}}',
    '{"type":"item.completed","item":{"type":"agent_message","text":"Done"}}',
    '{"type":"turn.completed","usage":{"input_tokens":10,"cached_input_tokens":4,"output_tokens":2}}',
    'not json',
  ].flatMap((line) => p.feed(line));
  assert.deepEqual(events.map((e) => e.kind), ['session', 'tool', 'tool', 'delta', 'result']);
  assert.equal(events[4].text, 'Done');
  assert.deepEqual(events[4].usage, { input_tokens: 10, cache_read_input_tokens: 4, output_tokens: 2 });
});

test('/agent-session parses its action', () => {
  assert.equal(parseSlash('/agent-session new all').args.action, 'new all');
  assert.equal(parseSlash('/agent-session').args.action, '');
});
