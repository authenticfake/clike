const CANONICAL_VERDICT_FIELDS = [
  'status',
  'passed',
  'promotable',
  'failed',
  'blocking_failures',
  'gate',
  'gate_status',
  'gate_verdict',
  'promote',
  'promotion',
];

function buildEffectiveEvalMethodologyContext(methodologyContext) {
  const ctx = methodologyContext || {};
  const methodology = String(ctx.methodology || '').trim().toLowerCase();
  if (methodology !== 'bmad') return null;

  const requestedAgent = String(ctx.agent || '').trim().toLowerCase();
  const agent = requestedAgent || 'qa';
  if (!['qa', 'developer'].includes(agent)) return null;

  return {
    ...ctx,
    methodology: 'bmad',
    phase: 'eval',
    agent,
    requested_agent: requestedAgent || null,
    default_agent: requestedAgent ? null : 'qa',
    advisory_only: true,
    authority: 'advisory',
  };
}

function isBmadEval(methodologyContext) {
  const ctx = buildEffectiveEvalMethodologyContext(methodologyContext);
  return (
    !!ctx &&
    String(ctx.methodology || '').toLowerCase() === 'bmad' &&
    String(ctx.phase || '').toLowerCase() === 'eval' &&
    ['qa', 'developer'].includes(String(ctx.agent || '').toLowerCase())
  );
}

function isBmadQaEval(methodologyContext) {
  const ctx = buildEffectiveEvalMethodologyContext(methodologyContext);
  return !!ctx && ctx.agent === 'qa';
}

function _caseName(item) {
  return String(item?.name || item?.cmd || item?.run || 'unnamed_check');
}

function _collectFailedCases(report) {
  const reportFailed = Number(report?.failed || 0) > 0;
  return (Array.isArray(report?.cases) ? report.cases : [])
    .filter(item => {
      if (!item) return false;
      const status = String(item.status || '').trim().toLowerCase();
      return (
        item.passed === false ||
        item.failed === true ||
        item.blocked === true ||
        status === 'fail' ||
        status === 'failed' ||
        status === 'block' ||
        status === 'blocked' ||
        (reportFailed && item.passed !== true)
      );
    })
    .map(item => ({
      name: _caseName(item),
      cmd: item.cmd || item.run || null,
      blocked: !!item.blocked,
      blocking: item.blocking !== false,
      status: item.status || null,
      passed: item.passed,
      stdout: item.stdout ? String(item.stdout).slice(0, 800) : '',
      stderr: item.stderr ? String(item.stderr).slice(0, 800) : '',
      summary: item.summary ? String(item.summary).slice(0, 800) : '',
      errors: Array.isArray(item.errors) ? item.errors.map(x => String(x).slice(0, 300)) : [],
      warnings: Array.isArray(item.warnings) ? item.warnings.map(x => String(x).slice(0, 300)) : [],
    }));
}

function _reportText(report, failedCases) {
  const parts = [
    report?.stdout,
    report?.stderr,
    report?.summary,
    ...(Array.isArray(report?.errors) ? report.errors : []),
    ...(Array.isArray(report?.warnings) ? report.warnings : []),
  ];

  for (const item of failedCases || []) {
    parts.push(item.name, item.cmd, item.stdout, item.stderr, item.summary);
    parts.push(...(item.errors || []), ...(item.warnings || []));
  }

  return parts.filter(Boolean).map(x => String(x)).join('\n').toLowerCase();
}

