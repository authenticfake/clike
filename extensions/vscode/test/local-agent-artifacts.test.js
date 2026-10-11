'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const { pruneLocalAgentCompleteArtifacts, LOCAL_AGENT_COMPLETE_MAX_TOTAL_CHARS } = require('../local-agent-artifacts');

const file = (path, size) => ({ path, content: 'x'.repeat(size) });

test('scratch is never sent and code/tests come first within the size budget', () => {
  const big = Math.floor(LOCAL_AGENT_COMPLETE_MAX_TOTAL_CHARS / 3);
  const artifacts = [
    file('runs/kit/REQ-005/ci/.tmp/compiler/lib.js', big),
    file('runs/kit/REQ-005/ci/.npm-cache/_logs/x.log', 10),
    file('runs/kit/REQ-005/ci/reports/huge.json', big),
    file('runs/kit/REQ-005/docs/notes.md', big),
    file('runs/kit/REQ-005/docs/more.md', big),
    file('runs/kit/REQ-005/ci/LTC.json', 100),
    file('runs/kit/REQ-005/src/web/app/page.tsx', 100),
    file('runs/kit/REQ-005/test/runs.spec.ts', 100),
  ];
  const r = pruneLocalAgentCompleteArtifacts(artifacts, 'kit', 'REQ-005');
  const kept = r.files.map((f) => f.path);
  assert.ok(!kept.some((p) => p.includes('/.tmp/') || p.includes('/.npm-cache/')));
  assert.deepEqual(kept.slice(0, 3), [
    'runs/kit/REQ-005/src/web/app/page.tsx',
    'runs/kit/REQ-005/test/runs.spec.ts',
    'runs/kit/REQ-005/ci/LTC.json',
  ]);
  assert.equal(r.truncated, true);
  assert.ok(r.dropped.length >= 1);
});
