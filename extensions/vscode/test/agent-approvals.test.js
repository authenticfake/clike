'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const http = require('http');
const path = require('path');

const { createApprovalGate, createCodexAppServerTurn, describeClaudeRequest, startClaudeApprovalServer } = require('../agent-approvals');
const { buildAgentChatArgs } = require('../agent-chat');

const WS = path.resolve('/tmp/ws');
const ROOT = path.join(WS, 'generated', 'abc');

test('gate: writes outside the Coding root are denied without asking; allow all lasts the turn', async () => {
  const asked = [];
  const answers = ['allowAll'];
  const events = [];
  const decide = createApprovalGate({
    ask: async (req) => { asked.push(req.summary); return answers.shift() || 'deny'; },
    workspaceRoot: WS,
    writeRoot: ROOT,
    onEvent: (e) => events.push(e.label),
  });
  const outside = await decide({ kind: 'edit', summary: 'Edit src/app.py', paths: ['src/app.py'] });
  assert.equal(outside.allow, false);
  assert.match(outside.reason, /generated\/abc/);
  assert.equal(asked.length, 0);

  assert.equal((await decide({ kind: 'command', summary: 'npm test', paths: [] })).allow, true);
  assert.equal((await decide({ kind: 'edit', summary: 'Edit', paths: [path.join(ROOT, 'a.py')] })).allow, true);
  assert.deepEqual(asked, ['npm test']);
  assert.ok(events.some((l) => l.startsWith('⏸ approval')) && events.some((l) => l.startsWith('✖ denied')));
});

test('gate: deny and closing the prompt both deny', async () => {
  const decide = createApprovalGate({ ask: async () => undefined, workspaceRoot: WS, writeRoot: ROOT });
  const d = await decide({ kind: 'command', summary: 'rm -rf x', paths: [] });
  assert.equal(d.allow, false);
});

test('claude: requests are described by tool, coding with approvals asks instead of acceptEdits', () => {
  assert.deepEqual(describeClaudeRequest('Write', { file_path: '/tmp/ws/generated/abc/a.py' }).paths, ['/tmp/ws/generated/abc/a.py']);
  assert.equal(describeClaudeRequest('Bash', { command: 'ls' }).kind, 'command');
  const args = buildAgentChatArgs({ executorId: 'claude_code', mode: 'coding', approvals: true });
  assert.ok(args.includes('default') && !args.includes('acceptEdits'));
});

function rpc(port, token, body) {
  return new Promise((resolve, reject) => {
    const raw = JSON.stringify(body);
    const req = http.request({
      host: '127.0.0.1', port, path: '/mcp', method: 'POST',
      headers: { 'content-type': 'application/json', authorization: `Bearer ${token}`, host: `127.0.0.1:${port}` },
    }, (res) => {
      let data = '';
      res.on('data', (c) => { data += c; });
      res.on('end', () => resolve({ status: res.statusCode, body: data ? JSON.parse(data) : null }));
    });
    req.on('error', reject);
    req.end(raw);
  });
}

test('claude: the one-turn MCP server answers the permission prompt tool', async () => {
  const server = await startClaudeApprovalServer(async (req) => ({ allow: req.kind === 'command', reason: 'no' }));
  try {
    const config = JSON.parse(server.args[server.args.indexOf('--mcp-config') + 1]);
    const { url, headers } = config.mcpServers.clike_approval;
    const port = Number(new URL(url).port);
    const token = headers.Authorization.slice(7);
    assert.equal(server.args.at(-1), 'mcp__clike_approval__approve');

    assert.equal((await rpc(port, 'wrong', { jsonrpc: '2.0', id: 1, method: 'tools/list' })).status, 401);
    assert.equal((await rpc(port, token, { jsonrpc: '2.0', method: 'notifications/initialized' })).status, 202);
    const tools = await rpc(port, token, { jsonrpc: '2.0', id: 2, method: 'tools/list' });
    assert.equal(tools.body.result.tools[0].name, 'approve');

    const call = (tool_name, input) => rpc(port, token, { jsonrpc: '2.0', id: 3, method: 'tools/call', params: { name: 'approve', arguments: { tool_name, input } } })
      .then((r) => JSON.parse(r.body.result.content[0].text));
    assert.deepEqual(await call('Bash', { command: 'ls' }), { behavior: 'allow', updatedInput: { command: 'ls' } });
    assert.deepEqual(await call('Write', { file_path: 'x' }), { behavior: 'deny', message: 'no' });
  } finally {
    await server.close();
  }
});

