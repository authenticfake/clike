'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const http = require('http');
const Module = require('module');
const { setCachedServiceToken } = require('../service-auth');

// service-auth and the client read 'vscode' lazily: a stub lets a test point the configured
// orchestrator URL at a local server (window.* is used by the 401/503 notice).
const settings = {};
const originalLoad = Module._load;
Module._load = function (request, parent, isMain) {
  if (request === 'vscode') {
    return {
      workspace: { getConfiguration: () => ({ get: (k) => settings[k] }) },
      window: { showWarningMessage: () => Promise.resolve(undefined) },
      commands: { executeCommand() {} },
    };
  }
  return originalLoad.call(this, request, parent, isMain);
};
test.after(() => { Module._load = originalLoad; });
const client = require('../orchestrator-client');

function server(handler) {
  return new Promise((resolve) => {
    const s = http.createServer(handler);
    s.listen(0, '127.0.0.1', () => resolve({ s, base: `http://127.0.0.1:${s.address().port}` }));
  });
}

test('sends JSON and the service token to the orchestrator; callers cannot override it', async () => {
  const seen = [];
  const { s, base } = await server((req, res) => {
    let body = '';
    req.on('data', (c) => { body += c; });
    req.on('end', () => { seen.push({ auth: req.headers.authorization, ct: req.headers['content-type'], body }); res.end('{"ok":true}'); });
  });
  try {
    setCachedServiceToken('tok');
    settings.orchestratorUrl = `${base}/`;
    assert.equal(client.orchestratorUrl('/x'), `${base}/x`);
    const opts = { body: { a: 1 }, headers: { Authorization: 'Bearer evil' } };
    assert.deepEqual(await client.requestJson('POST', client.orchestratorUrl('/x'), opts), { ok: true });
    assert.deepEqual(seen[0], { auth: 'Bearer tok', ct: 'application/json', body: '{"a":1}' });
    // a non-service origin never receives the token
    delete settings.orchestratorUrl;
    await client.requestJson('POST', `${base}/x`, { body: {} });
    assert.equal(seen[1].auth, undefined);
  } finally {
    setCachedServiceToken('');
    delete settings.orchestratorUrl;
    s.close();
  }
});

test('maps non-2xx to ServiceHttpError with status and FastAPI detail', async () => {
  const { s, base } = await server((req, res) => { res.statusCode = 502; res.end('{"detail":"gateway chat failed: boom"}'); });
  try {
    await assert.rejects(client.requestJson('GET', `${base}/x`), (e) => e instanceof client.ServiceHttpError && e.status === 502 && e.message === 'HTTP 502: gateway chat failed: boom');
    const raw = await client.request('GET', `${base}/x`);
    assert.equal(raw.ok, false);
    assert.equal(raw.status, 502);
  } finally {
    s.close();
  }
});

test('total timeout and abort reject with status 0', async () => {
  const { s, base } = await server(() => { /* never answers */ });
  try {
    await assert.rejects(client.request('GET', `${base}/slow`, { timeoutMs: 100 }), /Request timeout after 100ms/);
    const ac = new AbortController();
    setTimeout(() => ac.abort(), 50);
    await assert.rejects(client.request('GET', `${base}/slow`, { signal: ac.signal }), (e) => e.status === 0 && /aborted/.test(e.message));
  } finally {
    s.closeAllConnections();
    s.close();
  }
});

test('network errors reject with ServiceHttpError', async () => {
  await assert.rejects(client.request('GET', 'http://127.0.0.1:1/x', { timeoutMs: 2000 }), (e) => e instanceof client.ServiceHttpError && e.status === 0);
});

test('base URLs default and trim outside VS Code', () => {
  assert.equal(client.orchestratorUrl('/v1/x'), 'http://localhost:8080/v1/x');
  assert.equal(client.gatewayUrl('/health'), 'http://localhost:8000/health');
});
