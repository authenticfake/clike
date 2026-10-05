
const vscode = require('vscode');
const { readTextFile, getProjectNameFromWorkspace }  = require('./utility');
const { orchestratorUrl, requestJson } = require('./orchestrator-client');

// --- api.js ---
// Eval/gate run the REQ checks in the sandbox and may take minutes: same budget as a Harper phase.
function evalTimeoutMs() {
  return 60 * 1000 * Number(vscode.workspace.getConfiguration('clike').get('harperTimeout', 25));
}

// Auto-eval L2: eval/gate also re-run the checks of dependency and promoted REQs.
function evalRegression() {
  return vscode.workspace.getConfiguration('clike').get('eval.regression', true);
}

/**
 * Normalize a workspaceRoot value into a path string (without the "file://" scheme)
 */
function asFsPath(workspaceRoot) {
  
  if (!workspaceRoot) return ".";
  if (typeof workspaceRoot === "string") return workspaceRoot;
  // VS Code Uri
  return workspaceRoot.fsPath || workspaceRoot.path || ".";
}

/**
 * Runs /v1/eval/run
 * Expects 'profile' to be an existing path (relative or absolute) to the LTC.json file
 */
async function postEvalRun(profile, workspaceRoot,req_id, mode, modeResult) {
  const rootPath = asFsPath(workspaceRoot);
  // /eval RRQ-009 manual pass -> eval manual pass
  const projectName = getProjectNameFromWorkspace();
  if (!projectName) throw new Error('Cannot resolve current project name');

  const url = orchestratorUrl('/v1/eval/run') +
    `?profile=${encodeURIComponent(profile)}` +
    `&project_root=${encodeURIComponent(rootPath)}` +
    (req_id ? `&req_id=${encodeURIComponent(req_id)}` : "") +
    (projectName ? `&project_name=${encodeURIComponent(projectName)}` : "");

  
  const uri = vscode.Uri.joinPath(workspaceRoot, profile);
  const raw = await readTextFile(uri);
  const ltcDoc = raw ? JSON.parse(raw) : null;
  const body = (mode === 'manual')
    ? { mode: 'manual', verdict: modeResult, ltc:ltcDoc }
    : { ltc: ltcDoc, regression: evalRegression() };
  return requestJson('POST', url, { body, timeoutMs: evalTimeoutMs() });
}

/**
 * Runs /v1/gate/check
 */
async function postGateCheck(profile, workspaceRoot, req_id, options = {}) {
  // N10: the previous default was a destructuring assignment that created globals and left opts = {}.
  const opts = { promote: false, reqId: null, mode: 'auto', result: 'pass', ...options };
  const projectName = getProjectNameFromWorkspace();
  if (!projectName) throw new Error('Cannot resolve current project name');
  
  const rootPath = asFsPath(workspaceRoot);
  const qs = new URLSearchParams({
    profile,
    project_root: rootPath,
    req_id: req_id,
    project_name: projectName
  });
  const uri = vscode.Uri.joinPath(workspaceRoot, profile);
  const raw = await readTextFile(uri);
  const ltcDoc = raw ? JSON.parse(raw) : null;
  if (opts.promote) {
    qs.set("promote", "false");
    if (!opts.reqId) throw new Error("promote=true richiede reqId (es. REQ-009)");
    qs.set("req_id", opts.reqId);
  }
  const strict = vscode.workspace.getConfiguration('clike').get('gate.strictWarnings', false);
  const body = (opts.mode === 'manual')
    ? { mode: 'manual', verdict: opts.result, ltc:ltcDoc }
    : { ltc: ltcDoc, regression: evalRegression(), ...(strict ? { strict: true } : {}) };

  const url = orchestratorUrl(`/v1/gate/check?${qs.toString()}`);
  return requestJson('POST', url, { body, timeoutMs: evalTimeoutMs() });
}



/**
 * Auto-eval with a local agent: submit the acceptance files the repair changed (with their
 * previous content); the orchestrator accepts audited, non-weakening amendments only.
 */
async function postAcceptanceAmend(workspaceRoot, reqId, changes, previous, evidence, reason) {
  return requestJson('POST', orchestratorUrl('/v1/acceptance/amend'), {
    body: {
      project_root: asFsPath(workspaceRoot),
      project_name: getProjectNameFromWorkspace() || null,
      req_id: reqId,
      changes,
      previous,
      evidence,
      reason,
    },
    timeoutMs: 60 * 1000,
  });
}

/**
 * Developer override of a gate (WP6): reason required, audited by the orchestrator.
 * The result is reported as OVERRIDE, never as PASS.
 */
async function postGateOverride(workspaceRoot, reqId, reason, author) {
  const projectName = getProjectNameFromWorkspace();
  return requestJson('POST', orchestratorUrl('/v1/gate/override'), {
    body: {
      project_root: asFsPath(workspaceRoot),
      project_name: projectName || null,
      req_id: reqId,
      reason,
      author,
    },
    timeoutMs: 60 * 1000,
  });
}

module.exports = {
  postAcceptanceAmend,
  postGateOverride,
  postEvalRun,
  postGateCheck,
};
