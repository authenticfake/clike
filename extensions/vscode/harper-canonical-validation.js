const path = require('path');

const PROMPT_TEMPLATE_PHRASES = [
  'Print EXCLUSIVELY ' + 'one file block',
  'Produce only ' + 'the single',
  'single ' + 'BEGIN_FILE',
  'No additional ' + 'files',
];

const UNRESOLVED_PLACEHOLDERS = [
  '<Project Name>',
  '<X min',
  '<...>',
  'My Solution Name',
];

const GENERIC_TEMPLATE_ONLY_VALUES = [
  'aws-eks',
  'my-project-key',
  'https://api.openai.com',
];

function result(filePath, failedChecks, diagnostic) {
  return {
    ok: failedChecks.length === 0,
    path: filePath,
    failed_checks: failedChecks,
    diagnostic: failedChecks.length ? diagnostic : '',
    error_code: failedChecks.length ? 'invalid_canonical_artifact' : null,
  };
}

function normalizeOutputPath(filePath) {
  return String(filePath || '').replace(/\\/g, '/').replace(/^\.?\//, '').replace(/^\/+/, '');
}

function hasHeading(text, heading) {
  const escaped = heading.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  return new RegExp(`^\\s*${escaped}\\s*$`, 'im').test(text);
}

function headingIndex(text, heading) {
  const escaped = heading.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  const match = new RegExp(`^\\s*${escaped}\\s*$`, 'im').exec(text);
  return match ? match.index : -1;
}

function sectionAfter(text, heading) {
  const escaped = heading.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  const match = new RegExp(`^\\s*${escaped}\\s*$`, 'im').exec(text);
  if (!match) return '';
  const rest = text.slice(match.index + match[0].length);
  const next = /^\s*##\s+/m.exec(rest);
  return next ? rest.slice(0, next.index) : rest;
}

function commonMarkdownFailures(content, evidenceText = '') {
  const text = String(content || '');
  const lower = text.toLowerCase();
  const failures = [];
  if (text.includes('BEGIN_FILE')) failures.push('contains_BEGIN_FILE');
  if (text.includes('END_FILE')) failures.push('contains_END_FILE');
  for (const phrase of PROMPT_TEMPLATE_PHRASES) {
    if (lower.includes(phrase.toLowerCase())) {
      failures.push(`contains_prompt_template_phrase:${phrase}`);
    }
  }
  for (const placeholder of UNRESOLVED_PLACEHOLDERS) {
    if (text.includes(placeholder)) {
      failures.push(`contains_unresolved_placeholder:${placeholder}`);
    }
  }
  for (const value of GENERIC_TEMPLATE_ONLY_VALUES) {
    if (text.includes(value) && !String(evidenceText || '').includes(value)) {
      failures.push(`contains_unevidenced_template_value:${value}`);
    }
  }
  return failures;
}

function validateIdeaMarkdown(content, opts = {}) {
  const filePath = opts.path || 'docs/harper/IDEA.md';
  const evidenceText = opts.evidenceText || '';
  const text = String(content || '');
  const stripped = text.trimStart();
  const failures = commonMarkdownFailures(text, evidenceText);

  if (!(stripped.startsWith('# IDEA — ') || stripped.startsWith('# IDEA - '))) {
    failures.push('missing_idea_h1');
  }
  if (stripped.startsWith('```') || stripped.toLowerCase().startsWith('tech_constraints:')) {
    failures.push('starts_with_raw_yaml_or_fence');
  }

  const primary = [
    ['## Vision'],
    ['## Problem Statement'],
    ['## Target Users & Context'],
    ['## Value & Outcomes', '## Value & Outcomes (with initial targets)'],
    ['## Out of Scope', '## Out of Scope (slice-1)'],
    ['## Technology Constraints', '## Technology Constraints (SPEC-ready)'],
    ['## Risks & Assumptions'],
  ];
  const indexes = [];
  for (const options of primary) {
    const found = options.map((heading) => headingIndex(text, heading)).filter((idx) => idx >= 0);
    if (!found.length) {
      failures.push(`missing_heading:${options.join('|')}`);
    } else {
      indexes.push(Math.min(...found));
    }
  }
  if (indexes.length && indexes.some((idx, pos) => pos > 0 && idx < indexes[pos - 1])) {
    failures.push('primary_idea_sections_out_of_order');
  }
  const techSection = sectionAfter(text, '## Technology Constraints') || sectionAfter(text, '## Technology Constraints (SPEC-ready)');
  if (!/^```ya?ml\s*$/im.test(techSection)) {
    failures.push('missing_fenced_yaml_after_technology_constraints');
  }
  if (!/^\s*##\s+.*success metrics/im.test(text)) {
    failures.push('missing_success_metrics_section');
  }
  const coreOpeningIndexes = ['## Vision', '## Problem Statement', '## Target Users & Context']
    .map((heading) => headingIndex(text, heading))
    .filter((idx) => idx >= 0);
  const lastCoreOpening = coreOpeningIndexes.length ? Math.max(...coreOpeningIndexes) : -1;
  for (const heading of [
    '## Deployment Portability Rule',
    '## Technology Constraints Profile Rule',
    '## Strategic Fit',
    '## /spec Handoff Readiness',
  ]) {
    const idx = headingIndex(text, heading);
    if (idx >= 0 && lastCoreOpening >= 0 && idx < lastCoreOpening) {
      failures.push(`bmad_extra_section_before_primary:${heading}`);
    }
  }
  return result(filePath, failures, 'IDEA.md failed canonical Harper structure validation.');
}

function validateSpecMarkdown(content, opts = {}) {
  const filePath = opts.path || 'docs/harper/SPEC.md';
  const text = String(content || '');
  const lower = text.toLowerCase();
  const failures = commonMarkdownFailures(text);
  if (!text.trimStart().startsWith('# SPEC')) failures.push('missing_spec_h1');
  if (!['problem', 'scope', 'objective', 'requirement'].some((term) => lower.includes(term))) {
    failures.push('missing_problem_scope_or_requirements');
  }
  if (!['acceptance criteria', 'testability', 'test strategy'].some((term) => lower.includes(term))) {
    failures.push('missing_acceptance_or_testability');
  }
  if (!['constraint', 'non-functional', 'non functional'].some((term) => lower.includes(term))) {
    failures.push('missing_constraints_or_non_functional_requirements');
  }
  if (lower.includes('spec_ux_appendix') || (lower.includes('user journey') && !lower.includes('functional requirement'))) {
    failures.push('looks_like_companion_only_ux_content');
  }
  return result(filePath, failures, 'SPEC.md failed canonical Harper structure validation.');
}

function validatePlanMarkdown(content, opts = {}) {
  const filePath = opts.path || 'docs/harper/PLAN.md';
  const text = String(content || '');
  const lower = text.toLowerCase();
  const failures = commonMarkdownFailures(text);
  if (!text.trimStart().startsWith('# PLAN')) failures.push('missing_plan_h1');
  if (!text.includes('REQ-')) failures.push('missing_req_ids');
  if (!['dependencies', 'dependson', 'ordering', 'depends on'].some((term) => lower.includes(term))) {
    failures.push('missing_dependencies_or_ordering');
  }
  if (!['/kit', 'kit readiness', 'kit-readiness', 'implementation readiness'].some((term) => lower.includes(term))) {
    failures.push('missing_kit_or_implementation_readiness');
  }
  return result(filePath, failures, 'PLAN.md failed canonical Harper structure validation.');
}

function validatePlanJson(content, opts = {}) {
  const filePath = opts.path || 'docs/harper/plan.json';
  const text = String(content || '');
  const failures = [];
  if (text.trimStart().startsWith('#') || text.includes('```')) failures.push('looks_like_markdown');
  let data;
  try {
    data = JSON.parse(text);
  } catch {
    failures.push('invalid_json');
    return result(filePath, failures, 'plan.json must be valid JSON.');
  }
  const reqs = data && (data.reqs || data.requirements || data.items);
  if (!Array.isArray(reqs) || !reqs.length) {
    failures.push('missing_requirements_list');
  } else {
    reqs.forEach((req, index) => {
      if (!req || typeof req !== 'object' || Array.isArray(req)) {
        failures.push(`req_${index}_not_object`);
        return;
      }
      for (const field of ['id', 'title', 'status', 'acceptance']) {
        if (!req[field]) failures.push(`req_${index}_missing_${field}`);
      }
      if (!('dependsOn' in req) && !('dependencies' in req) && !('depends_on' in req)) {
        failures.push(`req_${index}_missing_dependencies`);
      }
    });
  }
  return result(filePath, failures, 'plan.json failed canonical Harper structure validation.');
}

function validateLaneGuideMarkdown(content, opts = {}) {
  const filePath = opts.path || 'docs/harper/lane-guides/<lane>.md';
  const text = String(content || '');
  const lower = text.toLowerCase();
  const failures = commonMarkdownFailures(text);
  if (!text.trimStart().startsWith('#')) failures.push('missing_heading');
  if (!['lane purpose', 'purpose', 'scope'].some((term) => lower.includes(term))) {
    failures.push('missing_lane_purpose_or_scope');
  }
  if (!['expected files', 'boundaries', 'boundary'].some((term) => lower.includes(term))) {
    failures.push('missing_expected_files_or_boundaries');
  }
  if (!['test command', 'validation command', 'commands'].some((term) => lower.includes(term))) {
    failures.push('missing_test_or_validation_commands');
  }
  if (!['eval/gate', 'eval expectations', 'gate expectations'].some((term) => lower.includes(term))) {
    failures.push('missing_eval_gate_expectations');
  }
  return result(filePath, failures, 'Lane guide failed canonical Harper structure validation.');
}

function validateCanonicalHarperArtifact(filePath, content, opts = {}) {
  const normalized = normalizeOutputPath(filePath);
  if (normalized === 'docs/harper/IDEA.md') return validateIdeaMarkdown(content, { ...opts, path: normalized });
  if (normalized === 'docs/harper/SPEC.md') return validateSpecMarkdown(content, { ...opts, path: normalized });
  if (normalized === 'docs/harper/PLAN.md') return validatePlanMarkdown(content, { ...opts, path: normalized });
  if (normalized === 'docs/harper/plan.json') return validatePlanJson(content, { ...opts, path: normalized });
  if (/^docs\/harper\/lane-guides\/[^/]+\.md$/i.test(normalized)) {
    return validateLaneGuideMarkdown(content, { ...opts, path: normalized });
  }
  return null;
}

function safeRejectedFileName(filePath) {
  return normalizeOutputPath(filePath)
    .replace(/[^A-Za-z0-9._-]+/g, '__')
    .replace(/[.]{2,}/g, '_')
    .replace(/^_+/, '')
    .slice(0, 180) || 'artifact';
}

function rejectedHarperArtifactPath({ phase, runId, filePath }) {
  const phasePart = String(phase || 'unknown').replace(/[^A-Za-z0-9._-]+/g, '_').replace(/[.]{2,}/g, '_');
  const runPart = String(runId || 'unknown').replace(/[^A-Za-z0-9._-]+/g, '_').replace(/[.]{2,}/g, '_');
  return path.posix.join(
    '.clike',
    'rejected',
    'harper',
    phasePart,
    runPart,
    `${safeRejectedFileName(filePath)}.invalid.md`
  );
}

function stringifyHarperValue(value) {
  if (value == null) return '';
  if (typeof value === 'string') return value;
  if (value instanceof Error) return value.message || String(value);
  if (Array.isArray(value)) {
    return value.map((item) => stringifyHarperValue(item)).filter(Boolean).join('\n');
  }
  if (typeof value === 'object') {
    if (typeof value.detail === 'string') return value.detail;
    if (value.detail && typeof value.detail === 'object') return stringifyHarperValue(value.detail);
    if (typeof value.message === 'string') return value.message;
    if (typeof value.text === 'string') return value.text;
    try {
      return JSON.stringify(value, null, 2);
    } catch {
      return Object.prototype.toString.call(value);
    }
  }
  return String(value);
}

function unwrapHarperFailure(value) {
  if (value && typeof value === 'object' && !(value instanceof Error)) {
    if (value.out && typeof value.out === 'object') return value.out;
    if (value.detail && typeof value.detail === 'object') return value.detail;
  }
  return value;
}

function normalizeHarperFailure(errorOrResult) {
  const result = unwrapHarperFailure(errorOrResult);
  if (typeof result === 'string' || result instanceof Error || !result || typeof result !== 'object') {
    return {
      ok: false,
      phase: undefined,
      error_code: undefined,
      text: stringifyHarperValue(result),
      errors: [],
      warnings: [],
      rejected: [],
      partial_files: [],
      diagnostic_files: [],
    };
  }

  const errors = Array.isArray(result.errors) ? result.errors : [];
  const warnings = Array.isArray(result.warnings) ? result.warnings : [];
  const rejected = Array.isArray(result.rejected) ? result.rejected : [];
  const partialFiles = Array.isArray(result.partial_files)
    ? result.partial_files
    : (Array.isArray(result.diagnostic_files) ? result.diagnostic_files : []);

  return {
    ok: result.ok === false ? false : Boolean(result.error_code || errors.length || rejected.length),
    phase: result.phase,
    error_code: result.error_code,
    text: typeof result.text === 'string' ? result.text : stringifyHarperValue(result),
    errors,
    warnings,
    rejected,
    partial_files: partialFiles,
    diagnostic_files: Array.isArray(result.diagnostic_files) ? result.diagnostic_files : partialFiles,
    runId: result.runId || result.run_id,
  };
}

function formatHarperError(errorOrResult) {
  const failure = normalizeHarperFailure(errorOrResult);
  const phase = failure.phase ? ` ${failure.phase}` : '';
  const code = failure.error_code || 'error';
  const lines = [`Harper${phase} failed: ${code}`];

  if (failure.text) {
    lines.push('', failure.text);
  }

  const diagnostics = [];
  const diagnosticItems = [
    ...failure.rejected,
    ...failure.errors.filter((item) => item && typeof item === 'object'),
  ];
  for (const item of diagnosticItems) {
    for (const check of (Array.isArray(item.failed_checks) ? item.failed_checks : [])) {
      diagnostics.push(String(check));
    }
  }
  if (diagnostics.length) {
    lines.push('', 'Failed checks:');
    for (const check of [...new Set(diagnostics)]) {
      lines.push(`- ${check}`);
    }
  }

  if (failure.rejected.length) {
    lines.push('', 'Rejected:');
    for (const item of failure.rejected) {
      const filePath = item && item.path ? item.path : stringifyHarperValue(item);
      lines.push(`- ${filePath}`);
      const debugPath = item && (item.debug_path || item.rejected_artifact_ref);
      if (debugPath) lines.push(`  debug: ${debugPath}`);
    }
  }

  const stringErrors = failure.errors
    .filter((item) => typeof item === 'string' && item.trim())
    .map((item) => item.trim());
  if (stringErrors.length) {
    lines.push('', 'Errors:');
    for (const item of stringErrors) lines.push(`- ${item}`);
  }

  if (failure.partial_files.length) {
    lines.push('', 'Partial files not applied:');
    for (const item of failure.partial_files.slice(0, 20)) {
      lines.push(`- ${item.path || stringifyHarperValue(item)}`);
    }
  }

  return lines.join('\n');
}

function formatInvalidCanonicalArtifactMessage(out) {
  const rejected = Array.isArray(out && out.rejected) ? out.rejected : [];
  const errors = Array.isArray(out && out.errors) ? out.errors : [];
  const items = rejected.length
    ? rejected
    : errors.filter((item) => item && typeof item === 'object' && item.error_code === 'invalid_canonical_artifact');

  const lines = [
    'CLike blocked a generated canonical Harper artifact because it failed structural validation.',
    'No canonical Harper file was overwritten.',
  ];

  if (items.length) {
    for (const item of items.slice(0, 5)) {
      const filePath = item.path || 'canonical artifact';
      const checks = Array.isArray(item.failed_checks) ? item.failed_checks.join(', ') : 'unknown';
      lines.push(`- ${filePath}: ${checks}`);
      const debugPath = item.debug_path || item.rejected_artifact_ref;
      if (debugPath) {
        lines.push(`  rejected debug path: ${debugPath}`);
      }
    }
  } else if (out && out.text) {
    lines.push(String(out.text));
  }

  lines.push('Repair the canonical artifact shape and rerun the Harper phase.');
  return lines.join('\n');
}

module.exports = {
  validateIdeaMarkdown,
  validateSpecMarkdown,
  validatePlanMarkdown,
  validatePlanJson,
  validateLaneGuideMarkdown,
  validateCanonicalHarperArtifact,
  rejectedHarperArtifactPath,
  stringifyHarperValue,
  normalizeHarperFailure,
  formatHarperError,
  formatInvalidCanonicalArtifactMessage,
};
