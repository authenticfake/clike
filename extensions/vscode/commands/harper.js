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

  if (status === 'PASS') {
    return `EVAL PASS — passed=${passed}, failed=${failed}, blocked=${blocked}`;
  }

  return `EVAL FAIL — passed=${passed}, failed=${failed}, blocked=${blocked}, warnings=${warnings}`;
}

async function handleEval(argument, workspaceRoot, req_id, mode = 'auto', result = 'pass') {
  let profile = null;

  try {
    profile = await resolveProfilePath(argument, workspaceRoot);
    const res = await postEvalRun(profile, workspaceRoot, req_id, mode, result);
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

    res.summary = `Eval ${profile}: ${msg}\nCases: ${casesCount}\nReport: ${res?.json || ''}`;
    return res;
  } catch (err) {
    const res = {
      passed: false,
      status: 'FAIL',
      passed_count: 0,
      failed: 1,
      blocked_count: 0,
      warning_count: 0,
      cases: [],
      summary: `Eval ${profile || argument}: EVAL ERROR\nReport: ${String(err)}`,
    };

    vscode.window.showErrorMessage(`EVAL error: ${String(err)}`);
    return res;
  }
}

async function handleGate(argument, workspaceRoot, req_id, opts = { promote: false, reqId: null, mode: 'auto', result: '' }) {
  let profile = null;

  try {
    profile = await resolveProfilePath(argument, workspaceRoot);
    const res = await postGateCheck(profile, workspaceRoot, req_id, opts);
    const status = String(res?.status || res?.gate || 'FAIL').toUpperCase();
    const msg = `GATE ${status} — passed=${Number(res?.passed_count || res?.passed || 0)}, failed=${Number(res?.failed || 0)}, blocked=${Number(res?.blocked_count || 0)}`;

    if (status === 'FAIL') {
      vscode.window.showErrorMessage(`${msg} | profile=${profile}`);
    } else if (status === 'PASS_WITH_WARNINGS') {
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

    vscode.window.showErrorMessage(
      `GATE error: ${String(err)} | req_id=${req_id} workspace=${workspaceRoot} argument=${argument}`,
    );

    return res;
  }
}

module.exports = { handleGate, handleEval };