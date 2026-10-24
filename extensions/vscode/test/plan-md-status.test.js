'use strict';
// A status update of PLAN.md (a REQ goes in_progress / done) rewrites the snapshot and the REQ table
// only: the per-REQ sections the plan wrote stay (ShortLink: the whole REQ-001 section was deleted).
const test = require('node:test');
const assert = require('node:assert/strict');
const Module = require('module');

const originalLoad = Module._load;
Module._load = function (request, parent, isMain) {
  if (request === 'vscode') {
    return { workspace: { getConfiguration: () => ({ get: (_k, d) => d }) }, window: { createOutputChannel: () => ({ appendLine() {} }) }, Uri: {} };
  }
  return originalLoad.call(this, request, parent, isMain);
};
const { replacePlanStatusSections } = require('../utility');
Module._load = originalLoad;

const PLAN_MD = `# PLAN — ShortLink

## Plan Snapshot

Total **2**; open **2**. Zero REQs done.

## REQ-IDs Table

| ID | Title | Acceptance | DependsOn | Track | Status |
| --- | --- | --- | --- | --- | --- |
| REQ-001 | Create links | a | [] | App | open |
| REQ-002 | List links | b | [REQ-001] | App | open |

## REQ-001 — Create links

Track: App. Status: open.

### Functional Scope — REQ-001
- create a link

### Acceptance — REQ-001
- the link resolves

## REQ-002 — List links

### Acceptance — REQ-002
- the list shows it

## Dependency Graph
- REQ-002 -> REQ-001
`;

const plan = { reqs: [
  { id: 'REQ-001', title: 'Create links', acceptance: ['a'], dependsOn: [], track: 'App', status: 'in_progress' },
  { id: 'REQ-002', title: 'List links', acceptance: ['b'], dependsOn: ['REQ-001'], track: 'App', status: 'open' },
] };

test('a status update keeps every section after the REQ table', () => {
  const out = replacePlanStatusSections(PLAN_MD, plan);
  for (const heading of ['## REQ-001 — Create links', '### Functional Scope — REQ-001', '### Acceptance — REQ-001',
    '## REQ-002 — List links', '## Dependency Graph']) {
    assert.ok(out.includes(heading), heading);
  }
  assert.ok(out.includes("| REQ-001 | Create links | a |  | App | in_progress |"));
  assert.equal((out.match(/## REQ-IDs Table/g) || []).length, 1);
  assert.match(out, /in_progress=1/);
  assert.ok(!out.includes('Zero REQs done'), 'the snapshot is rewritten');
});

test('a PLAN without the sections gets them, and a second update changes nothing more', () => {
  const out = replacePlanStatusSections('# PLAN\n\n## Notes\n- n\n', plan);
  assert.ok(out.includes('## Notes') && out.includes('## REQ-IDs Table') && out.includes('## Plan Snapshot'));
  const twice = replacePlanStatusSections(replacePlanStatusSections(PLAN_MD, plan), plan);
  assert.equal(twice, replacePlanStatusSections(PLAN_MD, plan));
});
