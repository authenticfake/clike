const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');

const {
  validateIdeaMarkdown,
  validateSpecMarkdown,
  validatePlanMarkdown,
  validatePlanJson,
  validateLaneGuideMarkdown,
  validateCanonicalHarperArtifact,
  rejectedHarperArtifactPath,
  formatInvalidCanonicalArtifactMessage,
  formatHarperError,
  normalizeHarperFailure,
} = require('../harper-canonical-validation');

const GOOD_IDEA = `# IDEA — CoffeeBuddy

## Vision
CoffeeBuddy coordinates office coffee runs with clear value and a small slice.

## Problem Statement
Coffee ordering is scattered in chat and mistakes are frequent.

## Target Users & Context
- Primary user: office teammate.

## Value & Outcomes
- Reduce coordination time.

## Out of Scope
- Payments.

## Technology Constraints
\`\`\`yaml
tech_constraints:
  version: 1
  profiles:
    - name: onprem
      runtime: unknown
\`\`\`

## Risks & Assumptions
- Slack access is assumed.

## Success Metrics
- Time from order to confirmation.
`;

const EXTENSION_JS = path.resolve(__dirname, '..', 'extension.js');

test('canonical IDEA validator accepts a good Harper IDEA', () => {
  const result = validateIdeaMarkdown(GOOD_IDEA);

  assert.equal(result.ok, true);
  assert.deepEqual(result.failed_checks, []);
});

test('canonical IDEA validator rejects prompt leakage and placeholders', () => {
  const bad = `# IDEA — <Project Name>

BEGIN_FILE docs/harper/IDEA.md

## Vision
Print EXCLUSIVELY one file block. My Solution Name.

END_FILE
`;

  const result = validateIdeaMarkdown(bad);

  assert.equal(result.ok, false);
  assert.ok(result.failed_checks.includes('contains_BEGIN_FILE'));
  assert.ok(result.failed_checks.includes('contains_END_FILE'));
  assert.ok(result.failed_checks.some((item) => item.startsWith('contains_prompt_template_phrase:')));
  assert.ok(result.failed_checks.includes('contains_unresolved_placeholder:<Project Name>'));
  assert.ok(result.failed_checks.includes('contains_unresolved_placeholder:My Solution Name'));
});

test('canonical validators reject malformed SPEC PLAN plan.json and lane guides', () => {
  assert.equal(validateSpecMarkdown('# SPEC UX Appendix\n\n## User Journeys\nOnly UX notes.').ok, false);
  assert.ok(validatePlanMarkdown('# PLAN\n\n## Dependencies\nNone.\n\n## KIT Readiness\n/kit ready.').failed_checks.includes('missing_req_ids'));
  assert.ok(validatePlanJson('# PLAN\nnot json').failed_checks.includes('invalid_json'));
  assert.ok(
    validateLaneGuideMarkdown('# Backend Lane\n\n## Purpose\nBackend.\n')
      .failed_checks.includes('missing_test_or_validation_commands')
  );
});

test('canonical artifact dispatcher validates only canonical Harper paths', () => {
  const canonical = validateCanonicalHarperArtifact('docs/harper/IDEA.md', GOOD_IDEA);
  const companion = validateCanonicalHarperArtifact('docs/harper/bmad/idea/BRIEF.md', 'BEGIN_FILE is acceptable here for dispatcher scope');

  assert.equal(canonical.ok, true);
  assert.equal(companion, null);
});

test('rejected Harper artifact path is controlled under .clike/rejected', () => {
  const rejectedPath = rejectedHarperArtifactPath({
    phase: 'idea',
    runId: 'run/../bad',
    filePath: '../docs/harper/IDEA.md',
  });

  assert.match(rejectedPath, /^\.clike\/rejected\/harper\/idea\//);
  assert.ok(rejectedPath.endsWith('.invalid.md'));
  assert.equal(rejectedPath.includes('..'), false);
});

test('structured invalid canonical response formats as friendly chat error', () => {
  const message = formatInvalidCanonicalArtifactMessage({
    ok: false,
    error_code: 'invalid_canonical_artifact',
    text: 'IDEA.md failed canonical validation and was not written.',
    rejected: [
      {
        path: 'docs/harper/IDEA.md',
        failed_checks: ['missing_idea_h1', 'missing_heading:## Vision'],
        debug_path: '/workspace/telemetry/rejected/project/run/idea/docs__harper__IDEA.md.invalid.md',
      },
    ],
  });

  assert.match(message, /CLike blocked a generated canonical Harper artifact/);
  assert.match(message, /No canonical Harper file was overwritten/);
  assert.match(message, /docs\/harper\/IDEA.md/);
  assert.match(message, /missing_idea_h1/);
  assert.match(message, /rejected debug path/);
  assert.doesNotMatch(message, /Traceback/);
});

test('Harper failure formatter handles BMAD partial files without object rendering', () => {
  const result = {
    ok: false,
    phase: 'idea',
    error_code: 'invalid_canonical_artifact',
    text: 'docs/harper/IDEA.md failed canonical validation and was not written.',
    errors: [],
    rejected: [
      {
        path: 'docs/harper/IDEA.md',
        failed_checks: ['missing_idea_h1', 'missing_heading:## Vision'],
        diagnostic: 'IDEA.md failed canonical Harper structure validation.',
      },
    ],
    files: [
      { path: 'docs/harper/bmad/idea/BRIEF.md', content: '...' },
    ],
    partial_files: [
      { path: 'docs/harper/bmad/idea/BRIEF.md', content: '...' },
    ],
  };

  const normalized = normalizeHarperFailure(result);
  const message = formatHarperError(result);

  assert.equal(normalized.ok, false);
  assert.match(message, /Harper idea failed: invalid_canonical_artifact/);
  assert.match(message, /docs\/harper\/IDEA.md failed canonical validation/);
  assert.match(message, /missing_idea_h1/);
  assert.match(message, /missing_heading:## Vision/);
  assert.match(message, /Rejected:/);
  assert.match(message, /Partial files not applied:/);
  assert.match(message, /docs\/harper\/bmad\/idea\/BRIEF.md/);
  assert.doesNotMatch(message, /\[object Object\]/);
});

test('Harper failure formatter unwraps FastAPI detail objects', () => {
  const message = formatHarperError({
    detail: {
      ok: false,
      phase: 'idea',
      error_code: 'invalid_canonical_artifact',
      text: 'IDEA.md failed canonical validation.',
      rejected: [{ path: 'docs/harper/IDEA.md', failed_checks: ['missing_idea_h1'] }],
    },
  });

  assert.match(message, /Harper idea failed: invalid_canonical_artifact/);
  assert.match(message, /missing_idea_h1/);
  assert.doesNotMatch(message, /\[object Object\]/);
});

test('extension declares Harper blocking state at module scope', () => {
  const source = fs.readFileSync(EXTENSION_JS, 'utf8');

  assert.match(source, /let\s+clikeHarperBlockingRun\s*=\s*false\s*;/);
});
