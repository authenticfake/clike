'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const Module = require('module');
const vm = require('vm');

// chat-ui.js requires 'vscode'; provide a minimal stub for the HTML builder.
const originalLoad = Module._load;
Module._load = function (request, parent, isMain) {
  if (request === 'vscode') {
    return {
      workspace: { getConfiguration: () => ({ get: (_k, d) => d }) },
      window: { createOutputChannel: () => ({ appendLine() {}, show() {} }) },
    };
  }
  return originalLoad.call(this, request, parent, isMain);
};
const { getWebviewHtml } = require('../chat-ui');
Module._load = originalLoad;

const csp = (html) => /http-equiv="Content-Security-Policy" content="([^"]+)"/.exec(html)[1];

test('CSP allows only nonce scripts and data: images (no remote hosts)', () => {
  const policy = csp(getWebviewHtml('http://localhost:8080'));
  assert.match(policy, /default-src 'none'/);
  assert.match(policy, /img-src data:;/);
  assert.doesNotMatch(policy, /https:|http:|\*/);
  assert.doesNotMatch(policy, /script-src[^;]*unsafe-(inline|eval)/);
});

test('nonce is cryptographically random and applied to every script', () => {
  const a = getWebviewHtml('http://localhost:8080');
  const b = getWebviewHtml('http://localhost:8080');
  const nonceA = /'nonce-([^']+)'/.exec(csp(a))[1];
  const nonceB = /'nonce-([^']+)'/.exec(csp(b))[1];
  assert.match(nonceA, /^[0-9a-f]{32}$/);
  assert.notEqual(nonceA, nonceB);
  const scripts = a.match(/<script\b[^>]*>/g) || [];
  assert.ok(scripts.length > 0);
  for (const tag of scripts) assert.ok(tag.includes(`nonce="${nonceA}"`), tag);
});

test('generated inline scripts are valid JavaScript', () => {
  const html = getWebviewHtml('http://localhost:8080');
  const bodies = [...html.matchAll(/<script\b[^>]*>([\s\S]*?)<\/script>/g)].map((m) => m[1]);
  assert.ok(bodies.length > 0);
  for (const body of bodies) assert.doesNotThrow(() => new vm.Script(body));
});

test('file lists escape server-provided paths and do not use btoa', () => {
  const html = getWebviewHtml('http://localhost:8080');
  assert.doesNotMatch(html, /btoa\(path\)/);
  assert.doesNotMatch(html, /data-path="' \+ path \+ '"/);
  assert.match(html, /const p = escapeHtml\(String\(\(f && f\.path\) \|\| ''\)\);/);
});
