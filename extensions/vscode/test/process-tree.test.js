'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const cp = require('child_process');
const { terminateProcessTree } = require('../local-agent-executors');

const alive = (pid) => { try { process.kill(pid, 0); return true; } catch { return false; } };
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

test('timeout termination kills the agent and its children (POSIX)', { skip: process.platform === 'win32' }, async () => {
  // a parent that ignores SIGTERM and spawns a long-lived child, like an agent CLI could
  const child = cp.spawn('sh', ['-c', "trap '' TERM; sleep 60 & echo $!; wait"], { detached: true, stdio: ['ignore', 'pipe', 'ignore'] });
  const grandchild = await new Promise((resolve) => child.stdout.once('data', (d) => resolve(Number(String(d).trim()))));
  assert.ok(alive(child.pid) && alive(grandchild));
  terminateProcessTree(child, { graceMs: 200 });
  await sleep(800);
  assert.equal(alive(grandchild), false, 'grandchild must be terminated');
  assert.equal(alive(child.pid), false, 'agent must be terminated even if it ignores SIGTERM');
});

test('Windows uses taskkill on the whole tree', () => {
  const calls = [];
  terminateProcessTree({ pid: 4242, exitCode: null }, { platform: 'win32', spawnSync: (cmd, args) => calls.push([cmd, ...args]) });
  assert.deepEqual(calls, [['taskkill', '/pid', '4242', '/T', '/F']]);
});

test('already exited processes are left alone', () => {
  const calls = [];
  terminateProcessTree({ pid: 1, exitCode: 0 }, { platform: 'win32', spawnSync: () => calls.push(1) });
  assert.equal(calls.length, 0);
});
