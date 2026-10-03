'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const { isServiceUrl, serviceAuthHeaders, generateServiceToken } = require('../service-auth');

const SERVICES = ['http://localhost:8080', 'http://localhost:8000'];
const TOKEN = 'a'.repeat(64);

test('service URLs match configured origins, including loopback aliases', () => {
  assert.equal(isServiceUrl('http://localhost:8080/v1/harper/kit', SERVICES), true);
  assert.equal(isServiceUrl('http://127.0.0.1:8080/v1/rag/search', SERVICES), true);
  assert.equal(isServiceUrl('http://[::1]:8000/v1/models', SERVICES), true);
});

test('other hosts, ports and schemes are not service URLs', () => {
  for (const url of [
    'http://localhost:9999/x',
    'https://localhost:8080/x',
    'https://api.openai.com/v1/models',
    'http://evil.example:8080/x',
    'file:///etc/passwd',
    'not a url',
  ]) {
    assert.equal(isServiceUrl(url, SERVICES), false, url);
  }
});

test('auth header is only attached to service URLs and only with a token', () => {
  assert.deepEqual(serviceAuthHeaders('http://localhost:8080/v1/chat', SERVICES, TOKEN), {
    Authorization: `Bearer ${TOKEN}`,
  });
  assert.deepEqual(serviceAuthHeaders('https://api.anthropic.com/v1/messages', SERVICES, TOKEN), {});
  assert.deepEqual(serviceAuthHeaders('http://localhost:8080/v1/chat', SERVICES, ''), {});
});

test('generated tokens are 256-bit hex and unique', () => {
  const a = generateServiceToken();
  const b = generateServiceToken();
  assert.match(a, /^[0-9a-f]{64}$/);
  assert.notEqual(a, b);
});
