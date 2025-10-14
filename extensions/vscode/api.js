
const vscode = require('vscode');
const { readTextFile, getProjectNameFromWorkspace }  = require('./utility');

// --- api.js ---
function baseUrl() {
  const cfg = vscode.workspace.getConfiguration('clike');
  return cfg.get('orchestratorUrl') || 'http://localhost:8080';
}

/**
 * Normalizza un valore workspaceRoot in path string (senza scheme "file://")
 */
function asFsPath(workspaceRoot) {
  
  if (!workspaceRoot) return ".";
  if (typeof workspaceRoot === "string") return workspaceRoot;
  // VS Code Uri
  return workspaceRoot.fsPath || workspaceRoot.path || ".";
}

/**
 * Esegue /v1/eval/run
 * Si aspetta che 'profile' sia un path esistente (relativo o assoluto) al file LTC.json
 */
async function postEvalRun(profile, workspaceRoot,req_id, mode, modeResult) {
  const rootPath = asFsPath(workspaceRoot);
  // /eval RRQ-009 manual pass -> eval manual pass
  const projectName = getProjectNameFromWorkspace();
  if (!projectName) throw new Error('Cannot resolve current project name');

  const url = `${baseUrl()}/v1/eval/run` +
    `?profile=${encodeURIComponent(profile)}` +
    `&project_root=${encodeURIComponent(rootPath)}` +
    (req_id ? `&req_id=${encodeURIComponent(req_id)}` : "") +
    (projectName ? `&project_name=${encodeURIComponent(projectName)}` : "");

  
  const uri = vscode.Uri.joinPath(workspaceRoot, profile);
  const raw = await readTextFile(uri);
  const ltcDoc = raw ? JSON.parse(raw) : null;
  console.log("ltcDoc", ltcDoc);
  const body = (mode === 'manual')
    ? { mode: 'manual', verdict: modeResult, ltc:ltcDoc }
    : {ltc:ltcDoc};  
  console.log("body", body);
  const res = await fetch(url, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: body ? JSON.stringify(body) : undefined
  });

  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(`HTTP ${res.status}: ${text || res.statusText}`);
  }
  return res.json();
}

/**
 * Esegue /v1/gate/check
 */
async function postGateCheck(profile, workspaceRoot,req_id,opts = { promote = false, reqId = null, mode =  'auto', result = 'pass'}  = {}) {
  const projectName = getProjectNameFromWorkspace();
  if (!projectName) throw new Error('Cannot resolve current project name');
  
  const rootPath = asFsPath(workspaceRoot);
  const qs = new URLSearchParams({
    profile,
    project_root: rootPath,
    req_id: req_id,
    project_name: projectName
  });
  console.log("postGateCheck");
  const uri = vscode.Uri.joinPath(workspaceRoot, profile);
  const raw = await readTextFile(uri);
  const ltcDoc = raw ? JSON.parse(raw) : null;
  if (opts.promote) {
    qs.set("promote", "false");
    if (!opts.reqId) throw new Error("promote=true richiede reqId (es. REQ-009)");
    qs.set("req_id", opts.reqId);
  }
  const body = (opts.mode === 'manual')
    ? { mode: 'manual', verdict: opts.result, ltc:ltcDoc }
    : {ltc:ltcDoc};  
  
  console.log("body", body);

  const url = `${baseUrl()}/v1/gate/check?${qs.toString()}`;
  console.log("url", url);

  const res = await fetch(url, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: body ? JSON.stringify(body) : undefined
  });
  console.log("res", res);

  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(`HTTP ${res.status}: ${text || res.statusText}`);
  }
  return res.json();
}



module.exports = {
  postEvalRun,
  postGateCheck,
};
