'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');

const { addApproved, catalogTool, ensureEvalTools, questionText, readApproved, removeApproved, toolsListing, unknownToolHint } = require('../eval-tools');
const { nextAutoEvalStep, nextAutoGateStep } = require('../auto-eval');
const { parseSlash } = require('../slash-parser');

const missing = (tools, extra = {}) => ({
  installable: true,
  missing: tools.map((tool) => ({ tool, about: `${tool} client`, source: 'used', in_catalog: true, approved: false, binaries: [tool], ...extra })),
});

function harness(checkResult, answer) {
  const calls = { asked: [], installed: [], approved: [], said: [] };
  return {
    calls,
    opts: {
      check: async () => checkResult,
      install: async (names) => { calls.installed.push(names); return { versions: { kafkacat: '1.7.1' }, seconds: 3 }; },
      ask: async (items) => { calls.asked.push(items.map((i) => i.tool)); return answer; },
      approve: (names) => calls.approved.push(names),
      say: (t) => calls.said.push(t),
    },
  };
}

test('asks before installing what the eval needs, and remembers "always"', async () => {
  const h = harness(missing(['kafkacat']), 'always');
  const r = await ensureEvalTools({ ...h.opts, policy: 'ask' });
  assert.deepEqual(r.installed, ['kafkacat']);
  assert.deepEqual(h.calls.asked, [['kafkacat']]);
  assert.deepEqual(h.calls.approved, [['kafkacat']]);
  assert.match(h.calls.said.join('\n'), /Installed kafkacat \(kafkacat 1\.7\.1\) in 3s/);
});

test('approved or "always" tools install without a question; "never" and "No" do not install', async () => {
  let h = harness(missing(['kafkacat'], { approved: true }), 'no');
  assert.deepEqual((await ensureEvalTools({ ...h.opts, policy: 'ask' })).installed, ['kafkacat']);
  assert.deepEqual(h.calls.asked, []);
  h = harness(missing(['mysql-client']), 'no');
  assert.deepEqual((await ensureEvalTools({ ...h.opts, policy: 'always' })).installed, ['mysql-client']);
  h = harness(missing(['mysql-client']), 'install');
  const never = await ensureEvalTools({ ...h.opts, policy: 'never' });
  assert.deepEqual([never.installed, never.declined, h.calls.asked], [[], ['mysql-client'], []]);
  h = harness(missing(['mysql-client']), 'no');
  assert.deepEqual((await ensureEvalTools({ ...h.opts })).declined, ['mysql-client']);
});

test('no answer within the timeout: the eval goes on without the tool', async () => {
  const h = harness(missing(['jdk@17']), 'install');
  h.opts.ask = () => new Promise(() => {});
  const r = await ensureEvalTools({ ...h.opts, timeoutMs: 20 });
  assert.deepEqual([r.installed, r.declined], [[], ['jdk@17']]);
  assert.match(h.calls.said.join('\n'), /No answer about jdk@17/);
});

test('programs a report says are missing are offered too; failures never throw', async () => {
  const h = harness({ installable: true, missing: [] }, 'install');
  assert.deepEqual((await ensureEvalTools({ ...h.opts, extra: ['kcat'] })).installed, ['kcat']);
  const broken = await ensureEvalTools({ ...h.opts, check: async () => { throw new Error('404'); } });
  assert.match(broken.error, /tools check failed: 404/);
  const notInstallable = harness({ installable: false, missing: missing(['kafkacat']).missing }, 'install');
  const r = await ensureEvalTools(notInstallable.opts);
  assert.deepEqual([r.installed, notInstallable.calls.asked], [[], []]);
});

test('.clike/eval-tools.yaml: approvals added and removed, other content kept', () => {
  assert.deepEqual(readApproved('tools: [kafkacat, "jdk@17"]\n'), ['kafkacat', 'jdk@17']);
  const text = addApproved('tools:\n  - kafkacat\ncustom:\n  sqlcl: {packages: [sqlcl], binaries: [sql]}\n', ['jdk@17', 'kafkacat']);
  assert.deepEqual(readApproved(text), ['kafkacat', 'jdk@17']);
  assert.match(text, /custom:\n {2}sqlcl/);
  assert.match(addApproved('', ['kafkacat']), /^# Native tools[^\n]*\ntools:\n {2}- kafkacat\n$/);
  assert.deepEqual(readApproved(removeApproved(text, ['jdk'])), ['kafkacat']);
});

test('/tools: parsed, listed, searched; libraries are pointed to the manifest', () => {
  assert.deepEqual(parseSlash('/tools add kafkacat jdk@17').args.names, ['kafkacat', 'jdk@17']);
  assert.equal(parseSlash('/tools').args.action, 'list');
  const data = {
    catalog: { kafkacat: { group: 'messaging', about: 'Kafka CLI', binaries: ['kcat'] }, jdk: { group: 'runtimes', about: 'JDK', binaries: ['javac'] } },
    installed: { kafkacat: {} }, approved: ['kafkacat'], installable: true,
  };
  assert.match(toolsListing(data), /Installed in the eval sandbox: kafkacat[\s\S]*messaging:\n {2}✔ kafkacat/);
  assert.doesNotMatch(toolsListing(data, 'jdk'), /kafkacat —/);
  assert.equal(catalogTool(data.catalog, 'kcat'), 'kafkacat');
  assert.equal(catalogTool(data.catalog, 'jdk@17'), 'jdk');
  assert.equal(catalogTool(data.catalog, 'psycopg'), null);
  assert.match(unknownToolHint(['psycopg']), /project manifest/);
  assert.match(questionText('REQ-013', [{ tool: 'kafkacat', about: 'Kafka CLI', source: 'used' }]), /REQ-013 needs[^\n]*kafkacat — Kafka CLI \(run by the code\)/);
});

test('a check still missing a tool stops the repair loop with how to install it', () => {
  const report = { status: 'FAIL', missing_tools: ['kcat'], cases: [{ name: 'e2e', passed: false, blocked: true }] };
  const step = nextAutoEvalStep({ cycle: 1, maxCycles: 2 }, report);
  assert.equal(step.action, 'stop');
  assert.match(step.reason, /\/tools add kcat/);
  assert.equal(nextAutoGateStep({ cycle: 0, maxCycles: 2 }, { ...report, gate: 'FAIL' }).action, 'stop');
});
