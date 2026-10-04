'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const { validateLocalMcpRequest } = require('../mcp-request-guard');

const TOKEN = 'b'.repeat(64);
const PORT = 55742;
const ok = (over = {}) => ({
  method: 'POST',
  headers: {
    host: `127.0.0.1:${PORT}`,
    authorization: `Bearer ${TOKEN}`,
    'content-type': 'application/json',
    ...over,
  },
});
const check = (req, token = TOKEN) => validateLocalMcpRequest(req, { token, port: PORT });

test('valid local MCP client request is accepted', () => {
  assert.deepEqual(check(ok()), { ok: true });
  assert.deepEqual(check(ok({ host: `localhost:${PORT}` })), { ok: true });
});

test('server without token refuses everything (no anonymous mode)', () => {
  assert.equal(check(ok(), '').status, 503);
});

test('browser requests (any Origin) are rejected', () => {
  assert.equal(check(ok({ origin: 'https://evil.example' })).status, 403);
  assert.equal(check(ok({ origin: 'null' })).status, 403);
});

test('DNS rebinding hosts and wrong ports are rejected', () => {
  assert.equal(check(ok({ host: `evil.example:${PORT}` })).status, 403);
  assert.equal(check(ok({ host: '127.0.0.1:1234' })).status, 403);
  assert.equal(check(ok({ host: undefined })).status, 403);
});

test('missing or wrong token is rejected', () => {
  assert.equal(check(ok({ authorization: undefined })).status, 401);
  assert.equal(check(ok({ authorization: `Bearer ${'c'.repeat(64)}` })).status, 401);
  assert.equal(check(ok({ authorization: TOKEN })).status, 401);
});

test('POST must be JSON (blocks text/plain form posts)', () => {
  assert.equal(check(ok({ 'content-type': 'text/plain' })).status, 415);
  assert.equal(check({ method: 'GET', headers: { ...ok().headers, 'content-type': undefined } }).ok, true);
});
