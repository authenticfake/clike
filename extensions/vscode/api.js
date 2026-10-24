
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
async function postEvalRun(profile, workspaceRoot,req_id, mode, modeResult, signal = null, options = {}) {
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
    : { ltc: ltcDoc, regression: evalRegression(),
        // a targeted re-eval in a repair loop: the regression of these promoted REQs only (never a verdict)
        ...(Array.isArray(options.regressionReqs) && options.regressionReqs.length ? { regression_reqs: options.regressionReqs } : {}) };
  // aborting closes the request: the orchestrator then stops the eval in the sandbox
  return requestJson('POST', url, { body, timeoutMs: evalTimeoutMs(), signal: signal || undefined });
}

/**
 * Re-runs only the named checks of a REQ's eval in the sandbox (no regression, never a verdict):
 * the eval checks a local agent asks for while it repairs (eval-check-bridge.js).
 */
async function postEvalChecks(profile, workspaceRoot, reqId, checks) {
  const projectName = getProjectNameFromWorkspace();
  if (!projectName) throw new Error('Cannot resolve current project name');
  const url = orchestratorUrl('/v1/eval/run') +
    `?profile=${encodeURIComponent(profile)}` +
    `&project_root=${encodeURIComponent(asFsPath(workspaceRoot))}` +
    `&req_id=${encodeURIComponent(reqId)}` +
    `&project_name=${encodeURIComponent(projectName)}`;
  const raw = await readTextFile(vscode.Uri.joinPath(workspaceRoot, profile));
  // regression::<REQ>[::check]: that promoted REQ's regression with this candidate overlaid
  const own = [];
  const regressionReqs = [];
  for (const name of checks || []) {
    const m = /^regression::(REQ-[A-Za-z0-9_-]+)(?:::|$)/i.exec(String(name));
    if (m) { if (!regressionReqs.includes(m[1].toUpperCase())) regressionReqs.push(m[1].toUpperCase()); } else own.push(name);
  }
  const body = {
    ltc: raw ? JSON.parse(raw) : null,
    regression: regressionReqs.length > 0,
    checks: own.length ? own : null,
    ...(regressionReqs.length ? { regression_reqs: regressionReqs } : {}),
  };
  return requestJson('POST', url, { body, timeoutMs: evalTimeoutMs() });
}

/**
 * Live progress of the REQ's eval or gate in flight (/v1/eval/progress): phase, checks done of
 * total, the promoted REQs of the regression; { state: 'unknown' } when none is known.
 */
async function getEvalProgress(workspaceRoot, reqId) {
  const projectName = getProjectNameFromWorkspace();
  const qs = new URLSearchParams({ project_root: asFsPath(workspaceRoot), req_id: String(reqId || '') });
  if (projectName) qs.set('project_name', projectName);
  return requestJson('GET', orchestratorUrl(`/v1/eval/progress?${qs.toString()}`), { timeoutMs: 4000 });
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
  return requestJson('POST', url, { body, timeoutMs: evalTimeoutMs(), signal: opts.signal || undefined });
}



/** Acceptance-first KIT: lock the REQ's freshly written tests and eval profile before the code. */
async function postAcceptanceLock(workspaceRoot, reqId) {
  return requestJson('POST', orchestratorUrl('/v1/acceptance/lock'), {
    body: { project_root: asFsPath(workspaceRoot), project_name: getProjectNameFromWorkspace() || null, req_id: reqId },
    timeoutMs: 60 * 1000,
  });
}

/**
 * Auto-eval with a local agent: submit the acceptance files the repair changed (with their
 * previous content); the orchestrator accepts audited, non-weakening amendments only.
 */
async function postAcceptanceAmend(workspaceRoot, reqId, changes, previous, evidence, reason, deleted = []) {
  return requestJson('POST', orchestratorUrl('/v1/acceptance/amend'), {
    body: {
      project_root: asFsPath(workspaceRoot),
      project_name: getProjectNameFromWorkspace() || null,
      req_id: reqId,
      changes,
      previous,
      evidence,
      reason,
      deleted,
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

/**
 * The developer accepts a deliberate, non-weakening edit of a REQ's locked tests / ci
 * (`/eval REQ --accept "reason"`): reason required, audited by the orchestrator.
 */
async function postAcceptanceAccept(workspaceRoot, reqId, reason, author) {
  return requestJson('POST', orchestratorUrl('/v1/acceptance/accept'), {
    body: {
      project_root: asFsPath(workspaceRoot),
      project_name: getProjectNameFromWorkspace() || null,
      req_id: reqId,
      reason,
      author,
    },
    timeoutMs: 60 * 1000,
  });
}

/** Native tools the REQ (or, without reqId, the solution profile) needs that the eval sandbox lacks. */
async function postEvalToolsCheck(workspaceRoot, reqId, profile) {
  return requestJson('POST', orchestratorUrl('/v1/eval/tools/check'), {
    body: {
      project_root: asFsPath(workspaceRoot),
      project_name: getProjectNameFromWorkspace() || null,
      req_id: reqId || null,
      profile: profile || null,
    },
    timeoutMs: 90 * 1000,
  });
}

/** Install catalog tools (`name` or `name@version`) into the eval sandbox tools volume. */
async function postEvalToolsInstall(workspaceRoot, tools) {
  return requestJson('POST', orchestratorUrl('/v1/eval/tools/install'), {
    body: { project_root: asFsPath(workspaceRoot), project_name: getProjectNameFromWorkspace() || null, tools },
    timeoutMs: 30 * 60 * 1000,
  });
}

/** Rebuild the installed eval tools (all, or `tools`) at their latest versions. */
async function postEvalToolsUpdate(tools = []) {
  return requestJson('POST', orchestratorUrl('/v1/eval/tools/update'), { body: { tools }, timeoutMs: 60 * 60 * 1000 });
}

/** The tools catalog, what is installed and what the project approved. */
async function getEvalTools(workspaceRoot) {
  const qs = new URLSearchParams({ project_root: asFsPath(workspaceRoot), project_name: getProjectNameFromWorkspace() || '' });
  return requestJson('GET', orchestratorUrl(`/v1/eval/tools?${qs.toString()}`), { timeoutMs: 30 * 1000 });
}

module.exports = {
  getEvalProgress,
  getEvalTools,
  postEvalToolsUpdate,
  postEvalToolsCheck,
  postEvalToolsInstall,
  postAcceptanceAccept,
  postAcceptanceAmend,
  postAcceptanceLock,
  postGateOverride,
  postEvalChecks,
  postEvalRun,
  postGateCheck,
};
