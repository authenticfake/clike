const vscode = require('vscode');

const { postEvalRun, postGateCheck } = require ("../api.js");
const {resolveProfilePath } = require('../utility.js')



// Handler comando /eval
async function handleEval(argument, workspaceRoot,req_id, mode='auto', result='pass') {
  try {
    const profile = await resolveProfilePath(argument, workspaceRoot);
    const res = await postEvalRun(profile, workspaceRoot, req_id, mode, result);
    // Mostra risultato
    const msg = res.passed
      ? `EVAL PASS — passed=${res.passed_count}, failed=${res.failed}`
      : `EVAL FAIL — passed=${res.passed_count}, failed=${res.failed}`;
    vscode.window.showInformationMessage(`${msg} | profile=${res.profile}`);
    res.summary=`Eval ${profile}: ${msg}\nCases: ${res.cases?.length}\nReport: ${res?.json}`
    return res;
  } catch (err) {
    var res = {passed:0}
    res.summary=`Eval ${profile}: ${msg}\nCases: ${res.cases?.length}\nReport: ${String(err)}`
    vscode.window.showErrorMessage(`EVAL error: ${String(err)}`);
    return res;
  }
}

// Handler comando /gate
async function handleGate(argument, workspaceRoot, req_id, opts={promote: false, reqId: null, mode: 'auto', result: ''}) {
  try {
    const profile = await resolveProfilePath(argument, workspaceRoot);
    var res = await postGateCheck(profile, workspaceRoot,req_id, opts);
    vscode.window.showInformationMessage(`GATE: ${res.gate} | profile=${profile}`);
    res.summary=`Gate ${profile}: ${res.gate}`;
    return res;

  } catch (err) {
    vscode.window.showErrorMessage(`GATE error: ${String(err)}`);
    var res = {gate:0}
    res.summary=`Gate ${profile}: ${res.gate}`;
    return res;
  }
}

module.exports = { handleGate,handleEval };
