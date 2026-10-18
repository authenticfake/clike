'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');

const mcp = require('../extension-mcp');
const { withIsolatedMcp } = require('../local-agent-executors');

const ctx = {
  serverInfo: { name: 'CLike Extension Operational MCP', version: 't' },
  tools: () => [{ name: 'harper_next_action', inputSchema: { type: 'object', properties: {} } }],
  callTool: async (name) => { if (name === 'boom') throw new Error('broken'); return { ok: true, name }; },
};

test('OAuth discovery and /register are 404 before authentication', () => {
  for (const p of ['/.well-known/oauth-protected-resource', '/.well-known/oauth-protected-resource/mcp',
    '/.well-known/oauth-authorization-server', '/.well-known/openid-configuration', '/register']) {
    assert.equal(mcp.preAuthRoute('GET', p).status, 404, p);
  }
  assert.equal(mcp.preAuthRoute('POST', '/mcp'), null);
});

test('streamable HTTP: POST is JSON-RPC, GET is 405, other paths 404', () => {
  assert.equal(mcp.postAuthRoute('POST', '/mcp'), null);
  const get = mcp.postAuthRoute('GET', '/mcp');
  assert.equal(get.status, 405);
  assert.equal(get.headers.Allow, 'POST');
  assert.equal(mcp.postAuthRoute('POST', '/other').status, 404);
});

test('initialize negotiates the protocol, notifications get no body, ping answers', async () => {
  const init = await mcp.handleRpc({ jsonrpc: '2.0', id: 1, method: 'initialize', params: { protocolVersion: '2025-03-26' } }, ctx);
  assert.equal(init.result.protocolVersion, '2025-03-26');
  const unknown = await mcp.handleRpc({ jsonrpc: '2.0', id: 2, method: 'initialize', params: { protocolVersion: '1999-01-01' } }, ctx);
  assert.equal(unknown.result.protocolVersion, mcp.SUPPORTED_PROTOCOL_VERSIONS[0]);
  assert.equal(await mcp.handleRpc({ jsonrpc: '2.0', method: 'notifications/initialized' }, ctx), null);
  assert.deepEqual((await mcp.handleRpc({ jsonrpc: '2.0', id: 3, method: 'ping' }, ctx)).result, {});
  assert.equal((await mcp.handleRpc({ jsonrpc: '2.0', id: 4, method: 'tools/list' }, ctx)).result.tools[0].name, 'harper_next_action');
  const ok = await mcp.handleRpc({ jsonrpc: '2.0', id: 5, method: 'tools/call', params: { name: 'x', arguments: {} } }, ctx);
  assert.match(ok.result.content[0].text, /"ok": true/);
  const err = await mcp.handleRpc({ jsonrpc: '2.0', id: 6, method: 'tools/call', params: { name: 'boom' } }, ctx);
  assert.equal(err.result.isError, true);
  assert.equal((await mcp.handleRpc({ jsonrpc: '2.0', id: 7, method: 'resources/list' }, ctx)).error.code, -32601);
  assert.equal((await mcp.handleRpc([1, 2], ctx)).error.code, -32600);
});

test('the next action respects dependsOn and finishes an in-progress REQ first', () => {
  const plan = [
    { id: 'REQ-001', status: 'done' },
    { id: 'REQ-002', status: 'open', dependsOn: ['REQ-003'] },
    { id: 'REQ-003', status: 'open', dependsOn: ['REQ-001'] },
  ];
  assert.equal(mcp.nextActionFromPlan(plan).req_id, 'REQ-003');                 // REQ-002 waits for REQ-003
  assert.equal(mcp.nextActionFromPlan([...plan, { id: 'REQ-004', status: 'in_progress' }]).req_id, 'REQ-004');
  const blocked = mcp.nextActionFromPlan([{ id: 'REQ-001', status: 'open', dependsOn: ['REQ-009'] }]);
  assert.equal(blocked.action, 'blocked');
  assert.deepEqual(blocked.blocked[0].waiting_for, ['REQ-009']);
  assert.equal(mcp.nextActionFromPlan([{ id: 'REQ-001', status: 'done' }]).action, 'finalize_only');
});

test('the run registry keeps running runs and the newest ones', () => {
  const runs = new Map();
  for (let i = 0; i < 60; i += 1) runs.set(`r${i}`, { status: i === 0 ? 'running' : 'done' });
  mcp.pruneRuns(runs, 50);
  assert.equal(runs.size, 50);
  assert.ok(runs.has('r0') && runs.has('r59') && !runs.has('r1'));
});

test('Harper phase runs of Claude load no MCP server', () => {
  assert.deepEqual(withIsolatedMcp('claude_code', ['-p', '--output-format', 'json']), ['-p', '--output-format', 'json', '--strict-mcp-config']);
  assert.deepEqual(withIsolatedMcp('claude_code', ['-p', '--mcp-config', '{}']), ['-p', '--mcp-config', '{}']);
  assert.deepEqual(withIsolatedMcp('gpt_codex', ['exec']), ['exec']);
});
