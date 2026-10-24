const vscode = require('vscode');

const { postEvalRun, postGateCheck } = require('../api.js');
const { resolveProfilePath } = require('../utility.js');

function buildEvalMessage(res) {
  const status = String(res?.status || (res?.passed ? 'PASS' : 'FAIL')).toUpperCase();
  const passed = Number(res?.passed_count || 0);
  const failed = Number(res?.failed || 0);
  const blocked = Number(res?.blocked_count || 0);
  const warnings = Number(res?.warning_count || 0);

  if (status === 'PASS_WITH_WARNINGS') {
    return `EVAL PASS_WITH_WARNINGS — passed=${passed}, failed=${failed}, blocked=${blocked}, warnings=${warnings}`;
  }

  if (res?.reason_code === 'EVAL_ENVIRONMENT_MISSING') {
    const names = (String((res.cases || []).find(c => c.name === 'env::required-variables')?.stderr || '')
      .match(/^ {2}- ([A-Z][A-Z0-9_]+)/gm) || []).map(l => l.replace(/^ {2}- /, ''));
    return res.environment_repairable
      ? `EVAL BLOCKED — CLike cannot create yet: ${names.join(', ') || 'required variables'} (no check run; /eval --fix declares them)`
      : `EVAL BLOCKED — missing in docker/eval.env: ${names.join(', ') || 'required variables'} (no check run)`;
  }

  if (status === 'PASS') {
    return `EVAL PASS — passed=${passed}, failed=${failed}, blocked=${blocked}`;
  }

  return `EVAL FAIL — passed=${passed}, failed=${failed}, blocked=${blocked}, warnings=${warnings}`;
}

async function handleEval(argument, workspaceRoot, req_id, mode = 'auto', result = 'pass', signal = null, options = {}) {
  let profile = null;

  try {
    profile = await resolveProfilePath(argument, workspaceRoot);
    const res = await postEvalRun(profile, workspaceRoot, req_id, mode, result, signal, options);
    const msg = buildEvalMessage(res);
    const casesCount = Array.isArray(res?.cases) ? res.cases.length : 0;
    const status = String(res?.status || '').toUpperCase();

    if (status === 'FAIL' || res?.passed === false) {
      vscode.window.showErrorMessage(`${msg} | profile=${res.profile}`);
    } else if (status === 'PASS_WITH_WARNINGS') {
      vscode.window.showWarningMessage(`${msg} | profile=${res.profile}`);
    } else {
      vscode.window.showInformationMessage(`${msg} | profile=${res.profile}`);
    }

    const scope = Array.isArray(res?.regression_scope) && res.regression_scope.length
      ? `\nTargeted re-eval: this REQ's checks and the regression of ${res.regression_scope.join(', ')} only (the full eval follows)`
      : '';
    res.summary = `Eval ${profile}: ${msg}\nCases: ${casesCount}${scope}\nReport: ${res?.json || ''}`;
    return res;
    } catch (err) {
      const normalizedReqId = String(req_id || '').trim().toUpperCase() || 'REQ-UNKNOWN';
      const res = {
        req_id: normalizedReqId,
        passed: false,
        status: 'FAIL',
        passed_count: 0,
        failed: 1,
        blocked_count: 0,
        warning_count: 0,
        cases: [],
        summary: `Eval ${profile || argument}: EVAL ERROR\nReport: ${String(err)}`,
      };

    if (signal && signal.aborted) res.cancelled = true;
    else vscode.window.showErrorMessage(`EVAL error: ${String(err)}`);
    return res;
  }
}

async function handleGate(argument, workspaceRoot, req_id, opts = { promote: false, reqId: null, mode: 'auto', result: '' }) {
  let profile = null;

  try {
    profile = await resolveProfilePath(argument, workspaceRoot);
    const res = await postGateCheck(profile, workspaceRoot, req_id, opts);
    const status = String(res?.status || res?.gate || 'FAIL').toUpperCase();
    const reasonCode = String(res?.reason_code || '').trim();
    const msg =
      `GATE ${status} — passed=${Number(res?.passed_count || res?.passed || 0)}, ` +
      `failed=${Number(res?.failed || 0)}, blocked=${Number(res?.blocked_count || 0)}` +
      (reasonCode ? `, reason=${reasonCode}` : '') +
      (res?.review_required ? ' — REVIEW: auto-eval fixed a test of this REQ (see acceptance_amendments)' : '');
    if (status === 'FAIL') {
      vscode.window.showErrorMessage(`${msg} | profile=${profile}`);
    } else if (status === 'PASS_WITH_WARNINGS') {
      vscode.window.showWarningMessage(`${msg} | profile=${profile}`);
    } else if (res?.review_required) {
      vscode.window.showWarningMessage(`${msg} | profile=${profile}`);
    } else {
      vscode.window.showInformationMessage(`${msg} | profile=${profile}`);
    }

    res.summary = `Gate ${profile}: ${msg}`;
    return res;
  } catch (err) {
    const res = {
      gate: 'FAIL',
      status: 'FAIL',
      passed: 0,
      failed: 1,
      summary: `Gate ${profile || argument}: GATE ERROR ${String(err)}`,
    };

    if (opts && opts.signal && opts.signal.aborted) res.cancelled = true;
    else vscode.window.showErrorMessage(
      `GATE error: ${String(err)} | req_id=${req_id} workspace=${workspaceRoot} argument=${argument}`,
    );

    return res;
  }
}

module.exports = { handleGate, handleEval };