test('codex: app-server turn starts or resumes the thread, answers approvals, reports the result', async () => {
  const written = [];
  const events = [];
  const decisions = [];
  const turn = createCodexAppServerTurn({
    cwd: WS,
    prompt: 'do it',
    session: { id: 'thr-1', started: true },
    model: 'gpt-x',
    sandbox: 'workspace-write',
    approvalPolicy: 'untrusted',
    decide: async (req) => { decisions.push(req); return { allow: req.kind === 'command' }; },
    onEvent: (e) => events.push(e),
  });
  const stdin = { write: (line) => written.push(JSON.parse(line)), end: () => {} };
  const tick = () => new Promise((r) => setImmediate(r));
  const reply = (id, result) => turn.feed(JSON.stringify({ jsonrpc: '2.0', id, result }));

  turn.attach(stdin);
  await tick();
  assert.equal(written[0].method, 'initialize');
  reply(written[0].id, {});
  await tick();
  const resume = written.find((m) => m.method === 'thread/resume');
  assert.deepEqual([resume.params.threadId, resume.params.sandbox, resume.params.approvalPolicy, resume.params.model], ['thr-1', 'workspace-write', 'untrusted', 'gpt-x']);
  reply(resume.id, { thread: { id: 'thr-1' } });
  await tick();
  const start = written.find((m) => m.method === 'turn/start');
  assert.equal(start.params.input[0].text, 'do it');
  reply(start.id, { turn: { id: 't1' } });

  turn.feed(JSON.stringify({ method: 'item/started', params: { item: { id: 'fc1', type: 'fileChange', changes: [{ path: 'src/a.py' }] } } }));
  turn.feed(JSON.stringify({ id: 0, method: 'item/fileChange/requestApproval', params: { itemId: 'fc1' } }));
  turn.feed(JSON.stringify({ id: 1, method: 'item/commandExecution/requestApproval', params: { itemId: 'c1', command: 'npm test' } }));
  turn.feed(JSON.stringify({ id: 2, method: 'item/tool/requestUserInput', params: {} }));
  await tick();
  assert.deepEqual(decisions[0].paths, ['src/a.py']);
  assert.equal(written.find((m) => m.id === 0 && !m.method).result.decision, 'decline');
  assert.equal(written.find((m) => m.id === 1 && !m.method).result.decision, 'accept');
  assert.ok(written.find((m) => m.id === 2 && !m.method).error);

  turn.feed(JSON.stringify({ method: 'item/agentMessage/delta', params: { delta: 'done' } }));
  turn.feed(JSON.stringify({ method: 'thread/tokenUsage/updated', params: { tokenUsage: { last: { inputTokens: 10, cachedInputTokens: 4, outputTokens: 2 } } } }));
  turn.feed(JSON.stringify({ method: 'turn/completed', params: { turn: { status: 'completed' } } }));
  const outcome = await turn.done;
  assert.deepEqual([outcome.ok, outcome.text, outcome.threadId], [true, 'done', 'thr-1']);
  const result = events.find((e) => e.kind === 'result');
  assert.deepEqual(result.usage, { input_tokens: 10, cache_read_input_tokens: 4, output_tokens: 2 });
  assert.ok(events.some((e) => e.kind === 'session' && e.id === 'thr-1'));
});

test('codex: a process that exits before the turn ends fails the turn', async () => {
  const turn = createCodexAppServerTurn({ cwd: WS, prompt: 'x', decide: async () => ({ allow: true }) });
  turn.closed(1);
  const outcome = await turn.done;
  assert.equal(outcome.ok, false);
  assert.match(outcome.error, /exited/);
});
