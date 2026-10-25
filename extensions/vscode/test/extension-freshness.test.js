'use strict';
// B2B REQ-032: a window opened before the extension was reinstalled ran the previous CLike all day.
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('fs');
const os = require('os');
const path = require('path');

const { createFreshnessCheck, STALE_MESSAGE } = require('../extension-freshness');

test('a run started after the extension changed on disk is warned once', () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'clike-fresh-'));
  const file = path.join(dir, 'extension.js');
  fs.writeFileSync(file, 'v1');
  const check = createFreshnessCheck(file);
  assert.equal(check('harperEDD'), null);
  fs.utimesSync(file, new Date(), new Date(Date.now() + 60000));
  assert.equal(check('setTheme'), null);
  assert.equal(check('harperEDD'), STALE_MESSAGE);
  assert.equal(check('harperRun'), null);
});

test('a removed extension (new version in another folder) counts as changed', () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'clike-fresh-'));
  const file = path.join(dir, 'extension.js');
  fs.writeFileSync(file, 'v1');
  const check = createFreshnessCheck(file);
  fs.rmSync(file);
  assert.equal(check('autopilot'), STALE_MESSAGE);
});
