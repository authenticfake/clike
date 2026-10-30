'use strict';
// A project outside the folders the stack reads: mounted on the developer's confirmation, the folder alone.
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('fs');
const os = require('os');
const path = require('path');
const { ensureProjectMounted, isWithin, SCRIPT } = require('../project-mount');

const stack = () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'clike-stack-'));
  fs.writeFileSync(path.join(dir, SCRIPT), '#!/bin/sh\n');
  return dir;
};

test('isWithin: the folder or below it, never a sibling with the same prefix', () => {
  assert.equal(isWithin('/u/dev/authenticfake/b2b', ['/u/dev/authenticfake']), true);
  assert.equal(isWithin('/u/dev/authenticfake', ['/u/dev/authenticfake/']), true);
  assert.equal(isWithin('/u/dev/authenticfake2/x', ['/u/dev/authenticfake']), false);
  assert.equal(isWithin('/u/dev/comau/core/foundation', ['/u/dev/authenticfake']), false);
});

test('ensureProjectMounted: readable → nothing; outside → asked, the script mounts that folder, the stack lists it', async () => {
  const root = '/u/dev/comau/core/foundation';
  let roots = ['/u/dev/authenticfake'];
  const calls = [];
  const dir = stack();
  const base = {
    getRoots: async () => ({ roots, stack_dir: dir }),
    pickStackDir: async () => { throw new Error('not asked'); },
    run: async (script, args, cwd) => { calls.push([script, args, cwd]); roots = [...roots, args[1]]; return { ok: true, output: '' }; },
  };
  assert.equal((await ensureProjectMounted({ ...base, root: '/u/dev/authenticfake/b2b', ask: async () => { throw new Error('asked'); } })).reason, 'readable');
  const out = await ensureProjectMounted({ ...base, root, ask: async () => true });
  assert.equal(out.mounted, true);
  assert.deepEqual(calls, [[path.join(dir, SCRIPT), ['add', root], dir]]);
  assert.equal((await ensureProjectMounted({ ...base, root, ask: async () => { throw new Error('asked'); } })).reason, 'readable');
});

test('ensureProjectMounted: declined once, not asked again; unattended, never asked; no stack folder, picked', async () => {
  const root = '/u/dev/comau/core/foundation';
  const declined = new Set();
  let asked = 0;
  const base = { root, getRoots: async () => ({ roots: ['/u/dev/authenticfake'], stack_dir: '' }), run: async () => ({ ok: true }) };
  const no = await ensureProjectMounted({ ...base, declined, ask: async () => { asked += 1; return false; }, pickStackDir: async () => '' });
  assert.equal(no.reason, 'declined');
  await ensureProjectMounted({ ...base, declined, ask: async () => { asked += 1; return true; }, pickStackDir: async () => '' });
  assert.equal(asked, 1);
  const auto = await ensureProjectMounted({ ...base, unattended: true, ask: async () => { throw new Error('asked'); }, pickStackDir: async () => '' });
  assert.match(auto.reason, /unattended/);
  const dir = stack();
  const picked = await ensureProjectMounted({ ...base, ask: async () => true, pickStackDir: async () => dir, run: async () => ({ ok: false, output: 'ERROR: not a CLike project' }) });
  assert.equal(picked.mounted, false);
  assert.match(picked.reason, /not a CLike project/);
  assert.equal(picked.stackDir, dir);
  const none = await ensureProjectMounted({ ...base, ask: async () => true, pickStackDir: async () => '/nowhere' });
  assert.match(none.reason, /no mount-project\.sh/);
});
