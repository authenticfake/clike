// extension.js — Clike Orchestrator+Gateway integration GOOGDDDD
const vscode = require('vscode');
const { applyPatch } = require('diff');
const { execFile } = require('child_process');
const http = require('http');
const { URL } = require('url');
const fs = require('fs/promises');
const fsSync = require('fs');
const path = require('path');

const {
  initServiceAuth,
  storeServiceToken,
  generateServiceToken,
} = require('./service-auth');
const { validateLocalMcpRequest } = require('./mcp-request-guard');
const extensionMcp = require('./extension-mcp');
const autopilot = require('./autopilot');
const { projectUseCaseCoverage, useCaseCoverageMessage } = require('./use-case-coverage');
const planReadiness = require('./plan-readiness');
const { saveRejectedTestFix, rejectedTestFixMessage, applyLatestTestFix, revertAppliedTestFix } = require('./rejected-test-fix');
const { createFreshnessCheck } = require('./extension-freshness');
const { openMemoryPanel, staleKitPaths } = require('./memory-panel');
const { ensureGuideIndexed } = require('./memory-guide');
// the code this window loaded; a reinstall changes the files, not the running code
const extensionFreshness = createFreshnessCheck(__filename);
const { collectExistingSourceEvidence } = require('./existing-source-evidence');
const { writeFinalizeOutcome } = require('./finalize-outcome');
const releasePublish = require('./release-publish');
const finalizeLocalCheck = require('./finalize-local-check');

/** The GitHub CLI: on PATH, else where Homebrew puts it (VS Code started from the Dock has a short PATH). */
function ghExecutable() {
  const { execFileSync } = require('child_process');
  for (const cand of ['gh', '/opt/homebrew/bin/gh', '/usr/local/bin/gh', 'C:\\Program Files\\GitHub CLI\\gh.exe']) {
    try { execFileSync(cand, ['--version'], { stdio: 'ignore' }); return cand; } catch { /* next */ }
  }
  return '';
}

// A passing /finalize delivers the release: the annotated tag vN on its commit and the release
// notes (runs/finalize/RELEASE_vN.md). The GitHub Release is published only when the developer
// says so (it is public): the tag is pushed, then gh creates or updates the release.
async function offerRelease(ws, settings, status, msg, say, { manual = false } = {}) {
  const root = ws.fsPath;
  let info;
  try { info = releasePublish.releaseInfo(root, { status, remote: settings.gitRemote || 'origin' }); } catch (e) {
    log(`[release] not prepared: ${e?.message || e}`);
    return;
  }
  const notes = releasePublish.writeReleaseNotes(root, info);
  if (!settings.gitAutoCommit && !manual) {
    // the finalize is not committed: a tag on HEAD would mark the code before it
    say(`ℹ RELEASE ${info.release}: release notes in ${notes}. clike.git.autoCommit is off: commit the finalize, ` +
      `then tag it (git tag -a ${info.tag} -m "${releasePublish.releaseTitle(info)}").`);
    return;
  }
  const tagged = releasePublish.tagRelease(root, info);
  if (tagged.error) {
    say(`ℹ RELEASE ${info.release}: ${tagged.error} Notes: ${notes}.`);
    return;
  }
  say(`🏷 RELEASE ${info.release}: tag ${tagged.tag} ${tagged.created ? 'created' : 'already'} on the finalize commit — ` +
    `${releasePublish.changeSummary(info.reqs)}. Release notes: ${notes}.`);
  const remote = settings.gitRemote || 'origin';
  const publishCmd = `git push ${remote} ${info.tag} && gh release create ${info.tag} --title "${releasePublish.releaseTitle(info)}" --notes-file ${notes} --latest --verify-tag ${info.assets.join(' ')}`;
  if (!info.repo) {
    say(`ℹ RELEASE ${info.release}: no GitHub remote — the release is the local tag ${info.tag}.`);
    return;
  }
  if (msg && (msg.__fromMcp || msg.__unattended)) {
    say(`ℹ RELEASE ${info.release}: not published (it needs your confirmation). To publish: ${publishCmd}`);
    return;
  }
  const gh = ghExecutable();
  if (!gh) {
    say(`ℹ RELEASE ${info.release}: the GitHub CLI (gh) is not installed — install it and run gh auth login, then CLike: Publish release. Or: ${publishCmd}`);
    return;
  }
  const run = (cmd, args) => new Promise((resolve, reject) => {
    require('child_process').execFile(cmd === 'gh' ? gh : cmd, args, { cwd: root }, (err, stdout, stderr) => (err ? reject(new Error(String(stderr || err.message).trim())) : resolve(String(stdout || '').trim())));
  });
  const publish = 'Publish release';
  const open = 'Open notes';
  const choice = await vscode.window.showInformationMessage(
    `Release ${info.release} of ${info.project} is tagged. Publish the GitHub Release on ${info.repo}? ` +
    `The tag ${info.tag} is pushed and the release is public (${releasePublish.changeSummary(info.reqs)}${info.prerelease ? ', pre-release: passed with warnings' : ''}).`,
    publish, open);
  if (choice === open) {
    openReadingMode(vscode.Uri.joinPath(ws, ...notes.split('/')));
    say(`ℹ RELEASE ${info.release}: not published. To publish later: ${publishCmd}`);
    return;
  }
  if (choice !== publish) {
    say(`ℹ RELEASE ${info.release}: not published. To publish later: ${publishCmd}`);
    return;
  }
  try {
    await run('git', ['push', remote, info.tag]);
    let exists = false;
    try { await run('gh', ['release', 'view', info.tag, '--json', 'tagName']); exists = true; } catch { /* a new release */ }
    for (const args of releasePublish.ghReleaseArgs(info, notes, { exists })) await run('gh', args);
    let url = '';
    try { url = await run('gh', ['release', 'view', info.tag, '--json', 'url', '--jq', '.url']); } catch { /* shown without the link */ }
    say(`✔ RELEASE ${info.release} ${exists ? 'updated' : 'published'}${url ? `: ${url}` : ` on ${info.repo}`}.`);
  } catch (e) {
    say(`✖ RELEASE ${info.release} not published: ${String(e?.message || e).split('\n')[0]}. To publish: ${publishCmd}`);
  }
}


/** The finalize commit message naming the release and its REQs; '' falls back to the default. */
function finalizeCommitMessage(root, runId, status = '') {
  try {
    const info = releasePublish.releaseInfo(root);
    return status ? releasePublish.evidenceCommitMessage(info, status, runId) : releasePublish.finalizeCommitMessage(info, runId);
  } catch (e) {
    log(`[finalize] release commit message: ${e?.message || e}`);
    return '';
  }
}

/** Records the outcome of /finalize for the cockpit (never fails the command). */
function recordFinalizeOutcome(status, reason) {
  try {
    const ws = getWorkspaceRoot();
    if (ws) writeFinalizeOutcome(toFsPath(ws), status, reason);
    // a finalize that passed: its README opens in reading mode, as the gate's promotion report
    if (ws && status === 'ok') openReadingMode(vscode.Uri.joinPath(ws, 'README.md'));
  } catch (e) {
    log(`[finalize] outcome not recorded: ${e?.message || e}`);
  }
}

/** Open a markdown file rendered (preview), or read-only text when the preview is not available. */
function openReadingMode(uri) {
  if (!fsSync.existsSync(uri.fsPath)) return;
  vscode.commands.executeCommand('markdown.showPreview', uri).then(undefined, () =>
    vscode.window.showTextDocument(uri, { preview: true }));
}
const { getEvalRoots, getEvalProgress, getEvalTools, postEvalToolsUpdate, postAcceptanceAccept, postAcceptanceAmend, postAcceptanceLock, postEvalChecks, postEvalToolsCheck, postEvalToolsInstall, postGateOverride } = require('./api');
const evalToolsLib = require('./eval-tools');
const { approveForProject, ensureEvalTools, questionText } = evalToolsLib;
const { agentArgsForEvalCheck, agentTimeoutMinutes, startEvalCheckBridge } = require('./eval-check-bridge');
const finalizeVerify = require('./finalize-verify');
const { request: serviceRequest, orchestratorUrl, serviceBaseUrls } = require('./orchestrator-client');
const { safeRelativePath, safeWorkspaceUri, resolveInsideWorkspace } = require('./safe-workspace');
const {  handleGate, handleEval } = require('./commands/harper');
const {  persistTelemetryVSCode } = require('./telemetry');


const {
  normalizeExecutionPreference,
  normalizeLocalAgentExecutor,
  executionPreferenceRequestsLocalAgent,
  resolveSelectedLocalAgentExecutor,
  detectLocalAgentAvailability,
  reconcileExecutionPreference,
  getExecutorConfig,
  resolveLocalAgentTimeoutMinutes,
  timeoutSettingKey,
  buildLocalAgentModelArgs,
  parseLocalAgentRun,
  normalizeAgentStdout,
  withMachineReadableOutput,
  withIsolatedMcp,
  buildLocalAgentDisplayLabel,
  terminateProcessTree,
} = require('./local-agent-executors');

const {
  readPlanJson,
  getProjectId,
  promoteReqSources,
  runPromotionFlow,
  preIndexRag,
  
  
  
  
  getProjectNameFromWorkspace,
  runLocalAgentSync,
  terminateActiveAgents,
  collectReqCandidateFiles,
  collectReqCandidateFileArtifacts,
  collectFinalizeCandidateFiles,
  collectFinalizeCandidateFileArtifacts,
} = require('./utility');

const {
  buildHarperBody,
  defaultCoreForPhase,
  runKitCommand,
  runEvalGateCommand,
  saveKitCommand,
  saveEvalCommand,
  saveGateCommand,
  
} = require('./utility');

const {
  
  logCurrentTimeStandard,
  httpPostJsonLong,
  
} = require('./utility');
const {
  getHarperSlashCommandName,
  shouldBlockHarperSlashFromGenericChatMessage,
} = require('./slash-parser');
const {
  acceptanceChanges,
  collectRepairFiles,
  evalPassed,
  fixCycleMethodology,
  ownFailureCount,
  targetedRegressionReqs,
  manualRepairRequest,
  nextAutoEvalStep,
  nextAutoGateStep,
  annotateIntermittentFailures,
  inputsFingerprint,
  readEarlierReports,
  repairNotesMarkdown,
  restoreAcceptanceFiles,
  writeRepairNotes,
  snapshotAcceptanceSurface,
} = require('./auto-eval');
const { validateExtendPlan, readPlanText } = require('./extend-guard');
const releaseExtend = require('./release-extend');
const adoptLib = require('./adopt');
const { copyTemplateTree, mergeGitignore, teamProcessRedirect, PROPOSALS_DIR } = require('./init-merge');
const { buildAgentChatArgs, createAgentStreamParser, newSession, sessionKey } = require('./agent-chat');
const { createApprovalGate, createCodexAppServerTurn, startClaudeApprovalServer } = require('./agent-approvals');
const { agentModelListMessage, CLAUDE_ALIASES, readCodexModelSlugs, validateAgentModel } = require('./agent-model-validation');

const {
  buildCodexArgsForLocalAgent,
  assertLocalAgentWritePreflight,
  validateLocalAgentRequiredOutputs,
  evaluateDocumentPhaseInputPreflight,
  evaluateExtendInputPreflight,
  classifyBlockedLocalAgentOutput,
  describeFailedLocalAgentRun,
  describeInterruptedLocalAgentRun,
  shouldFallbackToCloud,
  documentPhaseCompanionTargets,
  isFreshLocalAgentArtifact,
  isClikeOwnHarperFile,
} = require('./local-agent-write-policy');
const { ensureProjectMounted, stackFolder } = require('./project-mount');

// Harper phases that can run through the orchestrator-owned local-agent package
// path. Early document phases (idea/spec/plan) and the existing
// kit/finalize/extend actuator phases share the exact same dispatch.
const LOCAL_AGENT_ELIGIBLE_PHASES = new Set([
  'idea',
  'spec',
  'plan',
  'kit',
  'finalize',
  'extend',
]);

// Local-agent phases that are not REQ-scoped. They operate on the solution as a
// whole and use 'SOLUTION' as the agent req id.
const NO_REQ_LOCAL_AGENT_PHASES = new Set([
  'idea',
  'spec',
  'plan',
  'finalize',
  'extend',
]);

// Local-agent phases whose only outputs are canonical Harper documents under
// docs/harper. They share the extend-style collection/validation flow.
const DOCUMENT_LOCAL_AGENT_PHASES = new Set(['idea', 'spec', 'plan']);

function isLocalAgentEligiblePhase(phase) {
  return LOCAL_AGENT_ELIGIBLE_PHASES.has(String(phase || '').trim().toLowerCase());
}

function isNoReqLocalAgentPhase(phase) {
  return NO_REQ_LOCAL_AGENT_PHASES.has(String(phase || '').trim().toLowerCase());
}

function isDocumentLocalAgentPhase(phase) {
  return DOCUMENT_LOCAL_AGENT_PHASES.has(String(phase || '').trim().toLowerCase());
}


const{ toFsPath,  clikeGitSync } = require('./git'); // NEW: clikeGitSync
const { CHAT_THEMES, getChatTheme, getWebviewHtml } = require('./chat-ui');
const { buildCockpitState, kitBlockers, reportCounts } = require('./cockpit-state');
const { createRunTracker } = require('./run-tracker');
const chatHistory = require('./chat-history');
const {
  attachBmadQaAdvisory,
  buildEffectiveEvalMethodologyContext,
} = require('./bmad-advisory');
const {
  validateCanonicalHarperArtifact,
  rejectedHarperArtifactPath,
  formatHarperError,
} = require('./harper-canonical-validation');

let clikeChatPanel = null;
// the chat's message handler, so MCP tools can run phases through the same governed flow and await them
let clikeRunChatMessage = null;
// MCP runs (H2): run_id -> { status, phase, req_id, started_at, result }
const mcpRuns = new Map();
let clikeExtensionContext = null;
let clikeHarperBlockingRun = false;
let extensionMcpServer = null;
let extensionMcpState = {
  started: false,
  url: null,
  lastCommand: null,
  lastAcceptedAt: null,
  lastError: null,
};
let __clike_lastTargetUriCache = null;  
// --- In-flight request state (for Cancel) ---
let inflightController = null;
// Harper phases (/eval, /gate, a KIT repair, their --fix cycles) share one cancel signal: a phase
// the user starts takes a fresh one, the cycles it chains reuse it, Cancel aborts it.
let harperAbortController = null;
// /autopilot in progress: { stop, current, ... } (one at a time); the last one ended, for its status
let autopilotRun = null;
let lastAutopilotRun = null;
// "Stop after this step" (the run card): the --fix loops and the after-KIT auto-eval end at the
// next step boundary instead of going on; cleared when a new command starts.
let harperStopAfterStep = false;
// the run feed of the chat panel (run card, status bar): what the handlers and agents report to it
let activeRunFeed = null;
function runFeedLive(text) { try { if (activeRunFeed) activeRunFeed.live(text); } catch { /* the card is best effort */ } }
function runFeedCost(telemetry) { try { if (activeRunFeed) activeRunFeed.cost(telemetry); } catch { /* idem */ } }
/** The run card asked to stop after the current step: the loop says so and ends cleanly. */
function stopAfterStepRequested(say, what) {
  if (!harperStopAfterStep) return false;
  say(`⏸ ${what}: stopped after the current step, as you asked.`);
  return true;
}
/** On startup: an /autopilot that never ended (window closed, crash) resumes (clike.autopilot.resumeOnStartup). */
async function resumeInterruptedAutopilot() {
  const root = getWorkspaceRoot();
  if (!root || autopilotRun) return;
  if (!vscode.workspace.getConfiguration('clike').get('autopilot.resumeOnStartup', true)) return;
  let saved;
  try { saved = JSON.parse(fsSync.readFileSync(path.join(root.fsPath, ...autopilot.STATE_REL.split('/')), 'utf8')); } catch { return; }
  if (!saved || !saved.running) return;
  out.appendLine(`[autopilot] interrupted run found (at ${saved.current || '?'}): resuming`);
  await ensureClikeChatPanelForAgent();
  if (typeof clikeRunChatMessage === 'function') await clikeRunChatMessage({ type: 'autopilot', action: 'start', resume: true });
}

/** What /autopilot status and the MCP tool harper_autopilot answer. */
function autopilotSnapshot() {
  const run = autopilotRun || lastAutopilotRun;
  if (!run) return { running: false, message: 'Autopilot has not run in this VS Code window.' };
  const ids = (result) => run.reqs.filter((r) => r.result === result).map((r) => r.req_id);
  return {
    running: run === autopilotRun,
    current: run === autopilotRun ? run.current || 'between steps' : null,
    executor: run.executor || 'as configured',
    methodology: run.methodology || null,
    started_at: new Date(run.startedAt).toISOString(),
    ended_at: run.endedAt ? new Date(run.endedAt).toISOString() : null,
    outcome: run.outcome || null,
    promoted: ids('promoted'),
    review_required: run.reqs.filter((r) => r.review_required).map((r) => r.req_id),
    parked: run.reqs.filter((r) => r.result === 'parked').map((r) => ({ req_id: r.req_id, step: r.step, reason: r.reason })),
    quota_waits: run.waits.length,
    next: run.next || null,
    report: 'runs/autopilot/report.md',
  };
}
function harperSignal(fresh) {
  if (fresh || !harperAbortController) harperAbortController = new AbortController();
  return harperAbortController.signal;
}
/** `/eval REQ --accept "reason"`: the orchestrator accepts and audits a non-weakening edit of the locked surface. */
async function acceptAcceptanceEdit(wsRoot, reqId, givenReason) {
  const echo = (message) => clikeChatPanel?.webview.postMessage({ type: 'echo', message });
  try {
    let reason = givenReason.trim();
    if (reason.length < 10) {
      reason = (await vscode.window.showInputBox({
        title: `Accept the edited tests / ci of ${reqId}`,
        prompt: 'Why did the tests or the eval profile change? (recorded in the audit log)',
        value: reason,
        ignoreFocusOut: true,
        validateInput: (v) => (v && v.trim().length >= 10 ? null : 'At least 10 characters'),
      }) || '').trim();
    }
    if (!reason) {
      echo(`Acceptance of ${reqId} cancelled.`);
      return;
    }
    let author = '';
    try {
      author = require('child_process')
        .execFileSync('git', ['config', 'user.name'], { cwd: wsRoot.fsPath, stdio: ['ignore', 'pipe', 'ignore'] })
        .toString().trim();
    } catch {}
    // a test change the repair proposed and the lock restored: --accept applies it first
    let proposal = null;
    try {
      proposal = applyLatestTestFix(wsRoot.fsPath, reqId);
      if (proposal?.applied) echo(`${reqId}: applied the test change the repair proposed (${proposal.applied}).`);
      else if (proposal?.stale) echo(`${reqId}: the latest proposed test change (${proposal.stale}) no longer applies (already applied, or the test changed): accepting the tests as they are.`);
    } catch (e) {
      echo(`✖ ${reqId}: the proposed test change could not be applied (${String(e?.message || e).split('\n')[0]}); nothing accepted.`);
      return;
    }
    const res = await postAcceptanceAccept(wsRoot, reqId, reason, author || require('os').userInfo().username);
    const rejected = Object.entries(res?.rejected || {}).map(([file, why]) => `${file} (${[].concat(why).join('; ')})`);
    if (res?.accepted?.length) echo(`✔ ${reqId}: accepted ${res.accepted.join(', ')} (audit ${res.audit_id}). Run the eval again.`);
    else if (!rejected.length) echo(`${reqId}: the tests and ci/ match the lock, nothing to accept.`);
    if (rejected.length) echo(`✖ ${reqId}: not accepted, they remove or weaken checks — restore them or re-run /kit ${reqId}: ${rejected.join(', ')}`);
    if (rejected.length && proposal?.applied && !res?.accepted?.length) {
      echo(`${reqId}: the proposed test change was undone (${revertAppliedTestFix(wsRoot.fsPath, proposal.applied)}).`);
    }
  } catch (e) {
    echo(`✖ ${reqId}: acceptance failed (${String(e?.message || e).split('\n')[0]})`);
  } finally {
    clikeChatPanel?.webview.postMessage({ type: 'busy', on: false, force: true });
  }
}

function harperCancelled() {
  return !!(harperAbortController && harperAbortController.signal.aborted);
}
/** The chat's Cancel (and MCP cancel_run): stop the request, the eval it runs and every local agent. */
function cancelHarperWork() {
  if (autopilotRun) autopilotRun.stop = 'cancel';
  if (inflightController) inflightController.abort();
  inflightController = null;
  if (harperAbortController) harperAbortController.abort();
  if (activeChatAgentChild) {
    terminateProcessTree(activeChatAgentChild);
    activeChatAgentChild = null;
  }
  return terminateActiveAgents();
}
// the agent CLI answering the current chat message (Cancel terminates it)
let activeChatAgentChild = null;
// Chat state: per mode -> array of bubbles. Each bubble: { role: 'user'|'assistant', text, model, ts }

function getWorkspaceRoot() {
    const workspaceFolders = vscode.workspace.workspaceFolders;

    if (!workspaceFolders || workspaceFolders.length === 0) {
        // Handle the case where no folder is open
        return null; 
    }
    
    // Return the URI of the first open folder (the workspace root)
    return workspaceFolders[0].uri; 
}


const out = vscode.window.createOutputChannel('Clike');
/**
 * Custom logging function that writes to both channels.
 * @param {...any} args Messages or objects to log.
 */
function log(...args) {
    // 1. Log to the standard console for debugging.
    console.log(...args); 
    
    // 2. Log to the VS Code output channel.
    out.appendLine(args.map(arg => {
        // Convert each argument to a string for output.
        if (typeof arg === 'object' && arg !== null) {
            return JSON.stringify(arg, null, 2);
        }
        return String(arg);
    }).join(' ')); 
}

async function pathExists(p) {
  try { await fs.access(p); return true; } catch { return false; }
}
async function ensureDir(p) {
  await fs.mkdir(p, { recursive: true });
  return p;
}
async function isDirEmpty(p) {
  try { const items = await fs.readdir(p); return items.length === 0; } catch { return true; }
}
async function writeFileUtf8(filePath, content) {
  await ensureDir(path.dirname(filePath));
  await fs.writeFile(filePath, content, 'utf8');
}
async function writeJson(filePath, obj) {
  await ensureDir(path.dirname(filePath));
  await fs.writeFile(filePath, `${JSON.stringify(obj, null, 2)}\n`, 'utf8');
}
function nowIso() { return new Date().toISOString(); }

// --- profile hint for routing (used when model === 'auto') ---
function computeProfileHint(mode, model) {
  try {
    const m = String(mode || 'free').toLowerCase();

    const fixed = String(model || 'auto').toLowerCase() !== 'auto' ;
    if (fixed) return null; // explicit model → no hint
    if (m === 'harper') return 'plan.fast';
    if (m === 'coding') return 'code.strict';
    return null;
  } catch { return null; }
}


// Max size for inlining an attachment's bytes into the request so the
// orchestrator can materialize it under runs/<phase>/attachments/. Beyond this
// the file is referenced by path only (kept out of the inline payload).
const ATTACH_MAX_INLINE_BYTES = 10 * 1024 * 1024;

const ATTACH_TEXT_EXT = new Set([
  '.md', '.markdown', '.txt', '.text', '.log', '.json', '.yml', '.yaml', '.csv', '.tsv',
  '.xml', '.html', '.htm', '.py', '.js', '.ts', '.tsx', '.jsx', '.java', '.go', '.rs',
  '.c', '.cpp', '.h', '.hpp', '.cs', '.rb', '.php', '.sh', '.sql', '.ini', '.toml', '.cfg', '.env', '.properties',
]);

function attachmentExt(name) {
  const m = String(name || '').toLowerCase().match(/\.[^.]+$/);
  return m ? m[0] : '';
}

function isTextAttachment(name) {
  return ATTACH_TEXT_EXT.has(attachmentExt(name));
}

// Best-effort MIME so the manifest/prompt can tell the agent how to treat the
// attachment (PDF text vs image vision vs plain text).
function guessAttachmentMime(name) {
  const ext = attachmentExt(name);
  const map = {
    '.png': 'image/png', '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.gif': 'image/gif',
    '.webp': 'image/webp', '.bmp': 'image/bmp', '.svg': 'image/svg+xml', '.tif': 'image/tiff', '.tiff': 'image/tiff',
    '.pdf': 'application/pdf',
    '.doc': 'application/msword',
    '.docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    '.xls': 'application/vnd.ms-excel',
    '.xlsx': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    '.ppt': 'application/vnd.ms-powerpoint',
    '.pptx': 'application/vnd.openxmlformats-officedocument.presentationml.presentation',
  };
  if (map[ext]) return map[ext];
  return isTextAttachment(name) ? 'text/plain' : 'application/octet-stream';
}

function getDefaultExecutionPreference() {
  try {
    const cfg = vscode.workspace.getConfiguration('clike');
    return normalizeExecutionPreference(cfg.get('execution.defaultPreference', 'local_agent_only'));
  } catch {
    return 'local_agent_only';
  }
}

function getDefaultLocalAgentExecutor() {
  try {
    const cfg = vscode.workspace.getConfiguration('clike');
    return normalizeLocalAgentExecutor(
      cfg.get('localAgent.preferredExecutor', 'gpt_codex')
    );
  } catch {
    return 'auto';
  }
}

function normalizeAgentDefaultInput(value) {
  const raw = String(value || '').trim().toLowerCase();
  if (raw === 'codex') return 'gpt_codex';
  if (raw === 'claude') return 'claude_code';
  if (raw === 'auto') return 'auto';
  return '';
}


async function persistLocalAgentDefault(executorId) {
  const normalized = normalizeLocalAgentExecutor(executorId);
  const cfg = vscode.workspace.getConfiguration('clike');
  await cfg.update('localAgent.preferredExecutor', normalized, vscode.ConfigurationTarget.Workspace);
  return normalized;
}

function _looksTextual(p) {
  const exts = [
    '.md','.txt','.json','.yml','.yaml','.ini',
    '.js','.jsx','.ts','.tsx','.mjs','.cjs',
    '.py','.java','.go','.rb','.rs','.cs', 
    '.cpp','.cc','.c','.h','.hpp','.kt','.swift','.php',
    '.css','.scss','.less','.html'
  ];
  return exts.includes(path.extname(p).toLowerCase());
}

async function collectFinalizeRagItems(workspaceRootUri, maxFiles = 400, maxBytes = 512 * 1024) {
  // 1) Normalize: accept both vscode.Uri and string
  const rootPath =
    typeof workspaceRootUri === 'string'
      ? workspaceRootUri
      : (workspaceRootUri && (workspaceRootUri.fsPath || workspaceRootUri.path)) || '';

  if (!rootPath) {
    throw new Error('collectFinalizeRagItems: invalid workspace root (expected vscode.Uri or string path)');
  }

  // 2) Walk the FS using path strings (not Uri)
  async function walk(dir) {
    const out = [];
    let entries = [];
    try {
      entries = await fs.readdir(dir, { withFileTypes: true });
    } catch {
      return out; // missing dir = ok
    }
    for (const e of entries) {
      const p = path.join(dir, e.name);
      if (e.isDirectory()) {
        if (['.git', 'node_modules', 'dist', 'build', 'out', '.venv', '.mypy_cache'].includes(e.name)) continue;
        out.push(...(await walk(p)));
      } else {
        out.push(p);
      }
    }
    return out;
  }

  const targets = [];
  // If you also want to include docs/harper, add it back here
  const srcDir = path.join(rootPath, 'src');

  for (const d of [srcDir]) {
    const files = await walk(d);
    for (const absPath of files) {
      if (!_looksTextual(absPath)) continue;
      if (targets.length >= maxFiles) break;
      let buf;
      try {
        buf = await fs.readFile(absPath);
      } catch {
        continue;
      }
      if (buf.length > maxBytes) continue;

      // 3) Send a workspace-relative path (portable and clean)
      const rel = path.relative(rootPath, absPath).replace(/\\/g, '/');

      targets.push({
        path: rel,                              // <= relative
        bytes_b64: Buffer.from(buf).toString('base64'),
      });
    }
  }
  return targets;
}
// --- : collect lane-guides for RAG after /plan ------------------------
async function collectLaneGuidesRagItems(workspaceRoot, opts = {}) {
  if (!workspaceRoot) {
    return [];
  }

  const maxFiles = opts.maxFiles ?? 200;
  const maxBytes = opts.maxBytes ?? 256 * 1024;

  const rootFsPath = workspaceRoot.fsPath;
  const laneRootDir = path.join(rootFsPath, 'docs', 'harper', 'lane-guides');
  const laneRootUri = vscode.Uri.file(laneRootDir);

  let stat;
  try {
    stat = await vscode.workspace.fs.stat(laneRootUri);
  } catch {
    // Folder does not exist yet → nothing to index
    return [];
  }

  if (!stat || stat.type !== vscode.FileType.Directory) {
    return [];
  }

  const items = [];

  async function walk(dirUri, relBase) {
    const entries = await vscode.workspace.fs.readDirectory(dirUri);

    for (const [name, type] of entries) {
      const childUri = vscode.Uri.joinPath(dirUri, name);
      const relPath = relBase ? path.posix.join(relBase, name) : name;

      if (type === vscode.FileType.Directory) {
        await walk(childUri, relPath);
        if (items.length >= maxFiles) {
          return;
        }
        continue;
      }

      if (type !== vscode.FileType.File) {
        continue;
      }

      const ext = (name.split('.').pop() || '').toLowerCase();
      const ALLOWED = ['md', 'markdown', 'txt'];

      if (!ALLOWED.includes(ext)) {
        continue;
      }

      let data;
      try {
        data = await vscode.workspace.fs.readFile(childUri);
      } catch (err) {
        log(`[harperRAG] skip lane-guide (read error): ${childUri.fsPath} -> ${err}`);
        continue;
      }

      if (!data || !data.byteLength) {
        continue;
      }

      const slice = data.byteLength > maxBytes ? data.slice(0, maxBytes) : data;
      const b64 = Buffer.from(slice).toString('base64');
      const relFromRoot = path.posix.join('docs', 'harper', 'lane-guides', relPath);

      items.push({
        path: relFromRoot,
        bytes_b64: b64,
      });

      if (items.length >= maxFiles) {
        log(`[harperRAG] lane-guide RAG items truncated at ${maxFiles} files`);
        return;
      }
    }
  }

  await walk(laneRootUri, '');
  log(`[harperRAG] collected ${items.length} lane-guide RAG items`);
  return items;
}

// Collect RAG items for a given REQ under runs/kit/REQ-XXX.
// We index candidate source, tests, CI contracts, docs and reports.
// We still never index canonical /src or /test here.
async function collectKitRagItems(workspaceRoot, reqId, opts = {}) {
  if (!workspaceRoot) {
    return [];
  }

  const maxFiles = opts.maxFiles ?? 700;
  const maxBytes = opts.maxBytes ?? 512 * 1024;
  const rootFsPath = workspaceRoot.fsPath;
  const reqNorm = String(reqId || '').trim().toUpperCase();

  const candidateSubroots = ['src', 'test', 'ci', 'docs', 'reports', 'root'];
  const items = [];

  const CODE_EXTENSIONS = [
    'ts', 'tsx', 'js', 'jsx', 'mjs', 'cjs', 'html', 'htm', 'css', 'scss', 'sass',
    'java', 'cs', 'go', 'rs', 'swift', 'kt', 'm', 'mm', 'c', 'cpp', 'cc', 'h', 'hpp',
    'py', 'pyw', 'rb', 'pl', 'php', 'sh', 'bash', 'ps1', 'lua', 'dart',
    'json', 'yml', 'yaml', 'toml', 'ini', 'xml',
    'sql', 'pls', 'pck',
    'md', 'markdown', 'rst', 'tex', 'txt',
    'http', 'curl',
    'mpr'
  ];

  async function walk(dirUri, relBase, relRootFromWorkspace) {
    const entries = await vscode.workspace.fs.readDirectory(dirUri);

    for (const [name, type] of entries) {
      const childUri = vscode.Uri.joinPath(dirUri, name);
      const relPath = relBase ? path.posix.join(relBase, name) : name;

      if (type === vscode.FileType.Directory) {
        // hidden folders are tool state (ci/.tmp copies of the workspace, caches), not the KIT:
        // B2B's memory held 5,000 temporary copies, 72% of its chunks
        if (name.startsWith('.')) continue;
        if ([
          '__pycache__',
          '__MACOSX',
          '.pytest_cache',
          '.ruff_cache',
          '.mypy_cache',
          '.next',
          '.turbo',
          '.cache',
          'node_modules',
          'dist',
          'build',
          'out',
          'coverage',
        ].includes(name)) {
          continue;
        }

        await walk(childUri, relPath, relRootFromWorkspace);
        if (items.length >= maxFiles) {
          return;
        }
        continue;
      }

      if (type !== vscode.FileType.File) {
        continue;
      }

      const fileExtension = name.includes('.')
        ? name.split('.').pop().toLowerCase()
        : '';

      if (!CODE_EXTENSIONS.includes(fileExtension)) {
        log("[harperRAG] skip file (not code/text): " + childUri.fsPath);
        continue;
      }

      let data;
      try {
        data = await vscode.workspace.fs.readFile(childUri);
      } catch (err) {
        log(`[harperRAG] skip file (read error): ${childUri.fsPath} -> ${err}`);
        continue;
      }

      if (!data || !data.byteLength) {
        continue;
      }

      const slice = data.byteLength > maxBytes ? data.slice(0, maxBytes) : data;
      const b64 = Buffer.from(slice).toString('base64');
      const relFromRoot = path.posix.join(relRootFromWorkspace, relPath);

      items.push({
        path: relFromRoot,
        bytes_b64: b64,
      });

      if (items.length >= maxFiles) {
        log(`[harperRAG] kit RAG items truncated at ${maxFiles} files for ${reqNorm}`);
        return;
      }
    }
  }

  for (const subroot of candidateSubroots) {
    const absDir = path.join(rootFsPath, 'runs', 'kit', reqNorm, subroot);
    const uri = vscode.Uri.file(absDir);

    try {
      const stat = await vscode.workspace.fs.stat(uri);
      if (!stat || stat.type !== vscode.FileType.Directory) {
        continue;
      }
    } catch {
      continue;
    }

    const relRootFromWorkspace = path.posix.join('runs', 'kit', reqNorm, subroot);
    await walk(uri, '', relRootFromWorkspace);

    if (items.length >= maxFiles) {
      break;
    }
  }

  log(`[harperRAG] collected ${items.length} kit RAG items for ${reqNorm}`);
  return items;
}

const {
  LOCAL_AGENT_COMPLETE_MAX_FILES,
  LOCAL_AGENT_COMPLETE_MAX_TOTAL_CHARS,
  localAgentArtifactPath,
  localAgentArtifactSizeChars,
  pruneLocalAgentCompleteArtifacts,
  shouldSendLocalAgentCompleteArtifact,
} = require('./local-agent-artifacts');

const HARPER_REQUEST_TIMEOUT_MS = 35 * 60 * 1000; // 35 minutes timeout ...maybe too long
async function callHarper(cmd, payload, headers, opts = {}) {
  const url = orchestratorUrl(`/v1/harper/${cmd}`);

  // Optionally pass opts.timeoutMs to override (e.g. "lightweight" commands)
  const timeoutMs =
    typeof opts.timeoutMs === "number"
      ? opts.timeoutMs
      : HARPER_REQUEST_TIMEOUT_MS;

  try {
    log(
      `[harper] calling ${url} cmd=${cmd} timeout=${timeoutMs}ms (custom http)`
    );
    logCurrentTimeStandard("[harper] calling");

    const res = await httpPostJsonLong(
      url,
      {
        headers,
        body: JSON.stringify(payload),
        signal: opts.signal,
      },
      timeoutMs
    );

    logCurrentTimeStandard("[harper] done");

    if (!res.ok) {
      const text = await res.text().catch(() => "<no body>");
      log(
        `[harper] ${cmd} http error ${res.status}: ${text.slice(0, 500)}`
      );
      throw new Error(
        `orchestrator ${cmd} ${res.status}: ${text.slice(0, 200)}`
      );
    }

    const json = await res.json();
    return json;
  } catch (err) {
    if (opts.signal && opts.signal.aborted) {
      // the chat's Cancel: recognisable, not a generic "fetch failed"
      log(`[harper] ${cmd} cancelled by the user`);
      const cancelled = new Error(`Harper ${cmd} cancelled`);
      cancelled.name = 'AbortError';
      throw cancelled;
    }
    logCurrentTimeStandard("[harper] fetch failed");

    const errMsg =
      typeof err?.message === "string" ? err.message : String(err);
    const causeCode =
      err?.cause && typeof err.cause === "object" ? err.cause.code : undefined;

    log(
      `[harper] fetch failed for ${cmd}: ${errMsg}` +
        (causeCode ? ` (cause.code=${causeCode})` : "") +
        (err?.stack ? `\nSTACK: ${err.stack}` : "")
    );

    throw new Error(`Harper ${cmd} fetch failed: ${errMsg}`);
  }
}
async function collectExtendCandidateFileArtifacts(workspaceRootUri, runStartedAtMs = null) {
  const rootFsPath = workspaceRootUri.fsPath || workspaceRootUri.path;
  const docsRoot = path.join(rootFsPath, 'docs', 'harper');
  const baseUri = vscode.Uri.file(docsRoot);
  const out = [];

  async function walk(dirUri, rel = '') {
    let entries;
    try {
      entries = await vscode.workspace.fs.readDirectory(dirUri);
    } catch {
      return;
    }

    for (const [name, type] of entries) {
      if (!name || name === '.DS_Store') continue;

      const childUri = vscode.Uri.joinPath(dirUri, name);
      const relPath = rel ? `${rel}/${name}` : name;

      if (type === vscode.FileType.Directory) {
        if (['.git', 'node_modules', '.venv', '__pycache__', '__MACOSX'].includes(name)) {
          continue;
        }
        await walk(childUri, relPath);
        continue;
      }

      if (type !== vscode.FileType.File) continue;
      // the survey report and the code map /adopt wrote just before the run are CLike's, not the agent's
      if (isClikeOwnHarperFile(`docs/harper/${relPath}`)) continue;

      let data;
      try {
        if (!isFreshLocalAgentArtifact((await vscode.workspace.fs.stat(childUri)).mtime, runStartedAtMs)) continue;
        data = await vscode.workspace.fs.readFile(childUri);
      } catch {
        continue;
      }

      out.push({
        path: `docs/harper/${relPath}`.replace(/\\/g, '/'),
        content: Buffer.from(data).toString('utf8'),
        encoding: 'utf-8',
      });
    }
  }

  await walk(baseUri);
  return out;
}

// Early Harper document phases (idea/spec/plan) produce their canonical Harper
// documents and, under BMAD, the companion documents the package contract
// declares. Collect just those phase-owned outputs so the write policy
// validates real agent output and not pre-existing artifacts or the
// orchestrator package context/prompt files.
const DOCUMENT_PHASE_CANDIDATE_OUTPUTS = {
  idea: ['docs/harper/IDEA.md'],
  spec: ['docs/harper/SPEC.md'],
  plan: ['docs/harper/PLAN.md', 'docs/harper/plan.json'],
};
const DOCUMENT_PHASE_CANDIDATE_DIRS = {
  idea: [],
  spec: [],
  plan: ['docs/harper/lane-guides'],
};

async function collectDocumentPhaseCandidateFileArtifacts(
  workspaceRootUri,
  phase,
  outputContract = null,
  runStartedAtMs = null
) {
  const p = String(phase || '').trim().toLowerCase();
  const rootFsPath = workspaceRootUri.fsPath || workspaceRootUri.path;
  const out = [];

  async function readFileArtifact(relPath) {
    const fileUri = vscode.Uri.file(path.join(rootFsPath, relPath));
    try {
      // Pre-existing files (template, earlier run) are not output of this run.
      if (!isFreshLocalAgentArtifact((await vscode.workspace.fs.stat(fileUri)).mtime, runStartedAtMs)) return;
      const data = await vscode.workspace.fs.readFile(fileUri);
      out.push({
        path: relPath.replace(/\\/g, '/'),
        content: Buffer.from(data).toString('utf8'),
        encoding: 'utf-8',
      });
    } catch {
      // Missing file: the orchestrator/write-policy enforces required outputs.
    }
  }

  const companions = documentPhaseCompanionTargets(outputContract);
  const relPaths = [...(DOCUMENT_PHASE_CANDIDATE_OUTPUTS[p] || [])];
  for (const relPath of companions.files) {
    if (!relPaths.includes(relPath)) relPaths.push(relPath);
  }
  const relDirs = [...(DOCUMENT_PHASE_CANDIDATE_DIRS[p] || []), ...companions.dirs];

  for (const relPath of relPaths) {
    await readFileArtifact(relPath);
  }

  for (const relDir of relDirs) {
    const dirUri = vscode.Uri.file(path.join(rootFsPath, relDir));
    let entries;
    try {
      entries = await vscode.workspace.fs.readDirectory(dirUri);
    } catch {
      continue;
    }
    for (const [name, type] of entries) {
      if (!name || name === '.DS_Store') continue;
      if (type !== vscode.FileType.File) continue;
      const relPath = `${relDir}/${name}`;
      if (!out.some((artifact) => artifact.path === relPath)) await readFileArtifact(relPath);
    }
  }

  return out;
}

// Rejects an invalid agent model before the agent starts (every run, until fixed).
function assertAgentModelValid(executorId, executorConfig) {
  const check = validateAgentModel({
    executorId,
    model: executorConfig?.model,
    codexModels: readCodexModelSlugs(),
  });
  if (check.ok) return;
  const error = new Error(`${check.code}: ${check.message}`);
  error.code = check.code;
  throw error;
}

// Machine-scoped CLike settings (binaries, agent permissions, service URLs, Git commit/push)
// are read by VS Code only from User settings, so an opened project cannot turn them on. A value
// put in the project's .vscode/settings.json is silently ignored: say so, and offer to apply it
// in User settings (an explicit choice of the developer).
const reportedIgnoredSettings = new Set();
function machineScopedSettingKeys() {
  const config = require('./package.json')?.contributes?.configuration;
  const groups = Array.isArray(config) ? config : [config];
  return groups
    .flatMap((g) => Object.entries(g?.properties || {}))
    .filter(([, spec]) => spec?.scope === 'machine')
    .map(([key]) => key.replace(/^clike\./, ''));
}

function reportIgnoredWorkspaceSettings() {
  const c = vscode.workspace.getConfiguration('clike');
  for (const key of machineScopedSettingKeys()) {
    const inspected = c.inspect(key) || {};
    const projectValue = inspected.workspaceFolderValue !== undefined ? inspected.workspaceFolderValue : inspected.workspaceValue;
    if (projectValue === undefined || JSON.stringify(projectValue) === JSON.stringify(inspected.globalValue)) continue;
    const id = `${key}=${JSON.stringify(projectValue)}`;
    if (reportedIgnoredSettings.has(id)) continue;
    reportedIgnoredSettings.add(id);
    const effective = inspected.globalValue !== undefined ? inspected.globalValue : inspected.defaultValue;
    const message =
      `CLike: "clike.${key}": ${JSON.stringify(projectValue)} is in this project's settings, but VS Code applies it ` +
      `only from User settings, so CLike uses ${JSON.stringify(effective)}.`;
    out.appendLine(`[CLike][settings] ${message}`);
    vscode.window.showWarningMessage(message, 'Apply in User settings', 'Open User Settings').then(async (choice) => {
      if (choice === 'Apply in User settings') {
        await c.update(key, projectValue, vscode.ConfigurationTarget.Global);
        vscode.window.showInformationMessage(`CLike: clike.${key} = ${JSON.stringify(projectValue)} set in User settings.`);
      } else if (choice === 'Open User Settings') {
        vscode.commands.executeCommand('workbench.action.openSettings', `clike.${key}`);
      }
    });
  }
}

// Settings check at activation and on change: an invalid model shows an error now,
// not only when the next run fails.
function reportInvalidAgentModels() {
  const c = vscode.workspace.getConfiguration('clike');
  const codexModels = readCodexModelSlugs();
  for (const [executorId, key] of [['gpt_codex', 'localAgent.codex.model'], ['claude_code', 'claudeCode.model']]) {
    const check = validateAgentModel({ executorId, model: c.get(key, ''), codexModels });
    if (check.ok) continue;
    out.appendLine(`[CLike][agent-model] ${check.message}`);
    const fix = check.suggestion ? `Use "${check.suggestion}"` : null;
    vscode.window
      .showErrorMessage(`CLike: ${check.message}`, ...[fix, 'Open Settings'].filter(Boolean))
      .then(async (choice) => {
        if (choice === fix) {
          const inspected = c.inspect(key) || {};
          const target = inspected.workspaceFolderValue !== undefined
            ? vscode.ConfigurationTarget.WorkspaceFolder
            : inspected.workspaceValue !== undefined
              ? vscode.ConfigurationTarget.Workspace
              : vscode.ConfigurationTarget.Global;
          await c.update(key, check.suggestion, target);
        } else if (choice === 'Open Settings') {
          vscode.commands.executeCommand('workbench.action.openSettings', `clike.${key}`);
        }
      });
  }
}

async function executeLocalAgentPackage({
  localAgentPackage,
  phase,
  reqId,
  runId,
  executionPreference,
  settings,
  wsroot,
  headers,
  harperTimeout,
  panel,
  out,
  kitStage = null,
}) {
  const phaseForAgent = String(localAgentPackage?.phase || phase || '').trim().toLowerCase();
  const isFinalize = phaseForAgent === 'finalize';
  const isExtend = phaseForAgent === 'extend';
  const isDocumentPhase = isDocumentLocalAgentPhase(phaseForAgent);
  const reqForAgent = (isFinalize || isExtend || isDocumentPhase)
    ? String(localAgentPackage?.req_id || reqId || 'SOLUTION').trim().toUpperCase()
    : String(localAgentPackage?.req_id || reqId || '').trim().toUpperCase();

  if (!reqForAgent) {
    throw new Error('Invalid local-agent package: missing req_id.');
  }

  const invocation = localAgentPackage.invocation || {};
  const selectedExecutor = normalizeLocalAgentExecutor(
    invocation.executor || localAgentPackage.executor_hint || 'auto'
  );

  if (!selectedExecutor || selectedExecutor === 'auto') {
    throw new Error(
      'Invalid local-agent package: orchestrator did not provide a concrete executor.'
    );
  }

  const executorConfig = getExecutorConfig(selectedExecutor, settings);
  const executorLabel = buildLocalAgentDisplayLabel(selectedExecutor);
  const availability = detectLocalAgentAvailability(settings);
  const executorAvailable = !!availability?.[selectedExecutor]?.available;

  if (!executorConfig || !executorConfig.enabled || !executorAvailable) {
    throw new Error(
      `Orchestrator selected ${selectedExecutor}, but the local actuator cannot execute it. ` +
      `availability=${JSON.stringify(availability?.[selectedExecutor] || {})}`
    );
  }
  assertAgentModelValid(selectedExecutor, executorConfig);

  const invocationArgs = Array.isArray(invocation.args) ? invocation.args : [];
  const promptTransport = String(invocation.prompt_transport || '').trim();
  let launcherArgs = invocationArgs;
  let selectedCodexSandboxMode = '';

  const packageFiles = Array.isArray(localAgentPackage.package_files)
    ? localAgentPackage.package_files
    : [];

  if (packageFiles.length) {
    // CLike-written context files end with a newline (KIT format checks scan the KIT tree)
    await saveGeneratedFiles(packageFiles.map((f) => (
      typeof f?.content === 'string' && f.content && !f.content.endsWith('\n') ? { ...f, content: `${f.content}\n` } : f
    )));
    log(`[harperRun][agent] wrote orchestrator package files=${packageFiles.length} phase=${phaseForAgent}`);
  }

  const promptContent = String(localAgentPackage.prompt_content || '').trim();
  if (!promptContent) {
    throw new Error('Local agent package does not contain prompt_content.');
  }

  if (selectedExecutor === 'gpt_codex') {
    const codexLaunch = buildCodexArgsForLocalAgent({
      argsBeforePrompt: invocationArgs,
      phase: phaseForAgent,
      reqId: reqForAgent,
      configuredSandboxMode: settings.codexSandboxMode || 'auto',
      allowedWriteRoots: localAgentPackage.allowed_write_roots || [],
    });
    launcherArgs = codexLaunch.args;
    selectedCodexSandboxMode = codexLaunch.sandboxMode;

    assertLocalAgentWritePreflight({
      phase: phaseForAgent,
      reqId: reqForAgent,
      executorId: selectedExecutor,
      sandboxMode: selectedCodexSandboxMode,
      allowedWriteRoots: localAgentPackage.allowed_write_roots || [],
    });

    log(
      `[harperRun][agent] codex sandbox=${selectedCodexSandboxMode} ` +
      `source=${codexLaunch.sandboxModeSource} phase=${phaseForAgent} req=${reqForAgent}`
    );
  }

  panel.webview.postMessage({
    type: 'echo',
    message:
      `🤖 ${executorLabel} local ${phaseForAgent.toUpperCase()} package received for ${reqForAgent}. ` +
      `CLike remains the workflow owner; the agent is the local actuator/hardener.`
  });

  // Eval checks the agent can re-run in the real sandbox during this run (repair, finalize).
  const evalCheck = localAgentPackage.eval_check && localAgentPackage.eval_check.profile ? localAgentPackage.eval_check : null;
  let evalCheckBridge = null;
  if (evalCheck) {
    evalCheckBridge = startEvalCheckBridge({
      workspaceRoot: toFsPath(wsroot),
      maxRuns: Number(evalCheck.max_runs || 8),
      runChecks: (checks) => postEvalChecks(evalCheck.profile, wsroot, reqForAgent, checks),
      log,
      targets: Array.isArray(evalCheck.targets) ? evalCheck.targets : [],
      // a repair's changes to existing (locked) tests are governed after the run: the agent is told
      ...(phaseForAgent === 'kit' && reqForAgent ? { testRoot: `runs/kit/${reqForAgent}/test` } : {}),
    });
    launcherArgs = agentArgsForEvalCheck(selectedExecutor, launcherArgs);
    panel.webview.postMessage({
      type: 'echo',
      message: `🔁 ${executorLabel} can re-run the failed checks in the CLike eval sandbox during this repair (up to ${evalCheck.max_runs || 8} runs).`,
    });
  }

  const agentStartedAt = Date.now();
  let agentResult;
  let timedOut = null;
  // after a timeout, an output check failure says so and names the setting to raise
  const unlessTimedOut = (message) => (timedOut
    ? `${executorLabel} timed out after ${timedOut.timeoutMinutes} minute(s) before finishing (${message}). ` +
      `The files it wrote are kept; raise ${timeoutSettingKey(selectedExecutor)} and re-run.`
    : message);
  try {
    agentResult = await runLocalAgentSync({
      workspaceRootUri: wsroot,
      prompt: promptContent,
      executorId: selectedExecutor,
      command: executorConfig.command,
      // clike.claudeCode.model / clike.localAgent.codex.model apply to Harper phases too
      argsBeforePrompt: withIsolatedMcp(selectedExecutor, withMachineReadableOutput(selectedExecutor, [
        ...launcherArgs,
        ...(launcherArgs.includes('--model') ? [] : buildLocalAgentModelArgs(selectedExecutor, executorConfig)),
      ])),
      promptTransport,
      // the time spent waiting for eval checks in the sandbox does not eat the agent's own budget
      timeoutMinutes: agentTimeoutMinutes(Number(invocation.timeout_seconds || 1800) / 60, evalCheck),
      out,
      // what the agent does while it works (tools, files, commands): the run card's "now" line
      onStdoutLine: (() => {
        const parser = createAgentStreamParser(normalizeLocalAgentExecutor(selectedExecutor));
        return (line) => {
          for (const ev of parser.feed(line)) {
            if (ev.kind === 'tool') runFeedLive(`🤖 ${executorLabel}: ${ev.label}`);
            else if (ev.kind === 'delta' && String(ev.text || '').trim()) {
              runFeedLive(`🤖 ${executorLabel}: ${String(ev.text).trim().split('\n').pop().slice(0, 160)}`);
            }
          }
        };
      })(),
    });
  } catch (err) {
    // A timeout is a time budget, not a verdict: what the agent wrote goes through the
    // same output validation, orchestrator normalization and eval as a finished run.
    if (!err || err.code !== 'LOCAL_AGENT_TIMEOUT') throw err;
    timedOut = err;
    agentResult = { exitCode: 124, stdout: err.stdout || '', stderr: err.stderr || '' };
    log(`[harperRun][agent] ${selectedExecutor} timed out after ${err.timeoutMinutes} min; checking the outputs it wrote`);
    panel.webview.postMessage({
      type: 'echo',
      message: `⏱️ ${executorLabel} timed out after ${err.timeoutMinutes} minute(s). CLike checks the files it wrote: ` +
        `if the required outputs are there the run continues, otherwise raise ${timeoutSettingKey(selectedExecutor)} and re-run.`,
    });
  } finally {
    if (evalCheckBridge) {
      log(`[evalCheck] agent used ${evalCheckBridge.runs} eval-check run(s)`);
      evalCheckBridge.stop();
    }
  }
  // a stream-json run: from here on its stdout is the result envelope, as before the stream
  agentResult.stdout = normalizeAgentStdout(selectedExecutor, agentResult.stdout);
  // Cancel stopped the agent: nothing it left half-written goes to the orchestrator
  if (harperCancelled()) throw new Error(`${executorLabel} run cancelled by user.`);
  // Usage/cost/model of the run; downstream code keeps reading plain text.
  const agentRun = parseLocalAgentRun(selectedExecutor, agentResult.stdout, {
    durationMs: Date.now() - agentStartedAt,
    fallbackModel: executorConfig.model || '',
  });
  const rawAgentStdout = agentResult.stdout || '';
  agentResult.stdout = agentRun.text;
  log(`[harperRun][agent][telemetry] ${JSON.stringify(agentRun.telemetry)}`);

  const candidateFiles = (isFinalize)
    ? await collectFinalizeCandidateFiles(wsroot, { baseline: finalizeVerify.readDirtyBaseline(toFsPath(wsroot)) })
    : (isExtend || isDocumentPhase)
      ? []
      : await collectReqCandidateFiles(wsroot, reqForAgent);

  const candidateArtifacts = isFinalize
    ? await collectFinalizeCandidateFileArtifacts(wsroot, { baseline: finalizeVerify.readDirtyBaseline(toFsPath(wsroot)) })
    : isDocumentPhase
      ? await collectDocumentPhaseCandidateFileArtifacts(
        wsroot,
        phaseForAgent,
        localAgentPackage.active_output_contract || null,
        agentStartedAt
      )
      : isExtend
        ? await collectExtendCandidateFileArtifacts(wsroot, agentStartedAt)
        : await collectReqCandidateFileArtifacts(wsroot, reqForAgent);

  log(
    `[harperRun][agent] completed executor=${selectedExecutor} ` +
    `phase=${phaseForAgent} req=${reqForAgent} files=${candidateFiles.length} artifacts=${candidateArtifacts.length}`
  );

  if (!candidateArtifacts.length) {
    if (timedOut) throw timedOut;
    // The agent may have exited 0 yet been blocked (auth/login) or unable to read
    // a required source. Surface that precise cause instead of a generic empty
    // result, and never treat a blocked run as successful artifact generation.
    const blocked = classifyBlockedLocalAgentOutput({
      stdout: agentResult.stdout || '',
      stderr: agentResult.stderr || '',
    });
    if (blocked) {
      log(
        `[harperRun][agent] local-agent blocked phase=${phaseForAgent} ` +
        `code=${blocked.code} evidence=${JSON.stringify(blocked.evidence)}`
      );
      const blockedError = new Error(`${blocked.code}: ${blocked.message}`);
      blockedError.code = blocked.code;
      throw blockedError;
    }

    const failedRun = describeFailedLocalAgentRun({
      exitCode: agentResult.exitCode,
      stderr: agentResult.stderr || '',
      stdout: rawAgentStdout,
      executorLabel,
    });
    if (failedRun) {
      log(`[harperRun][agent] local-agent failed phase=${phaseForAgent} ${failedRun.message}`);
      const failedError = new Error(`${failedRun.code}: ${failedRun.message}`);
      failedError.code = failedRun.code;
      throw failedError;
    }

    const expectedRoot = isFinalize
      ? 'README.md, docs/harper, scripts, src, or runtime manifests'
      : (isExtend || isDocumentPhase)
        ? 'docs/harper/'
        : `runs/kit/${reqForAgent}/`;
    throw new Error(
      `${executorLabel} completed without returning readable candidate artifacts under ${expectedRoot}`
    );
  }

  // Files written, but the agent exited with an error (the model at capacity, a rate limit, a
  // crash): an incomplete result is never the phase's output, nor committed.
  const interrupted = timedOut ? null : describeInterruptedLocalAgentRun({
    exitCode: agentResult.exitCode,
    stderr: agentResult.stderr || '',
    stdout: rawAgentStdout,
    executorLabel,
    isError: agentRun.isError === true,
  });
  if (interrupted) {
    log(`[harperRun][agent] local-agent interrupted phase=${phaseForAgent} ${interrupted.message}`);
    const interruptedError = new Error(`${interrupted.code}: ${interrupted.message}`);
    interruptedError.code = interrupted.code;
    throw interruptedError;
  }

  const completeArtifacts = pruneLocalAgentCompleteArtifacts(
    candidateArtifacts,
    phaseForAgent,
    reqForAgent
  );

  log(
    `[harperRun][agent] local-agent/complete artifact pruning ` +
    `phase=${phaseForAgent} req=${reqForAgent} ` +
    `original=${completeArtifacts.original_count} ` +
    `filtered=${completeArtifacts.filtered_count} ` +
    `kept=${completeArtifacts.kept_count} ` +
    `chars=${completeArtifacts.total_chars} ` +
    `truncated=${completeArtifacts.truncated}`
  );
  if (completeArtifacts.truncated) {
    log(`[harperRun][agent] artifacts over the size budget, not sent: ${completeArtifacts.dropped.slice(0, 20).join(', ')}`);
  }

  if (!completeArtifacts.files.length) {
    throw new Error(unlessTimedOut(
      `${executorLabel} completed but no safe local-agent/complete artifacts remained after filtering. ` +
      `original=${completeArtifacts.original_count}`
    ));
  }

  if (['kit', 'eval', 'finalize', 'idea', 'spec', 'plan', 'extend'].includes(phaseForAgent)) {
    try {
      validateLocalAgentRequiredOutputs({
        phase: phaseForAgent,
        reqId: reqForAgent,
        artifacts: completeArtifacts.files,
        kitStage,
        outputContract: isDocumentPhase ? (localAgentPackage.active_output_contract || null) : null,
        allowedWriteRoots: Array.isArray(localAgentPackage.allowed_write_roots) ? localAgentPackage.allowed_write_roots : [],
        forbiddenPaths: Array.isArray(localAgentPackage.forbidden_paths) ? localAgentPackage.forbidden_paths : [],
      });
    } catch (err) {
      if (timedOut) err.message = unlessTimedOut(err.message);
      throw err;
    }
  }

  const completeBody = {
    phase: phaseForAgent,
    req_id: reqForAgent,
    runId,
    executionPreference,
    localAgentExecutor: selectedExecutor,
    // The orchestrator re-derives the BMAD companion paths from its manifest.
    methodology: localAgentPackage.active_output_contract?.methodology || null,
    methodology_agent: localAgentPackage.active_output_contract?.agent || null,
    allowed_write_roots: Array.isArray(localAgentPackage.allowed_write_roots)
      ? localAgentPackage.allowed_write_roots
      : [],
    forbidden_paths: Array.isArray(localAgentPackage.forbidden_paths)
      ? localAgentPackage.forbidden_paths
      : [],
    infra_profile: localAgentPackage.infra_profile || null,
    runtime_service_profile: localAgentPackage.runtime_service_profile || null,
    cloud_provisioning_profile: localAgentPackage.cloud_provisioning_profile || null,
    available_capabilities: localAgentPackage.available_capabilities || null,
    capability_metadata: localAgentPackage.capability_metadata || null,
    exit_code: agentResult.exitCode,
    stdout: agentResult.stdout || '',
    stderr: agentResult.stderr || '',
    files: completeArtifacts.files,
    // Finalize reuses the promoted code: the unchanged sources are the evidence of an existing
    // database/auth boundary the agent did not need to return.
    existing_source_files: phaseForAgent === 'finalize'
      ? collectExistingSourceEvidence(toFsPath(wsroot), (completeArtifacts.files || []).map((f) => f.path))
      : undefined,
    project_id: getProjectId(),
    project_name: getProjectNameFromWorkspace() || null,
    telemetry: agentRun.telemetry,
    artifact_pruning: {
      original_count: completeArtifacts.original_count,
      filtered_count: completeArtifacts.filtered_count,
      kept_count: completeArtifacts.kept_count,
      total_chars: completeArtifacts.total_chars,
      truncated: completeArtifacts.truncated,
    },
  };

  const completeGateway = await callHarper('local-agent/complete', completeBody, headers, {
    timeoutMs: 1000 * 60 * harperTimeout,
    signal: harperSignal(),
  });

  const completeOut = completeGateway.out;
  if (Array.isArray(completeOut?.format_fixes) && completeOut.format_fixes.length) {
    // safe mechanical lint fixes (e.g. import order) computed by the orchestrator, written before
    // the first eval locks the acceptance surface
    await saveGeneratedFiles(completeOut.format_fixes, { phase: phaseForAgent, runId });
    log(`[harperRun][agent] applied ${completeOut.format_fixes.length} format fix(es)`);
  }
  if (completeOut && !completeOut.telemetry) completeOut.telemetry = agentRun.telemetry;
  if (completeOut && !completeOut.usage) completeOut.usage = agentRun.telemetry.usage;

  if (!completeOut?.ok) {
    throw new Error(unlessTimedOut(
      `Orchestrator rejected local-agent result: ${(completeOut?.errors || []).join(' | ') || 'unknown error'}`
    ));
  }

  panel.webview.postMessage({
    type: 'echo',
    message: timedOut
      ? `✅ ${executorLabel} local ${phaseForAgent.toUpperCase()} normalized by orchestrator for ${reqForAgent} ` +
        `(the agent timed out, but its required outputs were complete).`
      : `✅ ${executorLabel} local ${phaseForAgent.toUpperCase()} normalized by orchestrator for ${reqForAgent}.`
  });

  return completeOut;
}


function cfgChat() {
  const c = vscode.workspace.getConfiguration();
  return {
    dir: c.get('clike.chat.persistDir', '.clike/sessions'),
    maxMem: c.get('clike.chat.maxInMemoryMessages', 50),
    autoWrite: c.get('clike.chat.autoWriteGeneratedFiles', true),
    neverSendSourceToCloud: c.get('clike.chat.never_send_source_to_cloud', true)
  };
}

// Invocation args for the standalone free/coding local-agent flows. Free (Q&A)
// runs read-only (no file edits); coding lets the agent write under the
// orchestrator-provided output_root.

// Badge shown next to a local-agent answer (mirrors how the cloud path shows
// the model name). The user requested 'agent-claude' / 'agent-codex'.
function localAgentBadge(executorId) {
  return normalizeLocalAgentExecutor(executorId) === 'gpt_codex' ? 'agent-codex' : 'agent-claude';
}

// List the files the agent generated under <wsroot>/<relRoot>. The files are
// already on disk (the agent wrote them), so we only need their relative paths
// for the Files tab — no content, no base64 image dumps in the chat bubble.
async function collectGeneratedFilePaths(wsrootUri, relRoot) {
  const segments = String(relRoot || '').split('/').filter(Boolean);
  if (!segments.length) return [];
  const rootUri = vscode.Uri.joinPath(wsrootUri, ...segments);
  const paths = [];

  async function walk(dirUri, relPrefix) {
    let entries;
    try {
      entries = await vscode.workspace.fs.readDirectory(dirUri);
    } catch {
      return;
    }
    for (const [name, ftype] of entries) {
      const childRel = relPrefix ? `${relPrefix}/${name}` : name;
      const childUri = vscode.Uri.joinPath(dirUri, name);
      if (ftype === vscode.FileType.Directory) {
        await walk(childUri, childRel);
      } else if (ftype === vscode.FileType.File) {
        paths.push(`${relRoot}/${childRel}`);
      }
    }
  }

  await walk(rootUri, '');
  return paths;
}

// Coding-mode approval asked to the developer: 'allow' | 'allowAll' | 'deny' (closing = deny).
async function askAgentChatApproval({ executorLabel, kind, summary, paths }) {
  const what = kind === 'edit' ? 'edit files' : kind === 'command' ? 'run a command' : 'use a tool';
  const detail = [String(summary || ''), ...(paths || []).map((p) => `• ${p}`)].filter(Boolean).join('\n');
  const choice = await vscode.window.showWarningMessage(
    `${executorLabel} wants to ${what}`,
    { modal: true, detail },
    'Allow',
    'Allow all this turn',
    'Deny',
  );
  if (choice === 'Allow') return 'allow';
  if (choice === 'Allow all this turn') return 'allowAll';
  return 'deny';
}

// Run the free/coding local-agent package returned by the orchestrator.
// Returns { mode, badge, answer?, synthesis, stdout, files? }.
async function runLocalChatAgent({ pkg, executorId, settings, wsrootUri, out, session = null, onEvent = null, onSpawn = null, askApproval = null }) {
  const mode = String(pkg.mode || 'free').toLowerCase();
  const executorConfig = getExecutorConfig(executorId, settings);
  const executorLabel = buildLocalAgentDisplayLabel(executorId);
  const badge = localAgentBadge(executorId);
  const prompt = String(pkg.prompt || '').trim();
  if (!prompt) throw new Error('Local execution package is missing a prompt.');
  assertAgentModelValid(executorId, executorConfig);

  const timeoutMinutes = executorConfig.timeoutMinutes;
  const parser = createAgentStreamParser(executorId);
  let streamResult = null;
  let streamError = '';
  let sessionId = (session && session.id) || '';
  const handleEvent = (event) => {
    if (event.kind === 'session') sessionId = event.id;
    if (event.kind === 'result') streamResult = event;
    if (event.kind === 'error') streamError = event.text;
    if (typeof onEvent === 'function') onEvent(event);
  };

  // With approvals each edit/command of the agent is asked (agent-approvals.js).
  // Coding and Harper write under pkg.output_root; Free stays read-only.
  const writable = (mode === 'coding' || mode === 'harper') && !!pkg.output_root;
  const approvals = writable && settings.agentChatApprovals === 'ask' && typeof askApproval === 'function';
  let approvalServer = null;
  let codexTurn = null;
  let argsBeforePrompt = buildAgentChatArgs({
    executorId,
    mode,
    executorConfig,
    modelArgs: buildLocalAgentModelArgs(executorId, executorConfig),
    session,
    approvals,
  });
  if (approvals) {
    const decide = createApprovalGate({
      ask: (request) => askApproval({ ...request, executorLabel }),
      workspaceRoot: wsrootUri.fsPath,
      writeRoot: path.join(wsrootUri.fsPath, String(pkg.output_root || 'generated')),
      onEvent: handleEvent,
    });
    if (executorId === 'claude_code') {
      approvalServer = await startClaudeApprovalServer(decide);
      argsBeforePrompt = [...argsBeforePrompt, ...approvalServer.args];
    } else {
      codexTurn = createCodexAppServerTurn({
        cwd: wsrootUri.fsPath,
        prompt,
        session,
        model: String(executorConfig.model || '').trim(),
        sandbox: 'workspace-write',
        approvalPolicy: 'untrusted',
        decide,
        onEvent: handleEvent,
        clientVersion: String(require('./package.json').version || '1'),
      });
      argsBeforePrompt = ['app-server'];
    }
  }

  let agentChild = null;
  let agentResult;
  try {
    const running = runLocalAgentSync({
      workspaceRootUri: wsrootUri,
      prompt,
      executorId,
      command: executorConfig.command,
      argsBeforePrompt,
      timeoutMinutes,
      out,
      onSpawn: (child) => {
        agentChild = child;
        if (typeof onSpawn === 'function') onSpawn(child);
      },
      onStdin: codexTurn ? (stdin) => codexTurn.attach(stdin) : null,
      onStdoutLine: codexTurn
        ? (line) => codexTurn.feed(line)
        : (line) => { for (const event of parser.feed(line)) handleEvent(event); },
    });
    if (codexTurn) {
      // app-server keeps running after the turn: stop it once the turn is over
      codexTurn.done.then(() => setTimeout(() => {
        if (agentChild && agentChild.exitCode === null) terminateProcessTree(agentChild);
      }, 2000));
    }
    agentResult = await running;
    if (codexTurn) codexTurn.closed(agentResult.exitCode);
  } finally {
    if (approvalServer) await approvalServer.close();
  }

  const stdout = agentResult.stdout || '';
  const stderr = agentResult.stderr || '';

  // Determine the model actually used. Claude reports it in the JSON envelope
  // (authoritative, also reflects any fallback model); Codex has no machine
  // -readable model list, so the model used is the one we pinned via --model.
  const usedModel = String(
    (streamResult && streamResult.model) || (executorConfig && executorConfig.model) || ''
  ).trim();
  if (out && typeof out.appendLine === 'function' && usedModel) {
    out.appendLine(`[CLike] [local-agent:${executorId}] model_used=${usedModel}`);
  }

  if (mode === 'coding') {
    const paths = await collectGeneratedFilePaths(wsrootUri, pkg.output_root);
    if (!paths.length) {
      const blocked = classifyBlockedLocalAgentOutput({ stdout, stderr });
      if (blocked) throw new Error(`${blocked.code}: ${blocked.message}`);
      throw new Error(`${executorLabel} completed without generating any files under ${pkg.output_root}/.`);
    }
    const synthesis =
      `Generated ${paths.length} file(s) under ${pkg.output_root}/:\n` +
      paths.map(p => '- ' + p).join('\n');
    return { mode, badge, model: usedModel, synthesis, stdout, sessionId, files: paths.map(p => ({ path: p })) };
  }

  // free (Q&A) and harper: the answer text; harper also lists the files it wrote.
  const answer = String((streamResult && streamResult.text) || parser.text() || '').trim();
  const harperFiles = mode === 'harper' && pkg.output_root ? await collectGeneratedFilePaths(wsrootUri, pkg.output_root) : [];
  if (mode === 'harper' && (answer || harperFiles.length)) {
    const where = harperFiles.length ? `, wrote ${harperFiles.length} file(s) under ${pkg.output_root}/` : '';
    const synthesis = `${executorLabel} answered locally${usedModel ? ` using ${usedModel}` : ''}${where} (exit=${agentResult.exitCode}).`;
    return {
      mode, badge, model: usedModel, answer: answer || synthesis, synthesis, stdout, sessionId,
      files: harperFiles.map(p => ({ path: p })),
    };
  }
  if (!answer) {
    const blocked = classifyBlockedLocalAgentOutput({ stdout, stderr });
    if (blocked) throw new Error(`${blocked.code}: ${blocked.message}`);
    throw new Error(`${executorLabel} returned no answer (exit=${agentResult.exitCode})${streamError ? ': ' + streamError : ''}.`);
  }
  const modelSuffix = usedModel ? ` using ${usedModel}` : '';
  const synthesis = `${executorLabel} answered locally${modelSuffix} (read-only, exit=${agentResult.exitCode}).`;
  return { mode, badge, model: usedModel, answer, synthesis, stdout, sessionId };
}

function effectiveHistoryScope(context) {
  try {
    const ui = context.workspaceState.get('clike.uiState') || {};
    return (ui.historyScope === 'allModels') ? 'allModels' : 'singleModel';
  } catch {
    return 'singleModel';
  }
}

function sessionsDirUri() {
  const root = getWorkspaceRoot();
  return vscode.Uri.joinPath(root, cfgChat().dir.replace(/^\.?\//,''));
}


async function ensureSessionsDir() {
  const dir = sessionsDirUri();
  try { await vscode.workspace.fs.createDirectory(dir); } catch {}
  return dir;
}
// ---------- Session & FS helpers ----------
function sessionFileUri(mode) {
  const safe = String(mode || 'free').replace(/[^\w.-]/g, '_');
  return vscode.Uri.joinPath(sessionsDirUri(), `${safe}.jsonl`);
}

async function appendSessionJSONL(mode, entry) {
  await ensureSessionsDir();
  const uri = sessionFileUri(mode);
  const line = JSON.stringify({ ts: Date.now(), mode, ...entry }) + '\n';
  const enc = Buffer.from(line, 'utf8');
  try {
    await vscode.workspace.fs.stat(uri);
    const old = await vscode.workspace.fs.readFile(uri);
    await vscode.workspace.fs.writeFile(uri, Buffer.concat([old, enc]));
  } catch {
    await vscode.workspace.fs.writeFile(uri, enc);
  }
}

async function loadSession(mode, limit = 200) {
  try {
    const buf = await vscode.workspace.fs.readFile(sessionFileUri(mode));
    const lines = buf.toString('utf8').split(/\r?\n/).filter(Boolean);
    const last = lines.slice(-limit).map(l => JSON.parse(l));
    return last.map(e => ({
      role: e.role,
      content: e.content,
      model: e.model,
      agentModel: e.agentModel || '',
      attachments: e.attachments || [],
      kind: e.kind || 'text',
      ts: e.ts || Date.now()
    }));
 } catch {
    return [];  
  }
}

async function loadSessionFiltered(mode, model, limit = 200) {
  const all = await loadSessionFilteredHarper(mode, limit);
  return all.filter(e => !model || (e.model || 'auto') === model)
}

async function loadSessionFilteredV2(mode, model, limit = 200) {
  const all = await loadSession(mode, limit);
  return all.filter(e => !model || (e.model || 'auto') === model)
}


async function loadSessionFilteredHarper(mode, limit = 200) {
  const all = await loadSession(mode, limit);

  // Prefixes for Harper commands, both "graphical" and textual
  const EXECUTION_PREFIXES = [
    '▶ IDEA',
    '▶ SPEC',
    '▶ PLAN',
    '▶ KIT',
    '▶ EVAL',
    '▶ GATE',
    '▶ FINALIZE',
    '✔',      // /gate outcome
    '🧪',     // /eval outcome
    '/idea',
    '/spec',
    '/plan',
    '/kit',
    '/eval',
    '/gate',
    '/finalize',
  ];

  function isExecutionCommandMessage(content) {
    if (!content || typeof content !== 'string') {
      return false;
    }

    // Take only the first non-empty line
    const firstLine = content
      .split('\n')
      .map((l) => l.trimStart())
      .find((l) => l.length > 0);

    if (!firstLine) {
      return false;
    }

    const firstLineLower = firstLine.toLowerCase();

    return EXECUTION_PREFIXES.some((prefix) => {
      const p = prefix.toLowerCase();
      // Simple comparison: the first line must start with the prefix
      return firstLineLower.startsWith(p);
    });
  }

  return all.filter((e) => {

    // 2. Exclude system messages
    if (e.role === 'system') {
      return false;
    }

    // 3. Keep only user/assistant
    if (e.role !== 'user' && e.role !== 'assistant') {
      return false;
    }

    // 4. Drop command messages
    if (isExecutionCommandMessage(e.content)) {
      return false;
    }
    
    return true;


  });
}


// Delete the **first** occurrence matching role+content+model in the session file
async function deleteSessionEntry(mode, role, content, model) {
  try {
    const uri = sessionFileUri(mode);
    const buf = await vscode.workspace.fs.readFile(uri);
    const lines = buf.toString('utf8').split(/\r?\n/).filter(Boolean);

    let deleted = false;
    const kept = [];

    for (const line of lines) {
      let entry;
      try {
        entry = JSON.parse(line);
      } catch {
        // invalid line → keep it
        kept.push(line);
        continue;
      }

      if (
        !deleted &&
        String(entry.role || '') === String(role || '') &&
        String(entry.content || '') === String(content || '') &&
        (!model || String(entry.model || '') === String(model || ''))
      ) {
        // skip ONLY the first match
        deleted = true;
        continue;
      }

      kept.push(line);
    }

    const out = kept.length ? kept.join('\n') + '\n' : '';
    await vscode.workspace.fs.writeFile(uri, Buffer.from(out, 'utf8'));
    return deleted;
  } catch (e) {
    log(`[session] deleteSessionEntry failed: ${e?.message || e}`);
    return false;
  }
}

async function pruneSessionByModel(mode, model) {
  // keep EVERYTHING except the current model's lines
  try {
    const uri = sessionFileUri(mode);
    const buf = await vscode.workspace.fs.readFile(uri);
    const lines = buf.toString('utf8').split(/\r?\n/).filter(Boolean);
    const kept = lines.filter(l => {
      try {
        const j = JSON.parse(l);
        return (j.model || 'auto') !== model;
      } catch { return true; }
    });
    const out = kept.length ? (kept.join('\n') + '\n') : '';
    await vscode.workspace.fs.writeFile(uri, Buffer.from(out, 'utf8'));
  } catch { }
}


async function clearSession(mode) {
  try { await vscode.workspace.fs.delete(sessionFileUri(mode)); } catch {}
}

async function saveGeneratedFiles(files, opts = {}) {
  if (!Array.isArray(files) || !files.length) return [];
  const root = getWorkspaceRoot();
  const written = [];
  for (const f of files) {
    // Accept text (content) or binary (content_base64) payloads. Binary
    // attachments are materialized as base64 and must not be silently dropped.
    if (!f || !f.path || (typeof f.content !== 'string' && typeof f.content_base64 !== 'string')) continue;
    // Paths come from the orchestrator / LLM / local agent: never write outside the workspace.
    let relativePath;
    try {
      relativePath = safeRelativePath(f.path);
    } catch (err) {
      log(`[harperWriteGuard] unsafe_path_rejected path=${JSON.stringify(String(f.path))} reason=${err.message}`);
      try { vscode.window.showWarningMessage(`CLike refused to write a file outside the workspace: ${String(f.path)}`); } catch {}
      continue;
    }
    const validation = (typeof f.content === 'string')
      ? validateCanonicalHarperArtifact(relativePath, f.content)
      : null;
    if (validation && !validation.ok) {
      const rejectedPath = rejectedHarperArtifactPath({
        phase: opts.phase,
        runId: opts.runId,
        filePath: relativePath,
      });
      const rejectedUri = safeWorkspaceUri(root, rejectedPath);
      const rejectedFolder = vscode.Uri.joinPath(rejectedUri, '..');
      try { await vscode.workspace.fs.createDirectory(rejectedFolder); } catch {}
      await vscode.workspace.fs.writeFile(rejectedUri, Buffer.from(f.content, 'utf8'));
      const message = `CLike rejected malformed canonical artifact ${relativePath}; kept existing file and saved rejected content to ${rejectedPath}.`;
      log(`[harperWriteGuard] invalid_canonical_artifact path=${relativePath} checks=${(validation.failed_checks || []).join(',')}`);
      try { vscode.window.showWarningMessage(message); } catch {}
      continue;
    }
    const uri = safeWorkspaceUri(root, relativePath);
    const folder = vscode.Uri.joinPath(uri, '..');
    try { await vscode.workspace.fs.createDirectory(folder); } catch {}
    if (typeof f.content === 'string') {
      await vscode.workspace.fs.writeFile(uri, Buffer.from(f.content, 'utf8'));
      written.push(uri.fsPath);
    } else if (typeof f.content_base64 === 'string') {
      await vscode.workspace.fs.writeFile(uri, Buffer.from(f.content_base64, 'base64'));
      written.push(uri.fsPath);
    }
  }
  return written;
}


function isSaneReplacement(originalText, patchedText) {
  try {
    const origLen = (originalText || '').length;
    const patLen  = (patchedText  || '').length;
    if (origLen >= 100 && patLen <= Math.max(60, Math.floor(origLen * 0.2))) return false; // shrink >80%
    if (patLen <= 5) return false; // practically empty
    return true;
  } catch { return true; }
}

function diffHeaderContainsPath(diffStr, filePath) {
  try {
    const short = (filePath || '').split(/[\\/]/).pop();
    return new RegExp(`\\+\\+\\+\\s+.*${short}`).test(diffStr) || new RegExp(`---\\s+.*${short}`).test(diffStr);
  } catch { return true; }
}

// ---- Helpers for apply & path context ----
function buildApplyCtx(op) {
  const editor = vscode.window.activeTextEditor;
  if (!editor) throw new Error('No active editor');
  const doc = editor.document;
  const selectionText = editor.selection && !editor.selection.isEmpty
    ? doc.getText(editor.selection)
    : '';
  const uriStr = __clike_lastTargetUriCache || doc.uri.toString();

  return {
    targetUri: vscode.Uri.parse(uriStr),
    intent: mapOpToIntent(op),
    lang: doc.languageId || 'plaintext',
    selectionText
  };
}

// Server-provided target paths (e.g. apply.path): relative, or absolute only inside the workspace.
function resolveToWorkspaceUri(p) {
  if (!p) return null;
  const ws = vscode.workspace.workspaceFolders && vscode.workspace.workspaceFolders[0];
  if (!ws) return null;
  try {
    return resolveInsideWorkspace(ws.uri, p);
  } catch (err) {
    log(`[apply] unsafe_target_path_rejected path=${JSON.stringify(String(p))} reason=${err.message}`);
    return null;
  }
}

function mapOpToIntent(op) {
  switch (op) {
    case 'add_docstring': return 'docstring';
    case 'generate_tests': return 'tests';
    case 'fix_errors': return 'fix_errors';
    case 'refactor': return 'refactor';
    default: return op || 'refactor';
  }
}

// === DRY helpers ===
function rememberTargetUri(context) {
  const editor = getActiveEditorOrThrow();
  const uriStr = editor.document.uri.toString();
  __clike_lastTargetUriCache = uriStr; // always cache

  try {
    if (context && context.workspaceState && typeof context.workspaceState.update === 'function') {
      context.workspaceState.update('clike.lastTargetUri', uriStr);
    }
  } catch (_) {}
  return uriStr;
}


// Build the payload matching the orchestrator-side signatures (text = whole file, selection = selection)
function mapDocContextToPayload(ctx, op, useContent = false) {
  
  const prompt = (ctx.selection && ctx.selection.trim()) ? ctx.selection.trim() : '';
  const payload = {
    op,
    intent: mapOpToIntent(op),
    path: ctx.file_path,
    text: ctx.text,                  // whole file (required by the orchestrator)
    language: ctx.language,
    selection: ctx.selection || '',  // current selection (if any)
    prompt,
    fallback: false
  };
  if (useContent) payload.content = ctx.text;
  return payload;
}


async function runApplyFromClipboard(context, label, { treatAsDiff = true } = {}) {
  const editor = getActiveEditorOrThrow();
  await rememberTargetUri(context);
  const input = await readSelectionOrClipboard(editor);
  if (!input || !input.trim()) throw new Error('Empty selection/clipboard.');
  const content = treatAsDiff ? input : extractCodeBlockOrPlain(input);
  await hardenedApplyFromString(context, content, { withPreview: true });
  vscode.window.setStatusBarMessage(`Clike: applied ${label}`, 3000);
}

/** Run a complete write action (build payload → POST → apply) */
async function runWriteCommand(context, op, label, { useContent = false } = {}) {
  await rememberTargetUri(context);

  const ctxDoc = currentDocContext();
  const payload = mapDocContextToPayload(ctxDoc, op, useContent);

  const { routes } = cfg();
  const resp = await postOrchestrator(routes.orchestrator.code, payload);

  if (!resp || !resp.ok) {
    const msg = (resp && resp.json && (resp.json.detail || resp.json.message)) || `HTTP ${resp && resp.status}`;
    return vscode.window.handleGaterrorMessage(`Clike ${label}: ${msg}`);
  }  
  vscode.window.setStatusBarMessage(`Clike ✓ ${op} applied`, 3000);
  vscode.window.showInformationMessage(`Clike: ${op} completato (${resp.json.source || 'embedded'})`);


  const applyCtx = buildApplyCtx(op);
  return applyOrchestratorResult(context, resp.json || {}, applyCtx);
}

// runtime feedback on AI settings
vscode.workspace.onDidChangeConfiguration((e) => {
  if (e.affectsConfiguration('clike.localAgent.codex.model') || e.affectsConfiguration('clike.claudeCode.model')) {
    reportInvalidAgentModels();
  }
  if (e.affectsConfiguration('clike')) reportIgnoredWorkspaceSettings();
  if (e.affectsConfiguration('clike.useAi') ||
      e.affectsConfiguration('clike.useAi.docstring') ||
      e.affectsConfiguration('clike.useAi.refactor')  ||
      e.affectsConfiguration('clike.useAi.tests')     ||
      e.affectsConfiguration('clike.useAi.fixErrors')) {
    const { useAiDocstring, useAiRefactor, useAiTests, useAiFixErrors } = cfg();
    out.appendLine(`[cfg] useAi: doc=${useAiDocstring} ref=${useAiRefactor} tests=${useAiTests} fix=${useAiFixErrors}`);
    vscode.window.setStatusBarMessage(`Clike settings updated (AI toggles)`, 2500);
  }
});


function documentInfoFromEditor(editor) {
  const doc = editor.document;
  return { uriStr: doc.uri.toString(), language: doc.languageId || 'plaintext' };
}


// The value the user set (any scope), or undefined when only the package default applies.
function explicitSetting(c, key) {
  const i = typeof c.inspect === 'function' ? c.inspect(key) : null;
  if (!i) return c.get(key);
  return i.workspaceFolderValue ?? i.workspaceValue ?? i.globalValue;
}

function cfg() {
  const c = vscode.workspace.getConfiguration('clike');

  const routes = c.get('routes', {
    orchestrator: {
      code: '/agent/code',
      ragIndex: '/v1/rag/index',
      ragReIndex: '/v1/rag/reindex',
      ragSearch: '/v1/rag/search',
      health: '/health',
      chat: '/v1/chat',
      generate: '/v1/generate'
    },
    gateway: {
      models: '/v1/models',
      chatCompletions: '/v1/chat/completions',
      health: '/health'
    }
  });

  return {
    orchestratorUrl: serviceBaseUrls().orchestrator,
    gatewayUrl: serviceBaseUrls().gateway,

    optimizeFor: c.get('optimizeFor', 'capability'),
    harperTimeout: c.get('harperTimeout', 25),
    autoEvalMaxCycles: c.get('autoEval.maxCycles', 2),
    autoEvalExtraCyclesOnProgress: c.get('autoEval.extraCyclesOnProgress', 3),
    autoEvalAgentEvalChecks: c.get('autoEval.agentEvalChecks', 8),
    evalToolsInstall: c.get('evalTools.install', 'ask'),
    finalizeVerify: c.get('finalize.verify', true),
    finalizeVerifyMaxCycles: c.get('finalize.verifyMaxCycles', 3),
    finalizeLocalCheck: c.get('finalize.localCheck', 'ask'),
    finalizeLocalCheckTimeoutMinutes: c.get('finalize.localCheckTimeoutMinutes', 30),
    autoEvalAfterKit: c.get('autoEval.afterKit', false),
    agentChatApprovals: c.get('agentChat.approvals', 'ask'),
    kitAcceptanceFirst: c.get('kit.acceptanceFirst', false),
    
    localAgentEnabled: c.get('localAgent.enabled', true),
    localAgentPreferredExecutor: c.get('localAgent.preferredExecutor', 'gpt_codex'),
    localAgentAllowEval: c.get('localAgent.allowEval', true),
    localAgentRestrictToKitPhases: c.get('localAgent.restrictToKitPhases', true),
    localAgentTimeoutMinutes: c.get('localAgent.timeoutMinutes', 30),

    claudeCodeEnabled: c.get('claudeCode.enabled', true),
    claudeCodeRestrictToKitPhases: c.get('claudeCode.restrictToKitPhases', true),
    claudeCodeEnableEval: c.get('claudeCode.enableEval', false),
    claudeCodeCommand: c.get('claudeCode.command', 'claude'),
    claudeCodeModel: c.get('claudeCode.model', 'opus'),
    claudeCodePermissionMode: c.get('claudeCode.permissionMode', 'acceptEdits'),
    claudeCodePrintModeFlag: c.get('claudeCode.printModeFlag', '-p'),
    // executor-specific timeouts apply only when set; otherwise localAgent.timeoutMinutes
    claudeCodeTimeoutMinutes: explicitSetting(c, 'claudeCode.timeoutMinutes'),

    codexEnabled: c.get('localAgent.codex.enabled', true),
    codexCommand: c.get('localAgent.codex.command', 'codex'),
    codexModel: c.get('localAgent.codex.model', 'gpt-5.5'),
    codexSandboxMode: c.get('localAgent.codex.sandboxMode', 'auto'),
    codexTimeoutMinutes: explicitSetting(c, 'localAgent.codex.timeoutMinutes'),

    requireCleanGit: c.get('apply.requireCleanGit', false),
    backup: c.get('apply.backup', true),
    dryRunPreview: c.get('apply.dryRunPreview', false),

    gitAutoCommit: c.get('git.autoCommit', false),
    gitMergeOnGate: c.get('git.gitMergeOnGate', false),
    gitDeleteBranchOnMerge: c.get('git.gitDeleteBranchOnMerge', false),
    gitReturnToFeatureAfterMerge: c.get('git.gitReturnToFeatureAfterMerge', false),
    gitRemoteUrl: c.get('git.remoteUrl', ''),
    gitCommitMessage: c.get('git.commitMessage', 'clike: apply patch (AI)'),
    gitOpenPR: c.get('git.openPR', false),
    gitAutoPush: c.get('git.autoPush', false),
    gitRemote: c.get('git.remote', 'origin'),
    gitDefaultBranch: c.get('git.defaultBranch', 'main'),
    gitConventionalCommits: c.get('git.conventionalCommits', true),
    gitPushRebase: c.get('git.pushRebase', false),
    gitBranchPrefix: c.get('git.branchPrefix', 'feature'),
    gitTagPrefix: c.get('git.tagPrefix', 'harper'),
    gitPrPerReqDraftEnabled: c.get('git.prPerReqDraft.enabled', false),
    gitPrPerReqDraftUseGhCli: c.get('git.prPerReqDraft.useGhCli', true),
    gitPrBodyPath: c.get('git.prBodyPath', 'docs/harper/PR_BODY.md'),

    mcpExtensionServerEnabled: c.get('mcp.extensionServerEnabled', false),
    mcpExtensionServerHost: c.get('mcp.extensionServerHost', '127.0.0.1'),
    mcpExtensionServerPort: c.get('mcp.extensionServerPort', 55742),
    mcpExtensionServerToken: c.get('mcp.extensionServerToken', ''),

    routes,
  };
}
function sendMcpJson(res, status, body) {
  const raw = JSON.stringify(body);
  res.writeHead(status, {
    'content-type': 'application/json; charset=utf-8',
    'content-length': Buffer.byteLength(raw),
    'cache-control': 'no-store',
  });
  res.end(raw);
}

async function readRequestJson(req) {
  const chunks = [];
  for await (const chunk of req) {
    chunks.push(Buffer.from(chunk));
  }

  const raw = Buffer.concat(chunks).toString('utf8').trim();
  if (!raw) {
    return {};
  }

  return JSON.parse(raw);
}

const MCP_EXTENSION_TOKEN_SECRET = 'clike.mcpExtensionToken';

// The local MCP server always requires a token: the explicit setting wins
// (legacy), otherwise a random token is generated once and kept in SecretStorage.
async function getExtensionMcpToken(context) {
  const override = String(cfg().mcpExtensionServerToken || '').trim();
  if (override) return override;
  let token = await context.secrets.get(MCP_EXTENSION_TOKEN_SECRET);
  if (!token) {
    token = generateServiceToken();
    await context.secrets.store(MCP_EXTENSION_TOKEN_SECRET, token);
  }
  return token;
}


async function getHarperNextAction() {
  const wsroot = getWorkspaceRoot();
  if (!wsroot) {
    return {
      ok: false,
      action: 'no_workspace',
      message: 'No VS Code workspace is open.',
    };
  }

  const plan = await readPlanJson(wsroot);
  const reqs = Array.isArray(plan?.reqs) ? plan.reqs : [];

  if (!reqs.length) {
    return {
      ok: false,
      action: 'no_plan',
      message: 'docs/harper/plan.json is missing or has no reqs.',
    };
  }

  // the first open REQ whose dependencies are done (an in-progress one first); blocked otherwise
  return extensionMcp.nextActionFromPlan(reqs);
}

async function ensureClikeChatPanelForAgent() {
  if (clikeChatPanel && clikeChatPanel.webview) {
    return clikeChatPanel;
  }

  if (!clikeExtensionContext) {
    throw new Error('CLike extension context is not initialized.');
  }

  await vscode.commands.executeCommand('clike.openChat');

  if (!clikeChatPanel || !clikeChatPanel.webview) {
    throw new Error('Unable to open CLike chat panel.');
  }

  return clikeChatPanel;
}

function summarizeEvalReport(report) {
  const r = report || {};
  return {
    status: r.status || null,
    gate: r.gate || null,
    reason_code: r.reason_code || null,
    passed: r.passed ?? null,
    counts: reportCounts(r),
    failed_checks: (Array.isArray(r.cases) ? r.cases : []).filter(c => !c.passed).map(c => c.name),
    regression_failures: r.regression_failures || [],
    review_required: !!r.review_required,
  };
}

/**
 * H2: run a Harper phase from an MCP client through the chat's governed flow (same handlers, same
 * lock/gate/write policy) and wait for it up to waitSeconds; longer runs keep going and are read
 * with harper_run_status(run_id).
 */
let mcpRunInFlight = null;

async function runHarperPhaseForMcp({ phase, reqId = '', fix = null, waitSeconds = 50, options = {} }) {
  await ensureClikeChatPanelForAgent();
  if (typeof clikeRunChatMessage !== 'function') throw new Error('CLike chat is not ready.');
  // one phase at a time: set here, before the chat handler takes its own lock
  if (autopilotRun) throw new Error('CLike autopilot is running: read it with harper_autopilot {action: "status"}, stop it with {action: "stop"}.');
  if (clikeHarperBlockingRun || mcpRunInFlight) {
    throw new Error(`CLike is running another Harper phase${mcpRunInFlight ? ` (${mcpRunInFlight})` : ''}; retry when it ends (see harper_run_status).`);
  }
  const isEdd = phase === 'eval' || phase === 'gate';
  // an MCP run has nobody in front of the modals: it confirms with confirm=true or stops with a reason
  const attachments = options.attachments && options.attachments.length ? await mcpWorkspaceAttachments(options.attachments) : [];
  const common = { attachments, __fromMcp: true, confirm: !!options.confirm };
  const msg = isEdd
    ? { type: 'harperEDD', cmd: phase, targets: [reqId], targetReqId: reqId, ...common, ...(fix ? { fix } : {}) }
    : {
        type: 'harperRun', cmd: phase, targets: reqId ? [reqId] : null, targetReqId: reqId || null, ...common,
        ...(options.methodology ? { methodology: options.methodology } : {}),
        ...(options.agent ? { agent: options.agent } : {}),
        ...(options.text ? { rawInput: options.text } : {}),
        ...(phase === 'idea' && options.extend ? {
          cmd: 'extend', extendMode: 'cascade', fromAttachment: attachments.length > 0, dryRun: !!options.dry_run,
          release: String(options.release || ''),
        } : {}),
      };
  const runId = `mcp-${Date.now().toString(36)}-${Math.random().toString(16).slice(2, 6)}`;
  const run = { run_id: runId, status: 'running', phase: msg.cmd, req_id: reqId || null, started_at: new Date().toISOString(), result: null };
  mcpRuns.set(runId, run);
  extensionMcp.pruneRuns(mcpRuns);
  mcpRunInFlight = runId;
  // what the chat says during the run: the reason when a phase stops early
  const transcript = [];
  const webview = clikeChatPanel?.webview;
  const originalPost = webview?.postMessage;
  try {
    if (webview && originalPost) {
      webview.postMessage = (m) => {
        if (m && (m.type === 'error' || m.type === 'echo') && m.message) transcript.push(String(m.message));
        return originalPost.call(webview, m);
      };
    }
    webview?.postMessage({ type: 'echo', message: `▶ MCP ${msg.cmd.toUpperCase()}${reqId ? ' ' + reqId : ''} (requested by an external agent)` });
  } catch { /* the chat only mirrors the run */ }
  const finish = () => {
    if (mcpRunInFlight === runId) mcpRunInFlight = null;
    try { if (webview && originalPost) webview.postMessage = originalPost; } catch { /* keep going */ }
  };
  const done = Promise.resolve(clikeRunChatMessage(msg)).then(() => {
    run.status = 'done';
    const base = isEdd
      ? { ok: !!msg.__report && msg.__report.status !== 'FAIL' && msg.__report.gate !== 'FAIL', ...(msg.__report || {}) }
      : { ok: msg.__result === 'ok', ...(msg.__outcome || {}), failed: msg.__result === 'failed' };
    if (!msg.__report && !msg.__result) {
      // stopped before running: say why (needs confirmation, missing input, blocked…)
      base.ok = false;
      base.reason = (msg.__outcome && msg.__outcome.error) || transcript.filter((t) => /not run|✖|blocked|cannot|required|missing/i.test(t)).slice(-3).join(' | ') || 'the phase did not run';
    }
    base.messages = transcript.slice(-8);
    run.result = base;
  }).catch((err) => {
    run.status = 'failed';
    run.result = { ok: false, error: String(err?.message || err), messages: transcript.slice(-8) };
  }).finally(finish);
  const waitMs = Math.max(0, Math.min(Number(waitSeconds) || 0, 600)) * 1000;
  await Promise.race([done, new Promise(resolve => setTimeout(resolve, waitMs))]);
  return { ...run };
}

/** Workspace files given to an MCP run as attachments (as the chat's Attach → Workspace files). */
async function mcpWorkspaceAttachments(relPaths) {
  const root = getWorkspaceRoot();
  if (!root) throw new Error('No VS Code workspace is open.');
  const atts = [];
  for (const raw of Array.isArray(relPaths) ? relPaths : []) {
    const rel = String(raw || '').replace(/\\/g, '/').replace(/^\.\//, '');
    if (!rel || rel.startsWith('/') || rel.split('/').includes('..')) throw new Error(`attachment must be a workspace-relative path: ${raw}`);
    const uri = vscode.Uri.joinPath(root, ...rel.split('/'));
    const stat = await vscode.workspace.fs.stat(uri);
    const baseName = rel.split('/').pop() || 'file';
    const common = { origin: 'workspace', source: 'workspace', name: baseName, path: rel, size: stat.size || 0, mime: guessAttachmentMime(baseName) };
    if ((stat.size || 0) > ATTACH_MAX_INLINE_BYTES) { atts.push(common); continue; }
    const bytes = await vscode.workspace.fs.readFile(uri);
    atts.push(isTextAttachment(baseName)
      ? { ...common, content: Buffer.from(bytes).toString('utf8') }
      : { ...common, bytes_b64: Buffer.from(bytes).toString('base64') });
  }
  return atts;
}

/** Cancel the phase an MCP client started (the same as the chat's Cancel). */
function cancelMcpRun(runId) {
  const run = mcpRuns.get(String(runId || '').trim());
  if (!run) throw new Error('Unknown run_id.');
  if (run.status !== 'running') return { ...run, cancelled: false, message: 'the run is not running' };
  cancelHarperWork();
  run.cancel_requested_at = new Date().toISOString();
  return { ...run, cancelled: true, message: 'cancel requested: the run stops at the next step (harper_run_status shows its end)' };
}

/** Modal confirmation, or for an MCP / autopilot run the caller's confirm flag (nobody is there to click). */
async function confirmOrMcp(msg, text, go) {
  if (msg && (msg.__fromMcp || msg.__unattended)) return msg.confirm === true;
  const choice = await vscode.window.showWarningMessage(text, { modal: true }, go);
  return choice === go;
}

async function ragDocsStatus(projectId = '') {
  const pid = String(projectId || getProjectId() || 'default').trim();
  const { orchestratorUrl } = cfg();

  try {
    const res = await postJson(`${orchestratorUrl}/v1/rag/fetch`, {
      project_id: pid,
      path_prefix: 'docs',
      limit_docs: 1,
      max_chars_per_doc: 200,
      search_top_k: 50,
    });

    const count = Number(res?.count || (Array.isArray(res?.docs) ? res.docs.length : 0));
    return {
      ok: true,
      project_id: pid,
      docs_count: count,
      empty: count <= 0,
    };
  } catch (err) {
    return {
      ok: false,
      project_id: pid,
      docs_count: 0,
      empty: true,
      error: String(err?.message || err),
    };
  }
}

async function ragReindexDocsIfEmpty(projectId = '') {
  const status = await ragDocsStatus(projectId);
  if (status.ok && !status.empty) {
    return {
      ok: true,
      reindexed: false,
      status,
      message: 'RAG docs context already exists.',
    };
  }

  const items = await cmdRagReindex('docs/**/*');
  return {
    ok: true,
    reindexed: true,
    indexed_items: Array.isArray(items) ? items.length : 0,
    previous_status: status,
    message: 'RAG docs context was empty or unavailable; docs/**/* reindex submitted.',
  };
}

async function runExtensionMcpTool(name, args = {}) {
  const tool = String(name || '').trim();

  if (tool === 'clike_extension_status') {
    const next = await getHarperNextAction().catch(err => ({
      ok: false,
      error: String(err?.message || err),
    }));

    return {
      ok: true,
      server: 'CLike Extension Operational MCP',
      mode: 'operational',
      workspace: getWorkspaceRoot()?.fsPath || null,
      chat_open: !!(clikeChatPanel && clikeChatPanel.webview),
      state: extensionMcpState,
      next_action: next,
    };
  }

  if (tool === 'harper_next_action') {
    return await getHarperNextAction();
  }

  if (tool === 'harper_init') {
    // /init of the folder open in VS Code, in place (existing files are kept, as /init --force)
    const root = getWorkspaceRoot();
    if (!root) throw new Error('No VS Code workspace is open: open the (empty) project folder first.');
    await ensureClikeChatPanelForAgent();
    if (clikeHarperBlockingRun || mcpRunInFlight) throw new Error('CLike is running another Harper phase; retry when it ends.');
    const name = path.basename(root.fsPath);
    const msg = { type: 'harperInit', name, path: path.dirname(root.fsPath), force: true, __inPlace: true, __fromMcp: true };
    await clikeRunChatMessage(msg);
    return { ok: msg.__result === 'ok', ...(msg.__outcome || {}),
      next: 'put the requirement documents in docs/inputs/ (UI material in docs/harper/ux/), then harper_run_phase idea with attachments' };
  }

  if (tool === 'harper_run_phase') {
    const phase = String(args.phase || '').trim().toLowerCase();
    let reqId = String(args.req_id || '').trim().toUpperCase();

    if (!phase) {
      throw new Error('phase is required.');
    }

    const reqPhases = new Set(['kit', 'eval', 'gate']);
    const noReqPhases = new Set(['idea', 'spec', 'plan', 'finalize']);

    if (!reqPhases.has(phase) && !noReqPhases.has(phase)) {
      throw new Error(`Unsupported Harper phase: ${phase}`);
    }

    if (reqPhases.has(phase) && !reqId) {
      const next = await getHarperNextAction();
      if (next.action === 'finalize_only') {
        return next;
      }
      if (!next.req_id) {
        throw new Error(`No eligible REQ available for /${phase}.`);
      }
      reqId = next.req_id;
    }

    const options = {
      confirm: args.confirm === true, text: args.text ? String(args.text) : '', extend: args.extend === true,
      dry_run: args.dry_run === true, release: args.release ? String(args.release) : '',
      methodology: args.methodology ? String(args.methodology).toLowerCase() : '', agent: args.agent ? String(args.agent).toLowerCase() : '',
      attachments: Array.isArray(args.attachments) ? args.attachments.map(String) : [],
    };
    if (options.extend && phase !== 'idea') throw new Error('extend applies to phase idea (/idea --extend).');
    // await=false: started and tracked like any run (run_id), the call returns at once
    return await runHarperPhaseForMcp({ phase, reqId, waitSeconds: args.await === false ? 0 : (args.wait_seconds ?? 50), options });
  }

  if (tool === 'eval_run' || tool === 'gate_check') {
    const reqId = String(args.req_id || '').trim().toUpperCase();
    if (!/^REQ-\d+/.test(reqId)) throw new Error('req_id is required (e.g. REQ-001).');
    const fix = tool === 'eval_run' && args.fix ? { hint: String(args.hint || '') } : null;
    return await runHarperPhaseForMcp({ phase: tool === 'eval_run' ? 'eval' : 'gate', reqId, fix, waitSeconds: args.wait_seconds ?? 50 });
  }

  if (tool === 'harper_run_status') {
    const run = mcpRuns.get(String(args.run_id || '').trim());
    if (!run) throw new Error('Unknown run_id.');
    return { ...run };
  }

  if (tool === 'cancel_run') {
    return cancelMcpRun(args.run_id);
  }

  if (tool === 'harper_autopilot') {
    // runs for hours: start returns at once; status / stop read and steer the run
    const action = String(args.action || 'status').trim().toLowerCase();
    if (!['start', 'stop', 'status'].includes(action)) throw new Error('action must be one of: start, stop, status.');
    if (action === 'status') return { ok: true, ...autopilotSnapshot() };
    if (action === 'stop') {
      if (!autopilotRun) return { ok: false, ...autopilotSnapshot(), message: 'Autopilot is not running.' };
      autopilotRun.stop = 'graceful';
      return { ok: true, ...autopilotSnapshot(), message: 'Autopilot stops after the current step.' };
    }
    await ensureClikeChatPanelForAgent();
    if (typeof clikeRunChatMessage !== 'function') throw new Error('CLike chat is not ready.');
    const msg = { type: 'autopilot', action: 'start', max: Math.max(0, Number(args.max_reqs || 0)),
      executor: String(args.executor || ''), methodology: String(args.methodology || '') };
    Promise.resolve(clikeRunChatMessage(msg)).catch((err) => out.appendLine(`[autopilot] ${err?.message || err}`));
    await new Promise((resolve) => setTimeout(resolve, 1500));
    if (msg.__refused) return { ok: false, running: !!autopilotRun, error: msg.__refused };
    return { ok: true, ...autopilotSnapshot(), message: 'Autopilot started: poll harper_autopilot {action: "status"} (every few minutes is enough), stop it with {action: "stop"}.' };
  }

  if (tool === 'harper_kit_next') {
    const next = await getHarperNextAction();
    if (next.action === 'finalize_only') {
      return next;
    }

    if (!next.req_id) {
      return next;
    }

    return await runHarperPhaseForMcp({ phase: 'kit', reqId: next.req_id, waitSeconds: args.wait_seconds ?? 50 });
  }

  if (tool === 'harper_continue_loop') {
    const next = await getHarperNextAction();

    if (next.action === 'finalize_only') {
      return {
        ...(await runHarperPhaseForMcp({ phase: 'finalize', waitSeconds: args.wait_seconds ?? 50, options: { confirm: args.confirm === true } })),
        next_action: next,
      };
    }

    if (!next.req_id) {
      return next;
    }

    const phase = String(args.phase || 'kit').trim().toLowerCase();
    if (!['kit', 'eval', 'gate'].includes(phase)) {
      throw new Error('phase must be one of: kit, eval, gate.');
    }

    return {
      ...(await runHarperPhaseForMcp({ phase, reqId: next.req_id, waitSeconds: args.wait_seconds ?? 50 })),
      next_action: next,
    };
  }

  if (tool === 'rag_reindex') {
    const glob = String(args.glob || 'docs/**/*').trim() || 'docs/**/*';
    const items = await cmdRagReindex(glob);
    return {
      ok: true,
      glob,
      indexed_items: Array.isArray(items) ? items.length : 0,
    };
  }

  if (tool === 'rag_docs_status') {
    return await ragDocsStatus(String(args.project_id || ''));
  }

  if (tool === 'rag_docs_reindex_if_empty') {
    return await ragReindexDocsIfEmpty(String(args.project_id || ''));
  }

  throw new Error(`Unknown tool: ${tool}`);
}

function extensionMcpToolsList() {
  return [
    {
      name: 'clike_extension_status',
      description: 'Read local CLike extension operational state and next Harper action.',
      inputSchema: {
        type: 'object',
        properties: {},
      },
    },
    {
      name: 'harper_next_action',
      description: 'The next eligible REQ: an in-progress one, else the first open REQ whose dependencies are done; blocked when every open REQ waits for dependencies; finalize_only when all are done.',
      inputSchema: {
        type: 'object',
        properties: {},
      },
    },
    {
      name: 'harper_run_phase',
      description: 'Run a CLike Harper phase through the governed extension flow (same lock, gate and write policy as the chat) and return its outcome: files written and warnings, or the eval/gate verdict. Waits up to wait_seconds (default 50); a longer run returns status=running and a run_id for harper_run_status. await=false only dispatches.',
      inputSchema: {
        type: 'object',
        properties: {
          phase: { type: 'string', enum: ['idea', 'spec', 'plan', 'kit', 'eval', 'gate', 'finalize'] },
          req_id: { type: 'string' },
          text: { type: 'string', description: 'request text, as typed after the command in the chat' },
          extend: { type: 'boolean', description: 'with phase idea: /idea --extend, the next release (inputs from docs/inputs/vN/)' },
          release: { type: 'string', description: 'with extend: target release, e.g. v2' },
          dry_run: { type: 'boolean', description: 'with extend: write only the EXTEND report' },
          attachments: { type: 'array', items: { type: 'string' }, description: 'workspace-relative files to attach (e.g. docs/inputs/brief.docx): /idea needs at least one' },
          methodology: { type: 'string', enum: ['bmad'] },
          agent: { type: 'string', description: 'BMAD role (analyst, pm, architect, ux, developer, qa, tech-writer)' },
          confirm: { type: 'boolean', description: 'answer yes to the confirmations the chat would ask (e.g. /finalize with REQs not promoted); without it such a run stops with the reason' },
          wait_seconds: { type: 'number' },
          await: { type: 'boolean', description: 'false: start and return the run_id at once' },
        },
        required: ['phase'],
      },
    },
    {
      name: 'eval_run',
      description: 'Run the canonical eval of a REQ in the CLike sandbox and return the verdict and failed checks. fix=true runs the governed auto-eval (KIT repair from the real failures, tests locked) and returns the report of the last eval plus auto_eval {outcome: pass|stopped, cycles, reason}; hint guides the repair.',
      inputSchema: {
        type: 'object',
        properties: {
          req_id: { type: 'string' },
          fix: { type: 'boolean' },
          hint: { type: 'string' },
          wait_seconds: { type: 'number' },
        },
        required: ['req_id'],
      },
    },
    {
      name: 'gate_check',
      description: 'Run the CLike promotion gate of a REQ (checks, regression of promoted REQs, required outputs) and return the decision. No overrides from MCP.',
      inputSchema: {
        type: 'object',
        properties: { req_id: { type: 'string' }, wait_seconds: { type: 'number' } },
        required: ['req_id'],
      },
    },
    {
      name: 'harper_run_status',
      description: 'Status and outcome of a phase started with harper_run_phase / eval_run / gate_check (status running|done|failed).',
      inputSchema: {
        type: 'object',
        properties: { run_id: { type: 'string' } },
        required: ['run_id'],
      },
    },
    {
      name: 'harper_init',
      description: '/init of the folder open in VS Code, in place: creates docs/harper, .clike, runs and the Harper templates; existing files are kept. Run it once, in a folder under CLIKE_PROJECTS_DIR.',
      inputSchema: { type: 'object', properties: {} },
    },
    {
      name: 'cancel_run',
      description: 'Cancel a phase started over MCP (same as the chat Cancel): the running agent or request is stopped.',
      inputSchema: {
        type: 'object',
        properties: { run_id: { type: 'string' } },
        required: ['run_id'],
      },
    },
    {
      name: 'harper_autopilot',
      description: 'The /autopilot of the chat: every REQ of the plan unattended, in dependency order (kit, eval with fix, gate), with the executor configured in VS Code and the same locks, gate and audit. A REQ that needs the developer is parked with its reason and the independent REQs go on; quota/rate limits wait and retry. start returns at once (it runs for hours); status: running, current step, promoted, parked with reasons, next; stop: after the current step. Report: runs/autopilot/report.md. It stops before finalize.',
      inputSchema: {
        type: 'object',
        properties: {
          action: { type: 'string', enum: ['start', 'status', 'stop'] },
          max_reqs: { type: 'number', description: 'with start: stop after this many promoted REQs (0 = all)' },
          executor: { type: 'string', enum: ['cloud', 'codex', 'claude'], description: 'with start: the KIT/repair executor for this run (default: as configured in VS Code; restored at the end)' },
          methodology: { type: 'string', enum: ['bmad'], description: 'with start: BMAD developer for the KIT, QA advisory for the eval' },
        },
        required: ['action'],
      },
    },
    {
      name: 'harper_kit_next',
      description: 'Find the next eligible REQ and dispatch /kit <REQ-ID>. If all REQs are done, returns finalize_only.',
      inputSchema: {
        type: 'object',
        properties: {},
      },
    },
    {
      name: 'harper_continue_loop',
      description: 'Continue the Harper loop on the next eligible REQ with phase kit/eval/gate, or finalize if all REQs are done.',
      inputSchema: {
        type: 'object',
        properties: {
          phase: { type: 'string', enum: ['kit', 'eval', 'gate'] },
        },
      },
    },
    {
      name: 'rag_reindex',
      description: 'Reindex workspace files into RAG using the extension collector. Default glob is docs/**/*.',
      inputSchema: {
        type: 'object',
        properties: {
          glob: { type: 'string' },
        },
      },
    },
    {
      name: 'rag_docs_status',
      description: 'Check whether docs/* content exists in project RAG.',
      inputSchema: {
        type: 'object',
        properties: {
          project_id: { type: 'string' },
        },
      },
    },
    {
      name: 'rag_docs_reindex_if_empty',
      description: 'If docs RAG context is empty, reindex docs/**/* through the extension.',
      inputSchema: {
        type: 'object',
        properties: {
          project_id: { type: 'string' },
        },
      },
    },
  ];
}

async function handleExtensionMcpRpc(body) {
  return extensionMcp.handleRpc(body, {
    serverInfo: { name: 'CLike Extension Operational MCP', version: String(require('./package.json').version || 'v1') },
    instructions: 'Operational CLike MCP surface: runs Harper phases, eval and gate through the same governed flow as the chat. ' +
      'Long runs return status=running and a run_id for harper_run_status; cancel_run stops them. ' +
      'To deliver every REQ unattended use harper_autopilot {action: "start"} and poll {action: "status"} every few minutes.',
    tools: extensionMcpToolsList,
    callTool: async (name, args) => {
      try {
        return await runExtensionMcpTool(name, args);
      } catch (err) {
        extensionMcpState.lastError = String(err?.message || err);
        throw err;
      }
    },
  });
}

async function startExtensionOperationalMcpServer(context) {
  const settings = cfg();

  if (!settings.mcpExtensionServerEnabled) {
    out.appendLine('[CLike][mcp-extension] disabled by settings.');
    return;
  }

  if (extensionMcpServer) {
    return;
  }

  const host = String(settings.mcpExtensionServerHost || '127.0.0.1');
  const port = Number(settings.mcpExtensionServerPort || 55742);
  const mcpToken = await getExtensionMcpToken(context);

  extensionMcpServer = http.createServer(async (req, res) => {
    try {
      const url = new URL(req.url || '/', `http://${host}:${port}`);
      // OAuth discovery does not exist here: 404 before auth, so a client without the token
      // reports the missing header instead of a failed OAuth registration
      const early = extensionMcp.preAuthRoute(req.method, url.pathname);
      if (early) return sendMcpJson(res, early.status, early.body);

      const verdict = validateLocalMcpRequest(req, { token: mcpToken, port });
      if (!verdict.ok) {
        return sendMcpJson(res, verdict.status, { ok: false, error: verdict.error });
      }

      if (req.method === 'GET' && url.pathname === '/health') {
        return sendMcpJson(res, 200, {
          ok: true,
          service: 'CLike Extension Operational MCP',
          chat_open: !!(clikeChatPanel && clikeChatPanel.webview),
          state: extensionMcpState,
        });
      }

      if (req.method === 'GET' && url.pathname === '/tools') {
        return sendMcpJson(res, 200, {
          ok: true,
          tools: extensionMcpToolsList(),
        });
      }

      const route = extensionMcp.postAuthRoute(req.method, url.pathname);
      if (route) {
        if (route.headers) for (const [k, v] of Object.entries(route.headers)) res.setHeader(k, v);
        return sendMcpJson(res, route.status, route.body);
      }
      const body = await readRequestJson(req);
      const response = await handleExtensionMcpRpc(body);
      if (response === null) {
        res.statusCode = 202; // notification: accepted, no body
        return res.end();
      }
      return sendMcpJson(res, 200, response);
    } catch (err) {
      extensionMcpState.lastError = String(err?.message || err);
      out.appendLine(`[CLike][mcp-extension] request error: ${extensionMcpState.lastError}`);
      return sendMcpJson(res, 500, { ok: false, error: 'internal_error' });
    }
  });

  extensionMcpServer.listen(port, host, () => {
    extensionMcpState.started = true;
    extensionMcpState.url = `http://${host}:${port}/mcp`;
    out.appendLine(`[CLike][mcp-extension] operational MCP listening at ${extensionMcpState.url}`);
    vscode.window.setStatusBarMessage(`CLike MCP extension: ${host}:${port}`, 2500);
  });

  extensionMcpServer.on('error', (err) => {
    extensionMcpState.started = false;
    extensionMcpState.lastError = String(err?.message || err);
    out.appendLine(`[CLike][mcp-extension] server error: ${extensionMcpState.lastError}`);
  });

  context.subscriptions.push({
    dispose: () => {
      try {
        if (extensionMcpServer) {
          extensionMcpServer.close();
          extensionMcpServer = null;
          extensionMcpState.started = false;
        }
      } catch {}
    },
  });
}
function getActiveEditorOrThrow() {
  const editor = vscode.window.activeTextEditor;
  if (!editor) throw new Error('Nessun editor attivo.');
  return editor;
}

function extractCodeBlockOrPlain(s) {
  if (!s) return '';
  const t = String(s).trim();
  const m = t.match(/```(?:[\w-]+)?\s*([\s\S]*?)```/m);
  return m ? m[1] : t;
}

async function writeBackupIfNeeded(doc, content) {
  const { backup } = cfg();
  if (!backup) return;
  const uri = doc.uri.with({ path: doc.uri.path + '~clike.bak' });
  if (typeof content !== 'string') {
    throw new Error('No new_content provided by orchestrator for writeBackupIfNeeded.');
  }
  await vscode.workspace.fs.writeFile(uri, Buffer.from(content, 'utf8'));
  out.appendLine(`[backup] scritto ${uri.fsPath}`);
}

async function ensureCleanGitIfRequired() {
  const { requireCleanGit } = cfg();
  if (!requireCleanGit) return;

  const ws = vscode.workspace.workspaceFolders && vscode.workspace.workspaceFolders[0];
  if (!ws) throw new Error('requireCleanGit attivo ma nessuna workspace folder aperta.');

  const cwd = ws.uri.fsPath;
  const runGit = (args) =>
    new Promise((resolve, reject) => {
      execFile('git', args, { cwd }, (err, stdout, stderr) => {
        if (err) return reject(new Error(stderr || err.message));
        resolve(stdout.trim());
      });
    });

  const inside = await runGit(['rev-parse', '--is-inside-work-tree']);
  if (inside !== 'true') throw new Error('Non sei dentro un repo Git.');
  const status = await runGit(['status', '--porcelain']);
  if (status !== '') throw new Error('Working tree non pulito. Committa/stasha prima di applicare la patch.');
}

async function readSelectionOrClipboard(editor) {
  const doc = editor.document;
  if (editor.selection && !editor.selection.isEmpty) {
    return doc.getText(editor.selection);
  }
  return await vscode.env.clipboard.readText();
}

function currentDocContext() {
  const editor = getActiveEditorOrThrow();
  const doc = editor.document;
  const sel = editor.selection;
  const selection = sel && !sel.isEmpty ? doc.getText(sel) : '';
  return {
    file_path: doc.uri.fsPath || doc.uri.toString(),
    language: doc.languageId || 'plaintext',
    text: doc.getText(),
    selection
  };
}

function isUnifiedDiffStr(s) {
  if (!s) return false;
  const t = String(s);
  return /(^|\n)---\s/.test(t) && /(^|\n)\+\+\+\s/.test(t) && /(^|\n)@@\s/.test(t);
}

function isLikelyShortDocstring(s, lang) {
  if (!s) return false;
  const t = String(s).trim();
  if ((lang === 'python' || lang === 'py') && /^""".+?"""$/s.test(t)) {
    const lines = t.split(/\r?\n/).length;
    return lines <= 15;
  }
  if (/(javascript|typescript|react|tsx|jsx)/i.test(lang) && /^\/\*\*[\s\S]*\*\/$/.test(t)) {
    const lines = t.split(/\r?\n/).length;
    return lines <= 15;
  }
  if (/^\/\*\*[\s\S]*\*\/$/.test(t)) {
    const lines = t.split(/\r?\n/).length;
    return lines <= 15;
  }
  if (/^(\/\*[\s\S]*\*\/|\/\/[^\n]+(\n\/\/[^\n]+)*)$/.test(t)) {
    const lines = t.split(/\r?\n/).length;
    return lines <= 15;
  }
  return false;
}

/** ---------- HTTP ---------- */
// Resolves with { ok, status, json | text } or { ok: false, status: 0, error }; never rejects.
async function httpPostJson(urlString, bodyObj, headers = {}) {
  try {
    const res = await serviceRequest('POST', urlString, { body: bodyObj || {}, headers });
    try {
      return { ok: res.ok, status: res.status, json: JSON.parse(res.text || '{}') };
    } catch (_) {
      return { ok: res.ok, status: res.status, text: res.text };
    }
  } catch (error) {
    return { ok: false, status: 0, error };
  }
}

async function postOrchestrator(path, payload = {}) {
  const { orchestratorUrl, optimizeFor } = cfg();
  const url = `${orchestratorUrl}${path}`;
  const base = { optimize_for: optimizeFor, fallback: true };
  const body = { ...base, ...payload };
  const bodyStr = (() => { try { return JSON.stringify(body); } catch { return ''; } })();
  console.log(`[REQ] POST ${url} ct=application/json len=${bodyStr.length} keys=${Object.keys(body).join(',')}`);
  
  out.appendLine(`[REQ] POST ${url} ct=application/json len=${bodyStr.length} keys=${Object.keys(body).join(',')}`);
  const res = await httpPostJson(url, body);
  const keys = res && res.json ? Object.keys(res.json) : (res ? Object.keys(res) : []);
  out.appendLine(`[RES] POST ${url} -> ${res && res.status} keys=${(keys||[]).join(',')}`);
  console.log(`[RES] POST ${url} -> ${res && res.status} keys=${(keys||[]).join(',')}`);
  if (res && res.json && (res.json.detail || res.json.message)) {
    out.appendLine(`[RES] detail: ${(res.json.detail || res.json.message)}`);
  }

  return res;
}

async function postGateway(path, payload = {}) {
  const { gatewayUrl } = cfg();
  const url = `${gatewayUrl}${path}`;
  const b = (() => { try { return JSON.stringify(payload); } catch { return ''; } })();
  out.appendLine(`[http] POST ${url} ct=application/json len=${b.length}`);
  return await httpPostJson(url, payload);
}

// utils
async function getJson(url) {
  try {
    const r = await serviceRequest('GET', url, { timeoutMs: 15000 });
    if (!r.ok) return { status: r.status };
    try { return r.json(); } catch { return { status: r.status }; }
  } catch (e) {
    throw new Error(`GET ${url} failed: ${e.message}`);
  }
}

/** ---------- Git helpers ---------- */
// After a code action is applied to a file: with clike.git.autoCommit, commit
// that file only (argv, no shell). Never `git add -A`, never opens a PR (WP5).
async function commitAppliedFile(fileUri) {
  const { gitAutoCommit, gitCommitMessage } = cfg();
  if (!gitAutoCommit || !fileUri) return;
  const ws = vscode.workspace.getWorkspaceFolder(fileUri);
  if (!ws) return;
  const rel = path.relative(ws.uri.fsPath, fileUri.fsPath);
  if (!rel || rel.startsWith('..') || path.isAbsolute(rel)) return;
  const runGit = (args) =>
    new Promise((resolve, reject) => {
      execFile('git', args, { cwd: ws.uri.fsPath }, (err, stdout, stderr) => {
        if (err) return reject(new Error(stderr || err.message));
        resolve(stdout.trim());
      });
    });
  try {
    await runGit(['add', '--', rel]);
    await runGit(['commit', '-m', String(gitCommitMessage || 'clike: apply patch (AI)'), '--', rel]);
    vscode.window.setStatusBarMessage(`Clike: committed ${rel}.`, 3000);
  } catch (e) {
    log(`[harperGit] commit skip/failed: ${e.message}`);
  }
}

/** ---------- Preview provider for diffs ---------- */
let clikePreviewProvider;
function ensurePreviewProvider() {
  if (clikePreviewProvider) return clikePreviewProvider;
  class MemContentProvider {
    constructor() {
      this._onDidChange = new vscode.EventEmitter();
      this.onDidChange = this._onDidChange.event;
      this._store = new Map();
    }
    set(key, value) { this._store.set(key, value); this._onDidChange.fire(vscode.Uri.from({ scheme: 'clike-preview', path: `/${key}` })); }
    provideTextDocumentContent(uri) {
      const key = uri.path.startsWith('/') ? uri.path.slice(1) : uri.path;
      return this._store.get(key) ?? '';
    }
  }
  clikePreviewProvider = new MemContentProvider();
  vscode.workspace.registerTextDocumentContentProvider('clike-preview', clikePreviewProvider);
  return clikePreviewProvider;
}
function explicitProviderForModel(model) {
  const m = String(model || '').trim();
  if (!m || m === 'auto') return '';
  if (m.includes(':')) {
    return m.split(':', 1)[0].trim().toLowerCase();
  }
  return '';
}

function buildModeContract(mode, phase = '') {
  const m = String(mode || 'free').toLowerCase();
  const p = String(phase || '').toLowerCase();

  if (m === 'free') {
    return {
      mode: 'free',
      allow_file_output: false,
      prefer_tools: false,
      prefer_response_format: true,
      require_phase_artifacts: false,
    };
  }

  if (m === 'coding') {
    return {
      mode: 'coding',
      allow_file_output: true,
      prefer_tools: true,
      prefer_response_format: true,
      require_phase_artifacts: false,
    };
  }

  if (m === 'harper') {
    return {
      mode: 'harper',
      phase: p,
      allow_file_output: true,
      prefer_tools: true,
      prefer_response_format: true,
      require_phase_artifacts: true,
    };
  }

  return {
    mode: m,
    allow_file_output: false,
    prefer_tools: false,
    prefer_response_format: true,
    require_phase_artifacts: false,
  };
}


async function showDiffPreview(originalText, patchedText, title = 'Clike Preview') {
  const provider = ensurePreviewProvider();
  const uid = String(Date.now()) + '-' + Math.random().toString(36).slice(2, 8);
  provider.set(`${uid}-left`, originalText);
  provider.set(`${uid}-right`, patchedText);

  const left = vscode.Uri.from({ scheme: 'clike-preview', path: `/${uid}-left` });
  const right = vscode.Uri.from({ scheme: 'clike-preview', path: `/${uid}-right` });

  await vscode.commands.executeCommand('vscode.diff', left, right, title, { preview: true });
}

/** ---------- APPLY “HARDENED�? ---------- */
// FIX: signature changed — now accepts (targetUri, newContent, lang?, intent?)
// it used to be called by mistake with "context"
async function replaceWholeSafe(targetUri, newContent, lang, intent) {
  // Safety: do not overwrite the file with a short docstring
  if (intent === 'docstring' && isLikelyShortDocstring(newContent, lang)) {
    throw new Error('Safety: refusing to replace whole file with a short docstring');
  }
  const doc = await vscode.workspace.openTextDocument(targetUri);
  const editor = await vscode.window.showTextDocument(doc, { preview: false });
  if (!editor) throw new Error('No active editor for replaceWholeSafe');

  await editor.edit(editBuilder => {
    const full = new vscode.Range(doc.positionAt(0), doc.positionAt(doc.getText().length));
    editBuilder.replace(full, newContent);
  });
}

async function hardenedApplyFromString(context, input, { withPreview = true } = {}) {
  const toStr = (x) => (x == null ? '' : String(x));

  const editor = getActiveEditorOrThrow();
  const doc = editor.document;
  const original = doc.getText();
  const cfgSafe = (() => { try { return cfg(); } catch { return {}; } })();
  const allowRawDiffFallback = !!cfgSafe.allowRawDiffFallback;

  await ensureCleanGitIfRequired();
  await writeBackupIfNeeded(doc, original);

  const raw = toStr(input);
  const looksLikeDiff = isUnifiedDiffStr(raw);

  // CASE A: plain content → whole-file replacement (with preview)
  if (!looksLikeDiff) {
    const newContent = extractCodeBlockOrPlain(raw);
    if (!newContent) throw new Error('No content to apply.');
    if (!isSaneReplacement(original, newContent)) {
      const cont3 = await vscode.window.showWarningMessage(
        `Replacement shrinks file from ${original.length} to ${newContent.length} chars. Continue?`,
        'Force Apply', 'Cancel'
      );
      if (cont3 !== 'Force Apply') throw new Error('Replacement rejected by safety check.');
    }
    if (withPreview) {
      await showDiffPreview(original, newContent, 'Clike New Content Preview (apply?)');
      const apply = await vscode.window.showInformationMessage('Replace file with the shown content?', 'Apply', 'Cancel');
      if (apply !== 'Apply') throw new Error('Application cancelled.');
    }
    // FIX: use doc.uri (not context)
    await replaceWholeSafe(doc.uri, newContent);
    vscode.window.showInformationMessage('Clike: applied content.');
    await vscode.commands.executeCommand('workbench.action.files.save');
    await commitAppliedFile(doc.uri);
    return;
  }

  // CASE B: unified diff → apply patch
  let patched = null;
  try {
    const tmp = applyPatch(original, raw, { fuzzFactor: 2 });
    if (typeof tmp === 'string') patched = tmp;
  } catch (e) {
    out.appendLine(`[hardened] applyPatch error: ${e.message}`);
  }

  if (patched) {
    if (!diffHeaderContainsPath(raw, doc.uri.fsPath)) {
      const cont = await vscode.window.showWarningMessage(
        'Patch header path does not match the current file. Continue?',
        'Force Apply', 'Cancel'
      );
      if (cont !== 'Force Apply') throw new Error('Patch path mismatch.');
    }
    if (!isSaneReplacement(original, patched)) {
      const cont2 = await vscode.window.showWarningMessage(
        `Patch shrinks file from ${original.length} to ${patched.length} chars. Continue?`,
        'Force Apply', 'Cancel'
      );
      if (cont2 !== 'Force Apply') throw new Error('Patch rejected by safety check.');
    }

    if (withPreview) {
      await showDiffPreview(original, patched, 'Clike Diff Preview (apply?)');
      const apply = await vscode.window.showInformationMessage('Apply the shown patch?', 'Apply', 'Cancel');
      if (apply !== 'Apply') throw new Error('Patch application cancelled.');
    }
    // FIX: use doc.uri
    await replaceWholeSafe(doc.uri, patched);
    vscode.window.showInformationMessage('Clike: patch applied (diff).');
    await vscode.commands.executeCommand('workbench.action.files.save');
    await commitAppliedFile(doc.uri);
    return;
  }

  // CASE C: patch not applicable → do not write the raw diff into the file
  await vscode.env.clipboard.writeText(raw);
  out.appendLine('[hardened] patch failed; raw diff copied to clipboard');
  if (!allowRawDiffFallback) {
    throw new Error('Patch not applicable. Raw diff was copied to clipboard (fallback disabled).');
  }
  const choice = await vscode.window.showWarningMessage(
    'Patch failed. Replace file with RAW diff text? (NOT recommended)',
    'Replace', 'Cancel'
  );
  if (choice !== 'Replace') {
    throw new Error('Patch not applicable and raw fallback refused.');
  }
  await replaceWholeSafe(doc.uri, raw);
  await vscode.commands.executeCommand('workbench.action.files.save');
  vscode.window.showWarningMessage('Clike: raw diff written to file (fallback).');
}

/** Insert text (docstring) above the selection or at the top of the file */
async function insertAboveSelection(targetUri, docstring) {
  const doc = await vscode.workspace.openTextDocument(targetUri);
  const editor = await vscode.window.showTextDocument(doc, { preview: false });
  if (!editor) throw new Error('No active editor for insertAboveSelection');

  const sel = editor.selection && !editor.selection.isEmpty ? editor.selection : null;
  const insertPos = sel ? new vscode.Position(sel.start.line, 0) : new vscode.Position(0, 0);

  await editor.edit(editBuilder => {
    const textToInsert = (extractCodeBlockOrPlain(docstring) || '').trimEnd() + '\n\n';
    editBuilder.insert(insertPos, textToInsert);
  });
  await vscode.commands.executeCommand('workbench.action.files.save');
}

/** ---------- Orchestrator-aware Applier ---------- */
async function applyOrchestratorResult(context, respJson, applyCtx) {
  const data = respJson || {};
  const diff = data.diff || data.patch || '';
  // FIX: sanitize new_content from the preamble ("Here is the updated code:") or ``` blocks
  const newContentRaw = data.new_content;
  const newContent = typeof newContentRaw === 'string' ? extractCodeBlockOrPlain(newContentRaw) : undefined;

  const apply = data.apply || {};
  const intent = (applyCtx.intent || '').toLowerCase();
  const lang = applyCtx.lang || '';
  const selectionText = applyCtx.selectionText || '';
  const targetUri = applyCtx.targetUri;

  // 1) explicit diff
  if (apply.type === 'unified_diff' && isUnifiedDiffStr(diff)) {
    if (apply.path) {
      const targetPathUri = resolveToWorkspaceUri(apply.path);
      const currentFs = targetUri.fsPath;
      if (targetPathUri && targetPathUri.fsPath !== currentFs && typeof newContent === 'string') {
        if (typeof newContent !== 'string') {
          throw new Error('No new_content provided by orchestrator for file write.');
        }
        await vscode.workspace.fs.writeFile(targetPathUri, Buffer.from(newContent, 'utf8'));
        await vscode.window.showTextDocument(targetPathUri, { preview: false });
        vscode.window.showInformationMessage(`Clike: scritto file ${targetPathUri.fsPath}`);
        return;
      }
    }
    await hardenedApplyFromString(context, diff, { withPreview: true });
    return;
  }

  // 2) DOCSTRING with selection → insert ABOVE the selection if the docstring is "short"
  if (intent === 'docstring' && selectionText && selectionText.trim().length > 0) {
    if (typeof newContent === 'string' && isLikelyShortDocstring(newContent, lang)) {
      await insertAboveSelection(targetUri, newContent);
      return;
    }
    if (typeof newContent === 'string' && !isUnifiedDiffStr(newContent)) {
      await insertAboveSelection(targetUri, newContent);
      return;
    }
  }

  // 3) explicit replace_selection
  if (apply.type === 'replace_selection' && typeof newContent === 'string') {
    const doc = await vscode.workspace.openTextDocument(targetUri);
    const editor = await vscode.window.showTextDocument(doc, { preview: false });
    if (!editor || !editor.selection || editor.selection.isEmpty) {
      throw new Error('replace_selection: no editor selection');
    }
    await editor.edit(eb => eb.replace(editor.selection, newContent));
    await vscode.commands.executeCommand('workbench.action.files.save');
    return;
  }

  // 4) explicit replace_whole
  if (apply.type === 'replace_whole' && typeof newContent === 'string') {
    await replaceWholeSafe(targetUri, newContent, lang, intent);
    await vscode.commands.executeCommand('workbench.action.files.save');
    return;
  }

  // 5) reasonable fallback
  if (isUnifiedDiffStr(diff)) {
    await hardenedApplyFromString(context, diff, { withPreview: true });
    return;
  }
  if (intent === 'docstring' && typeof newContent === 'string' && isLikelyShortDocstring(newContent, lang)) {
    await insertAboveSelection(targetUri, newContent);
    return;
  }
  if (typeof newContent === 'string') {
    await replaceWholeSafe(targetUri, newContent, lang, intent);
    await vscode.commands.executeCommand('workbench.action.files.save');
    return;
  }

  throw new Error('Nothing to apply: no diff, no actionable content');
}

/** ---------- Commands (aligned with the endpoints) ---------- */
async function cmdAddDocstring(context) {
  return runWriteCommand(context, 'add_docstring', 'docstring', { useContent: true });
}
async function cmdRefactor(context) {
  return runWriteCommand(context, 'refactor', 'refactor', { useContent: true });
}
async function cmdGenerateTests(context) {
  return runWriteCommand(context, 'generate_tests', 'tests', { useContent: true });
}
async function cmdFixErrors(context) {
  return runWriteCommand(context, 'fix_errors', 'fix', { useContent: true });
}

async function cmdListModels() {
  const { routes } = cfg();
  const resp = await postGateway(routes.gateway.models, {});
  if (!resp.ok) return vscode.window.showErrorMessage(`Clike Models: HTTP ${resp.status}`);
  const payload = resp.json || {};
  const models = payload.data || payload.models || payload;
  let items = [];
  if (Array.isArray(models)) {
    items = models.map(m => ({ label: String(m.id || m.name || m) }));
  } else if (models.data && Array.isArray(models.data)) {
    items = models.data.map(m => ({ label: String(m.id || m.name) }));
  }
  await vscode.window.showQuickPick(items.length ? items : [{ label: 'No models' }], { placeHolder: 'Modelli (gateway)' });
}

async function cmdCheckServices(context) {
  try {
    const editor = getActiveEditorOrThrow();
    const docInfo = documentInfoFromEditor(editor);
    await context.workspaceState.update('clike.lastTargetUri', docInfo.uriStr);

    const { routes } = cfg();
    const o = await getJson(cfg().orchestratorUrl + routes.orchestrator.health);
    const g = await getJson(cfg().gatewayUrl + routes.gateway.health);
    const gatewayStatus = g['clike gateway status'] || 'err';
    const orchestratorStatus = o['clike orchestrator status'] || 'err';

    vscode.window.showInformationMessage(`Health — Orchestrator: ${orchestratorStatus} | Gateway: ${gatewayStatus}`);
  } 
  catch (err) {
    vscode.window.showErrorMessage(`Clike: ${err.message}`);
  }
}

function shouldIndexWorkspacePathForRag(relPath) {
  const p = String(relPath || '').replace(/\\/g, '/');

  const EXCLUDED_PREFIXES = [
    'runs/',
    '.clike/sessions/',
    '.clike/telemetry/',
    '.clike/eval-check/',
    '.clike/bin/',
    '.git/',
    'node_modules/',
    'dist/',
    'build/',
    'out/',
    '.next/',
    '.venv/',
    '.mypy_cache/',
  ];

  if (EXCLUDED_PREFIXES.some(prefix => p.startsWith(prefix))) {
    return false;
  }

  const INCLUDED_TOP_LEVEL = [
    'src/',
    'test/',
    'tests/',
    'docs/harper/',
    'configs/',
    'prompts/',
    'README.md',
    'package.json',
    'package-lock.json',
    'requirements.txt',
    'pyproject.toml',
    'docker-compose.yml',
  ];

  return INCLUDED_TOP_LEVEL.some(prefix => p === prefix || p.startsWith(prefix));
}

async function cmdRagReindex(glob) {
  const ws = vscode.workspace.workspaceFolders && vscode.workspace.workspaceFolders[0];
  if (!ws) {
    return vscode.window.showWarningMessage('No workspace open.');
  }

  // Align the projectId with everything else (Harper, /kit, RAG from chat)
  const projectId = getProjectId();

  // Collect candidates
  let uris = [];
  if (typeof glob === 'string' && glob.trim()) {
    uris = await vscode.workspace.findFiles(glob.trim(), '**/node_modules/**', 10000);
  } else {
    const ok = await vscode.window.showWarningMessage(
      'This will re-index the whole workspace into RAG (text files only, size-capped). Continue?',
      { modal: true },
      'Reindex'
    );
    if (ok !== 'Reindex') return;
    uris = await vscode.workspace.findFiles('**/*', '**/node_modules/**', 20000);
  }

  const MAX_FILE_BYTES = 512 * 1024; // 512KB per file cap
  const items = [];
  for (const uri of uris) {
    try {
      const data = await vscode.workspace.fs.readFile(uri);
      if (!data || data.byteLength === 0) continue;
      if (data.byteLength > MAX_FILE_BYTES) continue;
      const buf = Buffer.from(data);
      if (buf.includes(0)) continue; // skip binaries

      const text = buf.toString('utf8');
      if (!text.trim()) continue;

      const rel = ws ? vscode.workspace.asRelativePath(uri, false) : uri.fsPath;
      if (!shouldIndexWorkspacePathForRag(rel)) continue;
      items.push({ path: rel, text });
    } catch (e) {
      console.warn('[RAG] Skipping file', uri.fsPath || uri.toString(), e);
    }
  }

  if (!items.length) {
    vscode.window.showWarningMessage('[RAG] No text files found to index.');
    return;
  }

  const { orchestratorUrl } = cfg();
  const url = '/v1/rag/index';

  try {
    await postJson(`${orchestratorUrl}${url}`, {
      project_id: projectId,
      items
    });
    
    vscode.window.showInformationMessage(`[RAG] Indexed ${items.length} items.`);
  } catch (e) {
    vscode.window.showErrorMessage(`[RAG] Index failed: ${String(e)}`);
  }
  return items
}

async function cmdRagSearch(q) {
  const ws = vscode.workspace.workspaceFolders && vscode.workspace.workspaceFolders[0];
  if (!ws) {
    return vscode.window.showWarningMessage('No workspace open.');
  }

  const projectId = getProjectId();

  let query = (typeof q === 'string') ? q : '';
  if (!query) {
    query = await vscode.window.showInputBox({ prompt: 'RAG search query' }) || '';
  }
  query = query.trim();
  if (!query) return;

  const topkStr = await vscode.window.showInputBox({ prompt: 'Top-K', value: '8' });
  const top_k = Number(topkStr || '8') || 8;

  const { orchestratorUrl } = cfg();
  const url = '/v1/rag/search';

  try {
    const res = await postJson(`${orchestratorUrl}${url}`, {
      project_id: projectId,
      query,
      top_k,
    });

    const hits = (res?.hits || res?.results || res?.matches || []).slice(0, top_k);

    vscode.window.showInformationMessage(`[RAG] Results: ${hits.length}`);
    try {
      const uniquePaths = Array.from(new Set(
        hits
          .map(h => (h && (h.path || h.source || h.name)) ? String(h.path || h.source || h.name) : '')
          .filter(Boolean)
      ));

      if (uniquePaths.length > 0) {
        const picked = await vscode.window.showQuickPick(
          uniquePaths.map(p => ({ label: p, description: 'RAG result' })),
          {
            title: `RAG results for: ${query}`,
            placeHolder: 'Select a file to open or Esc to dismiss',
            matchOnDescription: true,
          }
        );

        if (picked && picked.label) {
          try {
            const ws = vscode.workspace.workspaceFolders && vscode.workspace.workspaceFolders[0];
            if (ws) {
              const fileUri = vscode.Uri.joinPath(ws.uri, picked.label);
              const doc = await vscode.workspace.openTextDocument(fileUri);
              await vscode.window.showTextDocument(doc, { preview: false });
            }
          } catch (openErr) {
            vscode.window.showWarningMessage(`RAG result selected, but file could not be opened: ${picked.label}`);
          }
        }
      }
    } catch (qpErr) {
      log('[RAG] QuickPick failed:', String(qpErr && qpErr.message || qpErr));
    }
    const chatPanel = (clikeChatPanel && clikeChatPanel.webview) ? clikeChatPanel : null;

    if (chatPanel) {
      try {
        chatPanel.webview.postMessage({
          type: 'ragResults',
          results: hits,
          query,
        });
      } catch (postErr) {
        log('[RAG] failed to post results to existing chat panel:', String(postErr && postErr.message || postErr));
      }
    }

    // log utile in Output
    try {
      const uniquePaths = Array.from(new Set(
        hits
          .map(h => (h && (h.path || h.source || h.name)) ? String(h.path || h.source || h.name) : '')
          .filter(Boolean)
      ));

      log(`[RAG] query="${query}" raw_results=${hits.length} unique_paths=${uniquePaths.length}`);
      for (const p of uniquePaths.slice(0, 20)) {
        log(`[RAG] file: ${p}`);
      }
    } catch (e) {
      log('[RAG] result logging failed:', String(e && e.message || e));
    }

    return res;
  } catch (e) {
    vscode.window.showErrorMessage(`[RAG] Search failed: ${String(e)}`);
  }
}


async function cmdApplyUnifiedDiffHardened(context) {
  try { await runApplyFromClipboard(context, 'diff (hardened)', { treatAsDiff: true }); }
  catch (e) { vscode.window.showErrorMessage(`Clike: apply failed → ${e.message}`); out.appendLine(`[error] ${e.stack || e.message}`); out.show(true); }
}
async function cmdApplyUnifiedDiff(context) { return cmdApplyUnifiedDiffHardened(context); }
async function cmdApplyNewContent(context) {
  try { await runApplyFromClipboard(context, 'new_content', { treatAsDiff: false }); }
  catch (e) { vscode.window.showErrorMessage(`Clike: apply new_content failed → ${e.message}`); }
}
async function cmdApplyLastPatch(context) {
  await rememberTargetUri(context);
  const last = context.workspaceState.get('clike.lastPatch');
  if (!last) return vscode.window.showWarningMessage('No previous patch.');
  await hardenedApplyFromString(context, String(last), { withPreview: true });
}

async function cmdCodeAction() {
  const items = [
    { label: '$(edit) Add Docstring', cmd: 'clike.addDocstring' },
    { label: '$(wand) Refactor', cmd: 'clike.refactor' },
    { label: '$(beaker) Generate Tests', cmd: 'clike.generateTests' },
    { label: '$(tools) Fix Errors', cmd: 'clike.fixErrors' },
    { label: '$(diff) Apply Unified Diff (Hardened)', cmd: 'clike.applyUnifiedDiffHardened' },
    { label: '$(replace) Apply New Content', cmd: 'clike.applyNewContent' },
    { label: '$(list-unordered) List Models (Gateway)', cmd: 'clike.listModels' },
  ];
  const pick = await vscode.window.showQuickPick(items, { placeHolder: 'Clike: scegli un’azione', ignoreFocusOut: true });
  if (pick) return vscode.commands.executeCommand(pick.cmd);
}

async function cmdPing() { vscode.window.showInformationMessage('Clike: extension is alive.'); }

async function cmdClearChatSession(context) {
  const s = context.workspaceState.get('clike.uiState') || { mode: 'free', model: 'auto' };
  const historyScope = effectiveHistoryScope(context);
  if (historyScope === 'allModels') {
    await clearSession(s.mode);
    vscode.window.showInformationMessage(`CLike: cleared ALL messages (all models) in mode "${s.mode}"`);
    const hist = await loadSession(s.mode, 200);
    clikeChatPanel?.webview.postMessage({ type: 'hydrateSession', messages: hist });
  } else {
    await pruneSessionByModel(s.mode, s.model || 'auto');
    vscode.window.showInformationMessage(`CLike: cleared messages for model "${s.model}" in mode "${s.mode}"`);
    const hist = await loadSessionFilteredV2(s.mode, s.model, 200);
    clikeChatPanel?.webview.postMessage({ type: 'hydrateSession', messages: hist });
  }
}


async function cmdOpenChatSessionFile(context) {
  const s = context.workspaceState.get('clike.uiState') || { mode: 'free' };
  const uri = sessionFileUri(s.mode);
  try {
    const doc = await vscode.workspace.openTextDocument(uri);
    await vscode.window.showTextDocument(doc, { preview: false });
  } catch {
    vscode.window.showWarningMessage(`CLike: no session file yet for mode ${s.mode}`);
  }
}


async function cmdSetServiceToken(context) {
  const choice = await vscode.window.showQuickPick(
    [
      { id: 'paste', label: 'Paste existing token', description: 'Use the CLIKE_API_TOKEN already set in the stack .env' },
      { id: 'generate', label: 'Generate new token', description: 'Store a random token and copy the .env line to the clipboard' },
    ],
    { placeHolder: 'CLike service token (CLIKE_API_TOKEN)' }
  );
  if (!choice) return;
  if (choice.id === 'generate') {
    const token = generateServiceToken();
    await storeServiceToken(context, token);
    await vscode.env.clipboard.writeText(`CLIKE_API_TOKEN=${token}`);
    vscode.window.showInformationMessage(
      'CLike: new service token stored. "CLIKE_API_TOKEN=..." is in the clipboard: add it to the stack .env and restart the services.'
    );
    return;
  }
  const token = await vscode.window.showInputBox({
    prompt: 'CLIKE_API_TOKEN of the CLike stack',
    password: true,
    ignoreFocusOut: true,
    validateInput: (v) => (v && v.trim().length >= 32 ? null : 'At least 32 characters'),
  });
  if (token === undefined) return;
  await storeServiceToken(context, token);
  vscode.window.showInformationMessage('CLike: service token stored securely.');
}

async function cmdClearServiceToken(context) {
  await storeServiceToken(context, '');
  vscode.window.showInformationMessage('CLike: service token removed.');
}

async function cmdCopyExtensionMcpToken(context) {
  const token = await getExtensionMcpToken(context);
  await vscode.env.clipboard.writeText(token);
  vscode.window.showInformationMessage(
    `CLike: extension MCP token copied. Clients must send "Authorization: Bearer <token>" to ${extensionMcpState.url || 'the local MCP URL'}.`
  );
}

/**
 * CLike: Publish release — the release of the last passing /finalize (tag vN, notes, GitHub Release
 * on confirmation), for a finalize run before this existed or a publication declined at the time.
 */
async function cmdPublishRelease() {
  const ws = getWorkspaceRoot();
  const say = (text) => {
    out.appendLine(text);
    if (clikeChatPanel) clikeChatPanel.webview.postMessage({ type: 'echo', message: text });
    else vscode.window.showInformationMessage(text);
  };
  if (!ws) { say('CLike: open the project folder first.'); return; }
  const { finalizeDone, readFinalizeOutcome } = require('./finalize-outcome');
  if (!finalizeDone(ws.fsPath)) {
    const last = readFinalizeOutcome(ws.fsPath);
    say(`ℹ RELEASE: no passing /finalize for the current REQs${last?.status === 'failed' ? ` (the last one failed: ${last.reason})` : ''} — run /finalize first.`);
    return;
  }
  await offerRelease(ws, cfg(), '', null, say, { manual: true });
}

function activate(context) {
  const reg = (id, fn) => context.subscriptions.push(vscode.commands.registerCommand(id, () => fn(context)));
  //out.appendLine(`activate ${context}`);
  clikeExtensionContext = context;
  reportInvalidAgentModels();
  reportIgnoredWorkspaceSettings();
  const serviceAuthReady = initServiceAuth(context).catch((err) =>
    out.appendLine(`[CLike][auth] cannot load service token: ${err?.message || err}`)
  );
  // the status bar of a running command: back to the chat
  context.subscriptions.push(vscode.commands.registerCommand('clike.revealChat', () => {
    if (clikeChatPanel) clikeChatPanel.reveal(); else vscode.commands.executeCommand('clike.openChat');
  }));
  reg('clike.publishRelease', cmdPublishRelease);
  reg('clike.setServiceToken', cmdSetServiceToken);
  reg('clike.clearServiceToken', cmdClearServiceToken);
  reg('clike.copyExtensionMcpToken', cmdCopyExtensionMcpToken);
  reg('clike.chat.openSessionFile', cmdOpenChatSessionFile);
    reg('clike.harper.init', async () => {
    const panel = await cmdOpenChat(context); // reuse the existing open-chat
    try { panel.webview.postMessage({ type: 'prefill', text: '/init ' }); } catch {}
  });
  reg('clike.ping', () => cmdPing());
  reg('clike.codeAction', () => cmdCodeAction());
  reg('clike.chat.clearSession', cmdClearChatSession);
  reg('clike.applyUnifiedDiffHardened', cmdApplyUnifiedDiffHardened);
  reg('clike.applyUnifiedDiff', cmdApplyUnifiedDiff);
  reg('clike.applyNewContent', cmdApplyNewContent);
  reg('clike.applyLastPatch', cmdApplyLastPatch);
  reg('clike.addDocstring', cmdAddDocstring);
  reg('clike.refactor', cmdRefactor);
  reg('clike.generateTests', cmdGenerateTests);
  reg('clike.fixErrors', cmdFixErrors);

  reg('clike.openChat', cmdOpenChat);

  reg('clike.listModels', () => cmdListModels());
  reg('clike.checkServices', cmdCheckServices);
  reg('clike.ragReindex', () => cmdRagReindex());
  reg('clike.ragSearch', () => cmdRagSearch());

  reg('clike.gitCreateBranch', () => vscode.commands.executeCommand('git.createBranch'));
  reg('clike.gitCommitPatch', () => vscode.commands.executeCommand('git.commit'));
  reg('clike.gitOpenPR', () => vscode.commands.executeCommand('github.createPullRequest'));
  reg('clike.gitSmartPR', async () => { await vscode.commands.executeCommand('git.commit'); await vscode.commands.executeCommand('github.createPullRequest'); });


  reg('clike.promoteReqSources', async () => {
    const root = vscode.workspace.workspaceFolders?.[0]?.uri;
    if (!root) {
      vscode.window.showErrorMessage('No workspace folder open.');
      return;
    }
    await runPromotionFlow(root, null, out);
  });
  
  reg('clike.promoteReqSourcesQuick', async (reqId, strategy = 'folder') => {
    const root = vscode.workspace.workspaceFolders?.[0]?.uri;
    if (!root) {
      vscode.window.showErrorMessage('No workspace folder open.');
      return;
    }
    await promoteReqSources(root, reqId, strategy, out);
  });
  

  serviceAuthReady
    .then(() => startExtensionOperationalMcpServer(context))
    .catch((err) => out.appendLine(`[CLike][mcp-extension] start failed: ${err?.message || err}`));
  // an /autopilot interrupted by a closed window or a crash goes on by itself
  // the Memory panel: CLike's guide is indexed at start, again only when it changed
  reg('clike.openMemory', openMemory);
  serviceAuthReady.then(() => refreshGuideMemory());
  serviceAuthReady.then(() => setTimeout(() => {
    resumeInterruptedAutopilot().catch((err) => out.appendLine(`[autopilot] resume: ${err?.message || err}`));
  }, 20000));

  vscode.window.setStatusBarMessage('Clike: orchestrator+gateway integration ready', 2000);
}

// After a REQ's KIT is indexed, its files no longer in the KIT leave the memory (removed files,
// temporary copies indexed by earlier versions). Not when the collection hit its cap: the files past
// it are still in the KIT.
async function pruneKitMemory(projectId, reqId, items, maxFiles) {
  if (!items || !items.length || items.length >= maxFiles) return;
  try {
    const { orchestratorUrl } = cfg();
    const held = await postJson(`${orchestratorUrl}/v1/rag/sources`, { project_id: projectId });
    if (!held || held.ok === false) return;
    const stale = staleKitPaths(held.sources, reqId, items.map((i) => i.path));
    if (!stale.length) return;
    await postJson(`${orchestratorUrl}/v1/rag/purge`, { project_id: projectId, paths: stale });
    out.appendLine(`[harperRAG] ${reqId}: ${stale.length} file(s) no longer in the KIT removed from the memory`);
  } catch (e) {
    out.appendLine(`[harperRAG] ${reqId}: memory cleanup skipped (${e?.message || e})`);
  }
}

// The CLike guide in the Memory panel (memory-guide.js): its indexing state, shown by the panel.
let guideMemory = { status: 'idle' };
function refreshGuideMemory() {
  if (!clikeExtensionContext) return Promise.resolve(guideMemory);
  guideMemory = { status: 'indexing' };
  return ensureGuideIndexed({
    extensionRoot: clikeExtensionContext.extensionPath,
    state: clikeExtensionContext.globalState,
    post: postJson,
    orchestratorUrl: cfg().orchestratorUrl,
  }).then((r) => {
    guideMemory = r;
    out.appendLine(`[memory] CLike guide: ${r.status} (${r.files} files)${r.error ? ` ${r.error}` : ''}`);
    return r;
  }).catch((e) => {
    guideMemory = { status: 'failed', error: String(e?.message || e) };
    out.appendLine(`[memory] CLike guide indexing failed: ${guideMemory.error}`);
    return guideMemory;
  });
}

// The chat and the Memory panel are separate: each one only opens (or reveals) the other.
function revealOrOpenChat() {
  try {
    if (clikeChatPanel) { clikeChatPanel.reveal(); return; }
  } catch { /* disposed */ }
  vscode.commands.executeCommand('clike.openChat');
}

function openMemory() {
  return openMemoryPanel({
    context: clikeExtensionContext,
    extensionRoot: clikeExtensionContext.extensionPath,
    post: postJson,
    orchestratorUrl: () => cfg().orchestratorUrl,
    projectId: getProjectId,
    workspaceRoot: () => vscode.workspace.workspaceFolders?.[0]?.uri.fsPath || '',
    openChat: revealOrOpenChat,
    guide: { status: () => guideMemory, refresh: refreshGuideMemory },
    projectState: () => {
      const root = vscode.workspace.workspaceFolders?.[0]?.uri.fsPath;
      return root ? buildCockpitState(root, { methodology: (clikeExtensionContext.workspaceState.get(COCKPIT_PREFS_KEY) || {}).methodology }) : null;
    },
    ask: memoryAsk,
    copy: (text) => vscode.env.clipboard.writeText(text),
  });
}

// Ask (Memory panel): one free-mode turn, read-only, with the chat's execution choice — the cloud
// model through the orchestrator, or the local agent the chat uses. No session, no chat history.
async function memoryAsk(prompt) {
  const cur = clikeExtensionContext.workspaceState.get('clike.uiState') || {};
  const settings = cfg();
  const pref = normalizeExecutionPreference(cur.executionPreference || getDefaultExecutionPreference());
  let effectivePref = pref;
  let executor = null;
  if (executionPreferenceRequestsLocalAgent(pref)) {
    executor = resolveSelectedLocalAgentExecutor(settings, cur.localAgentExecutor || 'auto', 'free');
    if (!executor) {
      if (pref === 'local_agent_only') throw new Error('no local agent is available and Execution is "agent only"');
      effectivePref = 'cloud_only';
    }
  }
  const model = cur.model || 'auto';
  const provider = explicitProviderForModel(model) || '';
  const res = await postJson(`${settings.orchestratorUrl}/v1/chat`, {
    mode: 'free',
    project_id: getProjectId(),
    model,
    ...(provider ? { provider } : {}),
    messages: [{ role: 'user', content: prompt }],
    inline_files: [],
    rag_files: [],
    attachments: [],
    max_tokens: 1500,
    gen: { api: 'responses' },
    profileHint: computeProfileHint('free', model),
    executionPreference: effectivePref,
    localAgentExecutor: executor || normalizeLocalAgentExecutor(cur.localAgentExecutor || 'auto'),
    mode_contract: buildModeContract('free'),
  });
  if (res && res.ok === false && res.text) throw new Error(res.text);
  if (res && res.local_execution) {
    const answer = await runLocalChatAgent({ pkg: res, executorId: executor, settings, wsrootUri: getWorkspaceRoot(), out, session: null });
    return { text: answer.answer || answer.synthesis || '', by: answer.model ? `${answer.badge} · ${answer.model}` : answer.badge };
  }
  return { text: String(res?.text || res?.content || ''), by: `☁ ${res?.model || model}` };
}

function isTextFile(filePath) {
    const buffer    = Buffer.alloc(4096); // Read the first 4KB
    const fd        = fsSync.openSync(filePath, 'r');
    const bytesRead = fsSync.readSync(fd, buffer, 0, 4096, 0);
    fsSync.closeSync(fd);

    for (let i = 0; i < bytesRead; i++) {
        if (buffer[i] === 0) return false; // Found a null byte: it is BINARY
    }
    return true; // No null byte: it is TEXT
}


const COCKPIT_PREFS_KEY = 'clike.cockpit.prefs';
// messages that run a command: while one is in flight the layout is not reloaded
const LONG_CHAT_MESSAGES = new Set(['harperRun', 'harperEDD', 'harperInit', 'sendChat', 'sendGenerate', 'apply', 'autopilot', 'evalTools', 'ragIndex', 'ragSearch']);

const RUN_DURATIONS_KEY = 'clike.cockpit.durations';

/**
 * The run feed of the chat panel: the command in flight as the run card (every layout) and the
 * status bar show it — its real steps and their outcomes (run-tracker.js), the cycle of a --fix
 * loop, an estimate from earlier durations, the live progress of an eval in the sandbox (checks
 * n/N, regression REQs), what the agent is doing, the cost of the run and of the session.
 */
function createRunFeed(panel, context, post) {
  const settings = () => vscode.workspace.getConfiguration('clike');
  const tracker = createRunTracker({
    durations: context.workspaceState.get(RUN_DURATIONS_KEY) || {},
    maxCycles: Number(settings().get('autoEval.maxCycles', 2)) || 2,
    extraCycles: Number(settings().get('autoEval.extraCyclesOnProgress', 3)) || 0,
  });
  const session = { cost: 0, tokens: 0, runCost: 0, runTokens: 0 };
  const status = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Left, 50);
  status.command = 'clike.revealChat';
  let tick = null;
  let poll = null;
  let lastLiveAt = 0;
  let hideTimer = null;

  const executorLabel = () => {
    const st = context.workspaceState.get('clike.uiState') || {};
    const exec = normalizeExecutionPreference(st.executionPreference || getDefaultExecutionPreference());
    if (exec === 'cloud_only') return `cloud · ${st.model || 'auto'}`;
    const ex = normalizeLocalAgentExecutor(st.localAgentExecutor || getDefaultLocalAgentExecutor());
    return ex === 'claude_code' ? 'Claude Code' : ex === 'gpt_codex' ? 'Codex' : 'agent';
  };
  const mmss = (ms) => { const s = Math.max(0, Math.round(ms / 1000)); return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`; };

  function snapshot() {
    const snap = tracker.snapshot({
      stopAfterStep: harperStopAfterStep || !!(autopilotRun && autopilotRun.stopByCard),
      stopAfterReq: !!(autopilotRun && autopilotRun.stopAfterReq),
      session: { cost: session.cost, tokens: session.tokens },
      cost: { usd: session.runCost, tokens: session.runTokens },
    });
    if (snap && snap.kind === 'autopilot') {
      const ap = autopilotSnapshot();
      snap.autopilot = { current: ap.current, promoted: ap.promoted || [], parked: (ap.parked || []).map((p) => p.req_id), running: ap.running };
    }
    return snap;
  }

  function render() {
    const snap = snapshot();
    post({ type: 'runProgress', run: snap });
    if (!snap) return;
    if (!snap.ended) {
      const cur = snap.current;
      const ep = snap.evalProgress;
      const where = ep && ep.phase === 'checks' ? ` ${ep.checks_done}/${ep.checks_total}`
        : ep && ep.phase === 'regression' ? ` regression ${ep.regression_done}/${ep.regression_total}` : '';
      const cycle = snap.fix && snap.fix.cycle ? ` · cycle ${snap.fix.cycle}/${snap.fix.maxCycles}` : '';
      status.text = `$(sync~spin) ${cur ? `${cur.label}${cur.req ? ` ${cur.req}` : ''}${where}` : snap.title}${cycle} · ${mmss(Date.now() - snap.startedAt)} · ${snap.executor}`;
      status.tooltip = `CLike — ${snap.title}${snap.live ? `\n${snap.live}` : ''}\nClick: open the chat`;
      status.backgroundColor = undefined;
      status.show();
    }
  }

  function startTimers() {
    if (!tick) tick = setInterval(render, 1000);
    if (!poll) {
      poll = setInterval(async () => {
        const cur = tracker.current();
        const ws = getWorkspaceRoot();
        if (!cur || !ws || (cur.kind !== 'eval' && cur.kind !== 'gate') || !cur.req) return;
        try {
          if (tracker.evalProgress(await getEvalProgress(ws, cur.req))) render();
        } catch { /* the sandbox answers again at the next poll */ }
      }, 2000);
    }
  }

  function finish() {
    clearInterval(tick); tick = null;
    clearInterval(poll); poll = null;
    harperStopAfterStep = false;
    context.workspaceState.update(RUN_DURATIONS_KEY, tracker.durations()).then(undefined, () => {});
    const snap = snapshot();
    post({ type: 'runProgress', run: snap });
    if (snap && snap.ended) {
      const icon = { ok: '$(pass)', failed: '$(error)', cancelled: '$(circle-slash)' }[snap.ended.outcome] || '$(check)';
      status.text = `${icon} ${snap.title} · ${mmss(snap.ended.at - snap.startedAt)}`;
      status.show();
      clearTimeout(hideTimer);
      hideTimer = setTimeout(() => status.hide(), 15000);
    }
  }

  /** Around every chat handler call (nested ones included): the run's steps. */
  async function around(msg, fn) {
    const token = tracker.begin(msg, { executor: executorLabel() });
    if (token.started) {
      harperStopAfterStep = false;
      session.runCost = 0;
      session.runTokens = 0;
      clearTimeout(hideTimer);
      startTimers();
    }
    if (token.step) render();
    try {
      return await fn();
    } finally {
      const ended = tracker.end(token, msg, { cancelled: !!token.step && harperCancelled() });
      if (ended) finish(); else if (token.step) render();
    }
  }

  panel.onDidDispose(() => { clearInterval(tick); clearInterval(poll); clearTimeout(hideTimer); status.dispose(); });

  return {
    around,
    render,
    // the echoes of the handlers: the run card's "now" line
    observe(message) {
      if (!message || !tracker.active()) return;
      if ((message.type === 'echo' || message.type === 'error') && message.message) {
        const text = typeof message.message === 'string' ? message.message : String(message.message);
        if (message.type === 'error' ? tracker.error(text) : tracker.live(text)) render();
      }
    },
    // what a local agent does in a Harper phase (tool used, text written), at most 4 per second
    live(text) {
      if (Date.now() - lastLiveAt < 250) return;
      lastLiveAt = Date.now();
      if (tracker.live(text)) render();
    },
    cost(telemetry) {
      const t = telemetry || {};
      const usd = Number(t.pricing && t.pricing.total_cost);
      const u = t.usage || {};
      const tokens = ['input_tokens', 'output_tokens', 'cache_read_input_tokens', 'cache_creation_input_tokens']
        .reduce((sum, k) => sum + (Number(u[k]) || 0), 0);
      if (Number.isFinite(usd) && usd > 0) { session.cost += usd; session.runCost += usd; }
      session.tokens += tokens;
      session.runTokens += tokens;
      render();
    },
  };
}

/**
 * The feed of the chat's cockpit: the project state (cockpit-state.js), the agent and its models,
 * the cockpit preferences (methodology), the eval tools catalog for the autocompletion. Posted as
 * `cockpitState` to every layout (the autocompletion uses it everywhere); refreshed when plan.json,
 * the Harper documents or the eval/gate reports change, and after each chat message.
 */
function createCockpitFeed(panel, context, runs = null) {
  let timer = null;
  let inflight = 0;
  let pendingTheme = false;
  let catalog = { at: 0, tools: [], anthropic: [] };
  const disposables = [];

  const prefs = () => {
    const p = context.workspaceState.get(COCKPIT_PREFS_KEY) || {};
    return { methodology: p.methodology === 'bmad' ? 'bmad' : '', roles: p.roles && typeof p.roles === 'object' ? p.roles : {} };
  };

  // model ids and eval tools: fetched at most every 5 minutes, never blocking the state
  async function refreshCatalog() {
    if (Date.now() - catalog.at < 5 * 60 * 1000) return;
    catalog.at = Date.now();
    try {
      const res = await fetchJson(`${serviceBaseUrls().orchestrator}/v1/models`);
      const models = (Array.isArray(res?.models) ? res.models : []).filter((m) => m && m.enabled !== false && !/embed/i.test(String(m.name || m.id || '')));
      const names = (provider) => [...new Set(models.filter((m) => String(m.provider || '').toLowerCase() === provider)
        .map((m) => String(m.remote_name || m.name || '').trim()).filter(Boolean))];
      catalog.anthropic = names('anthropic');
    } catch (err) { log(`[cockpit] model catalog unavailable: ${err?.message || err}`); }
    try {
      const ws = getWorkspaceRoot();
      if (ws) catalog.tools = Object.keys((await getEvalTools(ws))?.catalog || {}).sort();
    } catch (err) { log(`[cockpit] eval tools catalog unavailable: ${err?.message || err}`); }
  }

  function agentInfo() {
    const c = vscode.workspace.getConfiguration('clike');
    const state = context.workspaceState.get('clike.uiState') || {};
    return {
      executor: normalizeLocalAgentExecutor(state.localAgentExecutor || getDefaultLocalAgentExecutor()),
      execution: state.executionPreference || getDefaultExecutionPreference(),
      claude_model: c.get('claudeCode.model', 'opus') || '',
      codex_model: c.get('localAgent.codex.model', 'gpt-5.5') || '',
      // the models each CLI accepts (as /agent-model list): Codex those of its login, never the cloud
      // catalog's API ids (Codex refuses them); Claude the tier aliases and the catalog's ids
      models: {
        claude: [...new Set([...CLAUDE_ALIASES.filter((a) => a !== 'default'), ...catalog.anthropic.filter((n) => /^claude-/.test(n) && !/\d{8}$/.test(n))])],
        codex: readCodexModelSlugs() || [],
      },
    };
  }

  async function post() {
    timer = null;
    const ws = getWorkspaceRoot();
    let project = null;
    if (ws) {
      try { project = buildCockpitState(ws.fsPath, { methodology: prefs().methodology }); } catch (err) { log(`[cockpit] state: ${err?.message || err}`); }
    }
    await refreshCatalog();
    panel.webview.postMessage({
      type: 'cockpitState',
      state: { project, agent: agentInfo(), prefs: prefs(), tools: catalog.tools, theme: getChatTheme(), running: inflight > 0, history: history() },
    });
    if (pendingTheme && inflight === 0) reloadTheme();
  }

  function refresh(delay = 300) {
    if (timer) clearTimeout(timer);
    timer = setTimeout(() => post().catch((err) => log(`[cockpit] post: ${err?.message || err}`)), delay);
  }

  // the conversations of the current mode (chat-history.js): the current one and the archived ones
  function currentMode() {
    return (context.workspaceState.get('clike.uiState') || {}).mode || 'free';
  }
  function history() {
    if (!getWorkspaceRoot()) return null;
    try { return { mode: currentMode(), ...chatHistory.listConversations(sessionsDirUri().fsPath, currentMode()) }; } catch { return null; }
  }
  async function rehydrate() {
    const ui = context.workspaceState.get('clike.uiState') || {};
    const mode = ui.mode || 'free';
    const msgs = effectiveHistoryScope(context) === 'allModels'
      ? await loadSession(mode, 200).catch(() => [])
      : await loadSessionFilteredV2(mode, ui.model || 'auto', 200).catch(() => []);
    panel.webview.postMessage({ type: 'hydrateSession', messages: msgs });
  }

  // a new layout: the webview is rebuilt (cronology and state come back with webview_ready)
  function reloadTheme() {
    if (inflight > 0 || clikeHarperBlockingRun || autopilotRun) { pendingTheme = true; return; }
    pendingTheme = false;
    panel.webview.html = getWebviewHtml(serviceBaseUrls().orchestrator, getChatTheme());
  }

  async function handle(msg) {
    if (msg.type === 'cockpitRefresh') { if (runs) runs.render(); return refresh(0); }
    // the run card: stop after the current step (or after the current REQ of the autopilot), or undo it
    if (msg.type === 'cancelAfterStep') {
      // the autopilot stops at its own step boundary (kit, eval --fix, gate): stopping the --fix
      // loop inside would read as a failure and park the REQ
      if (autopilotRun) {
        if (!autopilotRun.stop) { autopilotRun.stop = 'graceful'; autopilotRun.stopByCard = true; }
      } else {
        harperStopAfterStep = true;
      }
      if (runs) runs.render();
      return undefined;
    }
    if (msg.type === 'cancelAfterReq') {
      if (autopilotRun) autopilotRun.stopAfterReq = true;
      if (runs) runs.render();
      return undefined;
    }
    if (msg.type === 'cancelUndoStop') {
      harperStopAfterStep = false;
      if (autopilotRun) {
        if (autopilotRun.stopByCard && autopilotRun.stop === 'graceful') autopilotRun.stop = null;
        autopilotRun.stopByCard = false;
        autopilotRun.stopAfterReq = false;
      }
      if (runs) runs.render();
      return undefined;
    }
    if (msg.type === 'showChanges') return vscode.commands.executeCommand('workbench.view.scm');
    // history of conversations: never while a command runs (the webview disables it too)
    if (['historyNew', 'historyOpen', 'historyDelete'].includes(msg.type)) {
      if (inflight > 0 || clikeHarperBlockingRun || autopilotRun) return undefined;
      const dir = sessionsDirUri().fsPath;
      const mode = currentMode();
      try {
        if (msg.type === 'historyNew') {
          chatHistory.archiveCurrent(dir, mode);
          // the agent too starts a new conversation in this mode (as /agent-session new)
          const sessions = context.workspaceState.get('clike.agentSessions') || {};
          await context.workspaceState.update('clike.agentSessions',
            Object.fromEntries(Object.entries(sessions).filter(([key]) => !key.startsWith(`${mode}:`))));
        } else if (msg.type === 'historyOpen') {
          chatHistory.openConversation(dir, mode, String(msg.id || ''));
        } else {
          chatHistory.deleteConversation(dir, mode, String(msg.id || ''));
        }
      } catch (err) {
        vscode.window.showWarningMessage(`CLike history: ${err?.message || err}`);
      }
      if (msg.type !== 'historyDelete') await rehydrate();
      return refresh(0);
    }
    if (msg.type === 'copyText') return vscode.env.clipboard.writeText(String(msg.text || ''));
    if (msg.type === 'openMemory') return vscode.commands.executeCommand('clike.openMemory');
    if (msg.type === 'cockpitPrefs') {
      const next = { methodology: msg.methodology === 'bmad' ? 'bmad' : '', roles: msg.roles && typeof msg.roles === 'object' ? msg.roles : {} };
      await context.workspaceState.update(COCKPIT_PREFS_KEY, next);
      return refresh(0);
    }
    if (msg.type === 'setTheme') {
      const theme = String(msg.theme || '');
      if (!CHAT_THEMES.includes(theme)) return undefined;
      const c = vscode.workspace.getConfiguration('clike');
      const where = c.inspect('chat.theme');
      // the scope the developer already uses for it; User settings otherwise
      const target = where?.workspaceFolderValue !== undefined ? vscode.ConfigurationTarget.WorkspaceFolder
        : where?.workspaceValue !== undefined ? vscode.ConfigurationTarget.Workspace : vscode.ConfigurationTarget.Global;
      await c.update('chat.theme', theme, target);
      return undefined; // the configuration listener reloads the layout
    }
    return undefined;
  }

  const watch = (glob) => {
    const ws = getWorkspaceRoot();
    if (!ws) return;
    const w = vscode.workspace.createFileSystemWatcher(new vscode.RelativePattern(ws, glob));
    w.onDidCreate(() => refresh()); w.onDidChange(() => refresh()); w.onDidDelete(() => refresh());
    disposables.push(w);
  };
  ['docs/harper/*.{md,json}', 'docs/inputs/*', 'runs/{eval,gate}/*/report_*.json', 'runs/kit/*/ci/LTC.json'].forEach(watch);
  disposables.push(vscode.workspace.onDidChangeConfiguration((e) => {
    if (e.affectsConfiguration('clike.chat.theme')) reloadTheme();
    else if (e.affectsConfiguration('clike')) refresh();
  }));
  panel.onDidDispose(() => { if (timer) clearTimeout(timer); disposables.forEach((d) => d.dispose()); });

  return {
    handles: (type) => ['cockpitRefresh', 'cockpitPrefs', 'setTheme', 'copyText', 'openMemory', 'cancelAfterStep', 'cancelAfterReq', 'cancelUndoStop', 'showChanges',
      'historyNew', 'historyOpen', 'historyDelete'].includes(type),
    handle,
    refresh,
    track(type, promise) {
      if (!LONG_CHAT_MESSAGES.has(type)) return promise;
      inflight += 1;
      return Promise.resolve(promise).finally(() => { inflight -= 1; });
    },
  };
}

async function cmdOpenChat(context) {
  out.appendLine(`cmdOpenChat ${context}`);
  const panel = vscode.window.createWebviewPanel(
    'clikeChat',
    'CLike Chat',
    vscode.ViewColumn.Beside,
    { enableScripts: true, retainContextWhenHidden: true }
  );

  clikeChatPanel = panel;

  const originalPostMessage = panel.webview.postMessage.bind(panel.webview);
  // the run card's "now" line: what the handlers say while a command runs
  let runObserver = null;
  panel.webview.postMessage = (message, ...args) => {
    try { if (runObserver) runObserver(message); } catch { /* best effort */ }
    try {
      if (
        message &&
        message.type === 'busy' &&
        message.on === false &&
        clikeHarperBlockingRun &&
        message.force !== true
      ) {
        out.appendLine('[CLike][busy] suppressed premature busy=false during Harper blocking run');
        return Promise.resolve(true);
      }
    } catch {
      // Fall through to the original postMessage.
    }

    return originalPostMessage(message, ...args);
  };

  panel.onDidDispose(() => {
    if (clikeChatPanel === panel) {
      clikeChatPanel = null;
      clikeRunChatMessage = null;
    }
  });
  const orchestratorUrl = serviceBaseUrls().orchestrator;
  const chatTheme = getChatTheme()
  panel.webview.html = getWebviewHtml(orchestratorUrl, chatTheme);
  panel.webview.postMessage({ type: 'busy', on: false });
  // Initial state (mode/model)
  const savedState = context.workspaceState.get('clike.uiState') || {
    mode: 'free',
    model: 'auto',
    historyScope: 'singleModel',
    executionPreference: getDefaultExecutionPreference(),
    localAgentExecutor: getDefaultLocalAgentExecutor(),
  };
  savedState.historyScope = effectiveHistoryScope(context);
  savedState.executionPreference = reconcileExecutionPreference(
    savedState.executionPreference,
    getDefaultExecutionPreference()
  );
  savedState.localAgentExecutor = normalizeLocalAgentExecutor(
    savedState.localAgentExecutor || getDefaultLocalAgentExecutor()
  );
  // Persist the reconciled state so the value used at runtime (harperRun reads
  // workspaceState) matches the value shown in the selector from the first
  // command, without requiring the user to touch the Execution dropdown.
  await context.workspaceState.update('clike.uiState', savedState);
  panel.webview.postMessage({ type: 'initState', state: savedState });
  out.appendLine(`cmdOpenChat savedState done`);

  // HYDRATE per MODE (not per model)
  // Hydrate chat from the FS for the selected model
  try {
    
    const scope = effectiveHistoryScope(context);
    const modeCur  = savedState?.mode  ?? 'free';
    const modelCur = savedState?.model ?? 'auto';

    const msgs = (scope === 'allModels')
      ? await loadSession(modeCur).catch(() => [])
      : await loadSessionFilteredV2(modeCur, modelCur, 200).catch(() => []);

    panel.webview.postMessage({ type: 'hydrateSession', messages: msgs });

    out.appendLine(`cmdOpenChat msgs done`);
    panel.webview.postMessage({ type: 'hydrateSession', messages: msgs });
    out.appendLine(`cmdOpenChat postMessage done`);
  
  }  catch (e) {
    out.appendLine(`cmdOpenChat: ${e.message}`);
  }
  
  // Last run for Apply
  const lastRun = context.workspaceState.get('clike.lastRun');
  if (lastRun) panel.webview.postMessage({ type: 'lastRun', data: lastRun });
  // Listen to events from the webview
  out.appendLine(`cmdOpenChat lastRun  ${lastRun}`);
  if (lastRun) panel.webview.postMessage({ type: 'lastRun', data: lastRun });

  // After creating the panel and before returning:
  await showInitSummaryIfPresent(panel, context);

  
  

  // Listen to events from the webview
  // Named so the auto-eval loop can chain KIT repair and eval through the same handlers.
  const handleWebviewMessageCore = async (msg) => {
    panel.webview.postMessage({ type: 'busy', on: true });
    const stale = extensionFreshness(msg && msg.type);
    if (stale) {
      panel.webview.postMessage({ type: 'echo', message: `⚠ ${stale}` });
      vscode.window.showWarningMessage(stale, 'Reload Window').then((pick) => {
        if (pick === 'Reload Window') vscode.commands.executeCommand('workbench.action.reloadWindow');
      });
    }

    try {
      const state = context.workspaceState.get('clike.uiState') || {
        mode: 'free',
        model: 'auto',
        historyScope: 'singleModel',
        executionPreference: getDefaultExecutionPreference(),
        localAgentExecutor: getDefaultLocalAgentExecutor(),
      };
      
      const cur = context.workspaceState.get('clike.uiState') || { mode: 'free', model: 'auto' };
      const activeMode  = msg.mode  || cur.mode  || 'free';
      const activeModel = msg.model || cur.model || 'auto';

      if (msg.type === 'adopt') {
        // /adopt: an existing project brought into CLike (adopt.js). Deterministic, no model: the same
        // for cloud and local agents. Writes only CLike's files: .clike/project.json, runs/adopt/, the report.
        // every line of /adopt in the chat and in its history (one write at a time): a reload keeps the outcome
        let saved = Promise.resolve();
        const say = (text) => {
          panel.webview.postMessage({ type: 'echo', message: text });
          // the chat shows the history of the model it uses: the lines are saved under it
          const model = (context.workspaceState.get('clike.uiState') || {}).model || 'auto';
          saved = saved.then(() => appendSessionJSONL('harper', { ts: Date.now(), role: 'system', content: text, model, attachments: [] })).catch(() => {});
        };
        const done = () => panel.webview.postMessage({ type: 'busy', on: false, force: true });
        // what /adopt wrote, in the Files tab (the report opened in the editor)
        const showFiles = (root, rels, open = '') => {
          panel.webview.postMessage({ type: 'files', data: rels.filter((r) => fsSync.existsSync(path.join(root, ...r.split('/')))).map((r) => ({ path: r })), activate: true });
          // a report to read, not to edit: the Markdown preview (read-only), beside the chat
          if (open) {
            const uri = vscode.Uri.file(path.join(root, ...open.split('/')));
            const show = /\.md$/i.test(open)
              ? vscode.commands.executeCommand('markdown.showPreview', uri)
              : vscode.window.showTextDocument(uri, { preview: true, preserveFocus: true });
            Promise.resolve(show).then(() => {}, () => {});
          }
        };
        const ws = getWorkspaceRoot();
        let guard = null;
        const ownFiles = {};
        // CLike never changes a project file: what changed outside its own files and the root README while
        // /adopt ran (an editor, another agent working in the project, or the run) is reported, left as it is
        const reported = new Set();
        const restoreProject = () => {
          let changed = [];
          if (guard) {
            try { changed = adoptLib.guardChanges(ws.fsPath, guard).filter((rel) => !reported.has(rel)); } catch (e) { say(`⚠ /adopt: the project files could not be checked (${String(e?.message || e).slice(0, 200)}).`); }
          }
          for (const rel of changed) reported.add(rel);
          if (changed.length) {
            say(`ℹ /adopt: ${changed.length} project file(s) changed while the adoption ran — left as they are (CLike never changes them; ` +
              `if one is not yours, the adoption's agent wrote it: git diff shows it): ${changed.slice(0, 10).join(', ')}${changed.length > 10 ? ', …' : ''}.`);
          }
          // the survey report and the code map are CLike's own documents: a run that changed them gets them back
          const own = [];
          for (const [rel, text] of Object.entries(ownFiles)) {
            const abs = path.join(ws.fsPath, ...rel.split('/'));
            let now = null;
            try { now = fsSync.readFileSync(abs, 'utf8'); } catch { /* deleted */ }
            if (now !== text) { fsSync.mkdirSync(path.dirname(abs), { recursive: true }); fsSync.writeFileSync(abs, text); own.push(rel); }
          }
          if (own.length) say(`ℹ /adopt: CLike's ${own.join(' and ')} put back as CLike wrote them.`);
        };
        try {
          if (!ws) { say('✖ /adopt: open the project folder in VS Code first.'); return done(); }
          const root = ws.fsPath;
          const projectPath = path.join(root, '.clike', 'project.json');
          if (!fsSync.existsSync(projectPath)) { say('ℹ /adopt: run /init first — it adds CLike to this folder, in place, keeping every file.'); return done(); }
          guard = adoptLib.guardSnapshot(root);
          if (!guard) say('ℹ /adopt: no git here — CLike writes only docs/harper/, .clike/, runs/ and the root README; a change elsewhere cannot be reported.');
          await appendSessionJSONL('harper', { ts: Date.now(), role: 'user', content: `▶ ADOPT${msg.area ? ` --area ${msg.area}` : ''}${msg.dryRun ? ' --dry-run' : ''}`, model: (context.workspaceState.get('clike.uiState') || {}).model || 'auto', attachments: [] });
          say('▶ /adopt: survey of the project (areas, stack, roots, commands, runtimes, CI, documentation, git)…');
          const found = adoptLib.survey(root);
          // the areas as .clike/project.json has them (what the developer corrected or declared stays and is used)
          let meta = {};
          try { meta = JSON.parse(fsSync.readFileSync(projectPath, 'utf8')); } catch { /* template */ }
          const mergedMeta = adoptLib.mergeProjectAreas(meta, found.areas);
          found.areas = adoptLib.effectiveAreas(found.areas, mergedMeta.areas);
          const area = String(msg.area || '').trim();
          const picked = area ? found.areas.filter((a) => a.root === area || a.name === area) : found.areas;
          if (area && !picked.length) {
            say(`✖ /adopt: no area "${area}". Areas: ${found.areas.map((a) => `${a.name} (${a.root})`).join(', ') || 'none'}.`);
            return done();
          }
          say(`ℹ /adopt: ${found.areas.length} area(s) — ${found.areas.map((a) => `${a.root} (${a.stack})`).join(', ') || 'the repository root is one project'}; ` +
            `${found.docs.length} document(s); ${found.ci.length} CI workflow(s); ${found.git ? `${found.git.commits} commit(s)` : 'no git'}.`);
          const reportRel = `docs/harper/ADOPT_${new Date().toISOString().slice(0, 10)}.md`;
          const writeReport = (opts) => {
            fsSync.mkdirSync(path.join(root, 'docs', 'harper'), { recursive: true });
            fsSync.writeFileSync(path.join(root, ...reportRel.split('/')), adoptLib.reportMarkdown(found, { area, ...opts }));
          };
          if (msg.dryRun) {
            writeReport({ dryRun: true });
            say(`✔ /adopt --dry-run: report ${reportRel} (nothing else written).`);
            showFiles(root, [reportRel], reportRel);
            return done();
          }
          // the areas, in CLike's own settings (a root or command the developer corrected stays)
          fsSync.writeFileSync(projectPath, `${JSON.stringify(mergedMeta, null, 2)}\n`);
          // the baseline: the checks each (picked) area already has, as its team runs them, in the sandbox
          let baseline = null;
          const profile = adoptLib.baselineProfile(picked);
          if (profile.checks.length) {
            const full = path.join(root, ...adoptLib.BASELINE_PROFILE.split('/'));
            fsSync.mkdirSync(path.dirname(full), { recursive: true });
            fsSync.writeFileSync(full, `${JSON.stringify(profile, null, 2)}\n`);
            say(`▶ /adopt: baseline in the CLike eval sandbox — ${profile.checks.map((c) => c.id).join(', ')} (installs and test suites: minutes)…`);
            try {
              await ensureToolsForEval(null, { profile: adoptLib.BASELINE_PROFILE });
              baseline = await postEvalChecks(adoptLib.BASELINE_PROFILE, ws, adoptLib.BASELINE_ID, []);
              say(`${baseline?.passed ? '✔' : 'ℹ'} /adopt baseline: ${(baseline?.cases || []).filter((c) => !String(c.name).startsWith('env::')).map((c) => `${c.name} ${c.passed ? 'PASS' : 'FAIL'}`).join(', ')}`);
            } catch (e) {
              say(`⚠ /adopt: the baseline could not run (${String(e?.message || e).slice(0, 300)}); the report says so.`);
            }
          }
          // the code map of every area (the contracts between them too): what exists, by the code
          const mapped = adoptLib.codeMaps(root, found.areas);
          fsSync.mkdirSync(path.join(root, 'docs', 'harper'), { recursive: true });
          fsSync.writeFileSync(path.join(root, ...adoptLib.CODEMAP.split('/')), `${mapped.markdown}\n`);
          // the project memory: the documentation, the code map and the code of the areas adopted now —
          // a cloud model and every later phase cite them by path (a local agent reads the files too)
          let indexed = 0;
          const docItems = adoptLib.memoryItems(root, [...found.docs, adoptLib.CODEMAP]);
          const items = [...docItems, ...adoptLib.sourceItems(root, picked)];
          say(`▶ /adopt: project memory — ${docItems.length} document(s) and ${items.length - docItems.length} source file(s)…`);
          for (let i = 0; i < items.length;) {
            // batches of at most 40 files and ~1.5M characters
            const batch = [];
            let chars = 0;
            while (i < items.length && batch.length < 40 && (chars === 0 || chars + items[i].text.length <= 1500000)) { chars += items[i].text.length; batch.push(items[i]); i += 1; }
            let res = null;
            try {
              const r = await serviceRequest('POST', `${cfg().orchestratorUrl}/v1/rag/index`, { body: { project_id: getProjectId(), items: batch }, timeoutMs: 600000 });
              if (!r.ok) throw new Error(`${r.status} ${String(r.text || '').slice(0, 200)}`);
              res = r.json();
              if (res && res.ok === false) throw new Error(res.error || res.error_type || 'the index was skipped');
            } catch (e) {
              say(`⚠ /adopt: project memory indexing stopped at ${indexed}/${items.length} (${String(e?.message || e).slice(0, 200)}).`);
              break;
            }
            indexed += batch.length;
          }
          writeReport({ baseline, indexed });
          const message = `✔ /adopt survey: areas in .clike/project.json, code map ${adoptLib.CODEMAP}, ${indexed}/${items.length} file(s) in the project memory, ` +
            `baseline ${baseline ? String(baseline.status || (baseline.passed ? 'PASS' : 'FAIL')) : 'not run'}. Report ${reportRel}.`;
          say(message);
          showFiles(root, [reportRel, adoptLib.CODEMAP, '.clike/project.json', adoptLib.BASELINE_PROFILE], reportRel);
          // the analysis: the Harper documents as the project is, the capability REQs — by the model the chat
          // uses (cloud or local agent), through the same cascade as /idea --extend
          const planPath = path.join(root, 'docs', 'harper', 'plan.json');
          let plan = {};
          try { plan = JSON.parse(fsSync.readFileSync(planPath, 'utf8')); } catch { /* the /init template or none */ }
          const notAdoptable = adoptLib.adoptablePlan(plan, picked);
          if (notAdoptable) {
            say(`ℹ /adopt: no analysis — ${notAdoptable}.`);
            return done();
          }
          if (!picked.length) {
            say('ℹ /adopt: no area to analyse (the repository root is one project): declare it as an area in .clike/project.json, then run /adopt again.');
            return done();
          }
          // a run that stopped before its analysis left the baseline REQ of the area: written anew
          const kept = adoptLib.keptReqs(plan, picked);
          const base = adoptLib.baselineReqs(picked, baseline, kept);
          fsSync.mkdirSync(path.dirname(planPath), { recursive: true });
          fsSync.writeFileSync(planPath, `${JSON.stringify({ ...plan, snapshot: { total: kept.length + base.reqs.length }, reqs: [...kept, ...base.reqs] }, null, 2)}\n`);
          for (const [id, ltc] of Object.entries(base.ltcs)) {
            const p = path.join(root, 'runs', 'kit', id, 'ci', 'LTC.json');
            fsSync.mkdirSync(path.dirname(p), { recursive: true });
            fsSync.writeFileSync(p, `${JSON.stringify(ltc, null, 2)}\n`);
          }
          for (const rel of [reportRel, adoptLib.CODEMAP]) {
            try { ownFiles[rel] = fsSync.readFileSync(path.join(root, ...rel.split('/')), 'utf8'); } catch { /* not written */ }
          }
          say(`▶ /adopt: analysis of ${picked.map((a) => a.name).join(', ')} — IDEA, SPEC (with use cases), PLAN with the capability REQs, TECH_CONSTRAINTS, lane guides, HOWTO_RUN and the root README integrated (baseline REQs ${base.reqs.map((r) => r.id).join(', ')} already written)…`);
          done();
          await clikeRunChatMessage({
            type: 'harperRun', cmd: 'extend', extendMode: 'adopt', attachments: [],
            __adopt: {
              areas: picked, baselineIds: base.reqs.map((r) => r.id), surveyReport: reportRel, baseline, restoreProject,
              // a second area adds to the documents of the first: what they say stays, the team's README lines too
              adoptedBefore: adoptLib.adoptedAreas({ reqs: kept }), originalReadme: adoptLib.originalReadme(root),
              documents: adoptLib.contextDocuments(root, found, picked, reportRel, 6000, { maps: mapped.maps }),
            },
          });
          restoreProject();
          return;
        } catch (e) {
          say(`✖ /adopt failed: ${String(e?.message || e)}`);
        }
        restoreProject();
        return done();
      }

      if (msg.type === 'harperInit') {
        try {
          let name = (msg.name || '').trim();
          const passedPath = (msg.path || '').trim();   // optional positional
          let force = !!msg.force;
          // /init with no parameters: the folder open in VS Code, in place (as /init <name> <parent> --force)
          if (!name && getWorkspaceRoot()) {
            name = path.basename(getWorkspaceRoot().fsPath);
            msg.__inPlace = true;
            force = true;
          }
          out.appendLine(`[harperInit] recv name: ${name} path ${passedPath} force ${force}`);

          out.appendLine(`[harperInit] recv name: ${(!name)}`);

          if (!name) {
            panel.webview.postMessage({ type: 'error', message: 'Project name is required: /init <project_name> [<path>] [--force]' });
            panel.webview.postMessage({ type: 'busy', on: false });
            return;
          }
          const projectId = String(name)
            .trim()
            .toLowerCase()
            .replace(/[^a-z0-9]+/g, '')
            .replace(/^-+|-+$/g, '');

          if (!projectId) {
            panel.webview.postMessage({ type: 'error', message: 'Unable to derive a valid project_id from project name.' });
            panel.webview.postMessage({ type: 'busy', on: false });
            return;
          }

          const templateVars = {
            '${project.name}': name,
            '${project.id}': projectId,
            '${project.rag_namespace}': projectId,
          };

          // choose the parent folder (MCP: the open workspace itself, initialized in place)
          let parentUri = null;
          if (msg.__inPlace) {
            parentUri = vscode.Uri.file(path.dirname(getWorkspaceRoot().fsPath));
          } else if (passedPath) {
            parentUri = vscode.Uri.file(path.resolve(passedPath));
          } else {
            const pick = await vscode.window.showOpenDialog({
              canSelectFiles: false, canSelectFolders: true, canSelectMany: false,
              openLabel: 'Select parent folder for new workspace'
            });
            if (!pick || !pick.length) {
              panel.webview.postMessage({ type: 'busy', on: false });
              return;
            }
            parentUri = pick[0];
          }

          const targetDir = path.join(parentUri.fsPath, name);
          const exists = await pathExists(targetDir);
          if (exists && !(await isDirEmpty(targetDir)) && !force) {
            panel.webview.postMessage({ type: 'error', message: `Target not empty: ${targetDir}. Use --force to add CLike to it (existing files are kept).` });
            panel.webview.postMessage({ type: 'busy', on: false });
            return;
          }

          // a repository with its own review / PR / CI process keeps it: CLike's become proposals
          const processRedirect = teamProcessRedirect(targetDir);
          // folder structure
          const docRoot = path.join(targetDir, 'docs', 'harper');
          await ensureDir(path.join(targetDir, '.clike'));

          await ensureDir(path.join(targetDir, 'runs'));
          await ensureDir(docRoot);

          // Copy template files
          //const extRoot = vscode.extensions.getExtension('publisher.clike').extensionPath;
          const extRoot = context.extensionPath;
          
          const templatesDir = path.join(extRoot, 'templates', 'harper-init');
          // Never overwrites: in a non-empty folder (--force) only the missing template files are added.
          const copied = copyTemplateTree(templatesDir, targetDir, { vars: templateVars, isText: isTextFile, redirect: processRedirect });
          if (copied.proposed.length) {
            panel.webview.postMessage({ type: 'echo', message: `ℹ /init: the repository already has its own review / PR / CI process, so CLike did not add ${copied.proposed.join(', ')} — they are proposals in ${PROPOSALS_DIR}/ (copy them if you want them).` });
          }
          if (copied.kept.length) {
            out.appendLine(`[harperInit] kept ${copied.kept.length} existing file(s): ${copied.kept.join(', ')}`);
            panel.webview.postMessage({ type: 'echo', message: `ℹ /init kept ${copied.kept.length} existing file(s) unchanged (${copied.kept.slice(0, 8).join(', ')}${copied.kept.length > 8 ? ', …' : ''})` });
          }

          // file seed: an existing .gitignore keeps its rules and gets only the missing CLike ones
          const gitignorePath = path.join(targetDir, '.gitignore');
          const clikeIgnoreRules = [
            // no indentation: a leading space is part of a .gitignore pattern
            'node_modules/',
            'dist/',
            '.vscode/',
            '.env',
            '.env.*',
            '!.env.example',
            // runs/kit/<REQ>/ is committed by the phase commits (the REQ candidate): only the
            // eval scratch, installed dependencies and temporary stages are ignored
            'runs/eval/',
            'runs/context/',
            'runs/**/node_modules/',
            'runs/**/.tmp/',
            'runs/**/.npm-cache/',
            'runs/**/.venv/',
            // eval outputs, rewritten at every run: tracked, they keep the tree dirty and block
            // the switch to the next REQ branch
            'runs/**/ci/reports/',
            'runs/**/reports/',
            'local-eval-workspaces/',
            '*.log',
            // CLike local state: chat sessions and telemetry stay on this machine
            '.clike/sessions/',
            '.clike/telemetry/',
            // eval checks served to a local agent during a repair (removed when it ends)
            '.clike/eval-check/',
            '.clike/bin/',
            // the /init hand-off (it names the folder of this machine): local, never in the repository
            '.clike/last_init_summary*.json',
          ];
          const existingIgnore = fsSync.existsSync(gitignorePath) ? fsSync.readFileSync(gitignorePath, 'utf8') : null;
          await writeFileUtf8(gitignorePath, mergeGitignore(existingIgnore, clikeIgnoreRules).text);

          // handoff for the bubble in the new workspace
          const summary = {
            project_name: name,
            created_at: nowIso(),
            targetDir,
            doc_root: 'docs/harper',
            files_created: [
              'README.md',
              '.gitignore',
              '.clike/policy.yaml',
              '.clike/capabilities.yaml',
              '.clike/context.yaml',
              'docs/inputs/',
              'docs/harper/ux/',
              'docs/reference/',
              '.clike/project.json',
              '.clike/skills/local-cloud-parity/SKILL.md',
              '.clike/skills/eval-contract-writer/SKILL.md',
              '.clike/skills/gate-risk-reviewer/SKILL.md',
              '.clike/skills/vendor/bmad/README.md',
              '.clike/skills/vendor/bmad/manifest.json',
              '.clike/skills/vendor/bmad/prd-shaping/SKILL.md',
              '.clike/skills/vendor/bmad/epic-framing/SKILL.md',
              '.clike/skills/vendor/bmad/acceptance-modeling/SKILL.md',
              '.clike/skills/vendor/bmad/ux-flow-modeling/SKILL.md',
              '.clike/skills/vendor/bmad/architecture-readiness/SKILL.md',
              '.clike/skills/vendor/bmad/story-readiness/SKILL.md',
              '.clike/skills/vendor/bmad/dev-story-execution/SKILL.md',
              '.clike/skills/vendor/bmad/qa-risk-review/SKILL.md',
              '.clike/skills/vendor/bmad/release-narrative/SKILL.md',
              '.clike/packs/enterprise-onprem/PACK.md',
              '.clike/packs/industrial-manufacturing/PACK.md',
              '.clike/packs/consumer-saas/PACK.md',
              '.clike/design-profiles/enterprise-console/DESIGN.md',
              '.clike/design-profiles/industrial-control-room/DESIGN.md',
              '.github/CODEOWNERS',
              '.github/pull_request_template.md',
              '.github/worflow/clike-ci.yaml',
              'docs/harper/PLAYBOOK.md',
              'docs/harper/IDEA.md',
              'docs/harper/SPEC.md',
              'docs/harper/TECH_CONSTRAINTS.yaml',
              'runs/'
            ],
            next_steps: [
              'Open README.md',
              'Open docs/harper/IDEA.md and complete it',
              'Run /spec to generate SPEC.md from IDEA',
              'Init Git and push to GitHub'
            ]
          };
          await writeJson(path.join(targetDir, '.clike', 'last_init_summary.json'), summary);
          const msgText =
            `✅ CLike: initialized "${name}" at ${targetDir}\n` +
            `doc_root = docs/harper\n` +
            `Files: ${summary.files_created.join(', ')}\n` +
            `Next: open README.md, complete IDEA.md, then /spec`;
          // bubble in the ORIGIN workspace
          panel.webview.postMessage({
            type: 'echo',
            message:msgText
          });


          msg.__outcome = { project: name, project_root: targetDir, files_created: summary.files_created };
          msg.__result = 'ok';
          // open the new workspace in a new window (not when an agent initialized the open one in place)
          if (!msg.__inPlace) await vscode.commands.executeCommand('vscode.openFolder', vscode.Uri.file(targetDir), true);
          //await context.workspaceState.update('clike.initSummary', msgText);


        } catch (e) {
          console.error('[CLike] harperInit failed:', e);
          panel.webview.postMessage({ type: 'error', message: 'Init failed: ' + String(e?.message || e) });
        }
      }
      // Run Harper phase from webview (slash: /spec | /plan | /kit | /build)
      if (msg.type === 'harperRun') {
        // an auto-eval repair continues the /eval --fix the user started (and its Cancel)
        if (harperSignal(!msg.autoEvalRepair).aborted) {
          panel.webview.postMessage({ type: 'busy', on: false });
          return;
        }
        const runId = (Math.random().toString(16).slice(2) + Date.now().toString(16));
        //log(`[harperRun] inside ${JSON.stringify(msg)}`);
        const phase = msg.cmd;
        // Cancel while the phase ran: its response is dropped (no files written, no commit, no
        // follow-up step); files a local agent wrote before it was stopped stay where they are
        const discardCancelledRun = () => {
          const target = Array.isArray(msg.targets) && msg.targets.length ? ` ${msg.targets.join(' ')}` : '';
          panel.webview.postMessage({ type: 'echo', message:
            `⏹ /${phase}${target} cancelled: the response was discarded, nothing was written or committed` +
            (phase === 'kit' ? ` (files a local agent wrote before the stop stay in runs/kit/, uncommitted).` : '.') });
          msg.__result = 'cancelled';
          clikeHarperBlockingRun = false;
          panel.webview.postMessage({ type: 'busy', on: false, force: true });
        };
        try {
          if (phase === 'finalize' && !msg.finalizeRepair && !msg.finalizePendingConfirmed) {
            // /finalize integrates what the gates promoted (a REQ not done yet is not in it) and
            // commits on the default branch (a REQ branch not merged there is missing from it).
            const root = getWorkspaceRoot().fsPath;
            const gitSettings = cfg();
            const defaultBranch = gitSettings.gitDefaultBranch || 'main';
            const pending = finalizeVerify.pendingReqs(root);
            const unmerged = finalizeVerify.unmergedReqBranches(root, defaultBranch, gitSettings.gitBranchPrefix || 'feature');
            const problems = [];
            if (pending.length) {
              const list = pending.slice(0, 8).map(r => `${r.id} (${r.status})`).join(', ') + (pending.length > 8 ? ', …' : '');
              problems.push(`${pending.length} REQ(s) not promoted yet: ${list} — /finalize integrates only what the gates promoted.`);
            }
            if (unmerged.length) {
              problems.push(`${unmerged.join(', ')} not merged into ${defaultBranch} — /finalize commits on ${defaultBranch}: ` +
                `merge first (git switch ${defaultBranch} && git merge --no-ff ${unmerged[0]}).`);
            }
            if (problems.length) {
              const go = 'Run /finalize anyway';
              if (!(await confirmOrMcp(msg, problems.join(' '), go))) {
                msg.__outcome = { error: `/finalize not run: ${problems.join(' ')}${msg.__fromMcp ? ' (MCP: pass confirm=true to run it anyway)' : ''}`, code: 'needs_confirmation' };
                panel.webview.postMessage({ type: 'echo', message: `ℹ /finalize not run: ${problems.join(' ')}` });
                panel.webview.postMessage({ type: 'busy', on: false });
                return;
              }
              msg.finalizePendingConfirmed = true;
            }
          }

          if (phase === 'extend' && msg.extendMode === 'cascade' && !msg.__cascade) {
            // /idea --extend: the next release of a delivered project (release-extend.js)
            const root = getWorkspaceRoot().fsPath;
            const baselineInfo = releaseExtend.baselineStatus(root);
            const stop = (text) => {
              msg.__outcome = { error: `/idea --extend not run: ${text}`, code: 'not_run' };
              panel.webview.postMessage({ type: 'echo', message: `ℹ /idea --extend not run: ${text}` });
              panel.webview.postMessage({ type: 'busy', on: false, force: true });
            };
            if (!baselineInfo.hasPlan) {
              return stop('docs/harper/plan.json has no REQs to extend. For a new project run /idea; for a project ' +
                'not built with CLike run /adopt first (it writes the plan of the project as it is), then /idea --extend.');
            }
            const rel = releaseExtend.detectRelease(root, { release: msg.release });
            const inputCheck = releaseExtend.cascadeInputCheck(rel, Array.isArray(msg.attachments) ? msg.attachments.length : 0);
            if (!inputCheck.ok) return stop(inputCheck.message);
            if (baselineInfo.notDone.length) {
              const go = 'Extend anyway';
              const ok = await confirmOrMcp(msg,
                `${baselineInfo.notDone.length} REQ(s) of the current release are not delivered: ` +
                `${baselineInfo.notDone.slice(0, 8).join(', ')}. The new release builds on what is delivered.`, go);
              if (!ok) return stop(`REQs not delivered: ${baselineInfo.notDone.join(', ')}${msg.__fromMcp ? ' (MCP: pass confirm=true to extend anyway)' : ''}`);
            }
            msg.__cascade = { ...rel, baselineInfo, dryRun: !!msg.dryRun, attachments: (msg.attachments || []).map((a) => a?.name || a?.path).filter(Boolean),
              // a project of areas: every new REQ names its area, a new module is declared and registered
              areas: releaseExtend.projectAreas(root) };
            panel.webview.postMessage({ type: 'echo', message: `▶ /idea --extend: ${rel.baseline} → ${rel.release}` +
              ` (inputs: ${[...msg.__cascade.attachments, ...rel.inputs, ...rel.references].join(', ')})${msg.dryRun ? ' — dry run' : ''}` });
          }

          if (phase === 'finalize') {
            // the developer's own changes, recorded once per round (finalize-verify.js)
            try { finalizeVerify.ensureDirtyBaseline(getWorkspaceRoot().fsPath); } catch (e) { log(`[finalize] baseline: ${e?.message || e}`); }
          }

          if (phase === 'finalize' && !msg.finalizeRepair && finalizeVerifyInFlight) {
            // a second /finalize (or --verify) while the verification runs composed the same sandbox
            // workspace at once (B2B: a false FAIL, then a full agent run nobody needed)
            panel.webview.postMessage({ type: 'echo', message: 'ℹ /finalize: the solution verification is still running — wait for its outcome (or Stop it first).' });
            panel.webview.postMessage({ type: 'busy', on: false });
            return;
          }
          if (phase === 'finalize' && msg.verifyOnly && !msg.finalizeRepair) {
            // /finalize --verify: what the last finalize wrote is verified again (sandbox, the local
            // check, the outcome, the release tag) without a new agent run — no tokens when it passes;
            // the repair agent runs only on a failure, as in a full /finalize
            await appendSessionJSONL(activeMode, { ts: Date.now(), role: 'user', content: '▶ FINALIZE --verify (no agent run)', model: 'auto', attachments: [] });
            panel.webview.postMessage({ type: 'echo', message: '▶ /finalize --verify: the solution verification again, no new agent run.' });
            msg.__result = 'ok';
            clikeHarperBlockingRun = false;
            panel.webview.postMessage({ type: 'busy', on: false });
            if (cfg().finalizeVerify) await continueFinalizeVerify(msg);
            else recordFinalizeOutcome('ok', 'solution verification off (clike.finalize.verify)');
            return;
          }

          const project_id = getProjectId();
          const { cmd, attachments = [] } = msg;
          const state = context.workspaceState.get('clike.uiState') || {
            mode: 'harper',
            model: 'auto',
            historyScope: 'singleModel',
            executionPreference: getDefaultExecutionPreference(),
            localAgentExecutor: getDefaultLocalAgentExecutor(),
          };

          const executionPreference = normalizeExecutionPreference(
            state.executionPreference || getDefaultExecutionPreference()
          );

          const localAgentExecutor = normalizeLocalAgentExecutor(
            state.localAgentExecutor || getDefaultLocalAgentExecutor()
          );

          state.executionPreference = executionPreference;
          state.localAgentExecutor = localAgentExecutor;

          if (String(cmd || '').trim().toLowerCase() === 'agent-session') {
            // /agent-session [new|new all]: the CLike chat keeps one agent session per (mode, agent)
            const sessions = context.workspaceState.get('clike.agentSessions') || {};
            const action = String(msg.sessionAction || '').trim().toLowerCase();
            const currentMode = String(state.mode || 'harper').toLowerCase();
            let message;
            if (action === 'new' || action === 'new all' || action === 'reset') {
              const keep = action === 'new all' ? {} : Object.fromEntries(
                Object.entries(sessions).filter(([key]) => !key.startsWith(`${currentMode}:`))
              );
              await context.workspaceState.update('clike.agentSessions', keep);
              message = `✔ AGENT-SESSION new ${action === 'new all' ? 'conversation in every mode' : `conversation in ${currentMode}`}: the next message starts a fresh agent session.`;
            } else {
              const lines = Object.entries(sessions).map(([key, s]) => `${key} → ${s.id || 'pending'}${s.at ? ' (' + new Date(s.at).toLocaleString() + ')' : ''}`);
              message = lines.length
                ? `ℹ Agent sessions (resumed message after message): ${lines.join(' · ')}. /agent-session new starts a new one.`
                : 'ℹ No agent session yet: the next message to the agent starts one.';
            }
            await appendSessionJSONL(state.mode || 'harper', { role: 'system', content: message, model: state.model || 'auto' });
            panel.webview.postMessage({ type: 'echo', message });
            panel.webview.postMessage({ type: 'busy', on: false });
            return;
          }

          if (String(cmd || '').trim().toLowerCase() === 'agent-model') {
            // /agent-model [claude|codex] [model]: show or set the model the local agent runs with
            // (clike.claudeCode.model / clike.localAgent.codex.model, workspace scope).
            const c = vscode.workspace.getConfiguration('clike');
            const keys = { claude: 'claudeCode.model', codex: 'localAgent.codex.model' };
            const agent = String(msg.agentName || '').trim().toLowerCase();
            const model = String(msg.agentModel || '').trim();
            let message;
            let modelCheck;
            if (agent === 'list') {
              // Model ids from CLike's catalog (the same that fills the cloud model selector).
              let catalog = [];
              try {
                const res = await fetchJson(`${serviceBaseUrls().orchestrator}/v1/models`);
                catalog = (Array.isArray(res?.models) ? res.models : [])
                  .filter(m => m && m.enabled !== false && !/embed/i.test(String(m.name || m.id || '')));
              } catch (err) {
                log(`[agent-model] catalog unavailable: ${err?.message || err}`);
              }
              message = agentModelListMessage({ codexModels: readCodexModelSlugs(), catalog });
            } else if (!agent) {
              const executor = normalizeLocalAgentExecutor(state.localAgentExecutor || getDefaultLocalAgentExecutor());
              const executorLabel = executor === 'claude_code' ? 'Claude Code' : executor === 'gpt_codex' ? 'Codex' : 'auto';
              const execution = normalizeExecutionPreference(state.executionPreference || getDefaultExecutionPreference());
              message =
                `ℹ Execution: ${execution} · default agent: ${executorLabel} (/agent-default) · ` +
                `models — Claude Code: ${c.get('claudeCode.model', 'opus') || 'CLI default'}, ` +
                `Codex: ${c.get('localAgent.codex.model', 'gpt-5.5') || 'CLI default'} (/agent-model claude|codex <model>). ` +
                `Cloud model: ${state.model || 'auto'} (model selector).`;
            } else if (!keys[agent] || !model || !/^[A-Za-z0-9._:[\]-]+$/.test(model)) {
              message = '⚠ Usage: /agent-model [claude|codex] [model], e.g. /agent-model claude sonnet';
            } else if (!(modelCheck = validateAgentModel({
              executorId: agent === 'claude' ? 'claude_code' : 'gpt_codex',
              model,
              codexModels: readCodexModelSlugs(),
            })).ok) {
              message = `⚠ ${modelCheck.message}`;
            } else {
              await c.update(keys[agent], model, vscode.ConfigurationTarget.Workspace);
              message = `✔ AGENT-MODEL ${agent === 'claude' ? 'Claude Code' : 'Codex'} → ${model} (chat and Harper phases)`;
            }
            await appendSessionJSONL(state.mode || 'harper', { role: 'system', content: message, model: state.model || 'auto' });
            panel.webview.postMessage({ type: 'echo', message });
            panel.webview.postMessage({ type: 'busy', on: false });
            return;
          }

          if (String(cmd || '').trim().toLowerCase() === 'agent-default') {
            const rawValue = msg?.value || msg?.target || msg?.rawTarget || '';
            log(`[harperRun][agent-default] rawValue=${JSON.stringify(rawValue)}`);

            const requested = normalizeAgentDefaultInput(rawValue);
            log(`[harperRun][agent-default] normalized=${JSON.stringify(requested)}`);

            if (!requested) {
              const usage = 'Usage: /agent-default codex|claude|auto';
              log(`[harperRun][agent-default] invalid value=${JSON.stringify(rawValue)}`);

              panel.webview.postMessage({
                type: 'echo',
                message: `⚠ ${usage}`
              });
              panel.webview.postMessage({ type: 'busy', on: false });
              return;
            }

            const nextExecutor = normalizeLocalAgentExecutor(requested);
            // /agent-default just sets the preferred local executor. It must NOT
            // change the current mode, so it can be used from Free (Q&A) and
            // Coding as well as Harper.
            const currentUiMode = state.mode || 'harper';
            const nextState = {
              ...state,
              localAgentExecutor: nextExecutor,
            };

            await context.workspaceState.update('clike.uiState', nextState);
            await persistLocalAgentDefault(nextExecutor);

            const label =
              nextExecutor === 'gpt_codex'
                ? 'GPT Codex'
                : nextExecutor === 'claude_code'
                  ? 'Claude Code'
                  : 'auto';

            log(`[harperRun][agent-default] updated localAgentExecutor=${nextExecutor} mode=${currentUiMode}`);

            await appendSessionJSONL(currentUiMode, {
              role: 'system',
              content: `✔ AGENT-DEFAULT ${label}`,
              model: state.model || 'auto',
            });

            panel.webview.postMessage({
              type: 'echo',
              message: `✔ AGENT-DEFAULT ${label}`
            });

            panel.webview.postMessage({
              type: 'initState',
              state: {
                ...nextState,
                executionPreference: normalizeExecutionPreference(
                  nextState.executionPreference || getDefaultExecutionPreference()
                ),
                localAgentExecutor: nextExecutor,
              }
            });

            panel.webview.postMessage({ type: 'busy', on: false });
            return;
          }


          
          const profileHint = computeProfileHint(activeMode, activeModel);
          const activeProvider = profileHint ? '' : (explicitProviderForModel(activeModel) || '');
          const docRoot = 'docs/harper';
          log(`[harperRun] savedState ...${JSON.stringify(state)}`);
          if (phase === 'kit') {
            log(`[harperRun] kit raw targetReqId=${JSON.stringify(msg?.targetReqId)} raw targets=${JSON.stringify(msg?.targets)} phases=${JSON.stringify(msg?.phases || ['kit'])}`);
          }
          let targets = '';
          let project_name = '';
          const { orchestratorUrl, routes } = cfg();
          var prefixRag = (routes?.orchestrator?.ragIndex) || '/v1/rag/index';
          let urlRag = orchestratorUrl + prefixRag;

          if (phase === 'idea') {
            project_name = msg?.name;
          } else if (phase === 'kit') {
            const explicitTarget = String(msg?.targetReqId || '').trim().toUpperCase();
            const rawTargets = msg?.targets;
            const rawCommand = String(msg?.rawCommand || '').trim();

            const normalizeReq = (value) => {
              return String(value || '')
                .trim()
                .toUpperCase()
                .replace(/[–—]/g, '-')
                .replace(/[,;]+$/, '');
            };

            let rawCommandTarget = '';
            if (rawCommand) {
              const m = rawCommand.match(/\bREQ[-–—_ ]?(\d+)\b/i);
              if (m && m[1]) {
                rawCommandTarget = 'REQ-' + m[1];
              }
            }

            if (explicitTarget) {
              targets = normalizeReq(explicitTarget);
            } else if (Array.isArray(rawTargets) && rawTargets.length > 0) {
              targets = normalizeReq(rawTargets[0]);
            } else if (typeof rawTargets === 'string' && rawTargets.trim()) {
              targets = normalizeReq(rawTargets);
            } else if (rawCommandTarget) {
              targets = normalizeReq(rawCommandTarget);
            } else {
              targets = '';
            }

            log(`[harperRun] normalized kit target='${targets}' explicit=${JSON.stringify(explicitTarget)} raw=${JSON.stringify(rawTargets)} rawCommand=${JSON.stringify(rawCommand)} rawCommandTarget=${JSON.stringify(rawCommandTarget)}`);
          }
          const projectName = getProjectNameFromWorkspace() || project_name; //name form workspace not from chat input!!!

          // Document-phase input preflight: block invalid /idea, /spec, /plan
          // runs BEFORE any orchestrator interaction (no RAG index, no HTTP, no
          // local agent, no cloud fallback). CLike owns this gate.
          if (isDocumentLocalAgentPhase(phase)) {
            const wsrootPre = getWorkspaceRoot();
            let ideaPresent = false;
            let specPresent = false;
            if (wsrootPre) {
              if (phase === 'spec') {
                try {
                  await vscode.workspace.fs.stat(vscode.Uri.joinPath(wsrootPre, 'docs', 'harper', 'IDEA.md'));
                  ideaPresent = true;
                } catch { /* missing */ }
              } else if (phase === 'plan') {
                try {
                  await vscode.workspace.fs.stat(vscode.Uri.joinPath(wsrootPre, 'docs', 'harper', 'SPEC.md'));
                  specPresent = true;
                } catch { /* missing */ }
              }
            }
            const preflight = evaluateDocumentPhaseInputPreflight({
              phase,
              attachmentCount: Array.isArray(attachments) ? attachments.length : 0,
              ideaPresent,
              specPresent,
            });
            if (!preflight.ok) {
              log(`[harperRun] document-phase preflight blocked phase=${phase} code=${preflight.code}`);
              try { vscode.window.showErrorMessage(preflight.message); } catch {}
              panel.webview.postMessage({ type: 'error', message: preflight.message });
              panel.webview.postMessage({ type: 'busy', on: false, force: true });
              return;
            }
          }

          // /extend --from attachment requires at least one current attachment.
          // Block BEFORE any orchestrator interaction.
          if (phase === 'extend') {
            const extendPreflight = evaluateExtendInputPreflight({
              fromAttachment: !!msg.fromAttachment,
              attachmentCount: Array.isArray(attachments) ? attachments.length : 0,
            });
            if (!extendPreflight.ok) {
              log(`[harperRun] extend preflight blocked code=${extendPreflight.code}`);
              try { vscode.window.showErrorMessage(extendPreflight.message); } catch {}
              panel.webview.postMessage({ type: 'error', message: extendPreflight.message });
              panel.webview.postMessage({ type: 'busy', on: false, force: true });
              return;
            }
          }
          //RAG
          try {
            //log(`CLike preIndexRag: ${JSON.stringify(attachments)}`);
            const { inline_files, rag_files } =  partitionAttachments(attachments);
            log(`CLike rag_files size: ${rag_files.length} and inline_files size: ${inline_files.length}`);
            if (rag_files.length) {
              const res = await preIndexRag(project_id, rag_files, urlRag, out); 
              log((`CLike preIndexRag: ${JSON.stringify(res)} ${res}`));
            }
          } catch (e) { log(`CLike preIndexRag error: ${e}`); }
          // Core docs per phase
          let core = defaultCoreForPhase(phase);
          // the cascade merges into IDEA too
          if (msg.__cascade || msg.__adopt) core = ['IDEA.md', 'SPEC.md', 'PLAN.md', 'plan.json', 'TECH_CONSTRAINTS.yaml'];
          // Privacy flags (if already present elsewhere, reuse them)
          const flags = {
            neverSendSourceToCloud: !!cfgChat().neverSendSourceToCloud || false,
            redaction: true
          };
          //CHAT HARPEr START
          // History of the current MODE
          const historyScope  = effectiveHistoryScope(context);
          // History for a "stateless" conversation: load ONLY the bubbles of the current MODE
          const history = await loadSessionFilteredHarper(activeMode).catch(() => []);
          // Optionally filter by model if you want to send only that model's sub-thread:
          const historyForThisModel = await loadSessionFiltered(activeMode, activeModel); //history.filter(b => !b.model || b.model === activeModel);
          //log((`CLike history: ${JSON.stringify(history)}`));
          
          const source = (historyScope === 'allModels')
          ? history
          : historyForThisModel;
          const _source = source.filter(b => 
            // Condition 1: the role must be 'user' OR 'assistant'
            (b.role === 'user' || b.role === 'assistant') 
          );
        
          var _messages = _source.map(b => ({ role: b.role, content: b.content }));
          let msg_bubble='';
          const _gen={
            temperature: 0.2,
            max_tokens: (msg.__cascade || msg.__adopt ? 64000 : phase === 'plan' ? 45000 : phase === 'spec' ? 10500 : 9999),
            top_p: 0.9,
            stop: ["```.:: END ::.```"],
            presence_penalty: 0.0,
            frequency_penalty: 0.2,
            seed: 42,
            tools:'',
            remote:'',
            response_format:'',
            tool_choice:''
          }
        
          const payload = {
            cmd,
            phase: msg.cmd,
            mode: activeMode,
            model: activeModel,
            ...(activeProvider ? { provider: activeProvider } : {}),
            profileHint,
            executionPreference,
            docRoot,
            core,
            messages: _messages,
            gen: _gen,
            attachments,
            flags,
            runId,
            historyScope: state.historyScope || 'singleModel',
            project_id: project_id,
            project_name: projectName,
            mode_contract: buildModeContract(activeMode, msg.cmd),
          };
          if (msg.methodology) payload.methodology = msg.methodology;
          if (msg.agent) payload.agent = msg.agent;
          if (msg.methodology_context) payload.methodology_context = msg.methodology_context;

          //PATh for PLAN.md
          const wsroot = getWorkspaceRoot();
          let targetReqId;
          let plan;
          let requestedKitPhases = null;

          if (phase === 'kit') {
            plan = await readPlanJson(wsroot);
            if (!plan) {
              vscode.window.showErrorMessage('plan.json not found. Run /plan first.');
              panel.webview.postMessage({ type: 'busy', on: false });
              return;
            }

            targetReqId = await runKitCommand(plan, targets);
            log("happerRun targetReqId", targetReqId);

            if (!targetReqId) {
              panel.webview.postMessage({ type: 'busy', on: false });
              return;
            }
            requestedKitPhases = Array.isArray(msg?.phases) && msg.phases.length
              ? msg.phases
              : null;

            // the plan declares the REQ not ready for its KIT (decisions left open): asked first,
            // an agent run would write no code (MCP: only with confirm; the autopilot parks it before)
            const kitBlocked = (!requestedKitPhases && !msg.acceptanceStage && !msg.autoEvalRepair && !msg.repair)
              ? kitBlockers((plan.reqs || []).find((r) => String(r?.id || '').toUpperCase() === String(targetReqId).toUpperCase()))
              : null;
            if (kitBlocked && !(await confirmOrMcp(msg,
              `${targetReqId} is not ready for its KIT: the plan leaves open ${kitBlocked.blockers.join(', ') || 'decisions'}. ` +
              'An agent asked for the KIT writes no code until they are decided: write them to /spec (text or attachment), then /plan.',
              'Run the KIT anyway'))) {
              msg.__result = 'cancelled';
              panel.webview.postMessage({ type: 'echo', message: `⏸ /kit ${targetReqId} not started: decide ${kitBlocked.blockers.join(', ')} first (/spec <decisions>, then /plan).` });
              panel.webview.postMessage({ type: 'busy', on: false, force: true });
              return;
            }

            // Acceptance-first KIT (clike.kit.acceptanceFirst): the acceptance tests and the eval
            // profile are generated and locked first; this /kit then writes the code against them.
            if (!requestedKitPhases && !msg.acceptanceStage && !msg.autoEvalRepair && !msg.repair && cfg().kitAcceptanceFirst) {
              const stageMsg = {
                type: 'harperRun', cmd: 'kit', targets: [targetReqId], targetReqId,
                attachments: msg.attachments || [], phases: ['acceptance'], acceptanceStage: true,
              };
              panel.webview.postMessage({ type: 'echo', message: `▶ ACCEPTANCE-FIRST ${targetReqId} — stage 1/2: acceptance tests and eval profile` });
              await handleWebviewMessage(stageMsg);
              if (stageMsg.__result !== 'ok') {
                panel.webview.postMessage({ type: 'error', message: `ACCEPTANCE-FIRST ${targetReqId}: the acceptance stage failed; the code KIT was not run.` });
                panel.webview.postMessage({ type: 'busy', on: false, force: true });
                return;
              }
              try {
                const lock = await postAcceptanceLock(wsroot, targetReqId);
                panel.webview.postMessage({ type: 'echo', message: `🔒 ${targetReqId}: ${lock?.files ?? 0} acceptance files locked before the code` });
              } catch (err) {
                panel.webview.postMessage({ type: 'error', message: `ACCEPTANCE-FIRST ${targetReqId}: lock failed: ${err?.message || err}` });
                panel.webview.postMessage({ type: 'busy', on: false, force: true });
                return;
              }
              msg.acceptanceFirst = true;
              msg.__acceptanceBefore = snapshotAcceptanceSurface(wsroot.fsPath, targetReqId);
              panel.webview.postMessage({ type: 'echo', message: `▶ ACCEPTANCE-FIRST ${targetReqId} — stage 2/2: code against the locked tests` });
              clikeHarperBlockingRun = true;
            }

            if (requestedKitPhases && requestedKitPhases.length) {
              const normalizedPhases = requestedKitPhases
                .map(p => String(p || '').trim().toLowerCase())
                .filter(Boolean);

              const postKitPhases = ['integrity_eval', 'promotion_hardener', 'promotion_eval'];
              const needsExistingCandidate = normalizedPhases.some(p => postKitPhases.includes(p));

              if (needsExistingCandidate) {
                const reqRoot = vscode.Uri.joinPath(wsroot, 'runs', 'kit', targetReqId);
                const required = [
                  vscode.Uri.joinPath(reqRoot, 'src'),
                  vscode.Uri.joinPath(reqRoot, 'test'),
                  vscode.Uri.joinPath(reqRoot, 'docs', 'TARGET_CONTRACT.json'),
                  vscode.Uri.joinPath(reqRoot, 'docs', 'FILE_REQUIREMENTS.json'),
                  vscode.Uri.joinPath(reqRoot, 'docs', 'REQ_PROMOTION_MANIFEST.md'),
                ];

                if (normalizedPhases.includes('promotion_hardener') || normalizedPhases.includes('promotion_eval')) {
                  required.push(vscode.Uri.joinPath(reqRoot, 'docs', 'INTEGRITY_EVAL.json'));
                }

                const missing = [];
                for (const uri of required) {
                  try {
                    await vscode.workspace.fs.stat(uri);
                  } catch {
                    missing.push(vscode.workspace.asRelativePath(uri));
                  }
                }

                if (missing.length) {
                  const reason =
                    `Cannot run ${normalizedPhases.join(', ')} for ${targetReqId}: missing required KIT candidate artifacts in workspace.\n` +
                    missing.map(x => `- ${x}`).join('\n');
                  log(`[harperRun] kit phase preflight failed for ${targetReqId}: ${reason}`);
                  vscode.window.showErrorMessage(reason);
                  panel.webview.postMessage({ type: 'busy', on: false });
                  return;
                }
              }
            }

            payload["kit"] = {
              targets: [targetReqId],
              ...(requestedKitPhases ? { phases: requestedKitPhases } : {}),
              // a manual /kit --repair carries the latest failures like auto-eval (the cloud sees only the prompt)
              ...(msg.autoEvalRepair ? { repair: msg.autoEvalRepair } : (msg.repair ? { repair: manualRepairRequest(toFsPath(wsroot), targetReqId) || true } : {})),
              ...(msg.acceptanceFirst ? { acceptance_first: true } : {})
            };
          }
          if (phase === 'finalize' && cfg().finalizeVerify) {
            // the solution eval profile CLike runs after /finalize, the REQs' profiles to derive
            // it from and, in a verification repair, the failures (finalize-verify.js)
            const agentChecks = Number(cfg().autoEvalAgentEvalChecks ?? 8);
            payload["finalize_verify"] = {
              profile: finalizeVerify.SOLUTION_PROFILE,
              req_profiles: finalizeVerify.collectReqEvalProfiles(wsroot.fsPath),
              ...(agentChecks > 0 ? { eval_check: true, eval_check_max_runs: agentChecks } : {}),
              ...(msg.finalizeRepair ? { repair: msg.finalizeRepair } : {}),
            };
          }
          //log(`[harperRun] payload (gen):`,  JSON.stringify(payload.gen));
          msg_bubble = phase==='idea' ? project_id : targets; 
          // Persist the user's input in the MODE session (the model badge is shown at render time)
          await appendSessionJSONL(activeMode, {
            role: 'user',
            content: `▶ ${cmd.toUpperCase()} ${msg_bubble} | mode=${state.mode} model=${state.model} exec=${executionPreference} profile=${profileHint || '—'}${methodologyTag(msg)} core=${JSON.stringify(core)}`,
            model:  state.model || 'auto',
            attachments: Array.isArray(msg.attachments) ? msg.attachments : []
          });
          // Echo pre-run
          panel.webview.postMessage({
            type: 'echo',
            message: `▶ ${cmd.toUpperCase()} ${msg_bubble} | mode=${state.mode} model=${state.model} exec=${executionPreference} profile=${profileHint || '—'}${methodologyTag(msg)} core=${JSON.stringify(core)} attachments=${attachments.length}`
          });
          
          const settings = cfg();
          const localAgentAvailability = detectLocalAgentAvailability(settings);
          log(`[harperRun][agent][settings] ${JSON.stringify({
            localAgentEnabled: settings.localAgentEnabled,
            localAgentPreferredExecutor: settings.localAgentPreferredExecutor,
            claudeCodeEnabled: settings.claudeCodeEnabled,
            claudeCodeCommand: settings.claudeCodeCommand,
            codexEnabled: settings.codexEnabled,
            codexCommand: settings.codexCommand,
          })}`);
          log(`[harperRun][agent][availability] ${JSON.stringify(localAgentAvailability)}`);
          const localAgentRequested = executionPreferenceRequestsLocalAgent(executionPreference);
          const selectedLocalExecutor = resolveSelectedLocalAgentExecutor(
            settings,
            state.localAgentExecutor || 'auto',
            phase
          );
          const localExecutorConfig = selectedLocalExecutor
            ? getExecutorConfig(selectedLocalExecutor, settings)
            : null;
          if (localAgentRequested && !selectedLocalExecutor) {
            const msgNoExecutor =
              `No local agent executor detected locally for phase=${phase}. ` +
              `The request will still be sent to the orchestrator; fallback/package policy is orchestrator-owned.`;

            log(`[harperRun][agent][local] ${msgNoExecutor}`);

            panel.webview.postMessage({
              type: 'echo',
              message: `⚠ ${msgNoExecutor}`
            });
          }
          const _headers = { "Content-Type": "application/json" };
          if (isLocalAgentEligiblePhase(phase) && localAgentRequested && localExecutorConfig && localExecutorConfig.enabled) {
            log(
              `[harperRun][agent] local agent requested; orchestrator will decide package/fallback ` +
              `phase=${phase} req=${targetReqId || 'SOLUTION'} exec=${executionPreference} executor=${selectedLocalExecutor}`
            );
          }

          if (profileHint && typeof profileHint === 'string' && profileHint.trim()) {
            _headers["X-CLike-Profile"] = profileHint.trim();
          }
          //fals is for RAG chucks - TODO: RAG management via attachments is almost oden 70%
          const body = await buildHarperBody(phase, payload, wsroot, out);
          // /extend is append-only: keep the plan as it was, to check the result against it
          // (and to restore it when a local agent already wrote a plan that breaks the rule).
          const extendBefore = phase === 'extend' ? releaseExtend.snapshotDocs(toFsPath(wsroot)) : null;
          const extendStartedAt = Date.now();

          if (phase === 'extend') {
            body.extend = {
              anchorReq: msg.anchorReq || '',
              explicitReq: msg.explicitReq || '',
              fromAttachment: !!msg.fromAttachment,
              rawInput: msg.rawInput || '',
              alias: msg.alias || null,
              preserveExistingRequirements: true,
              updateSpecIfNeeded: true,
              updateLaneGuidesIfNeeded: true,
              emitAudit: true,
              ...(msg.__cascade ? {
                mode: 'cascade',
                release: msg.__cascade.release,
                baseline: msg.__cascade.baseline,
                dryRun: !!msg.__cascade.dryRun,
                ...(msg.__cascade.areas && msg.__cascade.areas.length ? {
                  areas: msg.__cascade.areas.map((a) => ({ name: a.name, root: a.root, commands: a.commands || {} })),
                } : {}),
              } : {}),
              // /adopt: the same cascade, describing the project as it is (adopt.js; rules in extend_cascade.py)
              ...(msg.__adopt ? {
                mode: 'adopt',
                areas: msg.__adopt.areas.map((a, i) => ({ name: a.name, root: a.root, baseline_req: msg.__adopt.baselineIds[i] })),
                survey_report: msg.__adopt.surveyReport,
                documents: msg.__adopt.documents,
                ...(msg.__adopt.adoptedBefore.length ? { adopted_before: msg.__adopt.adoptedBefore } : {}),
              } : {}),
            };
            if (msg.__adopt) {
              // a cloud model reads what CLike gives it: the project memory too, with room for it
              body.rag_strategy = 'auto';
              body.rag_top_k = 40;
              body.context_hard_limit = Math.max(Number(body.context_hard_limit || 0), 40000);
            }

            body.gen = {
              ...(body.gen || {}),
              anchorReq: msg.anchorReq || '',
              explicitReq: msg.explicitReq || '',
              rawInput: msg.rawInput || '',
            };
          }

          if (isLocalAgentEligiblePhase(phase)) {
            body.localAgentExecutor = normalizeLocalAgentExecutor(
              selectedLocalExecutor || state.localAgentExecutor || settings.localAgentPreferredExecutor || 'auto'
            );

            body.localAgentCapabilities = detectLocalAgentAvailability(settings);
            body.localAgentTimeoutSeconds = Math.max(
              60,
              resolveLocalAgentTimeoutMinutes(body.localAgentExecutor, settings) * 60
            );

            body.localRuntime = {
              shell: process.env.SHELL || 'zsh',

              // Runtime-neutral contract.
              // The orchestrator and the local agent must infer the implementation
              // stack from SPEC.md, PLAN.md, plan.json, TECH_CONSTRAINTS and
              // repository evidence. Do not force Python as the application runtime.
              implementation_runtime_policy: 'infer_from_project_contracts',
              dependency_strategy: 'use_existing_project_scripts_or_report_blocked',
              package_install_policy: 'never_install_global_packages',

              // Optional tool hints only. These are helpers, not implementation rules.
              tool_hints: {
                node: 'node',
                npm: 'npm',
                python: 'python3',
                java: 'java',
                go: 'go',
                ruby: 'ruby',
                rust: 'rustc',
                php: 'php',
                dotnet: 'dotnet',
                kubectl: 'kubectl',
              },
            };
          }

          if (phase === 'finalize' && localAgentRequested) {
            body.rag_strategy = 'off';
            body.rag_top_k = 0;
            body.context_hard_limit = Math.min(Number(body.context_hard_limit || 12500), 12500);
          }

          const keys = Object.keys(body.core_blobs);
          log(`[harperRun] body (keys::core_blobs):`,  keys)
          if (phase === 'finalize') {
            if (localAgentRequested) {
              log('[finalize] Skipping automatic RAG pre-index because local agent execution was requested. The agent will inspect the workspace directly.');
              panel.webview.postMessage({
                type: 'echo',
                message: 'ℹ FINALIZE RAG pre-index skipped: local agent will inspect the workspace directly.'
              });
            } else {
              try {
                const items = await collectFinalizeRagItems(wsroot);

                if (items.length) {
                  const res = await preIndexRag(project_id, items, urlRag, out, { timeoutMs: 15000 });
                  log((`CLike preIndexRag: ${JSON.stringify(res)} ${res}`));
                } else {
                  log('[finalize] No source files found for RAG indexing; continuing because finalize also supports document-only and agent-driven workspace inspection.');
                  panel.webview.postMessage({
                    type: 'echo',
                    message: 'ℹ FINALIZE RAG source indexing skipped: no source files found. Continuing with core docs and workspace inspection.'
                  });
                }
              } catch (e) {
                log(`ℹ️ RAG index skipped (${e?.message || e}); continuing finalize.`);
                panel.webview.postMessage({
                  type: 'echo',
                  message: `ℹ FINALIZE RAG indexing skipped: ${e?.message || e}. Continuing.`
                });
              }
            }
          }
          //log(`[harperRun] body (core_blobs):`,  JSON.stringify(body.core_blobs))
          if (activeProvider) _headers["X-CLike-Provider"] = activeProvider
          const harperTimeout = cfg().harperTimeout;
          clikeHarperBlockingRun = true;
          panel.webview.postMessage({ type: 'busy', on: true });
          let outGateway = await callHarper(cmd, body, _headers, { timeoutMs: 1000 * 60 * harperTimeout, signal: harperSignal() });
          if (harperCancelled()) return discardCancelledRun();
          let _out = outGateway.out;

          // log(`[harperRun][agent][response] ${JSON.stringify({
          //   hasOut: !!_out,
          //   outKeys: _out ? Object.keys(_out) : [],
          //   execution: _out?.execution || null,
          //   hasLocalAgent: !!_out?.local_agent,
          //   localAgentAction: _out?.local_agent?.action || null,
          //   rootHasLocalAgent: !!outGateway?.local_agent,
          // })}`);

           const localAgentPackage = _out?.local_agent || outGateway?.local_agent || null;

          if (isLocalAgentEligiblePhase(phase) && localAgentPackage?.action === 'local_agent_required') {
            try {
              _out = await executeLocalAgentPackage({
                localAgentPackage,
                phase,
                reqId: isNoReqLocalAgentPhase(phase) ? 'SOLUTION' : targetReqId,
                runId,
                executionPreference,
                settings,
                wsroot,
                headers: _headers,
                harperTimeout,
                panel,
                out,
                kitStage: msg.acceptanceStage ? 'acceptance' : null,
              });
            } catch (err) {
              const failMsg = `[harperRun][agent] ${err?.message || String(err)}`;
              log(failMsg);
              // the developer stopped the agent: no cloud fallback, nothing written
              if (harperCancelled()) return discardCancelledRun();

              if (executionPreference === 'local_agent_only') {
                clikeHarperBlockingRun = false;
                if (phase === 'finalize') recordFinalizeOutcome('failed', err?.message || String(err));
                panel.webview.postMessage({ type: 'busy', on: false, force: true });
                panel.webview.postMessage({ type: 'error', message: failMsg });
                return;
              }

              const errText = err?.message || String(err);
              const rejectedByNormalizer = /^Orchestrator rejected local-agent result:/i.test(errText);

              if (phase === 'finalize' && rejectedByNormalizer) {
                clikeHarperBlockingRun = false;
                recordFinalizeOutcome('failed', errText);
                panel.webview.postMessage({ type: 'busy', on: false, force: true });
                panel.webview.postMessage({
                  type: 'error',
                  message:
                    `FINALIZE local agent produced candidate artifacts but CLike rejected them during normalization. ` +
                    `Cloud fallback is blocked to avoid overwriting stronger local-agent source artifacts with weaker cloud documentation. ` +
                    `Reason: ${errText}`
                });
                return;
              }

              // one rule for every caller (tested in local-agent-write-policy.test.js)
              if (!shouldFallbackToCloud({ executionPreference, cancelled: harperCancelled(), phase, rejectedByNormalizer })) {
                return discardCancelledRun();
              }
              panel.webview.postMessage({
                type: 'echo',
                message: `⚠ Local agent failed. Falling back to current CLike cloud path. Reason: ${errText}`
              });

              const fallbackBody = {
                ...body,
                executionPreference: 'cloud_only',
                localAgentFallbackReason: errText,
                runtimeSelectionGuardrails: [
                  'Do not infer implementation language from lane alone.',
                  'Use TECH_CONSTRAINTS.yaml, SPEC.md, PLAN.md, plan.json, manifests, scripts, and repository structure as the primary runtime source of truth.',
                  'Use repository manifests and existing launchers before creating new runtime entrypoints.',
                  'Use Python only when project evidence explicitly identifies Python as the implementation stack.',
                  'Use Node/npm only when package.json or project evidence identifies a Node ecosystem.',
                  'If this is a fallback after a local-agent failure, generated documentation must explicitly say it is fallback output and must not contradict source files, manifests, run scripts, or boundaries already present in the workspace.',
                  'Do not claim source behavior was unchanged if source/config/runtime files are present in collected artifacts or known workspace evidence.',
                ],
              };

              outGateway  = await callHarper(cmd, fallbackBody, _headers, { timeoutMs: 1000 * 60 * harperTimeout, signal: harperSignal() });
              if (harperCancelled()) return discardCancelledRun();
              _out = outGateway.out;
            }
            if (harperCancelled()) return discardCancelledRun();
          }

          const harperFailed =
            _out &&
            (
              _out.ok === false ||
              Boolean(_out.error_code) ||
              (Array.isArray(_out.errors) && _out.errors.length > 0)
            );
          if (harperFailed) {
            panel.webview.postMessage({ type: 'busy', on: false });
            const message = formatHarperError(_out);
            log(`[harperRun] failed ${message.replace(/\n/g, ' | ')}`);
            try {
              vscode.window.showWarningMessage(
                _out.error_code === 'invalid_canonical_artifact'
                  ? 'CLike blocked malformed canonical Harper output. See chat for validation details.'
                  : 'CLike Harper phase failed. See chat for details.'
              );
            } catch {}
            panel.webview.postMessage({ type: 'error', message });
            msg.__result = 'failed';
            if (cmd === 'finalize') recordFinalizeOutcome('failed', message);
            const commandLabel = String(cmd || '').toUpperCase();
            const failureCode = _out.error_code || 'harper_error';
            await appendSessionJSONL(activeMode, {
              ts: Date.now(),
              role: 'system',
              content: `✖ ${commandLabel} failed — ${failureCode}`,
              model: state.model || 'auto',
              attachments: Array.isArray(msg.attachments) ? msg.attachments : []
            });
            clikeHarperBlockingRun = false;
            panel.webview.postMessage({ type: 'busy', on: false, force: true });
            return;
          }

          panel.webview.postMessage({ type: 'busy', on: false });
          if (extendBefore) {
            const commandLabel = msg.__adopt ? '/ADOPT' : msg.__cascade ? '/IDEA --EXTEND' : String(cmd || '').toUpperCase();
            const root = toFsPath(wsroot);
            const isAgent = String(_out?.execution?.selected || '').trim() === 'local_agent';
            if (!Array.isArray(_out.files)) _out.files = [];
            const returnedPlan = _out.files.find((f) => String(f?.path || '').replace(/^\.?\//, '') === 'docs/harper/plan.json');
            let verdict;
            if (msg.__adopt) {
              // the same reconcile as the cascade (restore and keep a rejected run aside); adopt.js checks the plan
              const a = msg.__adopt;
              // never a project file: only docs/harper/, CLike's own files and the root README are written and committed
              const writable = adoptLib.writableFiles(_out.files);
              _out.files = writable.kept;
              if (writable.dropped.length) {
                panel.webview.postMessage({ type: 'echo', message: `⚠ /ADOPT: ${writable.dropped.length} file(s) the analysis may not write ignored (it writes docs/harper/ and the root README; the survey report and the code map are CLike's): ${writable.dropped.slice(0, 10).join(', ')}` });
              }
              a.restoreProject();
              verdict = releaseExtend.reconcileExtend({
                root, before: extendBefore, files: _out.files, isAgent, mode: 'adopt',
                cascade: { release: 'v1', adoptedBefore: a.adoptedBefore, originalReadme: a.originalReadme },
                validateExtendPlan, startedAt: extendStartedAt,
                adopt: {
                  check: (beforeText, afterText) => adoptLib.checkAdoptedPlan({ beforeText, afterText, areas: a.areas, baselineIds: a.baselineIds, validateExtendPlan, projectAreas: releaseExtend.projectAreas(root) }),
                  section: (summary, warnings, docs) => adoptLib.adoptVerificationMarkdown({ areas: a.areas, baselineIds: a.baselineIds, summary, baseline: a.baseline, warnings, docs }),
                },
              });
            } else if (msg.__cascade) {
              verdict = releaseExtend.reconcileExtend({
                root, before: extendBefore, files: _out.files, isAgent, mode: 'cascade',
                cascade: msg.__cascade, validateExtendPlan, startedAt: extendStartedAt,
              });
            } else {
              verdict = validateExtendPlan({
                beforeText: extendBefore.plan,
                afterText: returnedPlan && typeof returnedPlan.content === 'string' ? returnedPlan.content : readPlanText(root),
                anchorReq: msg.anchorReq || '',
                explicitReq: msg.explicitReq || '',
              });
              if (verdict.ok && verdict.restored.length) {
                // Keep the repaired plan: in the files to write (cloud) and on disk (local agent).
                if (returnedPlan) returnedPlan.content = verdict.planText;
                if (isAgent) fsSync.writeFileSync(path.join(root, 'docs', 'harper', 'plan.json'), verdict.planText, 'utf8');
              }
              if (!verdict.ok && isAgent) {
                // The local agent already wrote the workspace: put PLAN.md and plan.json back.
                for (const [rel, text] of [['plan.json', extendBefore.plan], ['PLAN.md', extendBefore.planMd]]) {
                  if (text != null) fsSync.writeFileSync(path.join(root, 'docs', 'harper', rel), text, 'utf8');
                }
              }
              if (verdict.ok) {
                const tech = releaseExtend.reconcileExtend({ root, before: extendBefore, files: _out.files, isAgent, mode: 'plan' });
                verdict.warnings.push(...tech.warnings);
              }
            }
            for (const w of verdict.warnings) panel.webview.postMessage({ type: 'echo', message: `⚠ ${commandLabel}: ${w}` });
            if (!verdict.ok) {
              const message = `✖ ${commandLabel} rejected — the plan breaks the extend rules; the documents are restored:\n` +
                verdict.errors.map((e) => `- ${e}`).join('\n') +
                (verdict.kept ? `\nThe documents of this run are kept in ${verdict.kept}/ (compare them, or run the command again).` : '');
              panel.webview.postMessage({ type: 'echo', message });
              await appendSessionJSONL(activeMode, { ts: Date.now(), role: 'system', content: message, model: state.model || 'auto', attachments: [] });
              clikeHarperBlockingRun = false;
              panel.webview.postMessage({ type: 'busy', on: false, force: true });
              return;
            }
            if (msg.__adopt) {
              const ids = msg.__adopt.baselineIds;
              msg.__extendCommit = {
                files: [...releaseExtend.cascadeCommitFiles(root, 'v1'), ...Object.values(releaseExtend.ADOPT_FILES), adoptLib.CODEMAP, '.clike/project.json', msg.__adopt.surveyReport,
                  // what /init added (CLike settings, policies, skills, templates, .gitignore rules) and the baseline profile
                  ...adoptLib.clikeOwnFiles(root),
                  ...ids.map((id) => `runs/kit/${id}/ci/LTC.json`)],
                message: `docs(harper): adopt ${path.basename(root)} — ${msg.__adopt.areas.length} area(s), ${verdict.delta.length + ids.length} REQ(s)\n\n[harper:adopt] runId=${runId}`,
              };
              // the baseline is the oracle from now on: locked like any acceptance surface
              for (const id of ids) {
                try { await postAcceptanceLock(wsroot, id); } catch (e) { log(`[adopt] lock ${id}: ${e?.message || e}`); }
              }
              const done = verdict.delta.filter((r) => r.status === 'done').length;
              const message = `✔ /adopt: ${msg.__adopt.areas.length} area(s) adopted — ${ids.length} baseline REQ(s) (${ids.join(', ')}), ` +
                `${done} capability REQ(s) done, ${verdict.delta.length - done} open. Review ${verdict.report || 'the EXTEND report'} and ${msg.__adopt.surveyReport}. ` +
                (() => {
                  const adoptedNow = new Set([...(msg.__adopt.adoptedBefore || []), ...msg.__adopt.areas.map((x) => x.name)]);
                  const left = releaseExtend.projectAreas(toFsPath(wsroot)).map((x) => x.name).filter((n) => n && !adoptedNow.has(n));
                  return left.length
                    ? `Next: /adopt --area ${left[0]} (still to adopt: ${left.join(', ')}), or /kit an open REQ.`
                    : 'Next: /idea --extend for the next release, or /kit an open REQ.';
                })();
              panel.webview.postMessage({ type: 'echo', message });
              await appendSessionJSONL(activeMode, { ts: Date.now(), role: 'system', content: message, model: state.model || 'auto', attachments: [] });
            } else if (msg.__cascade) {
              // the delivered baseline gets its tag before the release changes the documents
              const tag = msg.__cascade.dryRun ? '' : releaseExtend.tagBaseline(root, msg.__cascade.baseline);
              const registered = !msg.__cascade.dryRun && releaseExtend.registerAreas(root, verdict.newAreas);
              if (registered) {
                panel.webview.postMessage({ type: 'echo', message: `✔ /idea --extend: new area(s) in .clike/project.json — ${verdict.newAreas.map((a) => `${a.name} (${a.root})`).join(', ')}` });
              }
              if (!msg.__cascade.dryRun) {
                msg.__extendCommit = {
                  files: [...releaseExtend.cascadeCommitFiles(root, msg.__cascade.release), ...(registered ? ['.clike/project.json'] : [])],
                  message: releaseExtend.cascadeCommitMessage({ ...msg.__cascade, delta: verdict.delta }, runId),
                };
              }
              const ids = verdict.delta.map((r) => `${r.id} ${r.change}`).join(', ');
              const message = `✔ /idea --extend ${msg.__cascade.baseline} → ${msg.__cascade.release}${msg.__cascade.dryRun ? ' (dry run)' : ''}: ` +
                `${verdict.delta.length} new REQ(s) — ${ids}. Review ${verdict.report}${tag ? `; baseline tagged ${tag}` : ''}.` +
                (msg.__cascade.dryRun ? '' : ` Next: /kit ${verdict.delta[0]?.id || ''}.`);
              panel.webview.postMessage({ type: 'echo', message });
              await appendSessionJSONL(activeMode, { ts: Date.now(), role: 'system', content: message, model: state.model || 'auto', attachments: [] });
            }
          }
          // 3) POST-RUN: persist the outcome (summary + optional echo/text)
          const summary = [
            _out?.echo ? `[echo] ${_out.echo}` : null,
            (Array.isArray(_out?.diffs) && _out.diffs.length) ? `[diffs] ${_out.diffs.length}` : null,
            (Array.isArray(_out?.files) && _out.files.length) ? `[files] ${_out.files.length}` : null,
            _out?.text ? `[text] ${Math.min(String(_out.text).length, 200)} chars` : null
          ].filter(Boolean).join(' • ') || 'no artifacts';
          log(`[harperRun] summary done`);
          // --- PERSIST TELEMETRY (avoid duplicates, one file per run) ---
          try {
            // Local-agent runs report their own executor/model/usage (_out.telemetry);
            // cloud runs are attributed to the selected provider and model.
            const t = _out?.telemetry || {};
            const isAgentRun = t.execution === 'local_agent';
            await persistTelemetryVSCode(wsroot, project_id, runId, phase, {
              ...t,
              provider: isAgentRun ? t.provider : activeProvider,
              model: isAgentRun ? t.model : activeModel,
              usage: _out?.usage || t.usage || {},
              pricing: t.pricing || {},
              files: _out?.files || [],
            });
            runFeedCost({ usage: _out?.usage || t.usage || {}, pricing: t.pricing || _out?.pricing || {} });
          } catch (e) {
            log(`[telemetry] skipped: ${e?.message || e}`);
          }
          log(`[harperRun] telemetry done`);
          await appendSessionJSONL(activeMode, {
            ts: Date.now(),
            role: 'system',
            content: `✔ ${String(cmd || '').toUpperCase()} ${msg_bubble} done — ${summary}`,
            model:  state.model || 'auto',
            attachments: Array.isArray(msg.attachments) ? msg.attachments : []
          });
          panel.webview.postMessage({
            type: 'echo',
            message: `✔ ${String(cmd || '').toUpperCase()} ${String(msg_bubble || '').toUpperCase()} done — ${summary}`
          });

          
          let written = [];
          const executionSelected = String(_out?.execution?.selected || '').trim();

          if (Array.isArray(_out?.files) && _out.files.length) {
            if (executionSelected === 'local_agent') {
              log(
                `[harperRun] local_agent produced ${_out.files.length} file artifact(s); ` +
                `skipping saveGeneratedFiles because the agent already wrote workspace files.`
              );
              // Exception: persist the orchestrator-normalized docs/harper/plan.json
              // for /plan and /extend so the deterministic capability enrichment
              // (structured `capabilities` block + schema_version) reaches disk for
              // /kit, matching the cloud path. Additive superset of the agent's file.
              if (phase === 'plan' || phase === 'extend') {
                const enrichedPlan = _out.files.filter(
                  f => String(f?.path || '').replace(/^\.?\//, '') === 'docs/harper/plan.json'
                );
                if (enrichedPlan.length) {
                  try {
                    await saveGeneratedFiles(enrichedPlan, { phase, runId });
                    log(`[harperRun] persisted orchestrator-enriched plan.json for ${phase}`);
                  } catch (e) {
                    log(`[harperRun] failed to persist enriched plan.json: ${e?.message || e}`);
                  }
                }
              }
            } else {
              written = await saveGeneratedFiles(_out.files, { phase, runId });
            }
            panel.webview.postMessage({ type: 'files', data: _out.files });
            log(`[harperRun] written ${written.length} files`);
            // A KIT without its eval profile is incomplete, whoever wrote it (cloud model, Codex,
            // Claude Code): not committed, not evaluated. B2B REQ-026 had only check.py in ci/.
            if (phase === 'kit' && targetReqId &&
                !fsSync.existsSync(path.join(toFsPath(wsroot), 'runs', 'kit', String(targetReqId).toUpperCase(), 'ci', 'LTC.json'))) {
              throw new Error(`KIT_INCOMPLETE: runs/kit/${String(targetReqId).toUpperCase()}/ci/LTC.json is missing: the KIT is not complete ` +
                `(not committed, not evaluated). Run /kit ${targetReqId} again to complete it.`);
            }
            // A cloud repair's rejected changes to locked tests come back from the orchestrator:
            // kept for the developer as for a local agent (rejected-test-fix.js)
            const cloudRejected = _out?.repair?.rejected_tests;
            if (phase === 'kit' && msg.__acceptance && cloudRejected && typeof cloudRejected === 'object') {
              const issues = _out?.repair?.amendments?.rejected || {};
              const saved = saveRejectedTestFix(toFsPath(wsroot), targetReqId, msg.__acceptance.cycle,
                Object.entries(cloudRejected).map(([rel, after]) => ({ rel, before: msg.__acceptance.before[rel], after, issues: issues[rel] || [] })));
              if (saved) msg.__rejectedTestFix = saved;
            }
            // Locked tests a local agent changed are governed (and the rejected ones restored)
            // before the commit: otherwise the commit holds a change CLike then reverts.
            const acceptance = phase === 'kit' && (msg.__acceptance ||
              (msg.acceptanceFirst && msg.__acceptanceBefore ? { before: msg.__acceptanceBefore, failures: [], cycle: 0 } : null));
            if (acceptance && !msg.__acceptanceGoverned) {
              await governAcceptanceChanges(targetReqId, acceptance.before, acceptance.failures, acceptance.cycle, msg);
              msg.__acceptanceGoverned = true;
            }
            const settings = cfg();
            // /adopt: a file naming this machine (the project's absolute path, the home folder) stays out of the commit
            let machineFiles = [];
            if (msg.__adopt && msg.__extendCommit) {
              machineFiles = adoptLib.machinePathFiles(toFsPath(wsroot), [...new Set([..._out.files.map((f) => f.path), ...msg.__extendCommit.files])].map((p) => String(p).replace(/^\.?\//, '')));
              if (machineFiles.length) {
                panel.webview.postMessage({ type: 'echo', message: `⚠ /adopt: ${machineFiles.length} file(s) name a folder of this machine and stay out of the commit (remove the path, then commit them): ${machineFiles.slice(0, 10).join(', ')}` });
              }
            }
            const notMachine = (p) => !machineFiles.includes(String(p).replace(/^\.?\//, ''));
            if (settings.gitAutoCommit) {
               try {
                const synced = await clikeGitSync(
                phase,
                runId,
                targetReqId,
                [..._out.files.map(f => f.path), ...(msg.__extendCommit?.files || []),
                  // the finalize closes a release: the Harper documents left out of earlier commits go with it
                  ...(phase === 'finalize' ? finalizeVerify.uncommittedHarperDocs(toFsPath(wsroot)) : [])].filter(notMachine),
                { workspaceRoot: toFsPath(wsroot), finalizeOpenPr: (phase === 'finalize'),
                  commitMessage: phase === 'finalize' ? finalizeCommitMessage(toFsPath(wsroot), runId) : (msg.__extendCommit?.message || '') },
                settings,
                out
              );
                // committed: the next /finalize records the developer's changes afresh
                if (phase === 'finalize' && synced?.committed) finalizeVerify.clearDirtyBaseline(toFsPath(wsroot));
              } catch (err) {
                log(`[harperRun] gitSync error ${err}`);

              }
            }
      
          }
          log(`[harperRun] written files done`);
          // every step of every SPEC use case is covered by a REQ (cloud and local agents alike)
          if (phase === 'plan' || phase === 'extend') {
            try {
              const coverage = projectUseCaseCoverage(toFsPath(wsroot));
              if (coverage) {
                panel.webview.postMessage({ type: 'echo', message: useCaseCoverageMessage(coverage) });
                log(`[useCases] ${JSON.stringify({ ...coverage, uncovered: coverage.uncovered.slice(0, 50) })}`);
              }
            } catch (e) {
              log(`[useCases] coverage not computed: ${e?.message || e}`);
            }
            // REQs the plan marks not KIT-ready: the owner's open questions, before any /kit
            try {
              const readiness = planReadiness.planReadiness(await readPlanJson(wsroot));
              const line = planReadiness.planReadinessMessage(readiness);
              if (line) panel.webview.postMessage({ type: 'echo', message: line });
              log(`[kitReadiness] ${JSON.stringify(readiness.notReady)}`);
            } catch (e) {
              log(`[kitReadiness] not computed: ${e?.message || e}`);
            }
          }
          // /extend and /idea --extend change lane guides too: the index follows them
          if (phase === 'plan' || phase === 'extend') {
            try {
              const laneItems = await collectLaneGuidesRagItems(wsroot, {
                maxFiles: 200,
                maxBytes: 512 * 1024,
              });
              const count = (laneItems && laneItems.length) || 0;
              log(`[harperRAG] lane-guides collection after /${phase}: ${count} items`);
              if (count > 0) {
                await preIndexRag(project_id, laneItems, urlRag, out);
                log(`[harperRAG] indexed ${count} lane-guide items for project ${project_id}`);
              }
            } catch (e) {
              log(`[harperRAG] lane-guides indexing failed: ${e?.message || e}`);
            }
          }
          if (phase==="kit") {
            await saveKitCommand(wsroot,plan,targetReqId,out)
            // --- KIT RAG indexing: runs/kit/REQ-XXX/src only ---
            const allItems = [];
            const normalizedReq = targetReqId.toUpperCase();
            const items = await collectKitRagItems(wsroot, normalizedReq, { maxFiles: 400, maxBytes: 512*1024 });
            if (items && items.length) {
              allItems.push(...items);
            }
            log(`[harperRAG] indexing ${allItems.length} KIT items for REQ(s): ${normalizedReq}`);

            if (allItems.length) {
              const ragIndexResult = await preIndexRag(project_id, allItems, urlRag, out);
              if (ragIndexResult && ragIndexResult.ok) {
                log(`[harperRAG] indexed ${allItems.length} KIT items for REQ(s): ${normalizedReq}`);
                await pruneKitMemory(project_id, normalizedReq, allItems, 400);
              } else {
                log(`[harperRAG] KIT RAG indexing skipped for REQ(s): ${normalizedReq} -> ${ragIndexResult?.error || 'unknown error'}`);
              }

            } else {
              log('[harperRAG] no KIT RAG items collected (nothing to index)');
            }

          }
          // Tests summary
          if (_out?.tests?.summary) {
            panel.webview.postMessage({ type: 'echo', message: `✅ Tests: ${_out.tests.summary}` });
          }
          // Warnings / Errors
          if (Array.isArray(_out?.warnings) && _out.warnings.length) {
            panel.webview.postMessage({ type: 'echo', message: `⚠ Warnings: ${_out.warnings.join(' | ')}` });
          }
          if (Array.isArray(_out?.errors) && _out.errors.length) {
            panel.webview.postMessage({ type: 'error', message: formatHarperError(_out) });
          }
          msg.__result = 'ok';
          msg.__outcome = {
            files: (Array.isArray(_out?.files) ? _out.files : []).map(f => f.path).filter(Boolean),
            warnings: Array.isArray(_out?.warnings) ? _out.warnings.slice(0, 20) : [],
          };
          if (phase === 'kit' && msg.acceptanceFirst && msg.__acceptanceBefore && !msg.__acceptanceGoverned) {
            // a local agent may have touched the locked tests: govern and restore
            await governAcceptanceChanges(targetReqId, msg.__acceptanceBefore, [], 0);
          }
          if (harperCancelled() && ((phase === 'finalize' && cfg().finalizeVerify) || (phase === 'kit' && cfg().autoEvalAfterKit))) {
            panel.webview.postMessage({ type: 'echo', message: `⏹ /${phase} cancelled: the next step (${phase === 'finalize' ? 'solution verification' : 'auto-eval'}) does not start.` });
          } else if (phase === 'finalize' && cfg().finalizeVerify) {
            clikeHarperBlockingRun = false;
            await continueFinalizeVerify(msg);
          } else if (phase === 'finalize') {
            recordFinalizeOutcome('ok', 'solution verification off (clike.finalize.verify)');
          }
          const afterKitEval = phase === 'kit' && !msg.autoEvalRepair && !msg.acceptanceStage && !msg.__autopilot && targetReqId && cfg().autoEvalAfterKit;
          if (afterKitEval && !harperCancelled() && harperStopAfterStep) {
            panel.webview.postMessage({ type: 'echo', message: `⏸ /kit ${targetReqId}: stopped after the KIT, as you asked; the auto-eval does not start (/eval ${targetReqId} --fix).` });
          } else if (afterKitEval && !harperCancelled()) {
            panel.webview.postMessage({ type: 'echo', message: `↻ AUTO-EVAL ${targetReqId} (clike.autoEval.afterKit)` });
            clikeHarperBlockingRun = false;
            await handleWebviewMessage({
              type: 'harperEDD', cmd: 'eval', targets: [targetReqId], targetReqId, attachments: [], fix: { hint: '' },
            });
          }
        } catch (e) {
          if (harperCancelled() || e?.name === 'AbortError') {
            discardCancelledRun();
            return;
          }
          panel.webview.postMessage({ type: 'busy', on: false }) 
          panel.webview.postMessage({ type: 'error', message: formatHarperError(e) });
          if (phase === 'finalize') recordFinalizeOutcome('failed', String(e?.message || e));
          if (phase === 'finalize' && msg.finalizeRepair) {
            panel.webview.postMessage({ type: 'echo', message:
              `✖ SOLUTION REPAIR cycle ${msg.finalizeRepair.cycle} could not run (${String(e?.message || e).split('\n')[0]}). ` +
              `The verification stopped: run /finalize again to continue from the current state. Evidence: ${finalizeVerify.EVIDENCE_PATH}` });
          }
        }
        clikeHarperBlockingRun = false;
        panel.webview.postMessage({ type: 'busy', on: false, force: true });
      }
      //Harper Evals
      //Harper Evals
      if (msg.type === 'harperEDD' ) {
        let targets, targetReqId
        const phase = msg.cmd;
        // a --fix cycle continues the phase the user started (and its Cancel)
        const harperAbort = harperSignal(!(msg.fix && Number(msg.fix.cycle || 0) > 0));
        if (harperAbort.aborted) {
          panel.webview.postMessage({ type: 'busy', on: false });
          return;
        }
        const gateMethodologyError = 'Gate is CLike-owned. Methodology flags are not accepted for /gate in MVP.';
        if (
          phase === 'gate' &&
          (msg.methodology || msg.agent || msg.methodology_context)
        ) {
          log('[harperEDD][gate] rejected methodology context for CLike-owned gate');
          vscode.window.showErrorMessage(gateMethodologyError);
          panel.webview.postMessage({ type: 'error', message: gateMethodologyError });
          panel.webview.postMessage({ type: 'busy', on: false });
          return;
        }
        const ws_root= getWorkspaceRoot()
        //log(`[harperEDD] ws_root: ${ws_root}`)
        const runId = (Math.random().toString(16).slice(2) + Date.now().toString(16));
        const executionPreference = normalizeExecutionPreference(
          state.executionPreference || getDefaultExecutionPreference()
        );
        log(`[harperEDD] runId ...`,  runId);
        const mode = (msg.running) ? msg.running : 'auto'
        const modeContent = (msg.modeContent) ? msg.modeContent : 'pass'
        const isManual = msg.running === 'manual' && msg.modeContent === 'pass' ? true : false

        const plan = await readPlanJson(ws_root);
       
        if (phase === 'eval' || phase === 'gate') {
          const explicitTarget = String(msg?.targetReqId || '').trim().toUpperCase();

          if (explicitTarget) {
            targets = explicitTarget;
          } else if (Array.isArray(msg?.targets) && msg.targets.length > 0) {
            targets = String(msg.targets[0] || '').trim().toUpperCase();
          } else if (typeof msg?.targets === 'string' && msg.targets.trim()) {
            targets = msg.targets.trim().toUpperCase();
          } else {
            targets = '';
          }
        }
        targetReqId = await runEvalGateCommand (plan, targets)
        if (!targetReqId) {
            panel.webview.postMessage({ type: 'busy', on: false });
            return;
          }
        targets = targetReqId
        msg.path =  "runs/kit/" + targets+"/ci/LTC.json"
        log("harperEDD targetReqId", targetReqId)
        
        if (!targets && !targetReqId){
          vscode.window.showErrorMessage('REQ-ID not found. Run /eval REQ-ID ... /gate REQ-ID');
          panel.webview.postMessage({ type: 'busy', on: false });
          return;
        }
        if (phase === 'eval' && msg.supersede) {
          // /eval REQ --supersede: the developer declares a change of the release, then the eval runs
          let author = '';
          try { author = require('child_process').execFileSync('git', ['config', 'user.name'], { cwd: ws_root.fsPath, stdio: ['ignore', 'pipe', 'ignore'] }).toString().trim(); } catch { /* none */ }
          const declared = releaseExtend.declareSupersede(ws_root.fsPath, targets, msg.supersede.ref, msg.supersede.reason, { author });
          panel.webview.postMessage({ type: 'echo', message: `${declared.ok ? '✔' : '✖'} /eval ${targets} --supersede: ${declared.message}` });
          await appendSessionJSONL(activeMode, { ts: Date.now(), role: 'system', content: `${declared.ok ? '✔' : '✖'} SUPERSEDE ${targets}: ${declared.message}`, model: state.model || 'auto', attachments: [] });
          if (!declared.ok) {
            panel.webview.postMessage({ type: 'busy', on: false, force: true });
            return;
          }
        }
        if (phase === 'eval' && msg.accept) {
          // /eval REQ --accept: the developer accepts a deliberate edit of the locked tests / ci
          await acceptAcceptanceEdit(ws_root, targets, String(msg.accept.reason || ''));
          return;
        }
        await appendSessionJSONL(activeMode, {
          role: 'user',
          content: `▶ ${phase.toUpperCase()} ${targets} ${mode} ${modeContent} | mode=${state.mode} model=${state.model} exec=${executionPreference}${methodologyTag(msg)}`,
          model:  state.model || 'auto',
          attachments: Array.isArray(msg.attachments) ? msg.attachments : []
        });
        // Echo pre-run
        panel.webview.postMessage({
          type: 'echo',
          message: `▶ ${phase.toUpperCase()} ${targets} ${mode} ${modeContent} | mode=${state.mode} model=${state.model} exec=${executionPreference}${methodologyTag(msg)}`
        });
        const path_ltc_json = msg.path
        log(`[harperEDD] path_ltc_json: ${path_ltc_json}`)
        const ltcUri = vscode.Uri.joinPath(ws_root, path_ltc_json);
        log(`[harperEDD] ltcUri: ${ltcUri}`);
        
        
        try {
          const stats = fsSync.statSync(ltcUri.fsPath);
          if (!stats.isFile() && !isManual) {
              vscode.window.showErrorMessage('LTC.json not found. Run /kit REQ-ID to generate source and tests and /eval REQ-ID -> /gate REQ-ID');
              panel.webview.postMessage({ type: 'busy', on: false });
              return;
          }
            // ... code to continue
        } catch (error) {
          // Handle the case where the file does not exist at all (fs.statSync would throw)
          vscode.window.showErrorMessage(`File LTC.json not found at: ${ltcUri.fsPath}`);
          panel.webview.postMessage({ type: 'busy', on: false });
          return;
        }
        var report = {}

        clikeHarperBlockingRun = true;
        panel.webview.postMessage({ type: 'busy', on: true });

        var files_git = []
        let callGit =true;
        const settings = cfg();
        const localAgentAvailability = detectLocalAgentAvailability(settings);
        log(`[harperEDD][agent][availability] ${JSON.stringify(localAgentAvailability)}`);
        const selectedLocalExecutor = resolveSelectedLocalAgentExecutor(
            settings,
            state.localAgentExecutor || 'auto',
            phase
        );

        switch (msg.cmd) {
          case 'eval': {
            // The eval right after an auto-eval repair runs without the pre-pass: the repair already
            // changed (and checked in the sandbox) the candidate; a pre-pass would change it again
            // unverified (it once undid a repair that had made the unit tests pass).
            const afterRepair = !!msg.fix && Number(msg.fix.cycle || 0) > 0;
            // clike.localAgent.allowEval = false: straight to the canonical eval, no pre-pass
            const evalAgentPrepassRequested =
              settings.localAgentAllowEval !== false &&
              executionPreference !== 'cloud_only' && !!selectedLocalExecutor && !afterRepair;

            if (evalAgentPrepassRequested) {
              log(
                `[harperEDD][agent] local eval pre-pass requested; ` +
                `canonical CLike eval will still run afterwards req=${targets} ` +
                `executor=${selectedLocalExecutor}`
              );

              const evalHeaders = { "Content-Type": "application/json" };
              const evalProjectId = getProjectId();
              const evalProjectName = getProjectNameFromWorkspace();

              const evalPayload = {
                cmd: 'eval',
                phase: 'eval',
                mode: 'harper',
                model: state.model || 'auto',
                profileHint: null,
                executionPreference: 'prefer_local_agent',
                docRoot: 'docs/harper',
                core: defaultCoreForPhase('eval'),
                messages: [],
                gen: {
                  temperature: 0.2,
                  max_tokens: 9999,
                  top_p: 0.9,
                  stop: ["````END```"],
                  presence_penalty: 0,
                  frequency_penalty: 0.2,
                  seed: 42,
                  tools: "",
                  remote: "",
                  response_format: "",
                  tool_choice: "",
                },
                attachments: [],
                flags: {
                  neverSendSourceToCloud: false,
                  redaction: true,
                },
                runId,
                historyScope: state.historyScope || 'singleModel',
                project_id: evalProjectId,
                project_name: evalProjectName,
                mode_contract: buildModeContract(activeMode, 'eval'),
                eval: {
                  targets: [targets],
                  ltc_path: path_ltc_json,
                  canonical_eval_after_prepass: true,
                },
              };
              if (msg.methodology) evalPayload.methodology = msg.methodology;
              if (msg.agent) evalPayload.agent = msg.agent;
              if (msg.methodology_context) evalPayload.methodology_context = msg.methodology_context;

              const evalBody = await buildHarperBody('eval', evalPayload, ws_root, out);

              evalBody.localAgentExecutor = normalizeLocalAgentExecutor(
                selectedLocalExecutor || state.localAgentExecutor || settings.localAgentPreferredExecutor || 'auto'
              );

              evalBody.localAgentCapabilities = detectLocalAgentAvailability(settings);
              evalBody.localAgentTimeoutSeconds = Math.max(
                60,
                resolveLocalAgentTimeoutMinutes(evalBody.localAgentExecutor, settings) * 60
              );

              evalBody.localRuntime = {
                shell: process.env.SHELL || 'zsh',

                // Runtime-neutral contract.
                // Eval must follow the LTC/HOWTO and repository-native commands.
                implementation_runtime_policy: 'infer_from_ltc_howto_and_project_contracts',
                dependency_strategy: 'use_existing_project_scripts_or_report_blocked',
                package_install_policy: 'never_install_global_packages',

                // Optional tool hints only. These are helpers, not implementation rules.
                tool_hints: {
                    node: 'node',
                    npm: 'npm',
                    python: 'python3',
                    java: 'java',
                    go: 'go',
                    ruby: 'ruby',
                    rust: 'rustc',
                    php: 'php',
                    dotnet: 'dotnet',
                    kubectl: 'kubectl',
                },
              };

              

              try {
                const evalPrepassGateway = await callHarper('eval', evalBody, evalHeaders, {
                  timeoutMs: 1000 * 60 * cfg().harperTimeout,
                  signal: harperAbort,
                });

                const evalPrepassOut = evalPrepassGateway.out;
                const evalLocalAgentPackage =
                  evalPrepassOut?.local_agent || evalPrepassGateway?.local_agent || null;

                log(`[harperEDD][agent][eval-response] ${JSON.stringify({
                  hasOut: !!evalPrepassOut,
                  execution: evalPrepassOut?.execution || null,
                  hasLocalAgent: !!evalPrepassOut?.local_agent,
                  localAgentAction: evalPrepassOut?.local_agent?.action || null,
                })}`);

                if (evalLocalAgentPackage?.action === 'local_agent_required') {
                  // The pre-pass agent repairs the candidate: lock the acceptance surface first
                  // (idempotent) and govern what it changed in test/ and ci/ afterwards, as the
                  // --fix repair does; otherwise its edits make the canonical eval ACCEPTANCE_TAMPERED.
                  let prepassAcceptanceBefore = null;
                  try {
                    await postAcceptanceLock(ws_root, targets);
                    prepassAcceptanceBefore = snapshotAcceptanceSurface(getWorkspaceRoot().fsPath, targets);
                  } catch (err) {
                    log(`[harperEDD][agent] acceptance lock before the eval pre-pass failed: ${err?.message || err}`);
                  }
                  const evalAgentOut = await executeLocalAgentPackage({
                    localAgentPackage: evalLocalAgentPackage,
                    phase: 'eval',
                    reqId: targets,
                    runId,
                    executionPreference,
                    settings,
                    wsroot: ws_root,
                    headers: evalHeaders,
                    harperTimeout: cfg().harperTimeout,
                    panel,
                    out,
                  });
                  try {
                    await persistTelemetryVSCode(ws_root, getProjectId(), runId, 'eval', {
                      ...(evalAgentOut?.telemetry || {}),
                      files: evalAgentOut?.files || [],
                    });
                    runFeedCost(evalAgentOut?.telemetry || {});
                  } catch (e) {
                    log(`[telemetry] eval pre-pass skipped: ${e?.message || e}`);
                  }
                  if (prepassAcceptanceBefore) {
                    // Evidence for test fixes: the failures of the previous eval of the --fix loop.
                    await governAcceptanceChanges(targets, prepassAcceptanceBefore, msg?.fix?.lastFailures || [], 'eval pre-pass');
                  }
                } else {
                  log(
                    `[harperEDD][agent] eval pre-pass did not return local_agent package; ` +
                    `continuing with canonical eval req=${targets}`
                  );
                }
              } catch (err) {
                const failMsg = `[harperEDD][agent] eval pre-pass failed: ${err?.message || String(err)}`;
                log(failMsg);
                if (harperAbort.aborted) {
                  // Cancel: no canonical eval after the stopped pre-pass
                  panel.webview.postMessage({ type: 'echo', message: `⏹ /eval ${targets} cancelled: the eval was stopped.` });
                  panel.webview.postMessage({ type: 'busy', on: false, force: true });
                  return;
                }

                if (executionPreference === 'local_agent_only') {
                  panel.webview.postMessage({ type: 'busy', on: false });
                  panel.webview.postMessage({ type: 'error', message: failMsg });
                  return;
                }

                panel.webview.postMessage({
                  type: 'echo',
                  message: `⚠ Local eval pre-pass failed. Continuing with canonical CLike eval. Reason: ${err?.message || String(err)}`
                });
              }
            }
            else {
              log(
                `[harperEDD][agent] local eval pre-pass skipped; ` +
                `reason=${afterRepair ? 'after_auto_eval_repair' : executionPreference === 'cloud_only' ? 'cloud_only' : 'no_local_executor_available'} ` +
                `req=${targets}`
              );
            }
            log("[harperEDD] Calling canonical eval for req:" + targets + " in: " + ws_root);
            if (!isManual) await ensureToolsForEval(targets);
            const evalOptions = Array.isArray(msg.regressionReqs) && msg.regressionReqs.length ? { regressionReqs: msg.regressionReqs } : {};
            report = await handleEval(path_ltc_json, ws_root, targets, mode, modeContent, harperAbort, evalOptions);
            if (!harperAbort.aborted && !isManual && await installReportedTools(targets, report)) {
              report = await handleEval(path_ltc_json, ws_root, targets, mode, modeContent, harperAbort, evalOptions);
            }
            if (harperAbort.aborted) {
              panel.webview.postMessage({ type: 'echo', message: `⏹ /eval ${targets} cancelled: the eval was stopped.` });
              panel.webview.postMessage({ type: 'busy', on: false, force: true });
              return;
            }
            const evalMethodologyContext = buildEffectiveEvalMethodologyContext(
              msg.methodology_context || {
                methodology: msg.methodology,
                agent: msg.agent,
              }
            );
            report = attachBmadQaAdvisory(report, targets, evalMethodologyContext);
            if (report?.bmad_advisory) {
              panel.webview.postMessage({
                type: 'echo',
                message: `ℹ BMAD QA advisory only. Canonical CLike EvalRunner remains authoritative. Suggested next command: ${report.bmad_advisory.suggested_next_command}`
              });
            }
            const reportFile = await saveEvalCommand(ws_root, plan, targets, report, out);
            msg.__report = summarizeEvalReport(report);
            files_git.push(toFsPath(reportFile));

            break;
          }
          case 'gate': {
            if (isManual) {
              // WP6: the override is decided and audited by the orchestrator, never produced here.
              const reason = await vscode.window.showInputBox({
                title: `Manual gate override for ${targets}`,
                prompt: 'Why are you promoting without a passing gate? (recorded in the audit log)',
                ignoreFocusOut: true,
                validateInput: (v) => (v && v.trim().length >= 10 ? null : 'At least 10 characters'),
              });
              if (!reason) {
                panel.webview.postMessage({ type: 'echo', message: `Gate override for ${targets} cancelled.` });
                panel.webview.postMessage({ type: 'busy', on: false });
                clikeHarperBlockingRun = false;
                return;
              }
              let author = '';
              try {
                author = require('child_process')
                  .execFileSync('git', ['config', 'user.name'], { cwd: ws_root.fsPath, stdio: ['ignore', 'pipe', 'ignore'] })
                  .toString().trim();
              } catch {}
              report = await postGateOverride(ws_root, targets, reason.trim(), author || require('os').userInfo().username);
            } else {
              await ensureToolsForEval(targets);
              const gateOpts = { promote: false, reqId: targets, mode: mode, result: modeContent, signal: harperAbort };
              report = await handleGate(path_ltc_json, ws_root, targets, gateOpts);
              if (!harperAbort.aborted && await installReportedTools(targets, report)) {
                report = await handleGate(path_ltc_json, ws_root, targets, gateOpts);
              }
              if (harperAbort.aborted) {
                panel.webview.postMessage({ type: 'echo', message: `⏹ /gate ${targets} cancelled: the gate was stopped.` });
                panel.webview.postMessage({ type: 'busy', on: false, force: true });
                return;
              }
            }

            if (report?.executor === 'reused_eval') {
              const at = report.reused_eval_at ? new Date(report.reused_eval_at * 1000).toLocaleTimeString() : '';
              panel.webview.postMessage({ type: 'echo', message: `⚡ GATE ${targets}: nothing changed since the passing eval${at ? ` of ${at}` : ''} — its verdict is reused (no second run); acceptance integrity and required outputs checked now.` });
            }
            msg.__report = summarizeEvalReport(report);
            const { report_file, filesToCommit, planFiles, promotion } = await saveGateCommand(
              ws_root,
              plan,
              targets,
              report,
              out,
              { promote: msg.promote || undefined }
            );
            if (promotion) {
              panel.webview.postMessage({
                type: 'echo',
                message: `${promotion.promoted ? '✔' : '⚠'} PROMOTION ${promotion.summary}` +
                  (promotion.report ? `\nReport: ${vscode.workspace.asRelativePath(promotion.report)}` : ''),
              });
              msg.__report = { ...(msg.__report || {}), promotion };
            }

            log("report_file, filesToCommit, planFiles", report_file, filesToCommit, planFiles);

            const gateVerdict = String(report?.gate || '').trim().toLowerCase();
            const reportFs = report_file ? toFsPath(report_file) : '';

            const committedTargets = Array.isArray(filesToCommit)
              ? filesToCommit.map(p => toFsPath(p)).filter(Boolean)
              : String(filesToCommit || '')
                  .split(',')
                  .map(s => s.trim())
                  .filter(Boolean)
                  .map(p => toFsPath(p));

            const planTargets = Array.isArray(planFiles)
              ? planFiles.map(p => toFsPath(p)).filter(Boolean)
              : [];

            files_git = [...new Set(
              [reportFs, ...planTargets, ...committedTargets].filter(Boolean)
            )];

            log(`[harperEDD] gate verdict=${gateVerdict} files_git=${files_git.length}`);

            if (gateVerdict !== 'pass') {
              callGit = false;
            }
            break;
          }
        }
        
        if (phase === 'eval') {
          try {
            const evalProjectId = getProjectId();
            const { orchestratorUrl } = cfg();
            const urlRag = `${orchestratorUrl}/v1/rag/index`;
            const evalRagItems = await collectKitRagItems(ws_root, targets, {
              maxFiles: 700,
              maxBytes: 512 * 1024,
            });

            log(`[harperEDD][RAG] indexing ${evalRagItems.length} candidate items after /eval for ${targets}`);

            if (evalRagItems.length) {
              await preIndexRag(evalProjectId, evalRagItems, urlRag, out);
              log(`[harperEDD][RAG] indexed ${evalRagItems.length} candidate items after /eval for ${targets}`);
              await pruneKitMemory(evalProjectId, targets, evalRagItems, 700);
            }
          } catch (err) {
            log(`[harperEDD][RAG] eval indexing skipped: ${err?.message || err}`);
          }
        }
        log(`[harperEDD] gitSync ${callGit}`)
        if (callGit) {
          //const changedFilesSafe = (files_git || []).map(sanitize).filter(Boolean);

          const settings = cfg(); 
          var wsRoot = getWorkspaceRoot();
          if (settings.gitAutoCommit) {
            try {
                await clikeGitSync(
                phase,
                runId,
                targets,
                files_git,
                {
                  workspaceRoot: toFsPath(wsRoot),
                  finalizeOpenPr: (phase === 'finalize'),
                  // a gate that passed but left promotion conflicts does not reach the default branch
                  skipMergeOnGate: phase === 'gate' && msg.__report?.promotion?.promoted === false,
                },
                settings,
                out
              );
            } catch (err) {
              log(`[harperEDD] gitSync error ${err}`);
            }
          }
        }
        // Persist the user's input in the MODE session (the model badge is shown at render time)
        // ✔ only for a passing verdict: a failed eval or gate is not shown as done
        const summaryIcon = ['PASS', 'PASS_WITH_WARNINGS'].includes(String(report.status || '').toUpperCase()) ? '✔' : '✖';
        await appendSessionJSONL(activeMode, {
          role: 'system',
          content: `${summaryIcon} ${String(report.summary || '')}`,
          model:  state.model || 'auto',
        });
        panel.webview.postMessage({ type: 'echo', message: `${summaryIcon} ${report.summary}` } );
        clikeHarperBlockingRun = false;
        panel.webview.postMessage({ type: 'busy', on: false, force: true });
        if (phase === 'eval' && msg.fix && !isManual) {
          await continueAutoEval(msg, report, targets);
        }
        if (phase === 'gate' && msg.fix && !isManual) {
          await continueAutoGate(msg, report, targets);
        }

      } 

      
     
      if (msg.type === 'ragIndex') {
      // optional: msg.glob (string). Reuse the command palette logic.
        try {
          panel.webview.postMessage({ type: 'busy', on: false });
          const items = await cmdRagReindex(msg.glob || '');
          panel.webview.postMessage({ type: 'echo', message: 'RAG indexing: request submitted' });
          panel.webview.postMessage({ type: 'echo', message:  `[RAG] Indexed ${items.length} items.`});
        } catch (e) {
          panel.webview.postMessage({ type: 'echo', message: 'RAG indexing error: ' + String(e && e.message || e) });
        }
        panel.webview.postMessage({ type: 'busy', on: false });
      }
      


      // RAG search requested by the webview (/rag, /ragSearch)
      if (msg.type === 'ragSearch') {
        try {
          const ws = vscode.workspace.workspaceFolders && vscode.workspace.workspaceFolders[0];
          if (!ws) throw new Error('No workspace open.');

          const projectId = getProjectId(); // e.g. "clike__<workspace-name>"

          // accept both msg.q and msg.query (old/new compatibility)
          const rawQ = (typeof msg.q !== 'undefined' ? msg.q : msg.query) || '';
          const query = String(rawQ || '').trim();
          const top_k = Number.isFinite(msg.top_k) ? msg.top_k : 8;

          if (!query) throw new Error('Query vuota.');

          const { orchestratorUrl } = cfg();
          //const path = (routes?.orchestrator?.ragSearch) || '/v1/rag/search';
          const path =  '/v1/rag/search';

          const res = await postJson(`${orchestratorUrl}${path}`, {
            project_id: projectId,
            query: query.trim(),
            top_k
          });


          const results = (res && (res.hits || res.results)) || [];
          panel.webview.postMessage({ type: 'ragResults', results, query });
        
          try {
            const uniquePaths = Array.from(new Set(
              (results || [])
                .map(r => (r && (r.path || r.source || r.name)) ? String(r.path || r.source || r.name) : '')
                .filter(Boolean)
            ));

            if (uniquePaths.length > 0) {
              const picked = await vscode.window.showQuickPick(
                uniquePaths.map(p => ({ label: p, description: 'RAG result' })),
                {
                  title: `RAG results for: ${query}`,
                  placeHolder: 'Select a file to open or Esc to dismiss',
                  matchOnDescription: true,
                }
              );

              if (picked && picked.label) {
                try {
                  const ws = vscode.workspace.workspaceFolders && vscode.workspace.workspaceFolders[0];
                  if (ws) {
                    const fileUri = vscode.Uri.joinPath(ws.uri, picked.label);
                    const doc = await vscode.workspace.openTextDocument(fileUri);
                    await vscode.window.showTextDocument(doc, { preview: false });
                  }
                } catch (openErr) {
                  vscode.window.showWarningMessage(`RAG result selected, but file could not be opened: ${picked.label}`);
                }
              }
            } else {
              vscode.window.showInformationMessage(`RAG: no files found for "${query}".`);
            }
          } catch (qpErr) {
            log('[RAG] QuickPick failed:', String(qpErr && qpErr.message || qpErr));
          }
        } catch (e) {
          panel.webview.postMessage({ type: 'busy', on: false });

          panel.webview.postMessage({
            type: 'echo',
            message: 'RAG Search failed: ' + (e && e.message ? e.message : String(e))
          });
        }
        panel.webview.postMessage({ type: 'busy', on: false });
      }

            // optional utility
      if (msg.type === 'echo') {
        await appendSessionJSONL(state.mode, {
          role: 'assistant',
          content: typeof msg.message === 'string' ? msg.message : JSON.stringify(msg.message || '', null, 2),
          model: 'system'
        });
        
      }
      if (msg.type === 'autopilot') {
        await handleAutopilotCommand(msg);
        return;
      }
      if (msg.type === 'evalTools') {
        // /tools: the native tools of the eval sandbox (catalog, installed, approved for the project)
        const say = (text) => panel.webview.postMessage({ type: 'echo', message: text });
        const ws = getWorkspaceRoot();
        const action = String(msg.action || 'list');
        const names = (Array.isArray(msg.names) ? msg.names : []).map(String).filter(Boolean);
        try {
          if (action === 'list' || action === 'search') {
            say(evalToolsLib.toolsListing(await getEvalTools(ws), action === 'search' ? names.join(' ') : ''));
          } else if (action === 'add' && names.length) {
            const data = await getEvalTools(ws);
            const known = names.filter((n) => evalToolsLib.catalogTool(data.catalog, n));
            const unknown = names.filter((n) => !known.includes(n));
            if (unknown.length) say(evalToolsLib.unknownToolHint(unknown));
            if (known.length) {
              say(`⬇ Installing in the eval sandbox: ${known.join(', ')}…`);
              const res = await postEvalToolsInstall(ws, known);
              evalToolsLib.approveForProject(ws.fsPath, known);
              const versions = Object.entries(res?.versions || {}).map(([k, v]) => `${k} ${v}`).join(', ');
              say(`✔ Installed ${known.join(', ')}${versions ? ` (${versions})` : ''}; approved for this project in .clike/eval-tools.yaml.`);
            }
          } else if (action === 'update') {
            say(`⬇ Updating the eval tools${names.length ? `: ${names.join(', ')}` : ''} (each one is rebuilt; the previous version stays if it fails)…`);
            say(evalToolsLib.updateSummary(await postEvalToolsUpdate(names)));
          } else if (action === 'remove' && names.length) {
            evalToolsLib.withdrawForProject(ws.fsPath, names);
            say(`Removed ${names.join(', ')} from .clike/eval-tools.yaml: CLike will ask again before using ${names.length > 1 ? 'them' : 'it'}. ` +
              'The installed files stay in the tools volume (shared by your projects).');
          } else {
            say('Usage: /tools | /tools search <text> | /tools add <tool[@version]>… | /tools update [tool…] | /tools remove <tool>…');
          }
        } catch (err) {
          say(`✖ /tools ${action}: ${err?.message || err}`);
        }
      }
      if (msg.type === 'where') {
        out.appendLine('[CLike] where state ' + state.mode);
        const ws = vscode.workspace.workspaceFolders && vscode.workspace.workspaceFolders[0];
        const p = ws ? ws.uri.fsPath : '(no workspace)';
        await appendSessionJSONL(state.mode, { role:'assistant', content:`Workspace: ${p}`, model:'system' });
        
      }
      if (msg.type === 'switchProject') {
        // Note: for multi-project we could store a pointer in .clike/config.json
        await appendSessionJSONL(state.mode, { role:'assistant', content:`(placeholder) Switched project to: ${String(msg.name||'')}`, model:'system' });
       
      }
      if (msg.type === 'webview_ready') {
        try {
          out.appendLine('[CLike] webview_ready');
          // 1) Saved UI state (no newState here)
          const saved = context.workspaceState.get('clike.uiState') || {
            mode: 'free',
            model: 'auto',
            historyScope: 'singleModel',
            executionPreference: getDefaultExecutionPreference(),
            localAgentExecutor: getDefaultLocalAgentExecutor(),
          };
          const ui = {
            mode: saved.mode || 'free',
            model: saved.model || 'auto',
            historyScope: (saved.historyScope === 'allModels') ? 'allModels' : 'singleModel',
            executionPreference: reconcileExecutionPreference(
              saved.executionPreference,
              getDefaultExecutionPreference()
            ),
            localAgentExecutor: normalizeLocalAgentExecutor(
              saved.localAgentExecutor || getDefaultLocalAgentExecutor()
            ),
          };
          // 2) Persist the reconciled state (so harperRun uses the same value
          // shown in the selector from the first command) and send initState.
          await context.workspaceState.update('clike.uiState', ui);
          panel.webview.postMessage({ type: 'initState', state: ui });
          // 3) Hydrate messages (do not block on errors)
          try {
            const msgs = (ui.historyScope === 'allModels')
              ? await loadSession(ui.mode, 200).catch(() => [])
              : await loadSessionFilteredV2(ui.mode, ui.model, 200).catch(() => []);
            panel.webview.postMessage({ type: 'hydrateSession', messages: msgs });
          } catch (e) {
            out.appendLine('[CLike] hydrate failed: ' + (e?.message || String(e)));
            panel.webview.postMessage({ type: 'hydrateSession', messages: [] });
          }
          // 4) Fetch models with timeout + "auto" fallback
          try {
            const orchestratorUrl = serviceBaseUrls().orchestrator;
            const controller = new AbortController();
            const timer = setTimeout(() => controller.abort(), 2000);

            const res = await fetchJson(`${orchestratorUrl}/v1/models`, { signal: controller.signal }).catch(() => ({}));
            clearTimeout(timer);
            let models = [];
            if (Array.isArray(res?.models)) {
              const raw = res.models
                .filter(m => (typeof m?.enabled === 'undefined' ? true : !!m.enabled))
                .filter(m => !/embed|embedding|nomic-embed/i.test(String(m?.name || m?.id || m?.model || '')))
                .map(m => m.name || m.id || m.model || 'unknown');

              models = raw;
            } else if (Array.isArray(res?.data)) {
              const raw = res.data.map(m => m.id || m.name || 'unknown');
              models = raw.filter(n => !/embed|embedding|nomic-embed/i.test(n));
            }
            if (!models.length) models = ['auto'];
            // Restore the persisted bubble (if any)

            // }

            panel.webview.postMessage({ type: 'models', models, providers: res?.providers || null });
            out.appendLine('[CLike] models sent: ' + models.join(', '));
          } catch (e) {
            out.appendLine('[CLike] models fetch failed: ' + (e?.message || String(e)));
            panel.webview.postMessage({ type: 'models', models: ['auto'] });
          }
        } catch (e) {
          out.appendLine('[CLike] webview_ready handler crashed: ' + (e?.message || String(e)));
          // Minimal fallback so the webview is not left "empty"
          panel.webview.postMessage({
            type: 'initState',
            state: {
              mode: 'free',
              model: 'auto',
              historyScope: 'singleModel',
              executionPreference: getDefaultExecutionPreference(),
              localAgentExecutor: getDefaultLocalAgentExecutor(),
            }
          });
          panel.webview.postMessage({ type: 'hydrateSession', messages: [] });
          panel.webview.postMessage({ type: 'models', models: ['auto'] });
        }
       
      }      
      if (msg.type === 'setHistoryScope') {
        const value = (msg.value === 'allModels') ? 'allModels' : 'singleModel';

        // 🔧 save to the SINGLE field used everywhere: historyScope
        const prev = context.workspaceState.get('clike.uiState') || { mode:'free', model:'auto', historyScope:'singleModel' };
        const ui = { ...prev, historyScope: value };
        await context.workspaceState.update('clike.uiState', ui);

        // Immediate re-hydrate consistent with the chosen scope
        const modeCur  = ui.mode  || 'free';
        const modelCur = ui.model || 'auto';
        const msgs = (value === 'allModels')
          ? await loadSession(modeCur, 200).catch(()=>[])
          : await loadSessionFilteredV2(modeCur, modelCur, 200).catch(()=>[]);
        panel.webview.postMessage({ type: 'hydrateSession', messages: msgs });

        // NO initState here (avoids combo bounce)
        vscode.window.setStatusBarMessage(`CLike: history scope = ${value}`, 2000);
        
      }
      // 1) MODELS
      if (msg.type === 'fetchModels') {
        const res = await fetchJson(`${orchestratorUrl}/v1/models`);
        let models = [];
        if (Array.isArray(res?.models)) {
          let raw = res.models
            .filter(m => (typeof m?.enabled === 'undefined' ? true : !!m.enabled))
            .map(m => m.name || m.id || m.model || 'unknown');

          const filtered = raw.filter(n => !/embed|embedding|nomic-embed/i.test(n));
          models = filtered.length ? filtered : raw;
        } else if (Array.isArray(res?.data)) {
          let raw = res.data.map(m => m.id || 'unknown');
          const filtered = raw.filter(n => !/embed|embedding|nomic-embed/i.test(n));
          models = filtered.length ? filtered : raw;
        }
        panel.webview.postMessage({ type: 'models', models, providers: res?.providers || null });

      }
      // 2) UI CHANGE (Mode/Model)
      if (msg.type === 'uiChanged') {
        const prev = context.workspaceState.get('clike.uiState') || {
          mode: 'free',
          model: 'auto',
          historyScope: 'singleModel',
          executionPreference: getDefaultExecutionPreference(),
          localAgentExecutor: getDefaultLocalAgentExecutor(),
        };

        const newState = {
          ...prev,
          ...(typeof msg.mode !== 'undefined' ? { mode: msg.mode } : {}),
          ...(typeof msg.model !== 'undefined' ? { model: msg.model } : {}),
          ...(typeof msg.executionPreference !== 'undefined'
            ? { executionPreference: normalizeExecutionPreference(msg.executionPreference) }
            : {}),
          ...(typeof msg.localAgentExecutor !== 'undefined'
            ? { localAgentExecutor: normalizeLocalAgentExecutor(msg.localAgentExecutor) }
            : {}),  
        };

        if (!newState.executionPreference) {
          newState.executionPreference = getDefaultExecutionPreference();
        }
        if (!newState.localAgentExecutor) {
          newState.localAgentExecutor = getDefaultLocalAgentExecutor();
        }
        await context.workspaceState.update('clike.uiState', newState);

        // If ONLY the model changed, do NOT re-hydrate the chat
        if (prev.mode === newState.mode && prev.model !== newState.model) {
          const scope = (newState.historyScope === 'allModels') ? 'allModels' : 'singleModel';
          if (scope === 'singleModel') {
            const modeCur  = newState.mode  || 'free';
            const modelCur = newState.model || 'auto';
            const msgs = await loadSessionFilteredV2(modeCur, modelCur, 200).catch(() => []);
            panel.webview.postMessage({ type: 'hydrateSession', messages: msgs });
          }
         
        }
        // If the mode changed (or both), re-hydrate based on the scope
        const scope   = (newState.historyScope === 'allModels') ? 'allModels' : 'singleModel';
        const modeCur = newState.mode || 'free';
        const modelCur= newState.model || 'auto';

        const msgs = (scope === 'allModels')
          ? await loadSession(modeCur).catch(() => [])
          : await loadSessionFilteredV2(modeCur, modelCur, 200).catch(() => []);

        panel.webview.postMessage({ type: 'hydrateSession', messages: msgs });
       
      }
      // 3) CLEAR SESSION (current mode only)
      if (msg.type === 'clearSession') {
        const st = context.workspaceState.get('clike.uiState') 
              || {  mode: 'free',
                    model: 'auto',
                    historyScope: 'singleModel',
                    executionPreference: getDefaultExecutionPreference(),
                    localAgentExecutor: getDefaultLocalAgentExecutor(),
                  };
        const modeCur   = msg.mode  || st.mode  || 'free';
        const modelCur  = msg.model || st.model || 'auto';

        const scope = effectiveHistoryScope(context);  //  UI ONLY
        if (scope === 'allModels') {
          // delete the whole MODE (entire file)
          await clearSession(modeCur);
          panel.webview.postMessage({ type: 'hydrateSession', messages: [] });
          vscode.window.setStatusBarMessage(`CLike: cleared ALL messages in mode "${modeCur}"`, 2500);
        } else {
         // singleModel → clean ONLY the current model's lines
          await pruneSessionByModel(modeCur, modelCur);
          // NEW: after cleanup, immediately show the mode's other conversations
          const msgs = await loadSessionFilteredV2(modeCur, modelCur, 200).catch(() => []);
          // Hydrate the webview with the remaining messages (all other models)
          // do NOT touch historyScope automatically: keep the one chosen in the combo
          panel.webview.postMessage({ type: 'hydrateSession', messages: msgs});
          vscode.window.setStatusBarMessage(`CLike: cleared messages for model "${modelCur}" in mode "${modeCur}"`, 2500);

        }
      
      }
      // 4) OPEN FILE (clickable Files tab)
      if (msg.type === 'openFile' && msg.path) {
        try {
          const ws = vscode.workspace.workspaceFolders && vscode.workspace.workspaceFolders[0];
          if (!ws) throw new Error('No workspace open');
          const uri = safeWorkspaceUri(ws.uri, msg.path);
          const doc = await vscode.workspace.openTextDocument(uri);
          await vscode.window.showTextDocument(doc, { preview: false });
        } catch (e) {
          vscode.window.showErrorMessage(`Open file failed: ${e.message}`);
        }        
       
      }
      // 3.a) CLEAR user/assistent bubble (the copy icon is handled by the cockpit feed: no busy state)
      if (msg.type === 'deleteBubble') {
        const ui = context.workspaceState.get('clike.uiState') || {
          mode: 'free',
          model: 'auto',
          historyScope: 'singleModel',
          executionPreference: getDefaultExecutionPreference(),
          localAgentExecutor: getDefaultLocalAgentExecutor(),


        };

        const modeCur  = msg.mode  || ui.mode  || 'free';
        const modelCur = msg.model || ui.model || 'auto';
        const role     = msg.role  || '';
        const content  = msg.content || '';

        const ok = await deleteSessionEntry(modeCur, role, content, modelCur);
        if (!ok) {
          panel.webview.postMessage({
            type: 'error',
            message: 'Unable to delete message from session history.'
          });
          panel.webview.postMessage({ type: 'busy', on: false });
          return;
        }

        // Reload the history based on the current scope (Model vs All models)
        const scope = (ui.historyScope === 'allModels') ? 'allModels' : 'singleModel';
        let msgs;
        if (scope === 'allModels') {
          msgs = await loadSession(modeCur, 200).catch(() => []);
        } else {
          msgs = await loadSessionFilteredV2(modeCur, modelCur, 200).catch(() => []);
        }

        panel.webview.postMessage({ type: 'hydrateSession', messages: msgs });
        panel.webview.postMessage({ type: 'busy', on: false });
        return;
      }
      // 5) CHAT / GENERATE
      if (msg.type === 'sendChat' || msg.type === 'sendGenerate') {
        log((`CLike: ${msg.type}`));
         // cancel any previous request
        if (inflightController) { inflightController.abort(); inflightController = null; }
        inflightController = new AbortController();
        panel.webview.postMessage({ type: 'busy', on: true });

        if (shouldBlockHarperSlashFromGenericChatMessage(msg)) {
          const commandName = getHarperSlashCommandName(msg.prompt) || 'unknown';
          out.appendLine(`[CLike] Blocked Harper slash command from generic chat route: /${commandName}`);
          panel.webview.postMessage({
            type: 'error',
            message: 'Harper slash command was blocked from generic chat routing. Please retry; this is a routing guard.',
          });
          panel.webview.postMessage({ type: 'busy', on: false, force: true });
          inflightController = null;
          return;
        }

        const cur = context.workspaceState.get('clike.uiState') || { mode: 'free', model: 'auto' };
        const activeMode  = msg.mode  || cur.mode  || 'free';
        const activeModel = msg.model || cur.model || 'auto';
        
        const activeProvider = explicitProviderForModel(activeModel) || '';
        out.appendLine(`CLike: ${msg.type} (${activeMode} ${activeModel} ${activeProvider})`);
        
        // Persist the user's input in the MODE session (the model badge is shown at render time)
        await appendSessionJSONL(activeMode, {
          role: 'user',
          content: String(msg.prompt || ''),
          model: activeModel,
          provider:activeProvider,
          attachments: Array.isArray(msg.attachments) ? msg.attachments : []
        });

        // Partition attachments ONLY HERE (N.B.: no global variables!)
        const atts = Array.isArray(msg.attachments) ? msg.attachments : [];
        const { inline_files, rag_files } =  partitionAttachments(atts);
        log(`CLike: ${inline_files.length} inline_files, ${rag_files.length} rag_files`);
        // History of the current MODE
        const historyScope  = effectiveHistoryScope(context);
        // History for a "stateless" conversation: load ONLY the bubbles of the current MODE
        const history = await loadSessionFilteredHarper(activeMode).catch(() => []);
        //log((`CLike historyForThisModel: ${historyForThisModel}`));
        const historyForThisModel = await loadSessionFiltered(activeMode, activeModel, 200);

        //log((`CLike history: ${JSON.stringify(history)}`));
        const source = (historyScope === 'allModels')
        ? history
        : historyForThisModel;


       
        const messages = source.map(b => ({ role: b.role, content: b.content }));
        const projectId = getProjectId();
        const { orchestratorUrl, routes } = cfg();
        try { 
          if (rag_files) {
            var urlOrch = (routes?.orchestrator?.ragIndex) ||  '/v1/rag/index';
            let urlOrchestrator = orchestratorUrl + urlOrch;
            const res = await preIndexRag(projectId, rag_files, urlOrchestrator, out); 
            log((`CLike preIndexRag: ${JSON.stringify(res)} ${res}`));
          }
          
        } catch (e) { log(`CLike preIndexRag error: ${e}`); }

        // payload
        const executionPreference = normalizeExecutionPreference(
          cur.executionPreference || getDefaultExecutionPreference()
        );

        // Local-agent pre-resolution (free/coding): the extension owns CLI
        // availability; the orchestrator only assembles the prompt package.
        const settingsLA = cfg();
        const localPhase = (msg.type === 'sendGenerate') ? 'coding' : 'free';
        let effectivePref = executionPreference;
        let selectedLocalExecutor = null;
        if (executionPreferenceRequestsLocalAgent(executionPreference)) {
          selectedLocalExecutor = resolveSelectedLocalAgentExecutor(
            settingsLA, cur.localAgentExecutor || 'auto', localPhase
          );
          if (!selectedLocalExecutor) {
            if (executionPreference === 'local_agent_only') {
              panel.webview.postMessage({
                type: 'error',
                message: 'No local agent (codex/claude) is available. Install or enable the claude/codex CLI, or switch Execution away from "agent only".',
              });
              panel.webview.postMessage({ type: 'busy', on: false, force: true });
              inflightController = null;
              return;
            }
            // prefer_local_agent with no installed agent: fall back to cloud.
            effectivePref = 'cloud_only';
          }
        }

        // Native agent chat (H1): one agent session per (mode, agent), resumed message after message.
        const agentSessions = context.workspaceState.get('clike.agentSessions') || {};
        const agentSessionKeyValue = selectedLocalExecutor
          ? sessionKey(msg.type === 'sendGenerate' ? 'coding' : activeMode, selectedLocalExecutor)
          : '';
        const agentSession = agentSessionKeyValue
          ? (agentSessions[agentSessionKeyValue] || newSession(selectedLocalExecutor))
          : null;

        const basePayload = {
            mode: activeMode,
            project_id: projectId,
            model: activeModel,
            ...(activeProvider ? { provider: activeProvider } : {}),
            messages,
            inline_files,
            rag_files,
            attachments: atts,
            max_tokens: 4000,
            gen: { api: "responses" }, // openai responses API
            profileHint: computeProfileHint(activeMode, activeModel),
            executionPreference: effectivePref,
            localAgentExecutor: selectedLocalExecutor || normalizeLocalAgentExecutor(cur.localAgentExecutor || 'auto'),
            mode_contract: buildModeContract(activeMode),
            // the agent holds the conversation: the orchestrator sends only the new turn
            ...(agentSession && agentSession.started ? { agentSessionResume: true } : {}),
        };

        // (fixed ternary)
        const payload = (msg.type === 'sendChat')
        ? basePayload
        : { ...basePayload, max_tokens: 5100 };

        const url = (msg.type === 'sendChat')
          ? `${orchestratorUrl}/v1/chat`
          : `${orchestratorUrl}/v1/generate`;

        log((`CLike: ${payload.inline_files?.length} inline_files, ${payload.rag_files?.length} rag_files}`));
        
        //log((`CLike payload: ${JSON.stringify(payload)} url: ${url}`));

        try {
          const res = await withTimeout(
            postJson(url, payload, { signal: inflightController.signal }),
            600000
          );

          // Provider unavailable (missing API key / unreachable local runtime):
          // the orchestrator returns a clean 200 envelope; surface it in the Text
          // panel as an error rather than as an assistant bubble.
          if (res && res.ok === false && res.text) {
            panel.webview.postMessage({ type: 'error', message: res.text });
            panel.webview.postMessage({ type: 'busy', on: false, force: true });
            inflightController = null;
            return;
          }

          // Local-agent execution: the orchestrator returned a prompt package;
          // spawn the codex/claude CLI here and render the result like the cloud
          // path (free -> answer bubble + Text synthesis; coding -> synthesis
          // bubble + Files tab).
          if (res && res.local_execution) {
            try {
              const chatExecutor = selectedLocalExecutor || normalizeLocalAgentExecutor(cur.localAgentExecutor || 'auto');
              panel.webview.postMessage({ type: 'agentStream', event: { kind: 'start', label: localAgentBadge(chatExecutor) } });
              let localOut;
              try {
                localOut = await runLocalChatAgent({
                  pkg: res,
                  executorId: chatExecutor,
                  settings: settingsLA,
                  wsrootUri: getWorkspaceRoot(),
                  out,
                  session: agentSession,
                  onEvent: (event) => panel.webview.postMessage({ type: 'agentStream', event }),
                  onSpawn: (child) => { activeChatAgentChild = child; },
                  askApproval: askAgentChatApproval,
                });
              } catch (err) {
                // a session that cannot be resumed (expired, deleted) starts again next time
                if (agentSessionKeyValue) {
                  delete agentSessions[agentSessionKeyValue];
                  await context.workspaceState.update('clike.agentSessions', agentSessions);
                }
                throw err;
              } finally {
                activeChatAgentChild = null;
                panel.webview.postMessage({ type: 'agentStream', event: { kind: 'end' } });
              }
              if (agentSessionKeyValue && localOut.sessionId) {
                agentSessions[agentSessionKeyValue] = { id: localOut.sessionId, started: true, at: Date.now() };
                await context.workspaceState.update('clike.agentSessions', agentSessions);
              }
              // Live bubble label: agent badge plus the model actually used.
              const liveBadge = localOut.model ? `${localOut.badge} · ${localOut.model}` : localOut.badge;
              if (localOut.mode === 'coding') {
                // Clean bubble (agent badge + file list), Files tab populated and
                // active. Files are already on disk, so no Apply/base64 preview.
                // Persist with activeModel (like the cloud path and the user
                // message) so the entry survives the per-model history filter on
                // reload; agentModel records which model the CLI actually used.
                await appendSessionJSONL(activeMode, { role: 'assistant', content: localOut.synthesis, model: activeModel, agentModel: localOut.model || '' });
                panel.webview.postMessage({ type: 'chatResult', data: { model: liveBadge, text: localOut.synthesis } });
                panel.webview.postMessage({ type: 'files', data: localOut.files, activate: true });
              } else {
                await appendSessionJSONL(activeMode, { role: 'assistant', content: localOut.answer, model: activeModel, agentModel: localOut.model || '' });
                panel.webview.postMessage({ type: 'chatResult', data: { model: liveBadge, text: localOut.answer } });
                panel.webview.postMessage({ type: 'text', text: localOut.synthesis });
                if (Array.isArray(localOut.files) && localOut.files.length) {
                  panel.webview.postMessage({ type: 'files', data: localOut.files, activate: true });
                }
              }
            } catch (e) {
              panel.webview.postMessage({ type: 'error', message: String(e?.message || e) });
            } finally {
              panel.webview.postMessage({ type: 'busy', on: false, force: true });
              inflightController = null;
            }
            return;
          }

          // Save last run (needed for Apply)
          if (res?.run_dir || res?.audit_id) {
            await context.workspaceState.update('clike.lastRun', { run_dir: res.run_dir, audit_id: res.audit_id });
          }

          if (msg.type === 'sendChat') {
            const modelName = res?.model || activeModel;
            const text = (res && (res.text || res.content))
              ? (res.text || res.content)
              : JSON.stringify(res, null, 2);

            await appendSessionJSONL(activeMode, {
              role: 'assistant',
              content: text,
              model: modelName
            });

            panel.webview.postMessage({ type: 'chatResult', data: res });
          } else {
            // generate: optional autowrite (if enabled in cfgChat)
            const { autoWrite } = cfgChat?.() || { autoWrite: false };
            if (autoWrite && Array.isArray(res.files) && res.files.length) {
              await saveGeneratedFiles(res.files, { phase: 'apply', runId: res.runId || res.run_id });
             
            }
            // Local cache of the last generate's files (needed for Apply fallback)
            try {
              await context.workspaceState.update('clike.lastFiles', Array.isArray(res?.files) ? res.files : []);
            } catch (e) {
                out.appendLine('[CLike] cache lastFiles failed: ' + (e?.message || String(e)));
            }
            const summary = Array.isArray(res.files) && res.files.length
              ? 'Generated files:\n' + res.files.map(f => '- ' + f.path).join('\n')
              : JSON.stringify(res, null, 2);

            await appendSessionJSONL(activeMode, {
              role: 'assistant',
              content: summary,
              model: activeModel
            });
            

            panel.webview.postMessage({ type: 'generateResult', data: res });
          }

        } catch (err) {
          const emsg = String(err);
          //await appendSessionJSONL(activeMode, { role: 'assistant', content: `Error: ${emsg}`, model: activeModel });
          panel.webview.postMessage({ type: 'error', message: emsg });
        } finally {
          panel.webview.postMessage({ type: 'busy', on: false });
          inflightController = null;
        }
      }
      // 6) APPLY (client-side only: the extension is the only component that writes the workspace)
      if (msg.type === 'apply') {
        const selection = msg.selection || { apply_all: true };
        const wantPaths = Array.isArray(selection?.paths) ? selection.paths : null;
        const lastFiles = context.workspaceState.get('clike.lastFiles') || [];
        if (!Array.isArray(lastFiles) || !lastFiles.length) {
          panel.webview.postMessage({ type: 'error', message: 'Nothing to apply: no generated files cached.' });
          panel.webview.postMessage({ type: 'busy', on: false });
          return;
        }

        // Filter by the selected paths (if any), otherwise apply everything
        const chosen = wantPaths
          ? lastFiles.filter(f => f && f.path && wantPaths.includes(f.path))
          : lastFiles;

        if (!chosen.length) {
          panel.webview.postMessage({ type: 'error', message: 'No files selected to apply.' });
          panel.webview.postMessage({ type: 'busy', on: false });
          return;
        }

        try {
          const paths = await saveGeneratedFiles(chosen, { phase: 'apply', runId: lastRun?.runId || lastRun?.run_id || lastRun?.audit_id });
          // Clear the cache to avoid accidental re-apply
          try { await context.workspaceState.update('clike.lastFiles', []); } catch {}
          panel.webview.postMessage({ type: 'applyResult', data: { applied: paths } });
        } catch (e) {
          panel.webview.postMessage({ type: 'error', message: 'Apply (local) failed: ' + (e?.message || String(e)) });
        }
        panel.webview.postMessage({ type: 'busy', on: false });
      }
      // 7) CANCEL
      if (msg.type === 'cancel') {
        const agents = cancelHarperWork();
        if (agents) log(`[cancel] stopped ${agents} local agent run(s)`);
        panel.webview.postMessage({ type: 'busy', on: false });
      }
      // --- PICK WORKSPACE FILES ----------------------------------------------------
      if (msg.type === 'pickWorkspaceFiles') {
        const ws = vscode.workspace.workspaceFolders && vscode.workspace.workspaceFolders[0];
        if (!ws) {
          panel.webview.postMessage({ type: 'busy', on: false });
          vscode.window.showWarningMessage('No workspace open.');
          return;
        }

        const uris = await vscode.window.showOpenDialog({
          canSelectFiles: true, canSelectFolders: false, canSelectMany: true,
          openLabel: 'Attach (workspace)'
        });
        if (!uris) {
          panel.webview.postMessage({ type: 'busy', on: false });
          return;
        }

        const atts = [];

        for (const uri of uris) {
          try {
            const stat = await vscode.workspace.fs.stat(uri);
            const size = stat.size || 0;
            const rel  = vscode.workspace.asRelativePath(uri);
            const fsPath = uri.fsPath || rel;
            const baseName = fsPath.split(/[\\/]/).pop() || 'file';
            const isText = isTextAttachment(baseName);
            const mime = guessAttachmentMime(baseName);
            const common = { origin: 'workspace', source: 'workspace', name: baseName, path: rel, size, mime };

            // Inline the bytes (text or base64) so the orchestrator materializes
            // the file under runs/<phase>/attachments/. Only very large files are
            // referenced by path only to avoid pathological payloads.
            if (size <= ATTACH_MAX_INLINE_BYTES) {
              const bytes = await vscode.workspace.fs.readFile(uri);
              if (isText) {
                atts.push(Object.assign({}, common, { content: Buffer.from(bytes).toString('utf8') }));
              } else {
                atts.push(Object.assign({}, common, { bytes_b64: Buffer.from(bytes).toString('base64') }));
              }
            } else {
              atts.push(common);
              vscode.window.showWarningMessage(`Attachment "${baseName}" is larger than ${Math.round(ATTACH_MAX_INLINE_BYTES / (1024 * 1024))}MB and was referenced by path only.`);
            }
          } catch (e) {
            vscode.window.showWarningMessage(`Attach (workspace) failed: ${e?.message || e}`);
          }
        }

        panel.webview.postMessage({ type: 'attachmentsAdded', attachments: atts });
      }
      // === REPLACE ENTIRE EXTERNAL PICKER HANDLER WITH THIS BLOCK ===
      if (msg.type === 'pickExternalFiles') {
        const ws = vscode.workspace.workspaceFolders && vscode.workspace.workspaceFolders[0];
        if (!ws) {
          panel.webview.postMessage({ type: 'busy', on: false });
          vscode.window.showWarningMessage('No workspace open.');
          return;
        }

        // Always copy into .clike/uploads so we ALWAYS have a workspace-relative path (RAG-friendly)
        const uploadsDir = vscode.Uri.joinPath(ws.uri, '.clike', 'uploads');
        try { await vscode.workspace.fs.createDirectory(uploadsDir); } catch (e) { /* ignore */ }

        const uris = await vscode.window.showOpenDialog({
          canSelectFiles: true,
          canSelectFolders: false,
          canSelectMany: true,
          openLabel: 'Attach (external)'
        });
        if (!uris) {
          panel.webview.postMessage({ type: 'busy', on: false });
          return;
        }

        const atts = [];

        for (let i = 0; i < uris.length; i++) {
          const uri = uris[i];
          try {
            // Read original external file
            const bytes = await vscode.workspace.fs.readFile(uri);
            const size = bytes.byteLength || 0;
            const fsPath = uri.fsPath || '';
            const baseName = fsPath.split(/[\\/]/).pop() || 'file';
            const isText = isTextAttachment(baseName);
            const mime = guessAttachmentMime(baseName);

            // 1) ALWAYS copy inside workspace (.clike/uploads/<name>)
            const dst = vscode.Uri.joinPath(uploadsDir, baseName);
            await vscode.workspace.fs.writeFile(dst, bytes);

            // 2) Build workspace-relative path (this is what backend/RAG will use)
            const rel = vscode.workspace.asRelativePath(dst);

            // 3) Create attachment with path ALWAYS present
            const common = {
              origin: 'workspace',          // now the file physically lives in workspace
              source: 'workspace',
              name: baseName,
              path: rel,
              size: size,
              mime,
            };

            // 4) Inline the bytes so the orchestrator materializes the file under
            // runs/<phase>/attachments/. Only very large files are referenced by
            // path only to avoid pathological payloads.
            if (size <= ATTACH_MAX_INLINE_BYTES) {
              if (isText) {
                atts.push(Object.assign({}, common, { content: Buffer.from(bytes).toString('utf8') }));
              } else {
                atts.push(Object.assign({}, common, { bytes_b64: Buffer.from(bytes).toString('base64') }));
              }
            } else {
              atts.push(common);
              vscode.window.showWarningMessage(`Attachment "${baseName}" is larger than ${Math.round(ATTACH_MAX_INLINE_BYTES / (1024 * 1024))}MB and was referenced by path only.`);
            }
          } catch (e) {
            vscode.window.showWarningMessage('Attach (external) failed: ' + (e && e.message ? e.message : String(e)));
          }
        }
        // Notify webview: attachments now have a valid `path` (and inline for small files)
        panel.webview.postMessage({ type: 'attachmentsAdded', attachments: atts });
      }

    } catch (err) {
      if (clikeHarperBlockingRun) {
        clikeHarperBlockingRun = false;
      }

      panel.webview.postMessage({ type: 'error', message: formatHarperError(err) });
      panel.webview.postMessage({ type: 'busy', on: false, force: true });
    }
    panel.webview.postMessage({ type: 'busy', on: false });
  };
  // Every handler call, the nested ones of the --fix loops and the autopilot included, goes
  // through the run feed: the run card and the status bar follow the real steps.
  const runs = createRunFeed(panel, context, (m) => originalPostMessage(m));
  activeRunFeed = runs;
  runObserver = runs.observe;
  panel.onDidDispose(() => { if (activeRunFeed === runs) activeRunFeed = null; });
  // runs nobody watches (MCP, autopilot): never a modal question
  let unattendedRuns = 0;
  const handleWebviewMessage = (msg) => {
    if (!(msg && (msg.__fromMcp || msg.__unattended))) return runs.around(msg, () => handleWebviewMessageCore(msg));
    unattendedRuns += 1;
    return Promise.resolve(runs.around(msg, () => handleWebviewMessageCore(msg))).finally(() => { unattendedRuns -= 1; });
  };

  // Cockpit (side panel of the cockpit layout, autocompletion in every layout): its messages never
  // touch the busy state, a run in progress stays as it is.
  const cockpit = createCockpitFeed(panel, context, runs);
  panel.webview.onDidReceiveMessage((msg) => {
    if (msg && cockpit.handles(msg.type)) return cockpit.handle(msg);
    const done = cockpit.track(msg && msg.type, handleWebviewMessage(msg));
    // what the project looks like after the message: a phase, a gate, a setting changed
    Promise.resolve(done).finally(() => cockpit.refresh(msg && msg.type === 'webview_ready' ? 0 : 300));
    return done;
  });
  clikeRunChatMessage = handleWebviewMessage;

  // Native tools of the eval sandbox (eval-tools.js): what the REQ declares or runs and the
  // sandbox lacks is installed from CLike's catalog, on the developer's confirmation, before the
  // eval. Never blocks the eval: a failed check or install is reported and the eval runs.
  // A project outside the folders the stack reads (eval answers 403): mounted read-only, on confirmation.
  const declinedMounts = new Set();
  async function ensureProjectReadable(ws) {
    const root = ws && ws.fsPath;
    if (!root) return;
    const out = await ensureProjectMounted({
      root,
      getRoots: () => getEvalRoots(),
      unattended: Boolean(autopilotRun) || unattendedRuns > 0,
      declined: declinedMounts,
      stackDir: String(vscode.workspace.getConfiguration('clike').get('stackDir', '') || ''),
      ask: async (dir) => (await vscode.window.showWarningMessage(
        `${dir} is outside the folders the CLike stack can read, so eval, gate and the /adopt baseline cannot run its tests. ` +
        'Mount this folder alone, read-only? The stack containers are recreated (about a minute): an eval running in another window stops.',
        { modal: true }, 'Mount read-only')) === 'Mount read-only',
      pickStackDir: async () => {
        const picked = await vscode.window.showOpenDialog({
          canSelectFolders: true, canSelectFiles: false, openLabel: 'Use this folder',
          title: 'The CLike repository (or its docker folder, with mount-project.sh)',
        });
        const dir = stackFolder(picked && picked[0] ? picked[0].fsPath : '');
        // saved only when it is the stack folder: a wrong pick is asked again next time
        if (dir) await vscode.workspace.getConfiguration('clike').update('stackDir', dir, vscode.ConfigurationTarget.Global);
        return dir;
      },
      run: (script, args, cwd) => new Promise((resolve) => {
        execFile('bash', [script, ...args], { cwd, timeout: 6 * 60 * 1000, maxBuffer: 4 * 1024 * 1024 }, (err, stdout, stderr) => {
          log(`[mount] ${stdout}${stderr}`);
          resolve({ ok: !err, output: `${stdout}${stderr}${err && !stderr ? err.message : ''}` });
        });
      }),
      say: (text) => panel.webview.postMessage({ type: 'echo', message: text }),
    });
    log(`[mount] ${root}: ${out.reason}`);
    if (out.mounted) panel.webview.postMessage({ type: 'echo', message: `✔ ${root} mounted read-only in the CLike stack: eval and gate can run its tests.` });
    else if (!['readable', 'declined'].includes(out.reason) && !/did not answer/.test(out.reason)) {
      panel.webview.postMessage({ type: 'echo', message: `⚠ ${root} is not readable by the CLike stack (${out.reason}): run docker/mount-project.sh add "${root}" in the CLike repo.` });
    }
  }

  async function ensureToolsForEval(reqId, { profile = null, extra = [] } = {}) {
    const ws = getWorkspaceRoot();
    try { await ensureProjectReadable(ws); } catch (e) { log(`[mount] ${e?.message || e}`); }
    let result;
    try {
      result = await ensureEvalTools({
      check: () => postEvalToolsCheck(ws, reqId, profile),
      install: (names) => postEvalToolsInstall(ws, names),
      ask: async (items) => {
        if (autopilotRun) return 'no'; // unattended: the missing tool parks the REQ with its reason
        const pick = await vscode.window.showInformationMessage(
          questionText(reqId, items), 'Install', 'Always for this project', 'No'
        );
        return pick === 'Install' ? 'install' : pick === 'Always for this project' ? 'always' : 'no';
      },
      approve: (names) => approveForProject(ws.fsPath, names),
      policy: String(cfg().evalToolsInstall || 'ask'),
      extra,
      say: (text) => panel.webview.postMessage({ type: 'echo', message: text }),
      });
    } catch (err) {
      result = { installed: [], declined: [], unavailable: [], error: String(err?.message || err) };
    }
    if (result.error) log(`[evalTools] ${result.error}`);
    return result;
  }

  // A check stopped on a program the sandbox lacks (report.missing_tools): offer it, and say
  // whether the eval should run again (once per run) instead of going to a repair.
  async function installReportedTools(reqId, report, opts = {}) {
    const missing = Array.isArray(report?.missing_tools) ? report.missing_tools : [];
    if (!missing.length) return false;
    const result = await ensureToolsForEval(reqId, { ...opts, extra: missing });
    return result.installed.length > 0;
  }

  // A local agent writes its repair directly: changed tests/LTC/ci files are submitted to the
  // orchestrator's governance, and what it rejects (and any deleted file) is restored. For a cloud
  // repair the orchestrator already filtered the files, so this finds nothing to do.
  async function governAcceptanceChanges(reqId, before, failures, cycle, owner = null) {
    const wsPath = getWorkspaceRoot().fsPath;
    let rejectedIssues = {};
    const { modified, deleted } = acceptanceChanges(before, snapshotAcceptanceSurface(wsPath, reqId));
    const say = (text) => panel.webview.postMessage({ type: 'echo', message: text });
    let rejected = [];
    if (Object.keys(modified).length || deleted.length) {
      // deleted files go too: a test-support file the eval asked to drop (e.g. a root conftest
      // shadowing the shared one) is accepted; anything else is put back
      const previous = Object.fromEntries([...Object.keys(modified), ...deleted].map((rel) => [rel, before[rel]]));
      const evidence = (failures || []).map((f) => `${f.name}\n${f.output || ''}`).join('\n');
      try {
        const result = await postAcceptanceAmend(
          getWorkspaceRoot(), reqId, modified, previous, evidence, `auto-eval repair cycle ${cycle}`, deleted
        );
        const accepted = new Set(result?.accepted || []);
        rejectedIssues = result?.rejected || {};
        rejected = [...Object.keys(result?.rejected || {}), ...deleted.filter((rel) => !accepted.has(rel) && !(rel in (result?.rejected || {})))];
        for (const rel of result?.accepted || []) say(`ℹ AUTO-EVAL ${reqId}: amendment accepted (audited): ${rel}${deleted.includes(rel) ? ' (removed)' : ''}`);
        for (const rel of result?.test_fixes || []) say(`⚠ AUTO-EVAL ${reqId}: test fixed — review required: ${rel}`);
      } catch (err) {
        rejected = [...Object.keys(modified), ...deleted];
        log(`[autoEval] amend failed: ${err?.message || err}`);
      }
    }
    const restore = [...new Set(rejected)];
    if (restore.length) {
      // what the repair proposed for a locked test is kept for the developer before the restore
      const saved = saveRejectedTestFix(wsPath, reqId, cycle, restore.map((rel) => ({
        rel, before: before[rel], after: modified[rel], issues: rejectedIssues[rel] || [],
      })));
      if (saved && owner) owner.__rejectedTestFix = saved;
      restoreAcceptanceFiles(wsPath, reqId, before, restore);
      say(`↺ AUTO-EVAL ${reqId}: restored locked acceptance files the repair may not change: ${restore.join(', ')}`);
    }
  }

  // Auto-eval (roadmap §3): after an eval of `/eval REQ --fix`, repair and re-evaluate until the
  // eval passes, the cycles are exhausted or nothing improves. msg.fix carries the loop state.
  // /finalize verification (no flag): run the solution eval profile in the sandbox; while it fails
  // and cycles remain, /finalize runs again with its errors. msg.finalizeVerifyState: loop state.
  // the solution verification of /finalize is running (sandbox eval, local check)
  let finalizeVerifyInFlight = false;

  async function continueFinalizeVerify(msg) {
    finalizeVerifyInFlight = true;
    try {
      return await continueFinalizeVerifyRun(msg);
    } finally {
      finalizeVerifyInFlight = false;
    }
  }

  async function continueFinalizeVerifyRun(msg) {
    const settings = cfg();
    const ws = getWorkspaceRoot();
    const say = (text) => panel.webview.postMessage({ type: 'echo', message: text });
    const prev = msg.finalizeVerifyState || {};
    const state = {
      cycle: Number(prev.cycle || 0),
      maxCycles: Math.max(1, Number(settings.finalizeVerifyMaxCycles || 3)),
      extraCycles: Math.max(0, Number(settings.autoEvalExtraCyclesOnProgress ?? 3)),
      lastFailureCount: prev.lastFailureCount,
      lastOwnFailureCount: prev.lastOwnFailureCount,
      hint: String(prev.hint || ''),
      lastSignature: prev.lastSignature || '',
      lastKitOk: msg.__result === 'ok',
      history: Array.isArray(prev.history) ? prev.history : [],
    };
    let report;
    if (!fsSync.existsSync(path.join(ws.fsPath, ...finalizeVerify.SOLUTION_PROFILE.split('/')))) {
      report = finalizeVerify.missingProfileReport();
    } else {
      say(`▶ SOLUTION EVAL ${finalizeVerify.SOLUTION_PROFILE} in the CLike eval sandbox (canonical tree)…`);
      try {
        const toolOpts = { profile: finalizeVerify.SOLUTION_PROFILE };
        await ensureToolsForEval(null, toolOpts);
        report = await postEvalChecks(finalizeVerify.SOLUTION_PROFILE, ws, finalizeVerify.SOLUTION_EVAL_ID, []);
        if (await installReportedTools(null, report, toolOpts)) {
          report = await postEvalChecks(finalizeVerify.SOLUTION_PROFILE, ws, finalizeVerify.SOLUTION_EVAL_ID, []);
        }
      } catch (e) {
        say(`✖ SOLUTION EVAL could not run: ${e?.message || e}`);
        recordFinalizeOutcome('failed', `the solution eval could not run: ${e?.message || e}`);
        return;
      }
    }
    report = finalizeVerify.withReportCheck(ws.fsPath, report);
    const failing = (Array.isArray(report?.cases) ? report.cases : [])
      .filter(c => c && !c.passed && c.blocking !== false).map(c => String(c.name));
    state.history = [...state.history, { cycle: state.cycle, status: String(report?.status || (report?.passed ? 'PASS' : 'FAIL')), failing }];
    const writeEvidence = async () => {
      try {
        await saveGeneratedFiles([{ path: finalizeVerify.EVIDENCE_PATH, content: finalizeVerify.solutionEvalMarkdown(report, {
          cycle: state.cycle, history: state.history, gates: finalizeVerify.gateEvidence(ws.fsPath) }) }]);
      } catch (e) {
        log(`[finalizeVerify] evidence not written: ${e?.message || e}`);
      }
    };
    await writeEvidence();
    const step = nextAutoEvalStep(state, report);
    log(`[finalizeVerify] cycle=${state.cycle}/${state.maxCycles} action=${step.action} reason=${step.reason}`);
    const verdict = String(report?.status || (report?.passed ? 'PASS' : 'FAIL')).toUpperCase();
    if (step.action === 'pass' || step.action === 'stop') {
      await commitFinalizeEvidence(ws, settings, step.action === 'pass' ? verdict : 'FAIL');
    }
    if (step.action === 'pass') {
      // the developer's default start (containers) is what the sandbox cannot run: checked here
      const local = await localSolutionCheck(ws, settings, msg, say);
      if (local && !local.ok) {
        const failure = finalizeLocalCheck.localCheckFailure(local);
        if (state.cycle < state.maxCycles && !harperCancelled() && !stopAfterStepRequested(say, 'LOCAL CHECK')) {
          const cycle = state.cycle + 1;
          say(`↻ SOLUTION REPAIR cycle ${cycle}/${state.maxCycles} — the local check failed on this machine (${local.rel}, exit ${local.code})`);
          await handleWebviewMessage({
            type: 'harperRun', cmd: 'finalize', targets: [], attachments: [],
            finalizeRepair: { cycle, max_cycles: state.maxCycles, failures: [failure], files: finalizeVerify.collectSolutionFiles(ws.fsPath), hint: state.hint },
            finalizeVerifyState: { ...state, cycle, lastSignature: `local:${local.code}`, lastFailureCount: 1, lastOwnFailureCount: 1 },
            finalizePendingConfirmed: true,
          });
          return;
        }
        recordFinalizeOutcome('failed', `local check failed on this machine: ${local.rel} exit ${local.code}`);
        say(`✖ /finalize: the sandbox verification passed but ${local.rel} failed on this machine (exit ${local.code}). ` +
          `Run /finalize again to repair it. Output: ${finalizeLocalCheck.REPORT_PATH}`);
        return;
      }
      recordFinalizeOutcome('ok', step.reason);
      say(`✔ SOLUTION EVAL PASS (${step.reason}): the integrated solution installs, builds, is configured, starts and answers. ` +
        `What /finalize did, how to start and see it, and what is still to provide: ${finalizeVerify.REPORT_PATH}. Evidence: ${finalizeVerify.EVIDENCE_PATH}`);
      // the release: tag vN on the finalize commit, notes from the documents, publication on request
      // not awaited: the publication question waits for the developer, the chat is free meanwhile
      offerRelease(ws, settings, verdict, msg, say).catch(e => log(`[release] ${e?.message || e}`));
      // not awaited: the notification waits for the developer, the chat is free meanwhile
      offerLocalSolutionRun(ws).catch(e => log(`[finalizeVerify] local run offer: ${e?.message || e}`));
      return;
    }
    if (step.action === 'stop') {
      const names = (step.failures || []).map(f => f.name).slice(0, 8).join(', ');
      recordFinalizeOutcome('failed', `solution eval stopped: ${step.reason}`);
      say(`✖ SOLUTION EVAL stopped: ${step.reason}.` + (names ? ` Failing: ${names}.` : '') +
        ` Run /finalize again to continue (it repairs from the current state). Report: ${finalizeVerify.REPORT_PATH}. Evidence: ${finalizeVerify.EVIDENCE_PATH}`);
      return;
    }
    if (stopAfterStepRequested(say, 'SOLUTION VERIFICATION')) {
      recordFinalizeOutcome('failed', 'the solution verification was stopped before it passed');
      say(`Run /finalize again to continue (it repairs from the current state). Evidence: ${finalizeVerify.EVIDENCE_PATH}`);
      return;
    }
    const cycle = state.cycle + 1;
    say(`↻ SOLUTION REPAIR cycle ${cycle}/${state.maxCycles} — ${step.reason}`);
    await handleWebviewMessage({
      type: 'harperRun',
      cmd: 'finalize',
      targets: [],
      attachments: [],
      finalizeRepair: {
        cycle,
        max_cycles: state.maxCycles,
        failures: step.failures,
        files: finalizeVerify.collectSolutionFiles(ws.fsPath),
        hint: state.hint,
      },
      finalizeVerifyState: { ...state, cycle, lastSignature: step.signature, lastFailureCount: (step.failures || []).length, lastOwnFailureCount: ownFailureCount(step.failures) },
      finalizePendingConfirmed: true,
    });
  }

  // scripts/check_solution_local on this machine after the sandbox verification passed (setting
  // clike.finalize.localCheck): null when not run, else its result, saved in runs/finalize/LOCAL_CHECK.md.
  async function localSolutionCheck(ws, settings, msg, say) {
    const mode = String(settings.finalizeLocalCheck || 'ask');
    const script = finalizeLocalCheck.localCheckScript(ws.fsPath);
    if (mode === 'off' || !script) return null;
    if (mode === 'ask') {
      if (msg && (msg.__fromMcp || msg.__unattended)) {
        say(`ℹ LOCAL CHECK not run (it needs your confirmation, clike.finalize.localCheck=ask): run ${script.rel} to check the local start.`);
        return null;
      }
      const go = 'Run local check';
      const choice = await vscode.window.showInformationMessage(
        `The solution passed in the CLike sandbox. Check it on this machine too? ${script.rel} builds and starts it as you ` +
        'start it (containers when installed), runs the smoke and stops it — a running local stack is stopped.', go, 'Skip');
      if (choice !== go) {
        say(`ℹ LOCAL CHECK skipped: the default local start is not verified on this machine (${script.rel}).`);
        return null;
      }
    }
    say(`▶ LOCAL CHECK ${script.rel} on this machine (build, start, smoke, stop — a few minutes; output in the CLike log)…`);
    const before = finalizeLocalCheck.visibleUntracked(ws.fsPath);
    const ran = await finalizeLocalCheck.runLocalCheck(ws.fsPath, script, {
      timeoutMs: Math.max(5, Number(settings.finalizeLocalCheckTimeoutMinutes || 30)) * 60000,
      onData: (text) => out.append(text),
    });
    const result = finalizeLocalCheck.withLeftovers(ran, before, finalizeLocalCheck.visibleUntracked(ws.fsPath));
    let report = '';
    try { report = finalizeLocalCheck.writeLocalCheckReport(ws.fsPath, result); } catch (e) { log(`[finalize] local check report: ${e?.message || e}`); }
    say(result.ok
      ? `✔ LOCAL CHECK PASS on this machine (${Math.round(result.ms / 1000)} s). ${report}`
      : `✖ LOCAL CHECK FAIL on this machine (exit ${result.code}${result.timedOut ? ', timed out' : ''}). ${report}`);
    return result;
  }

  // The verification's own files (the profile, its smoke scripts, the evidence, the report the last
  // repair updated) are committed when the loop ends: the finalize commit ran before them.
  async function commitFinalizeEvidence(ws, settings, status = '') {
    if (!settings.gitAutoCommit) return;
    const files = [finalizeVerify.SOLUTION_PROFILE, finalizeVerify.EVIDENCE_PATH, finalizeVerify.REPORT_PATH,
      ...listSolutionSmokeFiles(ws.fsPath)];
    const runId = `verify-${Date.now().toString(16)}`;
    try {
      await clikeGitSync('finalize', runId, null, files,
        { workspaceRoot: ws.fsPath, finalizeOpenPr: false, commitMessage: finalizeCommitMessage(ws.fsPath, runId, status || 'evidence') }, settings, out);
    } catch (e) {
      log(`[finalizeVerify] evidence not committed: ${e?.message || e}`);
    }
  }

  function listSolutionSmokeFiles(root) {
    const out = [];
    const walk = (dir) => {
      let entries = [];
      try { entries = fsSync.readdirSync(dir, { withFileTypes: true }); } catch { return; }
      for (const e of entries) {
        const full = path.join(dir, e.name);
        if (e.isDirectory()) walk(full);
        else if (e.isFile() && out.length < 200) out.push(path.relative(root, full).split(path.sep).join('/'));
      }
    };
    walk(path.join(root, 'ci', 'solution'));
    return out;
  }

  // After a passing verification: the developer can have the local configuration created and the
  // solution started on this machine, in a terminal they see (scripts written by /finalize).
  async function offerLocalSolutionRun(ws) {
    const win = process.platform === 'win32';
    const script = (name) => {
      const rel = `scripts/${name}.${win ? 'ps1' : 'sh'}`;
      return fsSync.existsSync(path.join(ws.fsPath, ...rel.split('/'))) ? rel : '';
    };
    const setup = script('setup_local');
    const start = script('start_solution_local');
    if (!setup && !start) return;
    const configure = 'Configure locally';
    const run = 'Configure and start';
    const choices = [setup && configure, start && run].filter(Boolean);
    const choice = await vscode.window.showInformationMessage(
      `The solution passed the CLike verification. Prepare it on this machine (${[setup, start].filter(Boolean).join(', ')})? ` +
      `Values only you can give are listed in ${finalizeVerify.REPORT_PATH}.`, ...choices);
    if (!choice) return;
    const command = (rel) => win ? `powershell -ExecutionPolicy Bypass -File ${rel}` : `bash ${rel}`;
    const steps = [setup && command(setup), choice === run && start && command(start)].filter(Boolean);
    const terminal = vscode.window.createTerminal({ name: 'CLike solution', cwd: ws.fsPath });
    terminal.show();
    terminal.sendText(steps.join(win ? '; ' : ' && '));
  }

  // /autopilot [N] | stop | status: the REQs of the plan unattended (autopilot.js decides, the
  // chat handlers run every step exactly as when the developer types them).
  async function handleAutopilotCommand(msg) {
    const say = (text) => panel.webview.postMessage({ type: 'echo', message: text });
    const action = String(msg.action || 'start');
    if (action === 'stop') {
      if (!autopilotRun) return say('Autopilot is not running.');
      autopilotRun.stop = 'graceful';
      return say(`⏸ AUTOPILOT: stops after the current step (${autopilotRun.current || 'between steps'}). Cancel stops it now.`);
    }
    if (action === 'status') {
      const snap = autopilotSnapshot();
      if (!snap.started_at) return say(snap.message);
      return say(`AUTOPILOT ${snap.running ? `running: ${snap.current}` : `ended: ${snap.outcome}`}; promoted ${snap.promoted.join(', ') || 'none'}; ` +
        `parked ${snap.parked.map((p) => `${p.req_id} (${p.step}: ${p.reason})`).join(', ') || 'none'}. Report: ${snap.report}`);
    }
    const refuse = (text) => { msg.__refused = text; say(text); };
    if (autopilotRun) return refuse('Autopilot is already running (/autopilot status, /autopilot stop).');
    if (clikeHarperBlockingRun || mcpRunInFlight) return refuse('A Harper phase is running: start /autopilot when it ends.');
    const ws = getWorkspaceRoot();
    if (!ws) return refuse('No workspace open.');
    if (String(vscode.workspace.getConfiguration('clike').get('gate.autoPromote', 'merge')) === 'ask') {
      return refuse('✖ AUTOPILOT not started: clike.gate.autoPromote is "ask" and nobody answers the promotion choice. Set it to "merge" (or "off" to promote yourself).');
    }
    const settings = vscode.workspace.getConfiguration('clike');
    const waitMin = Math.max(1, Number(settings.get('autopilot.quotaWaitMinutes', 30)));
    const waitRetries = Math.max(0, Number(settings.get('autopilot.quotaRetries', 8)));
    const statePath = path.join(ws.fsPath, ...autopilot.STATE_REL.split('/'));
    const reportRel = autopilot.REPORT_REL;
    let saved = null;
    try { saved = JSON.parse(fsSync.readFileSync(statePath, 'utf8')); } catch { /* first run */ }
    // An interrupted run (VS Code closed, crash: never ended) resumes with its own options.
    const interrupted = !!(saved && saved.running);
    const opts = interrupted && (msg.resume || (!msg.executor && !msg.methodology && !msg.max)) ? (saved.options || {}) : msg;
    const maxReqs = Math.max(0, Number(opts.max || 0));
    let override;
    try {
      override = autopilot.executorState(opts.executor);
      autopilot.methodologyFields(opts.methodology, 'kit');
    } catch (err) {
      return refuse(`✖ AUTOPILOT not started: ${err.message}.`);
    }
    const methodology = String(opts.methodology || '').trim().toLowerCase();
    const fingerprintOf = (reqId) => { try { return inputsFingerprint(ws.fsPath, reqId); } catch { return ''; } };
    // REQs parked by an earlier run stay parked until their inputs change (the developer fixed them)
    // the environment the REQs were parked in: a newer CLike or other sandbox tools retry them
    let installedTools = '';
    try { installedTools = Object.keys((await getEvalTools(ws))?.installed || {}).sort().join(','); } catch { /* unknown: inputs only */ }
    const parkEnv = installedTools ? `${context.extension?.packageJSON?.version || ''}|${installedTools}` : '';
    const { kept, released } = autopilot.keptParked(saved && saved.parked, fingerprintOf, parkEnv);
    const run = autopilotRun = { stop: null, current: '', startedAt: Date.now(), reqs: [], waits: [],
      parked: new Set(Object.keys(kept)), parkedInfo: { ...kept }, released, resumed: interrupted,
      executor: String(opts.executor || '').trim().toLowerCase() || '', methodology,
      options: { max: maxReqs, executor: String(opts.executor || ''), methodology } };
    // --executor: the chat execution state for this run (kit, repairs and eval pre-passes read it),
    // restored at the end; what it replaced is kept in the state file, so a resumed run restores it too
    const showUiState = (st) => { try { panel.webview.postMessage({ type: 'initState', state: st }); } catch { /* the chat only shows it */ } };
    const currentUi = context.workspaceState.get('clike.uiState');
    const replaced = interrupted && saved.replaced ? saved.replaced
      : override ? Object.fromEntries(Object.keys(override).map((k) => [k, currentUi && k in currentUi ? currentUi[k] : null])) : null;
    run.replaced = override ? replaced : null;
    if (override) {
      const next = { ...(currentUi || { mode: 'harper', model: 'auto', historyScope: 'singleModel' }), ...override };
      await context.workspaceState.update('clike.uiState', next);
      showUiState(next);
    }
    const writeReport = () => {
      try {
        fsSync.mkdirSync(path.dirname(statePath), { recursive: true });
        fsSync.writeFileSync(path.join(ws.fsPath, ...reportRel.split('/')), autopilot.autopilotReportMarkdown(run));
        fsSync.writeFileSync(statePath, JSON.stringify({
          version: 1, running: !run.endedAt, started_at: new Date(run.startedAt).toISOString(), current: run.current,
          options: run.options, replaced: run.replaced, parked: run.parkedInfo, outcome: run.outcome || null,
          reqs: run.reqs.map(({ req_id, result, step, reason, cycles, ms, review_required }) => ({ req_id, result, step, reason, cycles, ms, review_required })),
        }, null, 2));
      } catch (err) { log(`[autopilot] report not written: ${err?.message || err}`); }
    };
    // where an in-progress REQ resumes: no KIT → kit, last eval passed on these inputs → gate, else eval
    const stepOf = (reqId) => {
      const evals = readEarlierReports(ws.fsPath, reqId).filter((r) => r.phase === 'eval');
      let lastEval = null;
      if (evals.length) {
        const last = evals[evals.length - 1];
        try {
          const rep = JSON.parse(fsSync.readFileSync(path.join(ws.fsPath, 'runs', 'eval', reqId, `report_${reqId}_${last.ts}.json`), 'utf8'));
          lastEval = { status: rep.status, inputs: rep.inputs_fingerprint };
        } catch { lastEval = { status: '', inputs: last.inputs }; }
      }
      return autopilot.resumeStep({
        hasKit: fsSync.existsSync(path.join(ws.fsPath, 'runs', 'kit', reqId, 'ci', 'LTC.json')),
        lastEval, fingerprint: fingerprintOf(reqId),
      });
    };
    const sleep = async (ms) => {
      const end = Date.now() + ms;
      while (Date.now() < end && !run.stop) await new Promise((resolve) => setTimeout(resolve, Math.min(5000, end - Date.now())));
    };
    // one step through the chat handler; what the chat says is kept for the reason of a failure
    const runStep = async (reqId, step) => {
      const transcript = [];
      const webview = panel.webview;
      const originalPost = webview.postMessage;
      webview.postMessage = (m) => {
        if (m && (m.type === 'error' || m.type === 'echo') && m.message) transcript.push(String(m.message).split('\n')[0].slice(0, 300));
        return originalPost.call(webview, m);
      };
      const stepMsg = step === 'kit'
        ? { type: 'harperRun', cmd: 'kit', targets: [reqId], targetReqId: reqId, attachments: [], __autopilot: true, __unattended: true,
          ...autopilot.methodologyFields(methodology, 'kit') }
        : { type: 'harperEDD', cmd: step, targets: [reqId], targetReqId: reqId, attachments: [], argument: reqId,
          path: `runs/kit/${reqId}/ci/LTC.json`, __autopilot: true, __unattended: true, ...(step === 'eval' ? { fix: { hint: '' } } : {}),
          ...autopilot.methodologyFields(methodology, step) };
      try {
        await handleWebviewMessage(stepMsg);
      } catch (err) {
        transcript.push(String(err?.message || err));
      } finally {
        webview.postMessage = originalPost;
      }
      const cancelled = harperCancelled();
      return { outcome: autopilot.stepOutcome(step, stepMsg), transcript, cancelled };
    };
    say(`▶ AUTOPILOT ${interrupted ? 'resumed (the last run was interrupted)' : 'started'}${maxReqs ? ` (at most ${maxReqs} REQ)` : ''}: /kit → /eval --fix → /gate for each REQ, executor ${run.executor || 'as configured'}${methodology ? `, methodology ${methodology}` : ''}. ` +
      `A REQ that needs you is parked and the others go on.` +
      (run.parked.size ? ` Still parked (unchanged since): ${[...run.parked].join(', ')}.` : '') +
      (released.length ? ` Retried (changed since parked): ${released.join(', ')}.` : '') +
      ` /autopilot stop · /autopilot status · report: ${reportRel}`);
    try {
      while (!run.stop) {
        if (maxReqs && run.reqs.filter((r) => r.result === 'promoted').length >= maxReqs) { run.outcome = `${maxReqs} REQ promoted, as requested`; break; }
        const plan = await readPlanJson(ws);
        const next = autopilot.nextAutopilotReq(plan?.reqs, run.parked, stepOf);
        if (next.action === 'finalize_only') { run.outcome = 'every REQ is done'; run.next = '/finalize'; break; }
        if (next.action === 'blocked') {
          run.outcome = 'no REQ can go on';
          run.next = `Parked REQs need you: ${[...run.parked].join(', ') || 'none'} (fix them, then /autopilot: a changed REQ is retried). Waiting: ` +
            next.waiting.filter((w) => !w.parked).map((w) => `${w.req_id} (on ${w.waiting_for.join(', ') || '—'})`).join(', ');
          break;
        }
        const reqId = next.req_id;
        // the plan itself says the REQ cannot be built yet (decisions left open): no agent run for
        // nothing; parked for this run only, so the next /autopilot checks it again
        const blockedBy = next.step === 'kit'
          ? kitBlockers((plan?.reqs || []).find((r) => String(r?.id || '').toUpperCase() === reqId)) : null;
        if (blockedBy) {
          const reason = `not ready for its KIT: the plan leaves open ${blockedBy.blockers.join(', ') || 'decisions'} — ` +
            'write the decisions to /spec (text or attachment), then /plan';
          run.reqs.push({ req_id: reqId, startedAt: Date.now(), result: 'parked', step: 'kit', reason, cycles: 0, ms: 0 });
          run.parked.add(reqId);
          say(`⏸ AUTOPILOT ${reqId} parked before its KIT: ${reason}.`);
          writeReport();
          continue;
        }
        const entry = { req_id: reqId, startedAt: Date.now(), result: 'running', cycles: 0 };
        run.reqs.push(entry);
        if (next.step !== 'kit') say(`ℹ AUTOPILOT ${reqId} resumes at ${next.step}${next.step === 'gate' ? ' (its last eval passed on the current files)' : ' (its KIT is there)'}.`);
        for (const step of autopilot.STEPS.slice(autopilot.STEPS.indexOf(next.step))) {
          run.current = `${step} ${reqId}`;
          entry.step = step;
          writeReport();
          let attempt = 0;
          let res;
          while (true) {
            res = await runStep(reqId, step);
            const text = res.transcript.slice(-12).join('\n');
            const transient = res.outcome.ok || res.cancelled ? null : autopilot.transientFailure(text);
            if (!transient || attempt >= waitRetries || run.stop) break;
            attempt += 1;
            const why = transient === 'quota' ? 'provider quota/rate limit' : 'CLike services not answering';
            run.waits.push({ req_id: reqId, step, minutes: waitMin, reason: `${why}: ${(text.split('\n').filter(Boolean).pop() || '').slice(0, 140)}` });
            say(`⏳ AUTOPILOT ${reqId} ${step}: ${why} — retry ${attempt}/${waitRetries} in ${waitMin} min.`);
            writeReport();
            await sleep(waitMin * 60000);
          }
          if (res.cancelled) { run.stop = 'cancel'; }
          if (step === 'eval' && res.outcome.cycles !== undefined) entry.cycles = res.outcome.cycles;
          if (run.stop === 'cancel') { entry.result = 'cancelled'; entry.reason = 'cancelled'; entry.messages = res.transcript.slice(-3); break; }
          if (!res.outcome.ok) {
            entry.result = 'parked';
            entry.reason = res.outcome.reason;
            entry.messages = res.transcript.filter((t) => /✖|stopped|blocked|failed|cannot|missing|required/i.test(t)).slice(-3);
            run.parked.add(reqId);
            run.parkedInfo[reqId] = { step, reason: entry.reason, fingerprint: fingerprintOf(reqId), env: parkEnv, at: new Date().toISOString() };
            say(`⏸ AUTOPILOT ${reqId} parked at ${step}: ${res.outcome.reason}. Going on with the REQs that do not depend on it.`);
            break;
          }
          if (step === 'gate') {
            entry.result = 'promoted';
            entry.review_required = !!res.outcome.review_required;
            delete run.parkedInfo[reqId];
            say(`✔ AUTOPILOT ${reqId} promoted${entry.review_required ? ' (REVIEW: the repair fixed locked tests, check them)' : ''}.`);
          }
          if (run.stop) break;
        }
        entry.ms = Date.now() - entry.startedAt;
        writeReport();
        if (run.stopAfterReq && !run.stop) {
          run.stop = 'after-req';
          say(`⏸ AUTOPILOT: stopped after ${reqId}, as you asked.`);
        }
      }
      if (run.stop === 'graceful') run.outcome = run.stopByCard ? 'stopped after the current step, as asked' : 'stopped by /autopilot stop';
      if (run.stop === 'after-req') run.outcome = 'stopped after the current REQ, as asked';
      if (run.stop === 'cancel') run.outcome = 'cancelled';
    } catch (err) {
      run.outcome = `stopped on an error: ${err?.message || err}`;
    } finally {
      run.endedAt = Date.now();
      writeReport();
      if (override && replaced) {
        // only the keys this run set go back; a change made in the chat meanwhile to others stays
        const current = context.workspaceState.get('clike.uiState') || {};
        const restored = { ...current };
        for (const [key, value] of Object.entries(replaced)) {
          if (value === null || value === undefined) delete restored[key];
          else restored[key] = value;
        }
        await context.workspaceState.update('clike.uiState', restored);
        showUiState(restored);
      }
      lastAutopilotRun = run;
      autopilotRun = null;
    }
    const promoted = run.reqs.filter((r) => r.result === 'promoted').map((r) => r.req_id);
    say(`■ AUTOPILOT ended — ${run.outcome}. Promoted: ${promoted.join(', ') || 'none'}; parked: ${[...run.parked].join(', ') || 'none'}.${run.next ? ` Next: ${run.next}` : ''} Report: ${reportRel}`);
  }

  // ` methodology=bmad/qa` in the ▶ header of a phase run with a methodology (repair cycles included)
  function methodologyTag(msg) {
    return msg?.methodology ? ` methodology=${msg.methodology}${msg.agent ? '/' + msg.agent : ''}` : '';
  }

  async function continueAutoEval(msg, report, reqId) {
    const settings = cfg();
    const state = {
      cycle: Number(msg.fix.cycle || 0),
      maxCycles: Math.max(1, Number(msg.fix.maxCycles || settings.autoEvalMaxCycles || 2)),
      extraCycles: Math.max(0, Number(msg.fix.extraCycles ?? settings.autoEvalExtraCyclesOnProgress ?? 3)),
      lastFailureCount: msg.fix.lastFailureCount,
      lastOwnFailureCount: msg.fix.lastOwnFailureCount,
      hint: String(msg.fix.hint || ''),
      lastSignature: msg.fix.lastSignature || '',
      lastKitOk: msg.fix.lastKitOk,
    };
    const say = (text) => panel.webview.postMessage({ type: 'echo', message: text });
    // A targeted re-eval (this REQ's checks, the regression of the REQs that failed) that passes
    // is confirmed by the full eval, in the same cycle: only a full eval is the REQ's verdict.
    if (Array.isArray(msg.regressionReqs) && msg.regressionReqs.length && evalPassed(report)) {
      say(`↻ AUTO-EVAL ${reqId}: the targeted re-eval passed (regression of ${msg.regressionReqs.join(', ')}); full eval to confirm`);
      const fullMsg = {
        type: 'harperEDD', cmd: 'eval', targets: [reqId], targetReqId: reqId, attachments: [],
        ...fixCycleMethodology(msg).eval,
        fix: msg.fix,
      };
      await handleWebviewMessage(fullMsg);
      if (fullMsg.__report) msg.__report = fullMsg.__report;
      return;
    }
    const step = nextAutoEvalStep(state, report);
    log(`[autoEval] ${reqId} cycle=${state.cycle}/${state.maxCycles} action=${step.action} reason=${step.reason}`);
    // The outcome travels back to the caller (MCP eval_run) with the report of the last eval.
    const finish = (outcome) => {
      msg.__report = { ...(msg.__report || {}), auto_eval: { outcome, cycles: state.cycle, reason: step.reason } };
    };
    if (step.action === 'pass') {
      say(`✔ AUTO-EVAL ${reqId}: ${step.reason}. Next: /gate ${reqId}`);
      finish('pass');
      return;
    }
    if (step.action === 'stop') {
      const names = (step.failures || []).map(f => f.name).slice(0, 8).join(', ');
      say(
        `✖ AUTO-EVAL ${reqId} stopped: ${step.reason}.` +
        (names ? ` Failing: ${names}.` : '') +
        ` Re-run /eval ${reqId} --fix "<hint>" to continue with guidance, or fix the code manually.`
      );
      finish('stopped');
      return;
    }
    // The plan says the REQ waits for the owner's answers: a repair without them writes no code
    // either (ShortLink: KIT and repairs left a readiness handoff, the same checks failed). Stop and
    // say what to answer; --fix "<your decisions>" gives them to the repair and goes on.
    if (!state.hint.trim()) {
      let waiting = [];
      try { waiting = planReadiness.blockersOf(await readPlanJson(getWorkspaceRoot()), reqId); } catch { waiting = []; }
      if (waiting.length) {
        step.reason = planReadiness.notReadyReason(waiting);
        say(`✖ AUTO-EVAL ${reqId} stopped before a repair: ${step.reason}. Or give the answers to the repair: /eval ${reqId} --fix "<your decisions>".`);
        finish('stopped');
        return;
      }
    }
    if (stopAfterStepRequested(say, `AUTO-EVAL ${reqId}`)) {
      say(`Re-run /eval ${reqId} --fix to go on with the repair cycles.`);
      finish('stopped');
      return;
    }
    const cycle = state.cycle + 1;
    say(`↻ AUTO-EVAL ${reqId}: repair cycle ${cycle}/${state.maxCycles} — ${step.reason}`);
    // Failures that passed in earlier runs of this REQ on the same code are flagged as nondeterministic.
    const repairFailures = annotateIntermittentFailures(step.failures, readEarlierReports(getWorkspaceRoot().fsPath, reqId), inputsFingerprint(getWorkspaceRoot().fsPath, reqId));
    const intermittent = repairFailures.filter((f) => f.intermittent).map((f) => f.name);
    if (intermittent.length) say(`ℹ AUTO-EVAL ${reqId}: ${intermittent.join(', ')} passed in earlier runs: repairing it as a nondeterministic failure`);
    try {
      const notes = writeRepairNotes(getWorkspaceRoot().fsPath, 'eval', reqId, repairNotesMarkdown({
        reqId, phase: 'eval', cycle, maxCycles: state.maxCycles, reason: step.reason, hint: state.hint, failures: repairFailures,
      }));
      say(`ℹ AUTO-EVAL ${reqId}: what the repair receives (hint and CLike diagnosis): ${notes}`);
    } catch (err) {
      log(`[autoEval] repair notes not written: ${err?.message || err}`);
    }
    const loopMethodology = fixCycleMethodology(msg);
    const kitMsg = {
      type: 'harperRun',
      cmd: 'kit',
      targets: [reqId],
      targetReqId: reqId,
      attachments: [],
      ...loopMethodology.kit,
      autoEvalRepair: {
        cycle,
        max_cycles: state.maxCycles,
        failures: repairFailures,
        files: collectRepairFiles(getWorkspaceRoot().fsPath, reqId),
        hint: state.hint,
        // a local agent may re-run the failed checks in the sandbox while it repairs
        ...(Number(settings.autoEvalAgentEvalChecks ?? 8) > 0
          ? { eval_check: true, eval_check_max_runs: Number(settings.autoEvalAgentEvalChecks ?? 8) }
          : {}),
      },
    };
    const wsPath = getWorkspaceRoot().fsPath;
    const acceptanceBefore = snapshotAcceptanceSurface(wsPath, reqId);
    kitMsg.__acceptance = { before: acceptanceBefore, failures: step.failures, cycle };
    await handleWebviewMessage(kitMsg);
    if (!kitMsg.__acceptanceGoverned) await governAcceptanceChanges(reqId, acceptanceBefore, step.failures, cycle, kitMsg);
    if (kitMsg.__rejectedTestFix) {
      // the repair says a locked test is wrong: the developer decides, no more cycles on the code
      say(rejectedTestFixMessage(reqId, kitMsg.__rejectedTestFix));
      step.reason = `the repair proposed a change to a locked test (${kitMsg.__rejectedTestFix.patch})`;
      finish('stopped');
      return;
    }
    if (harperCancelled()) {
      say(`⏹ AUTO-EVAL ${reqId} cancelled at repair cycle ${cycle}.`);
      finish('cancelled');
      return;
    }
    if (stopAfterStepRequested(say, `AUTO-EVAL ${reqId} after repair cycle ${cycle}`)) {
      say(`The repair is not evaluated yet: /eval ${reqId} --fix evaluates it and goes on.`);
      finish('stopped');
      return;
    }
    const evalMsg = {
      type: 'harperEDD',
      cmd: 'eval',
      targets: [reqId],
      targetReqId: reqId,
      attachments: [],
      ...loopMethodology.eval,
      // after a repair of regression failures: the regression of those REQs first (minutes, not
      // the whole set); its pass is confirmed by a full eval above
      ...(targetedRegressionReqs(step.failures).length ? { regressionReqs: targetedRegressionReqs(step.failures) } : {}),
      fix: { ...state, cycle, lastSignature: step.signature, lastKitOk: kitMsg.__result === 'ok', lastFailures: step.failures, lastFailureCount: (step.failures || []).length, lastOwnFailureCount: ownFailureCount(step.failures) },
    };
    await handleWebviewMessage(evalMsg);
    if (evalMsg.__report) msg.__report = evalMsg.__report;
  }

  // `/gate REQ --fix`: the gate re-runs the checks; when they fail, the same KIT repair as
  // /eval --fix (same locked tests, governance and cycle bounds), then a full gate again. A
  // repaired candidate is promoted only by a gate that ran on it.
  async function continueAutoGate(msg, report, reqId) {
    const settings = cfg();
    const state = {
      cycle: Number(msg.fix.cycle || 0),
      maxCycles: Math.max(1, Number(msg.fix.maxCycles || settings.autoEvalMaxCycles || 2)),
      extraCycles: Math.max(0, Number(msg.fix.extraCycles ?? settings.autoEvalExtraCyclesOnProgress ?? 3)),
      lastFailureCount: msg.fix.lastFailureCount,
      lastOwnFailureCount: msg.fix.lastOwnFailureCount,
      hint: String(msg.fix.hint || ''),
      lastSignature: msg.fix.lastSignature || '',
      lastKitOk: msg.fix.lastKitOk,
    };
    const step = nextAutoGateStep(state, report);
    const say = (text) => panel.webview.postMessage({ type: 'echo', message: text });
    log(`[autoGate] ${reqId} cycle=${state.cycle}/${state.maxCycles} action=${step.action} reason=${step.reason}`);
    const finish = (outcome) => {
      msg.__report = { ...(msg.__report || {}), auto_gate: { outcome, cycles: state.cycle, reason: step.reason } };
    };
    if (step.action === 'pass') {
      say(`✔ AUTO-GATE ${reqId}: ${step.reason}.`);
      finish('pass');
      return;
    }
    if (step.action === 'stop') {
      const names = (step.failures || []).map(f => f.name).slice(0, 8).join(', ');
      say(
        `✖ AUTO-GATE ${reqId} stopped: ${step.reason}.` +
        (names ? ` Failing: ${names}.` : '') +
        ` Re-run /gate ${reqId} --fix "<hint>" to continue with guidance, or fix the code manually.`
      );
      finish('stopped');
      return;
    }
    if (stopAfterStepRequested(say, `AUTO-GATE ${reqId}`)) {
      say(`Re-run /gate ${reqId} --fix to go on with the repair cycles.`);
      return;
    }
    const cycle = state.cycle + 1;
    say(`↻ AUTO-GATE ${reqId}: repair cycle ${cycle}/${state.maxCycles} — ${step.reason}`);
    // Failures that passed in earlier runs of this REQ on the same code are flagged as nondeterministic.
    const repairFailures = annotateIntermittentFailures(step.failures, readEarlierReports(getWorkspaceRoot().fsPath, reqId), inputsFingerprint(getWorkspaceRoot().fsPath, reqId));
    const intermittent = repairFailures.filter((f) => f.intermittent).map((f) => f.name);
    if (intermittent.length) say(`ℹ AUTO-GATE ${reqId}: ${intermittent.join(', ')} passed in earlier runs: repairing it as a nondeterministic failure`);
    try {
      const notes = writeRepairNotes(getWorkspaceRoot().fsPath, 'gate', reqId, repairNotesMarkdown({
        reqId, phase: 'gate', cycle, maxCycles: state.maxCycles, reason: step.reason, hint: state.hint, failures: repairFailures,
      }));
      say(`ℹ AUTO-GATE ${reqId}: what the repair receives (hint and CLike diagnosis): ${notes}`);
    } catch (err) {
      log(`[autoGate] repair notes not written: ${err?.message || err}`);
    }
    const kitMsg = {
      type: 'harperRun',
      cmd: 'kit',
      targets: [reqId],
      targetReqId: reqId,
      attachments: [],
      autoEvalRepair: {
        cycle,
        max_cycles: state.maxCycles,
        failures: repairFailures,
        files: collectRepairFiles(getWorkspaceRoot().fsPath, reqId),
        hint: state.hint,
        ...(Number(settings.autoEvalAgentEvalChecks ?? 8) > 0
          ? { eval_check: true, eval_check_max_runs: Number(settings.autoEvalAgentEvalChecks ?? 8) }
          : {}),
      },
    };
    const acceptanceBefore = snapshotAcceptanceSurface(getWorkspaceRoot().fsPath, reqId);
    kitMsg.__acceptance = { before: acceptanceBefore, failures: step.failures, cycle };
    await handleWebviewMessage(kitMsg);
    if (!kitMsg.__acceptanceGoverned) await governAcceptanceChanges(reqId, acceptanceBefore, step.failures, cycle, kitMsg);
    if (kitMsg.__rejectedTestFix) {
      panel.webview.postMessage({ type: 'echo', message: rejectedTestFixMessage(reqId, kitMsg.__rejectedTestFix).replace('AUTO-EVAL', 'AUTO-GATE') });
      return;
    }
    if (harperCancelled()) {
      panel.webview.postMessage({ type: 'echo', message: `⏹ AUTO-GATE ${reqId} cancelled at repair cycle ${cycle}.` });
      return;
    }
    if (stopAfterStepRequested((text) => panel.webview.postMessage({ type: 'echo', message: text }), `AUTO-GATE ${reqId} after repair cycle ${cycle}`)) {
      panel.webview.postMessage({ type: 'echo', message: `The repair is not gated yet: /gate ${reqId} --fix checks it and goes on.` });
      return;
    }
    const gateMsg = {
      type: 'harperEDD',
      cmd: 'gate',
      targets: [reqId],
      targetReqId: reqId,
      attachments: [],
      ...(msg.promote ? { promote: msg.promote } : {}),
      fix: { ...state, cycle, lastSignature: step.signature, lastKitOk: kitMsg.__result === 'ok', lastFailures: step.failures, lastFailureCount: (step.failures || []).length, lastOwnFailureCount: ownFailureCount(step.failures) },
    };
    await handleWebviewMessage(gateMsg);
    if (gateMsg.__report) msg.__report = gateMsg.__report;
  }
}

async function showInitSummaryIfPresent(panel, context) {
  try {
    const ws = vscode.workspace.workspaceFolders?.[0]?.uri?.fsPath;
    if (!ws) return;
    const p = path.join(ws, '.clike', 'last_init_summary.json');
    out.appendLine (`[CLike] showInitSummaryIfPresent: ${p}`);
    if (!(await pathExists(p))) return;
     out.appendLine (`[CLike] showInitSummaryIfPresent file exites`);

    const raw = await fs.readFile(p, 'utf8');
    const sum = JSON.parse(raw);
    const msgTxt =  `✅ CLike: project "${sum.project_name}" is ready\n` +
        `doc_root = ${sum.doc_root}\n` +
        `Files: ${sum.files_created.join(', ')}\n` +
        `Next: open README.md, complete IDEA.md, then /spec`
    panel.webview.postMessage({
      type: 'echo',
      message:msgTxt
    });
    // Persist for subsequent chat restarts
    await context.workspaceState.update('clike.initSummary', msgTxt);
    // optional: rename to avoid repeating
    const donePath = path.join(ws, '.clike', 'last_init_summary.done.json');
    await fs.rename(p, donePath).catch(async () => {
    // if rename fails (e.g. cross-device), fallback: delete
    await fs.rm(p, { force: true });
    });
  } catch (e) {
    console.warn('[CLike] showInitSummaryIfPresent failed:', e);
    out.appendLine(`[error] ${e.stack || e.message}`);
  }
}

function partitionAttachments(atts) {
  const inline_files = [];
  const rag_files = [];
  for (const a of (atts || [])) {
    // small or already in memory
    if (a.content || a.bytes_b64) {
      inline_files.push({
        name: a.name || null,
        path: a.path || null,
        content: a.content || null,
        bytes_b64: a.bytes_b64 || null,
        origin: a.origin || null
      });
    } else if (a.path) {
      // workspace grande → RAG by path
      rag_files.push({ path: a.path });
    }
  }
  return { inline_files, rag_files };
}


async function fetchJson(url, { signal } = {}) {
  const res = await serviceRequest('GET', url, { signal });
  if (!res.ok) throw new Error(`GET ${url} -> ${res.status}`);
  return res.json();
}

async function postJson(url, body, { signal } = {}) {
  const res = await serviceRequest('POST', url, { body, signal });
  if (!res.ok) throw new Error(`POST ${url} -> ${res.status} ${res.text}`);
  return res.json();
}

// Soft timeout on the extension side
async function withTimeout(promise, ms) {
  let to;
  const t = new Promise((_, rej) => {
    to = setTimeout(() => rej(new Error(`Timeout after ${ms}ms`)), ms);
  });
  try {
    return await Promise.race([promise, t]);
  } finally {
    clearTimeout(to);
  }
}

function deactivate() {}
module.exports = { activate, deactivate };
