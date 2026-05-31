function isBmadQaEval(methodologyContext) {
  const ctx = methodologyContext || {};
  return (
    String(ctx.methodology || '').toLowerCase() === 'bmad' &&
    String(ctx.agent || '').toLowerCase() === 'qa' &&
    String(ctx.phase || '').toLowerCase() === 'eval'
  );
}

function _caseName(item) {
  return String(item?.name || item?.cmd || item?.run || 'unnamed_check');
}

function _collectFailedCases(report) {
  return (Array.isArray(report?.cases) ? report.cases : [])
    .filter(item => item && item.passed === false)
    .map(item => ({
      name: _caseName(item),
      cmd: item.cmd || item.run || null,
      blocked: !!item.blocked,
      blocking: item.blocking !== false,
      stdout: item.stdout ? String(item.stdout).slice(0, 800) : '',
      stderr: item.stderr ? String(item.stderr).slice(0, 800) : '',
    }));
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

function buildBmadQaAdvisory(report, reqId) {
  const target = String(reqId || report?.req_id || 'REQ-UNKNOWN').trim().toUpperCase();
  const failedCases = _collectFailedCases(report);
  const status = String(report?.status || '').toUpperCase();
  const blocked = Number(report?.blocked_count || 0);
  const warnings = Number(report?.warning_count || 0);

  const rootCauseHypothesis = failedCases.length
    ? `Canonical CLike eval reported ${failedCases.length} failing check(s). Start from the first blocking failure and repair the candidate-owned artifact that causes that command to fail.`
    : status === 'PASS'
      ? 'Canonical CLike eval passed. No blocking QA root cause is indicated; review coverage gaps before promotion.'
      : 'Canonical CLike eval did not expose case details. Inspect LTC/HOWTO and the generated eval report for missing or malformed check evidence.';

  const missingTests = failedCases.length
    ? [
        'Add or repair candidate tests that reproduce each failing acceptance criterion.',
        'Ensure tests cover error paths and contract boundaries touched by the failing checks.',
      ]
    : [
        'Review acceptance criteria for edge cases not represented in LTC.json cases.',
        'Add regression tests if the REQ changes behavior covered by promoted tests.',
      ];

  return {
    schema_version: 'clike.bmad_qa_advisory.v1',
    methodology: 'bmad',
    agent: 'qa',
    authority: 'advisory_only',
    canonical_eval_owner: 'clike_eval_runner',
    can_decide_pass_fail: false,
    can_change_promotable_status: false,
    can_affect_gate: false,
    req_id: target,
    eval_status_observed: status || null,
    eval_passed_observed: report?.passed,
    root_cause_hypothesis: rootCauseHypothesis,
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
    recommended_repair_strategy: [
      'Inspect the first blocking failed case and its command output.',
      'Patch only candidate-owned files under runs/kit/<REQ-ID>/src, test, ci, docs, or reports.',
      'Do not weaken LTC, tests, type checks, lint rules, security checks, or gate policy.',
      'Rerun the same failing command before rerunning the full eval.',
    ],
    suggested_next_command: `/kit ${target} --repair --methodology bmad --agent developer`,
    checks_to_rerun: failedCases.length
      ? failedCases.map(item => item.cmd).filter(Boolean)
      : [`/eval ${target} --methodology bmad --agent qa`],
    failed_cases: failedCases,
  };
}

function attachBmadQaAdvisory(report, reqId, methodologyContext) {
  if (!isBmadQaEval(methodologyContext)) return report;

  const advisory = buildBmadQaAdvisory(report || {}, reqId);
  return {
    ...(report || {}),
    bmad_advisory: advisory,
    advisory,
    summary: `${String(report?.summary || '').trim()}\n\nBMAD QA advisory: ${advisory.root_cause_hypothesis}\nSuggested next command: ${advisory.suggested_next_command}`.trim(),
  };
}

module.exports = {
  attachBmadQaAdvisory,
  buildBmadQaAdvisory,
  isBmadQaEval,
};
