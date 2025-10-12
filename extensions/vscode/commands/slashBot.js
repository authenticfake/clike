const vscode = require('vscode');

const { postEvalRun, postGateCheck } = require ("../api.js");
const {resolveProfilePath } = require('../utility.js')

function parseSlash(line) {
  const m = line.trim().match(/^\/([a-zA-Z][\w:-]*)(?:\s+(.+))?$/);
  if (!m) return null;
  const cmd = m[1];
  const args = m[2] ? m[2].split(/\s+/).filter(Boolean) : [];
  return { cmd, args };
}


// Handler comando /eval
async function handleEval(argument, workspaceRoot,req_id, mode='auto', modeContent='pass') {
  try {
    const profile = await resolveProfilePath(argument, workspaceRoot);
    
    const res = await postEvalRun(profile, workspaceRoot, req_id, mode, modeContent);
    // Mostra risultato
    const msg = res.passed
      ? `EVAL PASS — passed=${res.passed_count}, failed=${res.failed}`
      : `EVAL FAIL — passed=${res.passed_count}, failed=${res.failed}`;
    vscode.window.showInformationMessage(`${msg} | profile=${res.profile}`);
    return `Eval ${profile}: ${msg}\nCases: ${res.cases?.length}\nReport: ${res?.json}`;

    // opzionale: apri report junit/json se presenti
    // ...
  } catch (err) {
    vscode.window.showErrorMessage(`EVAL error: ${String(err)}`);
  }
}

// Handler comando /gate
async function handleGate(argument, workspaceRoot, req_id, opts={promote: false, reqId: null, mode: 'auto', modeContent: ''}) {
  try {
    const profile = await resolveProfilePath(argument, workspaceRoot);
    const res = await postGateCheck(profile, workspaceRoot,req_id, opts);
    vscode.window.showInformationMessage(`GATE: ${res.gate} | profile=${profile}`);
    return `Gate ${profile}: ${res.gate}`;

  } catch (err) {
    vscode.window.showErrorMessage(`GATE error: ${String(err)}`);
  }
}

module.exports = { handleGate,handleEval };