function _inferFilesToInspect(report, reqId) {
  const files = new Set([
    `runs/kit/${reqId}/ci/LTC.json`,
    `runs/kit/${reqId}/ci/HOWTO.md`,
    `runs/kit/${reqId}/src`,
    `runs/kit/${reqId}/test`,
  ]);

  for (const item of _collectFailedCases(report)) {
    const text = `${item.stdout}\n${item.stderr}`;
    const matches = text.match(/(?:runs\/kit\/REQ-[A-Z0-9._-]+\/[^\s:'")]+|(?:src|test|tests|ci)\/[^\s:'")]+)/gi) || [];
    for (const match of matches) files.add(match.replace(/[.,;]+$/, ''));
  }

  return Array.from(files);
}

function _classifyDiagnostics(report, failedCases) {
  const text = _reportText(report, failedCases);
  const blockedCount = Number(report?.blocked_count || 0);
  const warningCount = Number(report?.warning_count || 0);
  const classifications = [];

  if (/(enoent|no such file|not found|missing file|cannot find|could not find|missing candidate|candidate file)/i.test(text)) {
    classifications.push('missing_candidate_files');
  }
  if (/(ltc\.json|howto\.md|malformed|invalid json|schema|parse|contract)/i.test(text)) {
    classifications.push('malformed_ltc_or_contract_gap');
  }
  if (/(timeout|timed out|network|permission denied|eacces|environment|dependency|module not found|command not found|blocked)/i.test(text) || blockedCount > 0) {
    classifications.push('environment_blocker');
  }
  if (/(assert|expect|actual|expected|test failed|failure|failed)/i.test(text) && !classifications.includes('environment_blocker')) {
    classifications.push('candidate_defect');
  }
  if (/(coverage|missing test|untested|no tests|test gap)/i.test(text)) {
    classifications.push('missing_tests');
  }
  if (/(security|vulnerab|cve|secret|injection|xss|csrf|auth|permission)/i.test(text)) {
    classifications.push('security_failure');
  }
  if (/(typecheck|tsc|typescript|mypy|pyright|type error|typing)/i.test(text)) {
    classifications.push('typecheck_failure');
  }
  if (warningCount > 0 && !classifications.includes('candidate_defect')) {
    classifications.push('warning_review_required');
  }

  return classifications.length ? Array.from(new Set(classifications)) : ['eval_evidence_incomplete'];
}

function _failedChecks(report, failedCases) {
  if (failedCases.length) {
    return failedCases.map(item => ({
      name: item.name,
      cmd: item.cmd,
      status: item.status || (item.blocked ? 'blocked' : 'failed'),
      blocking: item.blocking,
      blocked: item.blocked,
      diagnostic_excerpt: [item.stderr, item.stdout, item.summary].filter(Boolean).join('\n').slice(0, 500),
    }));
  }

  return Number(report?.failed || 0) > 0
    ? [{
        name: 'canonical_eval_report',
        cmd: report?.cmd || report?.run || null,
        status: report?.status || 'failed',
        blocking: true,
        blocked: Number(report?.blocked_count || 0) > 0,
        diagnostic_excerpt: String(report?.summary || report?.stderr || report?.stdout || '').slice(0, 500),
      }]
    : [];
}

function buildBmadEvalAdvisory(report, reqId, methodologyContext) {
  const context = buildEffectiveEvalMethodologyContext(methodologyContext);
  if (!context) return null;

  const target = String(reqId || report?.req_id || 'REQ-UNKNOWN').trim().toUpperCase();
  const failedCases = _collectFailedCases(report);
  const status = String(report?.status || '').toUpperCase();
  const failedChecks = _failedChecks(report, failedCases);
  const classifications = _classifyDiagnostics(report, failedCases);
  const blocked = Number(report?.blocked_count || 0);
  const warnings = Number(report?.warning_count || 0);
  const agent = context.agent;

  const rootCauseHypothesis = failedCases.length
    ? `Canonical CLike eval reported ${failedCases.length} failing check(s). Likely category: ${classifications.join(', ')}. Start from the first blocking failure and repair the candidate-owned artifact that causes that command to fail.`
    : status === 'PASS'
      ? 'Canonical CLike eval passed. No blocking QA root cause is indicated; review coverage gaps before promotion.'
      : `Canonical CLike eval did not expose detailed case failures. Likely category: ${classifications.join(', ')}. Inspect LTC/HOWTO and the generated eval report for missing or malformed check evidence.`;

  const missingTests = classifications.includes('missing_tests') || failedCases.length
    ? [
        'Add or repair candidate tests that reproduce each failing acceptance criterion.',
        'Ensure tests cover error paths and contract boundaries touched by the failing checks.',
      ]
    : [
        'Review acceptance criteria for edge cases not represented in LTC.json cases.',
        'Add regression tests if the REQ changes behavior covered by promoted tests.',
      ];

  const repairStrategy = agent === 'developer'
    ? [
        'Treat this as a candidate repair advisory, not an eval verdict.',
        'Open the first failed check and patch only candidate-owned artifacts under runs/kit/<REQ-ID>.',
        'Preserve LTC/HOWTO intent unless the failure is clearly malformed candidate-local test metadata.',
        'Rerun the exact failing command, then rerun canonical /eval.',
      ]
    : [
        'Inspect the first blocking failed case and its command output.',
        'Patch only candidate-owned files under runs/kit/<REQ-ID>/src, test, ci, docs, or reports.',
        'Do not weaken LTC, tests, type checks, lint rules, security checks, or gate policy.',
        'Rerun the same failing command before rerunning the full eval.',
      ];

  const checksToRerun = failedChecks.length
    ? failedChecks.map(item => item.cmd).filter(Boolean)
    : [];
  if (!checksToRerun.length) checksToRerun.push(`/eval ${target} --methodology bmad --agent ${agent}`);

  return {
    schema_version: 'clike.bmad_eval_advisory.v1',
    methodology: 'bmad',
    agent,
    authority: 'advisory_only',
    advisory_only: true,
    advisory_type: agent === 'developer' ? 'developer_repair_advisory' : 'qa_advisory',
    canonical_eval_owner: 'clike_eval_runner',
    can_decide_pass_fail: false,
    can_change_promotable_status: false,
    can_affect_gate: false,
    req_id: target,
    eval_status_observed: status || null,
    eval_passed_observed: report?.passed,
    root_cause_hypothesis: rootCauseHypothesis,
    diagnostic_classifications: classifications,
    failed_checks: failedChecks,
    files_to_inspect: _inferFilesToInspect(report, target),
    missing_tests: missingTests,
    contract_gaps: [
      `Verify runs/kit/${target}/ci/LTC.json has executable cases[] with run commands.`,
      `Verify candidate source/test outputs match TARGET_CONTRACT and FILE_REQUIREMENTS for ${target}.`,
      'If a check is environment-blocked, preserve the blocker evidence and do not mark it as quality pass.',
    ],
    risk_notes: [
      blocked ? `${blocked} check(s) appear environment-blocked; separate environment blockers from candidate defects.` : 'No environment-blocked count reported.',
      warnings ? `${warnings} warning(s) reported; gate may still block warning-bearing eval results.` : 'No warning count reported.',
      'BMAD QA advisory must not override CLike eval/gate decisions.',
    ],
    recommended_repair_strategy: repairStrategy,
    suggested_next_command: `/kit ${target} --repair --methodology bmad --agent developer`,
    checks_to_rerun: checksToRerun,
    failed_cases: failedCases,
  };
}

function buildBmadQaAdvisory(report, reqId) {
  return buildBmadEvalAdvisory(report, reqId, {
    methodology: 'bmad',
    phase: 'eval',
    agent: 'qa',
  });
}

function attachBmadQaAdvisory(report, reqId, methodologyContext) {
  if (!isBmadEval(methodologyContext)) return report;

  const original = report || {};
  const canonicalVerdicts = {};
  for (const field of CANONICAL_VERDICT_FIELDS) {
    if (Object.prototype.hasOwnProperty.call(original, field)) {
      canonicalVerdicts[field] = original[field];
    }
  }

  const effectiveContext = buildEffectiveEvalMethodologyContext(methodologyContext);
  const advisory = buildBmadEvalAdvisory(original, reqId, effectiveContext);
  const next = {
    ...original,
    bmad_advisory: advisory,
    advisory,
    summary: `${String(original?.summary || '').trim()}\n\nBMAD ${advisory.agent.toUpperCase()} advisory: ${advisory.root_cause_hypothesis}\nSuggested next command: ${advisory.suggested_next_command}`.trim(),
  };

  for (const [field, value] of Object.entries(canonicalVerdicts)) {
    next[field] = value;
  }

  return next;
}

module.exports = {
  attachBmadQaAdvisory,
  buildBmadEvalAdvisory,
  buildEffectiveEvalMethodologyContext,
  buildBmadQaAdvisory,
  isBmadEval,
  isBmadQaEval,
};
