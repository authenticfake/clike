'use strict';
// WP7.15: package.json is the single source of the extension settings. Every `clike.*` key read
// by the code must be declared there, an in-code fallback must equal the declared default, and
// every declared setting must have a reader.
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('fs');
const path = require('path');

const ROOT = path.join(__dirname, '..');
const declared = require('../package.json').contributes.configuration.properties;
const SOURCES = fs.readdirSync(ROOT).filter((f) => f.endsWith('.js') && f !== 'eslint.config.js');
// .get('key'[, default]) / .update('key' / .inspect('key' on a configuration object; workspaceState
// and globalState use the same method names and are excluded.
const READ_RE = /\.(get|update|inspect)\(\s*'([A-Za-z0-9_.]+)'\s*(?:,\s*('(?:[^'\\]|\\.)*'|-?\d+(?:\.\d+)?|true|false)\s*\))?/g;

function configReads() {
  const reads = [];
  for (const file of SOURCES) {
    const lines = fs.readFileSync(path.join(ROOT, file), 'utf8').split('\n');
    lines.forEach((line, i) => {
      if (/State\.(get|update)\(/.test(line) || /^\s*\/\//.test(line)) return;
      for (const m of line.matchAll(READ_RE)) {
        const key = m[2].startsWith('clike.') ? m[2] : `clike.${m[2]}`;
        const literal = m[3];
        const fallback = literal === undefined ? undefined
          : literal.startsWith("'") ? literal.slice(1, -1) : JSON.parse(literal);
        reads.push({ key, fallback, where: `${file}:${i + 1}`, method: m[1] });
      }
    });
  }
  return reads;
}

test('every setting read by the code is declared in package.json', () => {
  const missing = configReads().filter((r) => !(r.key in declared)).map((r) => `${r.key} (${r.where})`);
  assert.deepEqual(missing, []);
});

test('in-code fallbacks equal the declared defaults', () => {
  const drift = configReads()
    .filter((r) => r.method === 'get' && r.fallback !== undefined && r.key in declared)
    .filter((r) => JSON.stringify(r.fallback) !== JSON.stringify(declared[r.key].default))
    .map((r) => `${r.key} code=${JSON.stringify(r.fallback)} package.json=${JSON.stringify(declared[r.key].default)} (${r.where})`);
  assert.deepEqual(drift, []);
});

test('every declared setting has a reader', () => {
  const source = SOURCES.map((f) => fs.readFileSync(path.join(ROOT, f), 'utf8')).join('\n');
  const unread = Object.keys(declared).filter((key) => {
    const short = key.replace(/^clike\./, '');
    return !source.includes(`'${short}'`) && !source.includes(`'${key}'`);
  });
  assert.deepEqual(unread, []);
});
