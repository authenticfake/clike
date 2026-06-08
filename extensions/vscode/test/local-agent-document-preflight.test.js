const assert = require('assert');
const test = require('node:test');

const {
  evaluateDocumentPhaseInputPreflight,
  evaluateExtendInputPreflight,
} = require('../local-agent-write-policy');

test('/idea is blocked when there are no current-run attachments', () => {
  const result = evaluateDocumentPhaseInputPreflight({
    phase: 'idea',
    attachmentCount: 0,
  });
  assert.strictEqual(result.ok, false);
  assert.strictEqual(result.code, 'IDEA_REQUIRES_CURRENT_ATTACHMENT');
  assert.match(result.message, /without at least one attached source file/i);
});

test('/idea is allowed with one current-run attachment', () => {
  const result = evaluateDocumentPhaseInputPreflight({
    phase: 'idea',
    attachmentCount: 1,
  });
  assert.strictEqual(result.ok, true);
});

test('/idea is allowed with multiple current-run attachments', () => {
  const result = evaluateDocumentPhaseInputPreflight({
    phase: 'idea',
    attachmentCount: 3,
  });
  assert.strictEqual(result.ok, true);
});

test('/spec is blocked when docs/harper/IDEA.md is missing', () => {
  const result = evaluateDocumentPhaseInputPreflight({
    phase: 'spec',
    ideaPresent: false,
  });
  assert.strictEqual(result.ok, false);
  assert.strictEqual(result.code, 'SPEC_REQUIRES_IDEA');
  assert.match(result.message, /docs\/harper\/IDEA\.md is missing/i);
});

test('/spec is allowed when docs/harper/IDEA.md exists (attachments irrelevant)', () => {
  const result = evaluateDocumentPhaseInputPreflight({
    phase: 'spec',
    ideaPresent: true,
    attachmentCount: 0,
  });
  assert.strictEqual(result.ok, true);
});

test('/plan is blocked when docs/harper/SPEC.md is missing', () => {
  const result = evaluateDocumentPhaseInputPreflight({
    phase: 'plan',
    specPresent: false,
  });
  assert.strictEqual(result.ok, false);
  assert.strictEqual(result.code, 'PLAN_REQUIRES_SPEC');
  assert.match(result.message, /docs\/harper\/SPEC\.md is missing/i);
});

test('/plan is allowed when docs/harper/SPEC.md exists', () => {
  const result = evaluateDocumentPhaseInputPreflight({
    phase: 'plan',
    specPresent: true,
  });
  assert.strictEqual(result.ok, true);
});

test('non-document phases are never blocked by this preflight', () => {
  for (const phase of ['kit', 'eval', 'finalize', 'extend']) {
    assert.strictEqual(
      evaluateDocumentPhaseInputPreflight({ phase, attachmentCount: 0 }).ok,
      true
    );
  }
});

// Regenerative behavior: an existing same-phase output must NOT block the run.
// The preflight has no spec/plan-output parameter, so output presence cannot
// gate the command — these tests document and lock that contract.
test('/spec is not blocked by an already-existing docs/harper/SPEC.md', () => {
  const result = evaluateDocumentPhaseInputPreflight({
    phase: 'spec',
    ideaPresent: true,
    // Simulate stale same-phase outputs already on disk (must be ignored).
    specOutputExists: true,
  });
  assert.strictEqual(result.ok, true);
});

test('/plan is not blocked by existing PLAN.md, plan.json, or lane-guides', () => {
  const result = evaluateDocumentPhaseInputPreflight({
    phase: 'plan',
    specPresent: true,
    // Simulate stale same-phase outputs already on disk (must be ignored).
    planOutputExists: true,
    laneGuidesExist: true,
  });
  assert.strictEqual(result.ok, true);
});

// --- /extend --from attachment preflight ---

test('/extend --from attachment is blocked without a current attachment', () => {
  const result = evaluateExtendInputPreflight({ fromAttachment: true, attachmentCount: 0 });
  assert.strictEqual(result.ok, false);
  assert.strictEqual(result.code, 'EXTEND_REQUIRES_CURRENT_ATTACHMENT');
  assert.match(result.message, /without at least one attached source file/i);
});

test('/extend --from attachment is allowed with an attachment', () => {
  assert.strictEqual(
    evaluateExtendInputPreflight({ fromAttachment: true, attachmentCount: 2 }).ok,
    true
  );
});

test('/extend without --from attachment is not blocked by attachment count', () => {
  assert.strictEqual(
    evaluateExtendInputPreflight({ fromAttachment: false, attachmentCount: 0 }).ok,
    true
  );
});
