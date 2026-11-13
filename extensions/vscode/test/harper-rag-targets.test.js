const assert = require('assert');
const test = require('node:test');

const { harperRagTargets, isRagIndexable } = require('../harper-rag-targets');

test('every document phase indexes its canonical artifact and its inputs or companions', () => {
  assert.ok(harperRagTargets('idea').files.includes('docs/harper/IDEA.md'));
  assert.ok(harperRagTargets('idea').dirs.includes('docs/inputs'));
  assert.ok(harperRagTargets('idea').dirs.includes('docs/reference'));
  assert.ok(harperRagTargets('spec').files.includes('docs/harper/SPEC.md'));
  assert.ok(harperRagTargets('spec').dirs.includes('docs/harper/ux'));
  assert.ok(harperRagTargets('spec').dirs.includes('docs/harper/bmad/spec'));
  assert.ok(harperRagTargets('plan').files.includes('docs/harper/PLAN.md'));
  assert.ok(harperRagTargets('plan').dirs.includes('docs/harper/lane-guides'));
  assert.ok(harperRagTargets('plan').dirs.includes('docs/harper/bmad/architecture'));
  assert.ok(harperRagTargets('plan').dirs.includes('docs/harper/bmad/plan'));
  assert.ok(harperRagTargets('finalize').files.includes('docs/harper/FINALIZE_REPORT.md'));
});

test('/extend indexes what idea, spec and plan index, once', () => {
  const extend = harperRagTargets('extend');
  for (const phase of ['idea', 'spec', 'plan']) {
    for (const f of harperRagTargets(phase).files) assert.ok(extend.files.includes(f), f);
    for (const d of harperRagTargets(phase).dirs) assert.ok(extend.dirs.includes(d), d);
  }
  assert.strictEqual(new Set(extend.files).size, extend.files.length);
  assert.strictEqual(new Set(extend.dirs).size, extend.dirs.length);
});

test('plan.json and non-document phases are not indexed here', () => {
  assert.ok(!harperRagTargets('plan').files.includes('docs/harper/plan.json'));
  for (const phase of ['kit', 'eval', 'gate', '', undefined]) {
    assert.deepStrictEqual(harperRagTargets(phase), { files: [], dirs: [] });
  }
});

test('the targets are copies: a caller cannot change the table', () => {
  harperRagTargets('spec').files.push('x');
  assert.ok(!harperRagTargets('spec').files.includes('x'));
});

test('text and convertible documents are indexable, hidden and binary files are not', () => {
  for (const name of ['SPEC.md', 'TECH_CONSTRAINTS.yaml', 'spec.docx', 'brief.pdf', 'data.xlsx', 'notes.txt']) {
    assert.ok(isRagIndexable(name), name);
  }
  for (const name of ['.gitkeep', '.DS_Store', 'logo.png', 'archive.zip', 'Makefile', '']) {
    assert.ok(!isRagIndexable(name), name);
  }
});
