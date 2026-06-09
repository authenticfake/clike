// extension.js — Clike Orchestrator+Gateway integration GOOGDDDD
const vscode = require('vscode');
const { applyPatch } = require('diff');
const { exec } = require('child_process');
const https = require('https');
const http = require('http');
const { URL } = require('url');
const fs = require('fs/promises');
const fsSync = require('fs');
const path = require('path');

const { registerCommands } = require('./commands/registerCommands');
const {  handleGate, handleEval } = require('./commands/harper');
const {  persistTelemetryVSCode } = require('./telemetry');


const {
  normalizeExecutionPreference,
  normalizeLocalAgentExecutor,
  executionPreferenceRequestsLocalAgent,
  resolveSelectedLocalAgentExecutor,
  detectLocalAgentAvailability,
  getExecutorConfig,
  buildLocalAgentDisplayLabel,
  localAgentSupportsPhase,
  //_d_etectLocalAgentAvailability,
} = require('./local-agent-executors');

const {
  readPlanJson,
  getProjectId,
  promoteReqSources,
  runPromotionFlow,
  preIndexRag,
  normalizeAttachment,
  safeLog,
  readWorkspaceTextFile,
  getFileSizeBytes,
  getProjectNameFromWorkspace,
  runLocalAgentSync,
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
  normalizeChangedFiles,
} = require('./utility');

const {
  sanitize,
  logCurrentTimeStandard,
  httpPostJsonLong,
  ensureReqIdInPlan,
} = require('./utility');
const {
  getHarperSlashCommandName,
  shouldBlockHarperSlashFromGenericChatMessage,
} = require('./slash-parser');

const {
  buildCodexArgsForLocalAgent,
  assertLocalAgentWritePreflight,
  validateLocalAgentRequiredOutputs,
  evaluateDocumentPhaseInputPreflight,
  evaluateExtendInputPreflight,
  classifyBlockedLocalAgentOutput,
} = require('./local-agent-write-policy');

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


function isLocalAgentExecutionPreference(value) {
  const pref = normalizeExecutionPreference(value);
  return new Set([
    'prefer_claude_code',
    'claude_code_only',
    'prefer_local_agent',
    'local_agent_only',
    'hybrid',
  ]).has(pref);
}

function isStrictLocalAgentExecutionPreference(value) {
  const pref = normalizeExecutionPreference(value);
  return pref === 'claude_code_only' || pref === 'local_agent_only';
}

const{ toFsPath, mapKitSrcToWorkspaceTarget, clikeGitSync } = require('./git'); // NEW: clikeGitSync
const { getChatTheme, getWebviewHtml } = require('./chat-ui');
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
let selectedPaths = new Set();
// --- Stato richiesta in corso (per Cancel) ---
let inflightController = null;
// Stato chat: per mode -> array di bolle. Ogni bolla: { role: 'user'|'assistant', text, model, ts }
const chatByMode = {
  free: [],
  coding: [],
  harper: [],
};

function getWorkspaceRoot() {
    const workspaceFolders = vscode.workspace.workspaceFolders;

    if (!workspaceFolders || workspaceFolders.length === 0) {
        // Gestisci il caso in cui non c'è una cartella aperta
        return null; 
    }
    
    // Restituisce l'URI della prima cartella aperta (la radice del workspace)
    return workspaceFolders[0].uri; 
}


const out = vscode.window.createOutputChannel('Clike');
/**
 * Funzione di logging personalizzata che scrive su entrambi i canali.
 * @param {...any} args Messaggi o oggetti da loggare.
 */
function log(...args) {
    // 1. Log nella console standard per il debug.
    console.log(...args); 
    
    // 2. Log nel canale di output di VS Code.
    out.appendLine(args.map(arg => {
        // Converte ogni argomento in stringa per l'output.
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
  await fs.writeFile(filePath, JSON.stringify(obj, null, 2), 'utf8');
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
      cfg.get('localAgent.preferredExecutor', 'auto')
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
  // 1) Normalizza: accetta sia vscode.Uri sia string
  const rootPath =
    typeof workspaceRootUri === 'string'
      ? workspaceRootUri
      : (workspaceRootUri && (workspaceRootUri.fsPath || workspaceRootUri.path)) || '';

  if (!rootPath) {
    throw new Error('collectFinalizeRagItems: invalid workspace root (expected vscode.Uri or string path)');
  }

  // 2) Cammina il FS usando path string (non Uri)
  async function walk(dir) {
    const out = [];
    let entries = [];
    try {
      entries = await fs.readdir(dir, { withFileTypes: true });
    } catch {
      return out; // dir mancante = ok
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
  // Se vuoi includere anche docs/harper, riaggiungilo qui
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

      // 3) Invia path relativo al workspace (portabile e pulito)
      const rel = path.relative(rootPath, absPath).replace(/\\/g, '/');

      targets.push({
        path: rel,                              // <= relativo
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

// Collect RAG items for a given REQ under runs/kit/REQ-XXX/src.
// We index only KIT-generated code, not the global /src folder.
// async function collectKitRagItems(workspaceRoot, reqId,  opts = {}) {
//   if (!workspaceRoot) {
//     return [];
//   }

//   const maxFiles = opts.maxFiles ?? 400;
//   const maxBytes = opts.maxBytes ?? 512 * 1024;

//   const rootFsPath = workspaceRoot.fsPath;
//   const kitSrcDir = path.join(rootFsPath, 'runs', 'kit', reqId, 'src');
//   const kitSrcUri = vscode.Uri.file(kitSrcDir);

//   let stat;
//   try {
//     stat = await vscode.workspace.fs.stat(kitSrcUri);
//   } catch {
//     // No KIT src dir yet for this REQ
//     return [];
//   }

//   if (!stat || stat.type !== vscode.FileType.Directory) {
//     return [];
//   }

//   const items = [];

//   async function walk(dirUri, relBase) {
//     const entries = await vscode.workspace.fs.readDirectory(dirUri);

//     for (const [name, type] of entries) {
//       const childUri = vscode.Uri.joinPath(dirUri, name);
//       const relPath = relBase ? path.posix.join(relBase, name) : name;

//       if (type === vscode.FileType.Directory) {
//         await walk(childUri, relPath);
//         if (items.length >= maxFiles) {
//           return;
//         }
//         continue;
//       }

//       if (type !== vscode.FileType.File) {
//         continue;
//       }
//       // constants.js o all'inizio del tuo file
//       const CODE_EXTENSIONS = [
//         // Web & UI
//         'ts', 'tsx', 'js', 'jsx', 'html', 'htm', 'css', 'scss', 'sass',

//         // Core & Compilati
//         'java', 'cs', 'go', 'rs', 'swift', 'kt', 'm', 'mm', 'c', 'cpp', 'cc', 'h', 'hpp',

//         // Scripting
//         'py', 'pyw', 'rb', 'pl', 'php', 'sh', 'bash', 'ps1', 'lua', 'dart',

//         // Configurazione & Dati
//         'json', 'yml', 'yaml', 'toml', 'ini', 'xml',

//         // Database
//         'sql', 'pls', 'pck',

//         // Documentazione & Markup
//         'md', 'markdown', 'rst', 'tex', 'txt',

//         // Mendix (o altri specifici)
//         'mpr' 
//       ];
//       const fileExtension = name.split('.').pop().toLowerCase();
//       // Only index "code-ish" and text files. Adjust/extensions as needed.
//       if (!CODE_EXTENSIONS.includes(fileExtension)) {
//           log("[harperRAG] skip file (not code): " + childUri.fsPath);
//         continue;
//       }

//       let data;
//       try {
//         data = await vscode.workspace.fs.readFile(childUri);
//       } catch (err) {
//         log(`[harperRAG] skip file (read error): ${childUri.fsPath} -> ${err}`);
//         continue;
//       }

//       if (!data || !data.byteLength) {
//         continue;
//       }

//       const slice = data.byteLength > maxBytes ? data.slice(0, maxBytes) : data;
//       const b64 = Buffer.from(slice).toString('base64');

//       // Path relative to workspace root, so RAG can later map it back.
//       const relFromRoot = path.posix.join('runs', 'kit', reqId, 'src', relPath);

//       items.push({
//         path: relFromRoot,
//         bytes_b64: b64,
//       });

//       if (items.length >= maxFiles) {
//         log(`[harperRAG] kit RAG items truncated at ${maxFiles} files for ${reqId}`);
//         return;
//       }
//     }
//   }

//   await walk(kitSrcUri, '');

//   log(`[harperRAG] collected ${items.length} kit RAG items for ${reqId}`);
//   return items;
// }

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

  const candidateSubroots = ['src', 'test', 'ci', 'docs', 'reports'];
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

const LOCAL_AGENT_COMPLETE_MAX_FILES = 500;
const LOCAL_AGENT_COMPLETE_MAX_TOTAL_CHARS = 8 * 1024 * 1024;

const LOCAL_AGENT_EXCLUDED_ARTIFACT_SEGMENTS = new Set([
  '.git',
  '.venv',
  'node_modules',
  '.next',
  'dist',
  'build',
  'out',
  'coverage',
  '.turbo',
  '.cache',
  '.pytest_cache',
  '.ruff_cache',
  '.mypy_cache',
  '__pycache__',
  '__MACOSX',
]);

const LOCAL_AGENT_EXCLUDED_ARTIFACT_FILENAMES = new Set([
  '.DS_Store',
  'tsconfig.tsbuildinfo',
]);

function localAgentArtifactPath(artifact) {
  return String(artifact?.path || artifact?.file || artifact?.name || '').replace(/\\/g, '/');
}

function localAgentArtifactSizeChars(artifact) {
  if (!artifact || typeof artifact !== 'object') return 0;

  if (typeof artifact.content === 'string') {
    return artifact.content.length;
  }

  if (typeof artifact.text === 'string') {
    return artifact.text.length;
  }

  if (typeof artifact.bytes_b64 === 'string') {
    return artifact.bytes_b64.length;
  }

  if (typeof artifact.content_base64 === 'string') {
    return artifact.content_base64.length;
  }

  try {
    return JSON.stringify(artifact).length;
  } catch {
    return 0;
  }
}

function shouldSendLocalAgentCompleteArtifact(artifact) {
  const relPath = localAgentArtifactPath(artifact);
  if (!relPath) return false;

  const parts = relPath.split('/').filter(Boolean);
  const filename = parts[parts.length - 1] || '';

  if (LOCAL_AGENT_EXCLUDED_ARTIFACT_FILENAMES.has(filename)) {
    return false;
  }

  if (parts.some((part) => LOCAL_AGENT_EXCLUDED_ARTIFACT_SEGMENTS.has(part))) {
    return false;
  }

  return true;
}

function pruneLocalAgentCompleteArtifacts(artifacts, phaseForAgent, reqForAgent) {
  const phase = String(phaseForAgent || '').trim().toLowerCase();
  const req = String(reqForAgent || '').trim().toUpperCase();

  const filtered = (Array.isArray(artifacts) ? artifacts : []).filter((artifact) => {
    if (!shouldSendLocalAgentCompleteArtifact(artifact)) {
      return false;
    }

    const relPath = localAgentArtifactPath(artifact);

    if (phase === 'eval') {
      const reqPrefix = `runs/kit/${req}/`;
      if (!relPath.startsWith(reqPrefix)) {
        return false;
      }

      return (
        relPath.startsWith(`${reqPrefix}ci/`) ||
        relPath.startsWith(`${reqPrefix}docs/`) ||
        relPath.startsWith(`${reqPrefix}reports/`) ||
        relPath.startsWith(`${reqPrefix}test/`)
      );
    }

    return true;
  });

  const kept = [];
  let totalChars = 0;

  for (const artifact of filtered) {
    if (kept.length >= LOCAL_AGENT_COMPLETE_MAX_FILES) {
      break;
    }

    const sizeChars = localAgentArtifactSizeChars(artifact);
    if (totalChars + sizeChars > LOCAL_AGENT_COMPLETE_MAX_TOTAL_CHARS) {
      break;
    }

    kept.push(artifact);
    totalChars += sizeChars;
  }

  return {
    files: kept,
    original_count: Array.isArray(artifacts) ? artifacts.length : 0,
    filtered_count: filtered.length,
    kept_count: kept.length,
    total_chars: totalChars,
    truncated: kept.length < filtered.length,
  };
}

const HARPER_REQUEST_TIMEOUT_MS = 35 * 60 * 1000; // 35 minuti #porcocazzo il timeout ...maybe too long
async function callHarper(cmd, payload, headers, opts = {}) {
  const base =
    vscode.workspace.getConfiguration().get("clike.orchestratorUrl") ||
    "http://localhost:8080";
  const url = `${base}/v1/harper/${cmd}`;

  // Se vuoi, puoi passare opts.timeoutMs per override (es. comandi "leggeri")
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
async function collectExtendCandidateFileArtifacts(workspaceRootUri) {
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

      let data;
      try {
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

// Early Harper document phases (idea/spec/plan) only ever produce their
// canonical Harper documents. Collect just those phase-owned outputs so the
// write policy validates real agent output and not pre-existing artifacts or
// the orchestrator package context/prompt files.
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

async function collectDocumentPhaseCandidateFileArtifacts(workspaceRootUri, phase) {
  const p = String(phase || '').trim().toLowerCase();
  const rootFsPath = workspaceRootUri.fsPath || workspaceRootUri.path;
  const out = [];

  async function readFileArtifact(relPath) {
    const fileUri = vscode.Uri.file(path.join(rootFsPath, relPath));
    try {
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

  for (const relPath of DOCUMENT_PHASE_CANDIDATE_OUTPUTS[p] || []) {
    await readFileArtifact(relPath);
  }

  for (const relDir of DOCUMENT_PHASE_CANDIDATE_DIRS[p] || []) {
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
      await readFileArtifact(`${relDir}/${name}`);
    }
  }

  return out;
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

  const invocationArgs = Array.isArray(invocation.args) ? invocation.args : [];
  const promptTransport = String(invocation.prompt_transport || '').trim();
  let launcherArgs = invocationArgs;
  let selectedCodexSandboxMode = '';

  const packageFiles = Array.isArray(localAgentPackage.package_files)
    ? localAgentPackage.package_files
    : [];

  if (packageFiles.length) {
    await saveGeneratedFiles(packageFiles);
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

  const agentResult = await runLocalAgentSync({
    workspaceRootUri: wsroot,
    prompt: promptContent,
    executorId: selectedExecutor,
    command: executorConfig.command,
    argsBeforePrompt: launcherArgs,
    promptTransport,
    timeoutMinutes: Math.ceil(Number(invocation.timeout_seconds || 1800) / 60),
    out,
  });

  const candidateFiles = (isFinalize)
    ? await collectFinalizeCandidateFiles(wsroot)
    : (isExtend || isDocumentPhase)
      ? []
      : await collectReqCandidateFiles(wsroot, reqForAgent);

  const candidateArtifacts = isFinalize
    ? await collectFinalizeCandidateFileArtifacts(wsroot)
    : isDocumentPhase
      ? await collectDocumentPhaseCandidateFileArtifacts(wsroot, phaseForAgent)
      : isExtend
        ? await collectExtendCandidateFileArtifacts(wsroot)
        : await collectReqCandidateFileArtifacts(wsroot, reqForAgent);

  log(
    `[harperRun][agent] completed executor=${selectedExecutor} ` +
    `phase=${phaseForAgent} req=${reqForAgent} files=${candidateFiles.length} artifacts=${candidateArtifacts.length}`
  );

  if (!candidateArtifacts.length) {
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

    const expectedRoot = isFinalize
      ? 'README.md, docs/harper, scripts, src, or runtime manifests'
      : (isExtend || isDocumentPhase)
        ? 'docs/harper/'
        : `runs/kit/${reqForAgent}/`;
    throw new Error(
      `${executorLabel} completed without returning readable candidate artifacts under ${expectedRoot}`
    );
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

  if (!completeArtifacts.files.length) {
    throw new Error(
      `${executorLabel} completed but no safe local-agent/complete artifacts remained after filtering. ` +
      `original=${completeArtifacts.original_count}`
    );
  }

  if (['kit', 'eval', 'finalize', 'idea', 'spec', 'plan', 'extend'].includes(phaseForAgent)) {
    validateLocalAgentRequiredOutputs({
      phase: phaseForAgent,
      reqId: reqForAgent,
      artifacts: completeArtifacts.files,
    });
  }

  const completeBody = {
    phase: phaseForAgent,
    req_id: reqForAgent,
    runId,
    executionPreference,
    localAgentExecutor: selectedExecutor,
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
  });

  const completeOut = completeGateway.out;

  if (!completeOut?.ok) {
    throw new Error(
      `Orchestrator rejected local-agent result: ${(completeOut?.errors || []).join(' | ') || 'unknown error'}`
    );
  }

  panel.webview.postMessage({
    type: 'echo',
    message: `✅ ${executorLabel} local ${phaseForAgent.toUpperCase()} normalized by orchestrator for ${reqForAgent}.`
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
function buildChatInvocationArgs(executorId, mode, executorConfig) {
  if (executorId === 'claude_code') {
    const flag = (executorConfig && executorConfig.printModeFlag) || '-p';
    if (mode === 'coding') {
      const pm = (executorConfig && executorConfig.permissionMode) || 'acceptEdits';
      return [flag, '--permission-mode', pm];
    }
    return [flag];
  }
  // gpt_codex: non-interactive exec; prompt is delivered on stdin.
  return Array.isArray(executorConfig && executorConfig.argsBeforePrompt)
    ? executorConfig.argsBeforePrompt
    : ['exec'];
}

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

// Run the free/coding local-agent package returned by the orchestrator.
// Returns { mode, badge, answer?, synthesis, stdout, files? }.
async function runLocalChatAgent({ pkg, executorId, settings, wsrootUri, out }) {
  const mode = String(pkg.mode || 'free').toLowerCase();
  const executorConfig = getExecutorConfig(executorId, settings);
  const executorLabel = buildLocalAgentDisplayLabel(executorId);
  const badge = localAgentBadge(executorId);
  const prompt = String(pkg.prompt || '').trim();
  if (!prompt) throw new Error('Local execution package is missing a prompt.');

  const argsBeforePrompt = buildChatInvocationArgs(executorId, mode, executorConfig);
  const timeoutMinutes = settings.localAgentTimeoutMinutes || 20;

  const agentResult = await runLocalAgentSync({
    workspaceRootUri: wsrootUri,
    prompt,
    executorId,
    command: executorConfig.command,
    argsBeforePrompt,
    timeoutMinutes,
    out,
  });

  const stdout = agentResult.stdout || '';
  const stderr = agentResult.stderr || '';

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
    return { mode, badge, synthesis, stdout, files: paths.map(p => ({ path: p })) };
  }

  // free (Q&A)
  const answer = stdout.trim();
  if (!answer) {
    const blocked = classifyBlockedLocalAgentOutput({ stdout, stderr });
    if (blocked) throw new Error(`${blocked.code}: ${blocked.message}`);
    throw new Error(`${executorLabel} returned no answer (exit=${agentResult.exitCode}).`);
  }
  const synthesis = `${executorLabel} answered locally (read-only, exit=${agentResult.exitCode}).`;
  return { mode, badge, answer, synthesis, stdout };
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
  const safe = String(mode || 'free').replace(/[^\w\-\.]/g, '_');
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

// async function loadSessionFilteredHarper(mode, model, limit = 200) {
//   const all = await loadSession(mode, limit);

//   return all.filter(e => {
//     // Condizione 1 (Esistente): Filtra per modello (se specificato)
//     const modelFilter = !model || (e.model || 'auto') === model;
//     if (e.role === 'system') {
//       return false; 
//     }
//     if (e.role !== 'user' && e.role !== 'assistant') {
//       return false;
//     }

//     // La logica si semplifica usando un array di prefissi
//     const EXECUTION_COMMAND_PREFIXES = [
//         '▶IDEA',
//         '▶SPEC',
//         '▶PLAN',
//         '▶KIT',
//         '▶EVAL',
//         '▶GATE',
//         '▶FINALIZE',
//         '✔',
//         '🧪'
//     ];
//     const isExecutionCommand = e.content && EXECUTION_COMMAND_PREFIXES.some(prefix => 
//         e.content.replace(/\s/g, "").startsWith(prefix)
//     );
//     if (isExecutionCommand) {
//         return false; // Scarta i comandi di esecuzione
//     }
//     return modelFilter;
//     });

// }

async function loadSessionFilteredHarper(mode, limit = 200) {
  const all = await loadSession(mode, limit);

  // Prefissi per i comandi Harper, sia "grafici" sia testuali
  const EXECUTION_PREFIXES = [
    '▶ IDEA',
    '▶ SPEC',
    '▶ PLAN',
    '▶ KIT',
    '▶ EVAL',
    '▶ GATE',
    '▶ FINALIZE',
    '✔',      // esito /gate
    '🧪',     // esito /eval
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

    // Prendiamo solo la prima riga non vuota
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
      // Confronto semplice: la linea iniziale deve cominciare con il prefisso
      return firstLineLower.startsWith(p);
    });
  }

  return all.filter((e) => {

    // 2. Escludi i system
    if (e.role === 'system') {
      return false;
    }

    // 3. Tieni solo user/assistant
    if (e.role !== 'user' && e.role !== 'assistant') {
      return false;
    }

    // 4. Scarta i messaggi comando
    if (isExecutionCommandMessage(e.content)) {
      return false;
    }
    
    return true;


  });
}


// Cancella la **prima** occorrenza che matcha role+content+model nel file di sessione
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
        // linea non valida → la teniamo
        kept.push(line);
        continue;
      }

      if (
        !deleted &&
        String(entry.role || '') === String(role || '') &&
        String(entry.content || '') === String(content || '') &&
        (!model || String(entry.model || '') === String(model || ''))
      ) {
        // saltiamo SOLO la prima che matcha
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
  // tiene TUTTO tranne le righe del modello corrente
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
    const relativePath = f.path.replace(/^\.?\//,'');
    const validation = (typeof f.content === 'string')
      ? validateCanonicalHarperArtifact(relativePath, f.content)
      : null;
    if (validation && !validation.ok) {
      const rejectedPath = rejectedHarperArtifactPath({
        phase: opts.phase,
        runId: opts.runId,
        filePath: relativePath,
      });
      const rejectedUri = vscode.Uri.joinPath(root, rejectedPath);
      const rejectedFolder = vscode.Uri.joinPath(rejectedUri, '..');
      try { await vscode.workspace.fs.createDirectory(rejectedFolder); } catch {}
      await vscode.workspace.fs.writeFile(rejectedUri, Buffer.from(f.content, 'utf8'));
      const message = `CLike rejected malformed canonical artifact ${relativePath}; kept existing file and saved rejected content to ${rejectedPath}.`;
      log(`[harperWriteGuard] invalid_canonical_artifact path=${relativePath} checks=${(validation.failed_checks || []).join(',')}`);
      try { vscode.window.showWarningMessage(message); } catch {}
      continue;
    }
    const uri = vscode.Uri.joinPath(root, relativePath);
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
    if (patLen <= 5) return false; // praticamente vuoto
    return true;
  } catch { return true; }
}

function diffHeaderContainsPath(diffStr, filePath) {
  try {
    const short = (filePath || '').split(/[\\/]/).pop();
    return new RegExp(`\\+\\+\\+\\s+.*${short}`).test(diffStr) || new RegExp(`---\\s+.*${short}`).test(diffStr);
  } catch { return true; }
}

// ---- Helpers per contesto di apply & path ----
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

function resolveToWorkspaceUri(p) {
  if (!p) return null;
  if (p.startsWith('file://')) return vscode.Uri.parse(p);
  if (p.startsWith('/') || /^[A-Za-z]:[\\/]/.test(p)) return vscode.Uri.file(p);
  const ws = vscode.workspace.workspaceFolders && vscode.workspace.workspaceFolders[0];
  return ws ? vscode.Uri.joinPath(ws.uri, p.replace(/^\.?\//, '')) : vscode.Uri.file(p);
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
  __clike_lastTargetUriCache = uriStr; // cache sempre

  try {
    if (context && context.workspaceState && typeof context.workspaceState.update === 'function') {
      context.workspaceState.update('clike.lastTargetUri', uriStr);
    }
  } catch (_) {}
  return uriStr;
}



// Costruisce il payload rispettando le firme lato orchestrator (text = intero file, selection = selezione)
function mapDocContextToPayload(ctx, op, useContent = false) {
  
  const prompt = (ctx.selection && ctx.selection.trim()) ? ctx.selection.trim() : '';
  const payload = {
    op,
    intent: mapOpToIntent(op),
    path: ctx.file_path,
    text: ctx.text,                  // intero file (richiesto dall’orchestrator)
    language: ctx.language,
    selection: ctx.selection || '',  // selezione corrente (eventuale)
    prompt,
    fallback: false
  };
  if (useContent) payload.content = ctx.text;
  return payload;
}

function makeLocalDocstring(selectionOrFileText) {
  try {
    const src = selectionOrFileText || '';
    const m = src.match(/^\s*def\s+([a-zA-Z_]\w*)\s*\(([^)]*)\)\s*:/m);
    if (!m) {
      const c = src.match(/^\s*class\s+([A-Z][A-Za-z0-9_]*)/m);
      if (c) return `"""${c[1]}: Class description.\n\nAttributes:\n    ...\n"""`;
      return `"""Module description.\n\nAdd details here.\n"""`;
    }
    const fn = m[1]; const params = m[2].trim();
    const paramList = params ? params.split(',').map(s => s.trim()).filter(Boolean) : [];
    const filtered = paramList.filter(p => !/^self\b|^cls\b/.test(p));
    const paramsSection = filtered.length
      ? `\n\nArgs:\n${filtered.map(p => `    ${p.split('=')[0]}: ...`).join('\n')}`
      : '';
    return `"""${fn}: Describe what it does.${paramsSection}\n\nReturns:\n    ...\n"""`;
  } catch { return `"""Auto docstring placeholder."""`; }
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

/** Esegue un’azione write completa (build payload → POST → apply) */
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

// feedback runtime su settings AI
vscode.workspace.onDidChangeConfiguration((e) => {
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

// ---------- Editor helpers ----------
async function getOrOpenEditor(targetUriString) {
  if (vscode.window.activeTextEditor && !vscode.window.activeTextEditor.document.isClosed) {
    return vscode.window.activeTextEditor;
  }
  if (targetUriString) {
    const uri = vscode.Uri.parse(targetUriString);
    const doc = await vscode.workspace.openTextDocument(uri);
    return await vscode.window.showTextDocument(doc, { preview: false, preserveFocus: false });
  }
  await vscode.commands.executeCommand('workbench.action.focusActiveEditorGroup');
  if (vscode.window.activeTextEditor && !vscode.window.activeTextEditor.document.isClosed) {
    return vscode.window.activeTextEditor;
  }
  throw new Error('No open editor to apply changes.');
}

function documentInfoFromEditor(editor) {
  const doc = editor.document;
  return { uriStr: doc.uri.toString(), language: doc.languageId || 'plaintext' };
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
    orchestratorUrl: c.get('orchestratorUrl', 'http://localhost:8080').replace(/\/+$/, ''),
    gatewayUrl: c.get('gatewayUrl', 'http://localhost:8000').replace(/\/+$/, ''),

    optimizeFor: c.get('optimizeFor', 'capability'),
    harperTimeout: c.get('harperTimeout', 35),
    
    localAgentEnabled: c.get('localAgent.enabled', true),
    localAgentPreferredExecutor: c.get('localAgent.preferredExecutor', 'auto'),
    localAgentAllowEval: c.get('localAgent.allowEval', false),
    localAgentRestrictToKitPhases: c.get('localAgent.restrictToKitPhases', true),
    localAgentTimeoutMinutes: c.get('localAgent.timeoutMinutes', 30),

    claudeCodeEnabled: c.get('claudeCode.enabled', false),
    claudeCodeRestrictToKitPhases: c.get('claudeCode.restrictToKitPhases', true),
    claudeCodeEnableEval: c.get('claudeCode.enableEval', false),
    claudeCodeCommand: c.get('claudeCode.command', 'claude'),
    claudeCodePermissionMode: c.get('claudeCode.permissionMode', 'acceptEdits'),
    claudeCodePrintModeFlag: c.get('claudeCode.printModeFlag', '-p'),
    claudeCodeTimeoutMinutes: c.get('claudeCode.timeoutMinutes', 30),

    codexEnabled: c.get('localAgent.codex.enabled', true),
    codexCommand: c.get('localAgent.codex.command', 'codex'),
    codexSandboxMode: c.get('localAgent.codex.sandboxMode', 'auto'),
    codexTimeoutMinutes: c.get('localAgent.codex.timeoutMinutes', 35),

    requireCleanGit: c.get('apply.requireCleanGit', false),
    backup: c.get('apply.backup', true),
    dryRunPreview: c.get('apply.dryRunPreview', true),

    gitAutoCommit: c.get('git.autoCommit', true),
    gitMergeOnGate: c.get('git.gitMergeOnGate', true),
    gitDeleteBranchOnMerge: c.get('git.gitDeleteBranchOnMerge', false),
    gitReturnToFeatureAfterMerge: c.get('git.gitReturnToFeatureAfterMerge', false),
    gitRemoteUrl: c.get('git.remoteUrl', ''),
    gitCommitMessage: c.get('git.commitMessage', 'clike: apply patch (AI)'),
    gitOpenPR: c.get('git.openPR', true),
    gitRemote: c.get('git.remote', 'origin'),
    gitDefaultBranch: c.get('git.defaultBranch', 'main'),
    gitConventionalCommits: c.get('git.conventionalCommits', true),
    gitPushRebase: c.get('git.pushRebase', true),
    gitBranchPrefix: c.get('git.branchPrefix', 'feature'),
    gitTagPrefix: c.get('git.tagPrefix', 'harper'),
    gitPrPerReqDraftEnabled: c.get('git.prPerReqDraft.enabled', false),
    gitPrPerReqDraftUseGhCli: c.get('git.prPerReqDraft.useGhCli', true),
    gitPrBodyPath: c.get('git.prBodyPath', 'docs/harper/PR_BODY.md'),

    mcpExtensionServerEnabled: c.get('mcp.extensionServerEnabled', true),
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

function mcpTextResult(id, payload, isError = false) {
  return {
    jsonrpc: '2.0',
    id,
    result: {
      content: [
        {
          type: 'text',
          text: typeof payload === 'string' ? payload : JSON.stringify(payload, null, 2),
        },
      ],
      isError,
    },
  };
}

function mcpError(id, code, message, data = null) {
  return {
    jsonrpc: '2.0',
    id,
    error: {
      code,
      message,
      data,
    },
  };
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

function ensureLocalMcpAuthorized(req) {
  const settings = cfg();
  const expected = String(settings.mcpExtensionServerToken || '').trim();

  if (!expected) {
    return true;
  }

  const header = String(req.headers.authorization || '').trim();
  return header === `Bearer ${expected}`;
}

// async function getHarperNextAction() {
//   const wsroot = getWorkspaceRoot();
//   if (!wsroot) {
//     return {
//       ok: false,
//       action: 'no_workspace',
//       message: 'No VS Code workspace is open.',
//     };
//   }

//   const plan = await readPlanJson(wsroot);
//   const reqs = Array.isArray(plan?.reqs) ? plan.reqs : [];

//   if (!reqs.length) {
//     return {
//       ok: false,
//       action: 'no_plan',
//       message: 'docs/harper/plan.json is missing or has no reqs.',
//     };
//   }

//   const done = new Set(
//     reqs
//       .filter(r => String(r?.status || '').trim().toLowerCase() === 'done')
//       .map(r => String(r?.id || '').trim().toUpperCase())
//       .filter(Boolean)
//   );

//   const open = reqs.filter(r => String(r?.status || '').trim().toLowerCase() !== 'done');

//   for (const req of open) {
//     const reqId = String(req?.id || '').trim().toUpperCase();
//     const deps = Array.isArray(req?.dependsOn)
//       ? req.dependsOn.map(x => String(x || '').trim().toUpperCase()).filter(Boolean)
//       : [];

//     const missingDeps = deps.filter(dep => !done.has(dep));
//     if (!missingDeps.length) {
//       return {
//         ok: true,
//         action: 'run_req',
//         next_phase: 'kit',
//         req_id: reqId,
//         req,
//         message: `Next eligible REQ is ${reqId}.`,
//       };
//     }
//   }

//   if (!open.length) {
//     return {
//       ok: true,
//       action: 'finalize_only',
//       next_phase: 'finalize',
//       req_id: null,
//       message: 'All REQs are done. Only /finalize is available.',
//     };
//   }

//   return {
//     ok: true,
//     action: 'blocked',
//     next_phase: null,
//     req_id: null,
//     open_reqs: open.map(r => ({
//       id: r.id,
//       status: r.status,
//       dependsOn: r.dependsOn || [],
//     })),
//     message: 'No eligible REQ found because dependencies are not satisfied.',
//   };
// }

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

  const firstOpen = reqs.find(req => {
    const status = String(req?.status || '').trim().toLowerCase();
    return status === 'open';
  });

  if (firstOpen) {
    const reqId = String(firstOpen?.id || '').trim().toUpperCase();
    const deps = Array.isArray(firstOpen?.dependsOn)
      ? firstOpen.dependsOn.map(x => String(x || '').trim().toUpperCase()).filter(Boolean)
      : [];

    return {
      ok: true,
      action: 'run_req',
      selection_policy: 'first_open_in_plan_order',
      next_phase: 'kit',
      req_id: reqId,
      req: firstOpen,
      dependsOn: deps,
      message: `Next open REQ is ${reqId}.`,
    };
  }

  const inProgress = reqs.find(req => {
    const status = String(req?.status || '').trim().toLowerCase();
    return status === 'in_progress';
  });

  if (inProgress) {
    const reqId = String(inProgress?.id || '').trim().toUpperCase();
    const deps = Array.isArray(inProgress?.dependsOn)
      ? inProgress.dependsOn.map(x => String(x || '').trim().toUpperCase()).filter(Boolean)
      : [];

    return {
      ok: true,
      action: 'run_req',
      selection_policy: 'first_in_progress_fallback',
      next_phase: 'kit',
      req_id: reqId,
      req: inProgress,
      dependsOn: deps,
      message: `No open REQ found. Continuing first in_progress REQ ${reqId}.`,
    };
  }

  return {
    ok: true,
    action: 'finalize_only',
    next_phase: 'finalize',
    req_id: null,
    selection_policy: 'no_open_or_in_progress_req',
    message: 'All REQs are done. Only /finalize is available.',
  };
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

async function dispatchAgentSlashCommand(command) {
  const clean = String(command || '').trim();
  if (!clean.startsWith('/')) {
    throw new Error('Agent command must be a slash command.');
  }

  const allowedPrefixes = [
    '/agent-default',
    '/idea',
    '/spec',
    '/plan',
    '/kit',
    '/eval',
    '/gate',
    '/finalize',
    '/ragIndex',
    '/ragSearch',
  ];

  if (!allowedPrefixes.some(prefix => clean === prefix || clean.startsWith(prefix + ' '))) {
    throw new Error(`Unsupported CLike agent command: ${clean}`);
  }

  const panel = await ensureClikeChatPanelForAgent();

  extensionMcpState.lastCommand = clean;
  extensionMcpState.lastAcceptedAt = new Date().toISOString();
  extensionMcpState.lastError = null;

  panel.webview.postMessage({
    type: 'agentRunSlash',
    command: clean,
  });

  return {
    ok: true,
    accepted: true,
    command: clean,
    note: 'Command dispatched to chat clike. The normal extension/orchestrator flow will execute it.',
  };
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

    const command = reqPhases.has(phase) ? `/${phase} ${reqId}` : `/${phase}`;
    return await dispatchAgentSlashCommand(command);
  }

  if (tool === 'harper_kit_next') {
    const next = await getHarperNextAction();
    if (next.action === 'finalize_only') {
      return next;
    }

    if (!next.req_id) {
      return next;
    }

    return await dispatchAgentSlashCommand(`/kit ${next.req_id}`);
  }

  if (tool === 'harper_continue_loop') {
    const next = await getHarperNextAction();

    if (next.action === 'finalize_only') {
      return {
        ...(await dispatchAgentSlashCommand('/finalize')),
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
      ...(await dispatchAgentSlashCommand(`/${phase} ${next.req_id}`)),
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
      description: 'Return the next eligible REQ or say that only finalize is available.',
      inputSchema: {
        type: 'object',
        properties: {},
      },
    },
    {
      name: 'harper_run_phase',
      description: 'Dispatch a normal CLike slash phase through the VS Code extension chat flow.',
      inputSchema: {
        type: 'object',
        properties: {
          phase: { type: 'string', enum: ['idea', 'spec', 'plan', 'kit', 'eval', 'gate', 'finalize'] },
          req_id: { type: 'string' },
        },
        required: ['phase'],
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
  const method = String(body?.method || '').trim();
  const id = body?.id ?? null;

  if (method === 'initialize') {
    return {
      jsonrpc: '2.0',
      id,
      result: {
        protocolVersion: '2024-11-05',
        capabilities: {
          tools: {},
        },
        serverInfo: {
          name: 'CLike Extension Operational MCP',
          version: 'v1',
        },
        instructions: (
          'Operational CLike MCP surface. Use it to ask the VS Code extension to run normal CLike slash commands. ' +
          'The extension never bypasses the orchestrator; it dispatches into the same chat-driven flow used by developers.'
        ),
      },
    };
  }

  if (method === 'notifications/initialized') {
    return {
      jsonrpc: '2.0',
      id,
      result: {},
    };
  }

  if (method === 'tools/list') {
    return {
      jsonrpc: '2.0',
      id,
      result: {
        tools: extensionMcpToolsList(),
      },
    };
  }

  if (method === 'tools/call') {
    const params = body?.params || {};
    const name = String(params.name || '').trim();
    const args = params.arguments || {};

    try {
      const result = await runExtensionMcpTool(name, args);
      return mcpTextResult(id, result, false);
    } catch (err) {
      extensionMcpState.lastError = String(err?.message || err);
      return mcpTextResult(id, {
        ok: false,
        tool: name,
        error: String(err?.message || err),
      }, true);
    }
  }

  return mcpError(id, -32601, `Unsupported MCP method: ${method}`);
}

function startExtensionOperationalMcpServer(context) {
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

  extensionMcpServer = http.createServer(async (req, res) => {
    try {
      const url = new URL(req.url || '/', `http://${host}:${port}`);

      if (!ensureLocalMcpAuthorized(req)) {
        return sendMcpJson(res, 401, { ok: false, error: 'unauthorized' });
      }

      if (req.method === 'GET' && url.pathname === '/health') {
        return sendMcpJson(res, 200, {
          ok: true,
          service: 'CLike Extension Operational MCP',
          workspace: getWorkspaceRoot()?.fsPath || null,
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

      if (req.method === 'POST' && (url.pathname === '/mcp' || url.pathname === '/')) {
        const body = await readRequestJson(req);
        const response = await handleExtensionMcpRpc(body);
        return sendMcpJson(res, 200, response);
      }

      return sendMcpJson(res, 404, {
        ok: false,
        error: 'not_found',
        path: url.pathname,
      });
    } catch (err) {
      extensionMcpState.lastError = String(err?.message || err);
      return sendMcpJson(res, 500, {
        ok: false,
        error: String(err?.message || err),
      });
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
  const run = (cmd) =>
    new Promise((resolve, reject) => {
      exec(cmd, { cwd }, (err, stdout, stderr) => {
        if (err) return reject(new Error(stderr || err.message));
        resolve(stdout.trim());
      });
    });

  const inside = await run('git rev-parse --is-inside-work-tree');
  if (inside !== 'true') throw new Error('Non sei dentro un repo Git.');
  const status = await run('git status --porcelain');
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
function httpPostJson(urlString, bodyObj, headers = {}) {
  const url = new URL(urlString);
  const isHttps = url.protocol === 'https:';
  const payload = JSON.stringify(bodyObj || {});
  const opts = {
    method: 'POST',
    hostname: url.hostname,
    port: url.port || (isHttps ? 443 : 80),
    path: url.pathname + (url.search || ''),
    headers: { 'Content-Type': 'application/json', 'Content-Length': Buffer.byteLength(payload), ...headers },
  };

  return new Promise((resolve) => {
    const req = (isHttps ? https : http).request(opts, (res) => {
      let data = '';
      res.on('data', (chunk) => (data += chunk));
      res.on('end', () => {
        try {
          const json = JSON.parse(data || '{}');
          resolve({ ok: res.statusCode >= 200 && res.statusCode < 300, status: res.statusCode, json });
        } catch (_) {
          resolve({ ok: res.statusCode >= 200 && res.statusCode < 300, status: res.statusCode, text: data });
        }
      });
    });
    req.on('error', (error) => resolve({ ok: false, status: 0, error }));
    req.write(payload);
    req.end();
  });
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
  const r = await fetch(url, { method: 'GET' });
  if (!r.ok) return { status: r.status };
  try { return await r.json(); } catch { return { status: r.status }; }
}

/** ---------- Git helpers ---------- */
/**
 * @deprecated Questo metodo è obsoleto. Usa `clikeGitSync()` al suo posto.
 */
async function gitAutoCommitAndPR() {
  const { gitAutoCommit, gitCommitMessage, gitOpenPR } = cfg();
  if (!gitAutoCommit) return;

  const ws = vscode.workspace.workspaceFolders && vscode.workspace.workspaceFolders[0];
  if (!ws) return;
  const cwd = ws.uri.fsPath;

  const run = (cmd) =>
    new Promise((resolve, reject) => {
      exec(cmd, { cwd }, (err, stdout, stderr) => {
        if (err) return reject(new Error(stderr || err.message));
        resolve(stdout.trim());
      });
    });

  try {
    await run('git add -A');
    await run(`git commit -m "${gitCommitMessage.replace('"', '\\"')}"`);
    vscode.window.setStatusBarMessage('Clike: changes committed.', 3000);
  } catch (e) {
    log(`[harperGit] commit skip/failed: ${e.message}`);
  }

  if (gitOpenPR) {
    const ok = await vscode.commands.executeCommand('github.createPullRequest');
    if (!ok) {
      vscode.window.showInformationMessage('Clike: installa "GitHub Pull Requests and Issues" per aprire una PR.');
    }
  }
}

/** ---------- Preview provider per diff ---------- */
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

function _inferProvider(modelName) {
  const n = String(modelName||'').toLowerCase();
  if (n.startsWith('gpt')) {
    console.log("GPT", n);
    return 'openai';
  }
  if (/(llama|ollama|codellama|mistral|mixtral|phi|qwen|granite|yi|gemma|llava)/.test(n)) return 'ollama';
  if(n.startsWith('claude')) return 'anthropic';
  if(n.startsWith('vllm')) return 'vllm';
  if(n.startsWith('deepseek')) return 'deepseek';
  
  return 'openai'; // fallback conservativo
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
// FIX: cambia firma — ora accetta (targetUri, newContent, lang?, intent?)
// in passato veniva chiamata per errore con “context�?
async function replaceWholeSafe(targetUri, newContent, lang, intent) {
  // Safety: non sovrascrivere il file con una docstring breve
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

  // CASE A: contenuto puro → replacement intero file (con preview)
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
    // FIX: usa doc.uri (non context)
    await replaceWholeSafe(doc.uri, newContent);
    vscode.window.showInformationMessage('Clike: applied content.');
    await vscode.commands.executeCommand('workbench.action.files.save');
    await gitAutoCommitAndPR();
    return;
  }

  // CASE B: unified diff → applica patch
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
    // FIX: usa doc.uri
    await replaceWholeSafe(doc.uri, patched);
    vscode.window.showInformationMessage('Clike: patch applied (diff).');
    await vscode.commands.executeCommand('workbench.action.files.save');
    await gitAutoCommitAndPR();
    return;
  }

  // CASE C: patch non applicabile → non scrivere il diff raw nel file
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

/** Inserisce testo (docstring) sopra la selezione o in testa al file */
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
  // FIX: sanifica new_content dal preambolo (“Here is the updated code:�?) o blocchi ```
  const newContentRaw = data.new_content;
  const newContent = typeof newContentRaw === 'string' ? extractCodeBlockOrPlain(newContentRaw) : undefined;

  const apply = data.apply || {};
  const intent = (applyCtx.intent || '').toLowerCase();
  const lang = applyCtx.lang || '';
  const selectionText = applyCtx.selectionText || '';
  const targetUri = applyCtx.targetUri;

  // 1) diff esplicito
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

  // 2) DOCSTRING con selezione → inserisci SOPRA la selezione se la docstring è "breve"
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

  // 3) replace_selection esplicito
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

  // 4) replace_whole esplicito
  if (apply.type === 'replace_whole' && typeof newContent === 'string') {
    await replaceWholeSafe(targetUri, newContent, lang, intent);
    await vscode.commands.executeCommand('workbench.action.files.save');
    return;
  }

  // 5) fallback ragionevole
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

/** ---------- Commands (allineati agli endpoint) ---------- */
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
    //log("cmdCheckServices g", JSON.stringify(g), g);
    //log("cmdCheckServices o", JSON.stringify(o), o);
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

  // Allinea il projectId a tutto il resto (Harper, /kit, RAG da chat)
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
      if (buf.includes(0)) continue; // skip binari

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

  const { orchestratorUrl, routes } = cfg();
  const url = '/v1/rag/index';

  try {
    const res = await postJson(`${orchestratorUrl}${url}`, {
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
    panel?.webview.postMessage({ type: 'hydrateSession', messages: hist });
  } else {
    await pruneSessionByModel(s.mode, s.model || 'auto');
    vscode.window.showInformationMessage(`CLike: cleared messages for model "${s.model}" in mode "${s.mode}"`);
    const hist = await loadSessionFilteredV2(s.mode, s.model, 200);
    panel?.webview.postMessage({ type: 'hydrateSession', messages: hist });
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


function activate(context) {
  const reg = (id, fn) => context.subscriptions.push(vscode.commands.registerCommand(id, () => fn(context)));
  //out.appendLine(`activate ${context}`);
  clikeExtensionContext = context;
  reg('clike.chat.openSessionFile', cmdOpenChatSessionFile);
    reg('clike.harper.init', async () => {
    const panel = await cmdOpenChat(context); // riusa l’apri-chat esistente
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
  
  registerCommands(context);

  startExtensionOperationalMcpServer(context);

  vscode.window.setStatusBarMessage('Clike: orchestrator+gateway integration ready', 2000);
}

function isTextFile(filePath) {
    const buffer    = Buffer.alloc(4096); // Leggiamo i primi 4KB
    const fd        = fsSync.openSync(filePath, 'r');
    const bytesRead = fsSync.readSync(fd, buffer, 0, 4096, 0);
    fsSync.closeSync(fd);

    for (let i = 0; i < bytesRead; i++) {
        if (buffer[i] === 0) return false; // Trovato byte nullo: è BINARIO
    }
    return true; // Nessun byte nullo: è TESTO
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
  panel.webview.postMessage = (message, ...args) => {
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
    }
  });
  const c = vscode.workspace.getConfiguration();
  const orchestratorUrl = c.get('clike.orchestratorUrl') || 'http://localhost:8080';
  const chatTheme = getChatTheme()
  panel.webview.html = getWebviewHtml(orchestratorUrl, chatTheme);
  panel.webview.postMessage({ type: 'busy', on: false });
  // Stato iniziale (mode/model)
  const savedState = context.workspaceState.get('clike.uiState') || {
    mode: 'free',
    model: 'auto',
    historyScope: 'singleModel',
    executionPreference: getDefaultExecutionPreference(),
    localAgentExecutor: getDefaultLocalAgentExecutor(),
  };
  savedState.historyScope = effectiveHistoryScope(context);
  savedState.executionPreference = normalizeExecutionPreference(
    savedState.executionPreference || getDefaultExecutionPreference()
  );
  savedState.localAgentExecutor = normalizeLocalAgentExecutor(
    savedState.localAgentExecutor || getDefaultLocalAgentExecutor()
  );
  panel.webview.postMessage({ type: 'initState', state: savedState });
  out.appendLine(`cmdOpenChat savedState done`);

  // HYDRATE per MODE (non per model)
  // Hydrate chat dal FS per il modello selezionato
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
  
  // Ultimo run per Apply
  const lastRun = context.workspaceState.get('clike.lastRun');
  if (lastRun) panel.webview.postMessage({ type: 'lastRun', data: lastRun });
  // Ascolto eventi dalla webview
  out.appendLine(`cmdOpenChat lastRun  ${lastRun}`);
  if (lastRun) panel.webview.postMessage({ type: 'lastRun', data: lastRun });

  // Dopo aver creato il panel e prima di restituire:
  await showInitSummaryIfPresent(panel, context);

  function escapeHtml(s){return s.replace(/[&<>"']/g, m=>({ "&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;","'":"&#39;"}[m]))}
  

  // Ascolto eventi dalla webview
  panel.webview.onDidReceiveMessage(async (msg) => {
    panel.webview.postMessage({ type: 'busy', on: true });

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

      if (msg.type === 'harperInit') {
        try {
          const name = (msg.name || '').trim();
          const passedPath = (msg.path || '').trim();   // posizionale opzionale
          const force = !!msg.force;
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

          // scegli la cartella parent
          let parentUri = null;
          if (passedPath) {
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
            panel.webview.postMessage({ type: 'error', message: `Target not empty: ${targetDir}. Use --force to proceed.` });
            panel.webview.postMessage({ type: 'busy', on: false });
            return;
          }

          // struttura cartelle
          const docRoot = path.join(targetDir, 'docs', 'harper');
          await ensureDir(path.join(targetDir, '.clike'));
          await ensureDir(path.join(targetDir, '.github'));
          await ensureDir(path.join(targetDir, '.github/workflows'));

          await ensureDir(path.join(targetDir, 'runs'));
          await ensureDir(docRoot);

          // Copy template files
          //const extRoot = vscode.extensions.getExtension('publisher.clike').extensionPath;
          const extRoot = context.extensionPath;
          
          const templatesDir = path.join(extRoot, 'templates', 'harper-init');
          const BINARY_EXTENSIONS = new Set(['.png', '.jpg', '.jpeg', '.gif', '.pdf', '.zip', '.exe', '.dll', '.so', '.dylib', '.woff', '.woff2', '.ttf', '.eot']);
          function copyRecursive(src, dest) {
            //out.appendLine(`copyRecursive ${src} -> ${dest}`);
            if (fsSync.statSync(src).isDirectory()) {
              fsSync.mkdirSync(dest, { recursive: true });
              for (const entry of fsSync.readdirSync(src)) {
                copyRecursive(path.join(src, entry), path.join(dest, entry));
              }
            } else {
              if (fsSync.existsSync(dest) && !force) {
                panel.webview.postMessage({ type: 'busy', on: false });
                return;
              }

              const ext = path.extname(src).toLowerCase();
              const BINARY_EXTENSIONS = new Set([
                '.png', '.jpg', '.jpeg', '.gif', '.pdf', '.zip', '.exe', '.dll',
                '.so', '.dylib', '.woff', '.woff2', '.ttf', '.eot'
              ]);

              if (BINARY_EXTENSIONS.has(ext) || !isTextFile(src)) {
                fsSync.copyFileSync(src, dest);
              } else {
                let content = fsSync.readFileSync(src, 'utf-8');
                for (const [token, value] of Object.entries(templateVars)) {
                  content = content.split(token).join(String(value));
                }
                fsSync.writeFileSync(dest, content);
              }
            }
          }
          copyRecursive(templatesDir, targetDir);

          // file seed
          await writeFileUtf8(path.join(targetDir, '.gitignore'),`node_modules/
          dist/
          .vscode/
          runs/eval/.venvs/
          .env
          runs/**/local-eval-workspaces/
          local-eval-workspaces/
          runs/
          *.log
          `);

          // handoff per bubble nel nuovo workspace
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
          // bubble nel workspace ORIGINE
          panel.webview.postMessage({
            type: 'echo',
            message:msgText
          });


          // apri il nuovo workspace in una nuova window
          await vscode.commands.executeCommand('vscode.openFolder', vscode.Uri.file(targetDir), true);
          //await context.workspaceState.update('clike.initSummary', msgText);


        } catch (e) {
          console.error('[CLike] harperInit failed:', e);
          panel.webview.postMessage({ type: 'error', message: 'Init failed: ' + String(e?.message || e) });
        }
      }
      // Run Harper phase from webview (slash: /spec | /plan | /kit | /build)
      if (msg.type === 'harperRun') {
        const runId = (Math.random().toString(16).slice(2) + Date.now().toString(16));
        //log(`[harperRun] inside ${JSON.stringify(msg)}`);
        const phase = msg.cmd;
        try {

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
            const nextState = {
              ...state,
              mode: 'harper',
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

            log(`[harperRun][agent-default] updated localAgentExecutor=${nextExecutor}`);

            await appendSessionJSONL('harper', {
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
            if (rag_files) {
              const res = await preIndexRag(project_id, rag_files, urlRag, out); 
              log((`CLike preIndexRag: ${JSON.stringify(res)} ${res}`));
            }
          } catch (e) { log(`CLike preIndexRag error: ${e}`); }
          // Core docs per fase
          let core = defaultCoreForPhase(phase);
          // Flags privacy (se già presenti altrove, riusale)
          const flags = {
            neverSendSourceToCloud: !!cfgChat().neverSendSourceToCloud || false,
            redaction: true
          };
          //CHAT HARPEr START
          // History del MODE corrente
          const historyScope  = effectiveHistoryScope(context);
          // History per conversazione “stateless�?: carico SOLO le bolle del MODE corrente
          const history = await loadSessionFilteredHarper(activeMode).catch(() => []);
          // Filtra eventualmente per modello se vuoi inviare solo il sotto-filo di quel model:
          const historyForThisModel = await loadSessionFiltered(activeMode, activeModel); //history.filter(b => !b.model || b.model === activeModel);
          //log((`CLike history: ${JSON.stringify(history)}`));
          
          const source = (historyScope === 'allModels')
          ? history
          : historyForThisModel;
          const _source = source.filter(b => 
            // Condizione 1: Il ruolo deve essere 'user' O 'assistant'
            (b.role === 'user' || b.role === 'assistant') 
          );
        
          var _messages = _source.map(b => ({ role: b.role, content: b.content }));
          let msg_bubble='';
          const _gen={
            temperature: 0.2,
            max_tokens: (phase === 'plan' ? 45000 : phase === 'spec' ? 10500 : 9999),
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
              ...(msg.repair ? { repair: true } : {})
            };
          }
          //log(`[harperRun] payload (gen):`,  JSON.stringify(payload.gen));
          msg_bubble = phase==='idea' ? project_id : targets; 
          // Persisti l’input dell’utente nella sessione del MODE (e mostreremo badge del modello in render)
          await appendSessionJSONL(activeMode, {
            role: 'user',
            content: `▶ ${cmd.toUpperCase()} ${msg_bubble} | mode=${state.mode} model=${state.model} exec=${executionPreference} profile=${profileHint || '—'} core=${JSON.stringify(core)}`,
            model:  state.model || 'auto',
            attachments: Array.isArray(msg.attachments) ? msg.attachments : []
          });
          // Echo pre-run
          panel.webview.postMessage({
            type: 'echo',
            message: `▶ ${cmd.toUpperCase()} ${msg_bubble} | mode=${state.mode} model=${state.model} exec=${executionPreference} profile=${profileHint || '—'} core=${JSON.stringify(core)} attachments=${attachments.length}`
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
          const localExecutorLabel = buildLocalAgentDisplayLabel(selectedLocalExecutor || 'auto');
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
          const onlyBaseKitPhase =
            !requestedKitPhases ||
            !requestedKitPhases.length ||
            (requestedKitPhases.length === 1 && String(requestedKitPhases[0] || '').trim().toLowerCase() === 'kit');
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
            };

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
              Number(settings.localAgentTimeoutMinutes || 20) * 60
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
          harperTimeout = cfg().harperTimeout;
          clikeHarperBlockingRun = true;
          panel.webview.postMessage({ type: 'busy', on: true });
          let outGateway = await callHarper(cmd, body, _headers, { timeoutMs: 1000 * 60 * harperTimeout} );
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
              });
            } catch (err) {
              const failMsg = `[harperRun][agent] ${err?.message || String(err)}`;
              log(failMsg);

              if (executionPreference === 'local_agent_only') {
                clikeHarperBlockingRun = false;
                panel.webview.postMessage({ type: 'busy', on: false, force: true });
                panel.webview.postMessage({ type: 'error', message: failMsg });
                return;
              }

              const errText = err?.message || String(err);
              const rejectedByNormalizer = /^Orchestrator rejected local-agent result:/i.test(errText);

              if (phase === 'finalize' && rejectedByNormalizer) {
                clikeHarperBlockingRun = false;
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

              outGateway  = await callHarper(cmd, fallbackBody, _headers, { timeoutMs: 1000 * 60 * harperTimeout });
              _out = outGateway.out;
            }
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
          // 3) POST-RUN: persisti esito (riassunto + eventuale echo/testo)
          const summary = [
            _out?.echo ? `[echo] ${_out.echo}` : null,
            (Array.isArray(_out?.diffs) && _out.diffs.length) ? `[diffs] ${_out.diffs.length}` : null,
            (Array.isArray(_out?.files) && _out.files.length) ? `[files] ${_out.files.length}` : null,
            _out?.text ? `[text] ${Math.min(String(_out.text).length, 200)} chars` : null
          ].filter(Boolean).join(' • ') || 'no artifacts';
          log(`[harperRun] summary done`);
          // --- PERSIST TELEMETRY (avoid duplicates, one file per run) ---
          try {
            // sorgente principale lato orchestrator
            const tFromServer = _out?.telemetry || outGateway?.telemetry || _out?.usage ? {
              provider: activeProvider,
              model: activeModel,
              usage: _out?.usage,
              pricing: _out?.telemetry?.pricing,
              files: _out?.files
            } : null;
            await persistTelemetryVSCode(wsroot, project_id, runId, phase, tFromServer || {
              provider: activeProvider,
              model: activeModel,
              usage: _out?.usage || {},
              pricing: _out?.telemetry?.pricing || {},
              files: _out?.files || []});
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
            const settings = cfg();
            if (settings.gitAutoCommit) {
               try {
                await clikeGitSync(
                phase,
                runId,
                targetReqId,
                _out.files.map(f => f.path),
                { workspaceRoot: toFsPath(wsroot), finalizeOpenPr: (phase === 'finalize') },
                settings,
                out
              );
              } catch (err) {
                log(`[harperRun] gitSync error ${err}`);

              }
            }
      
          }
          log(`[harperRun] written files done`);
          if (phase === 'plan') {
            try {
              const laneItems = await collectLaneGuidesRagItems(wsroot, {
                maxFiles: 200,
                maxBytes: 512 * 1024,
              });
              const count = (laneItems && laneItems.length) || 0;
              log(`[harperRAG] lane-guides collection after /plan: ${count} items`);
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
        } catch (e) {
          panel.webview.postMessage({ type: 'busy', on: false }) 
          panel.webview.postMessage({ type: 'error', message: formatHarperError(e) });
        }
        clikeHarperBlockingRun = false;
        panel.webview.postMessage({ type: 'busy', on: false, force: true });
      }
      //Harper Evals
      //Harper Evals
      if (msg.type === 'harperEDD' ) {
        let targets, targetReqId
        const phase = msg.cmd;
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
        await appendSessionJSONL(activeMode, {
          role: 'user',
          content: `▶ ${phase.toUpperCase()} ${targets} ${mode} ${modeContent} | mode=${state.mode} model=${state.model} exec=${executionPreference}`,
          model:  state.model || 'auto',
          attachments: Array.isArray(msg.attachments) ? msg.attachments : []
        });
        // Echo pre-run
        panel.webview.postMessage({
          type: 'echo',
          message: `▶ ${phase.toUpperCase()} ${targets} ${mode} ${modeContent} | mode=${state.mode} model=${state.model} exec=${executionPreference}`
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
            // ... codice per continuare
        } catch (error) {
          // Gestisce il caso in cui il file non esiste affatto (fs.statSync lancerebbe un errore)
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
        const localAgentRequested = executionPreferenceRequestsLocalAgent(executionPreference);
        const localAgentAvailability = detectLocalAgentAvailability(settings);
        log(`[harperEDD][agent][availability] ${JSON.stringify(localAgentAvailability)}`);
        const selectedLocalExecutor = resolveSelectedLocalAgentExecutor(
            settings,
            state.localAgentExecutor || 'auto',
            phase
        );
        const localExecutorConfig = selectedLocalExecutor
            ? getExecutorConfig(selectedLocalExecutor, settings)
            : null;
        const localExecutorLabel = buildLocalAgentDisplayLabel(selectedLocalExecutor || 'auto');

        switch (msg.cmd) {
          case 'eval': {
            const evalAgentPrepassRequested =
              executionPreference !== 'cloud_only' && !!selectedLocalExecutor;

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
                Number(settings.localAgentTimeoutMinutes || 20) * 60
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
                  await executeLocalAgentPackage({
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
                } else {
                  log(
                    `[harperEDD][agent] eval pre-pass did not return local_agent package; ` +
                    `continuing with canonical eval req=${targets}`
                  );
                }
              } catch (err) {
                const failMsg = `[harperEDD][agent] eval pre-pass failed: ${err?.message || String(err)}`;
                log(failMsg);

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
                `reason=${executionPreference === 'cloud_only' ? 'cloud_only' : 'no_local_executor_available'} ` +
                `req=${targets}`
              );
            }
            log("[harperEDD] Calling canonical eval for req:" + targets + " in: " + ws_root);
            report = await handleEval(path_ltc_json, ws_root, targets, mode, modeContent);
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
            reportFile = await saveEvalCommand(ws_root, plan, targets, report, out);
            files_git.push(toFsPath(reportFile));

            break;
          }
          case 'gate':
            if (isManual) {
              report = {
                req_id: targets,
                status: 'PASS',
                gate: 'pass',
                reason_code: 'manual_override',
                summary: `Manual gate override accepted for ${targets}.`,
                passed: 1,
                failed: 0,
                passed_count: 1,
                blocked_count: 0,
                warning_count: 0,
                cases: [
                  {
                    name: 'manual_gate_override',
                    passed: true,
                    cmd: `/gate ${targets} manual pass`,
                    stdout: `Manual gate override accepted for ${targets}.`
                  }
                ]
              };
            } else {
              report = await handleGate(
                path_ltc_json,
                ws_root,
                targets,
                { promote: false, reqId: targets, mode: mode, result: modeContent }
              );
            }

            const { report_file, filesToCommit, planFiles } = await saveGateCommand(
              ws_root,
              plan,
              targets,
              report,
              out
            );

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
                { workspaceRoot: toFsPath(wsRoot), finalizeOpenPr: (phase === 'finalize') },
                settings,
                out
              );
            } catch (err) {
              log(`[harperEDD] gitSync error ${err}`);
            }
          }
        }
        // Persisti l’input dell’utente nella sessione del MODE (e mostreremo badge del modello in render)
        await appendSessionJSONL(activeMode, {
          role: 'system',
          content:"✔ "+ String(report.summary || ''),
          model:  state.model || 'auto',
        });
        panel.webview.postMessage({ type: 'echo', message: "✔ " + report.summary } );
        clikeHarperBlockingRun = false;
        panel.webview.postMessage({ type: 'busy', on: false, force: true });

      } 

      
     
      if (msg.type === 'ragIndex') {
      // opzionale: msg.glob (stringa). Riusiamo la logica del comando palette.
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
      


      // RAG search richiesto dalla webview (/rag, /ragSearch)
      if (msg.type === 'ragSearch') {
        try {
          const ws = vscode.workspace.workspaceFolders && vscode.workspace.workspaceFolders[0];
          if (!ws) throw new Error('No workspace open.');

          const projectId = getProjectId(); // es. "clike__<workspace-name>"

          // accetta sia msg.q che msg.query (compatibilità vecchia/new)
          const rawQ = (typeof msg.q !== 'undefined' ? msg.q : msg.query) || '';
          const query = String(rawQ || '').trim();
          const top_k = Number.isFinite(msg.top_k) ? msg.top_k : 8;

          if (!query) throw new Error('Query vuota.');

          const { orchestratorUrl, routes } = cfg();
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

            // opzionale utility
      if (msg.type === 'echo') {
        await appendSessionJSONL(state.mode, {
          role: 'assistant',
          content: typeof msg.message === 'string' ? msg.message : JSON.stringify(msg.message || '', null, 2),
          model: 'system'
        });
        
      }
      if (msg.type === 'where') {
        out.appendLine('[CLike] where state ' + state.mode);
        const ws = vscode.workspace.workspaceFolders && vscode.workspace.workspaceFolders[0];
        const p = ws ? ws.uri.fsPath : '(no workspace)';
        await appendSessionJSONL(state.mode, { role:'assistant', content:`Workspace: ${p}`, model:'system' });
        
      }
      if (msg.type === 'switchProject') {
        // Nota: per multi-progetto potremo salvare un puntatore in .clike/config.json
        await appendSessionJSONL(state.mode, { role:'assistant', content:`(placeholder) Switched project to: ${String(msg.name||'')}`, model:'system' });
       
      }
      if (msg.type === 'webview_ready') {
        try {
          out.appendLine('[CLike] webview_ready');
          // 1) Stato UI salvato (nessun newState qui)
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
            executionPreference: normalizeExecutionPreference(
              saved.executionPreference || getDefaultExecutionPreference()
            ),
            localAgentExecutor: normalizeLocalAgentExecutor(
              saved.localAgentExecutor || getDefaultLocalAgentExecutor()
            ),
          };
          // 2) Invia initState alla webview
          panel.webview.postMessage({ type: 'initState', state: ui });
          // 3) Hydrate dei messaggi (non bloccare su errori)
          try {
            const msgs = (ui.historyScope === 'allModels')
              ? await loadSession(ui.mode, 200).catch(() => [])
              : await loadSessionFilteredV2(ui.mode, ui.model, 200).catch(() => []);
            panel.webview.postMessage({ type: 'hydrateSession', messages: msgs });
          } catch (e) {
            out.appendLine('[CLike] hydrate failed: ' + (e?.message || String(e)));
            panel.webview.postMessage({ type: 'hydrateSession', messages: [] });
          }
          // 4) Fetch modelli con timeout + fallback "auto"
          try {
            const orchestratorUrl = vscode.workspace.getConfiguration().get('clike.orchestratorUrl') || 'http://localhost:8080';
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
            // Ripristina il bubble persistito (se presente)
            // try {
            //   const memo = context.workspaceState.get('clike.initSummary');
            //   if (memo) panel.webview.postMessage({ type: 'echo', message: memo });
            // } catch {

            // }

            panel.webview.postMessage({ type: 'models', models, providers: res?.providers || null });
            out.appendLine('[CLike] models sent: ' + models.join(', '));
          } catch (e) {
            out.appendLine('[CLike] models fetch failed: ' + (e?.message || String(e)));
            panel.webview.postMessage({ type: 'models', models: ['auto'] });
          }
        } catch (e) {
          out.appendLine('[CLike] webview_ready handler crashed: ' + (e?.message || String(e)));
          // Fallback minimo per non lasciare la webview “vuota�?
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

        // 🔧 salva sul campo UNICO usato ovunque: historyScope
        const prev = context.workspaceState.get('clike.uiState') || { mode:'free', model:'auto', historyScope:'singleModel' };
        const ui = { ...prev, historyScope: value };
        await context.workspaceState.update('clike.uiState', ui);

        // Re-hydrate immediato coerente con lo scope scelto
        const modeCur  = ui.mode  || 'free';
        const modelCur = ui.model || 'auto';
        const msgs = (value === 'allModels')
          ? await loadSession(modeCur, 200).catch(()=>[])
          : await loadSessionFilteredV2(modeCur, modelCur, 200).catch(()=>[]);
        panel.webview.postMessage({ type: 'hydrateSession', messages: msgs });

        // NIENTE initState qui (evita rimbalzi della combo)
        vscode.window.setStatusBarMessage(`CLike: history scope = ${value}`, 2000);
        
      }
      // 1) MODELLI
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
      // 2) CAMBIO UI (Mode/Model)
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

        // Se è cambiato SOLO il modello, NON re-idratare la chat
        if (prev.mode === newState.mode && prev.model !== newState.model) {
          const scope = (newState.historyScope === 'allModels') ? 'allModels' : 'singleModel';
          if (scope === 'singleModel') {
            const modeCur  = newState.mode  || 'free';
            const modelCur = newState.model || 'auto';
            const msgs = await loadSessionFilteredV2(modeCur, modelCur, 200).catch(() => []);
            panel.webview.postMessage({ type: 'hydrateSession', messages: msgs });
          }
         
        }
        // Se è cambiato il mode (o entrambi), re-idrata in base allo scope
        const scope   = (newState.historyScope === 'allModels') ? 'allModels' : 'singleModel';
        const modeCur = newState.mode || 'free';
        const modelCur= newState.model || 'auto';

        const msgs = (scope === 'allModels')
          ? await loadSession(modeCur).catch(() => [])
          : await loadSessionFilteredV2(modeCur, modelCur, 200).catch(() => []);

        panel.webview.postMessage({ type: 'hydrateSession', messages: msgs });
       
      }
      // 3) CLEAR SESSION (solo mode corrente)
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

        const scope = effectiveHistoryScope(context);  //  SOLO UI
        if (scope === 'allModels') {
          // cancella tutto il MODE (file intero)
          await clearSession(modeCur);
          panel.webview.postMessage({ type: 'hydrateSession', messages: [] });
          vscode.window.setStatusBarMessage(`CLike: cleared ALL messages in mode "${modeCur}"`, 2500);
        } else {
         // singleModel → ripulisci SOLO le righe del modello corrente
          await pruneSessionByModel(modeCur, modelCur);
          // NEW: dopo la pulizia, mostra subito le altre conversazioni del mode
          const msgs = await loadSessionFilteredV2(modeCur, modelCur, 200).catch(() => []);
          // Idrata la webview con i messaggi rimanenti (tutti gli altri modelli)
          // NON tocchiamo historyScope automaticamente: resta quello scelto in combo
          panel.webview.postMessage({ type: 'hydrateSession', messages: msgs});
          vscode.window.setStatusBarMessage(`CLike: cleared messages for model "${modelCur}" in mode "${modeCur}"`, 2500);

        }
      
      }
      // 4) OPEN FILE (tab Files cliccabile)
      if (msg.type === 'openFile' && msg.path) {
        try {
          const ws = vscode.workspace.workspaceFolders && vscode.workspace.workspaceFolders[0];
          if (!ws) throw new Error('No workspace open');
          const uri = vscode.Uri.joinPath(ws.uri, msg.path.replace(/^\.?\//,''));
          const doc = await vscode.workspace.openTextDocument(uri);
          await vscode.window.showTextDocument(doc, { preview: false });
        } catch (e) {
          vscode.window.showErrorMessage(`Open file failed: ${e.message}`);
        }        
       
      }
      // 3.a) CLEAR user/assistent bubble
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

        // Ricarico la history in base allo scope attuale (Model vs All models)
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
         // cancel eventuale richiesta precedente
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
        
        // Persisti l’input dell’utente nella sessione del MODE (e mostreremo badge del modello in render)
        await appendSessionJSONL(activeMode, {
          role: 'user',
          content: String(msg.prompt || ''),
          model: activeModel,
          provider:activeProvider,
          attachments: Array.isArray(msg.attachments) ? msg.attachments : []
        });

        // Partiziona allegati SOLO QUI (N.B.: niente variabili globali!)
        const atts = Array.isArray(msg.attachments) ? msg.attachments : [];
        const { inline_files, rag_files } =  partitionAttachments(atts);
        log(`CLike: ${inline_files.length} inline_files, ${rag_files.length} rag_files`);
        // History del MODE corrente
        const historyScope  = effectiveHistoryScope(context);
        // History per conversazione “stateless�?: carico SOLO le bolle del MODE corrente
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
        };

        // (ternario corretto)
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
              const localOut = await runLocalChatAgent({
                pkg: res,
                executorId: selectedLocalExecutor || normalizeLocalAgentExecutor(cur.localAgentExecutor || 'auto'),
                settings: settingsLA,
                wsrootUri: getWorkspaceRoot(),
                out,
              });
              if (localOut.mode === 'coding') {
                // Clean bubble (agent badge + file list), Files tab populated and
                // active. Files are already on disk, so no Apply/base64 preview.
                await appendSessionJSONL(activeMode, { role: 'assistant', content: localOut.synthesis, model: localOut.badge });
                panel.webview.postMessage({ type: 'chatResult', data: { model: localOut.badge, text: localOut.synthesis } });
                panel.webview.postMessage({ type: 'files', data: localOut.files, activate: true });
              } else {
                await appendSessionJSONL(activeMode, { role: 'assistant', content: localOut.answer, model: localOut.badge });
                panel.webview.postMessage({ type: 'chatResult', data: { model: localOut.badge, text: localOut.answer } });
                panel.webview.postMessage({ type: 'text', text: localOut.synthesis });
              }
            } catch (e) {
              panel.webview.postMessage({ type: 'error', message: String(e?.message || e) });
            } finally {
              panel.webview.postMessage({ type: 'busy', on: false, force: true });
              inflightController = null;
            }
            return;
          }

          // Salva ultimo run (serve per Apply)
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
            // generate: opzionale autowrite (se l’hai abilitato in cfgChat)
            const { autoWrite } = cfgChat?.() || { autoWrite: false };
            if (autoWrite && Array.isArray(res.files) && res.files.length) {
              const paths = await saveGeneratedFiles(res.files, { phase: 'apply', runId: res.runId || res.run_id });
             
            }
            // Cache locale dei file dell’ultimo generate (serve per Apply fallback)
            try {
              await context.workspaceState.update('clike.lastFiles', Array.isArray(res?.files) ? res.files : []);
            } catch (e) {
                out.appendLine('[CLike] cache lastFiles failed: ' + (e?.message || String(e)));
                throw new Error(`POST ${url} -> ${res.status} ${txt}`);
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
      // 6) APPLY
      if (msg.type === 'apply') {
        const run_dir  = msg.run_dir  || null;
        const audit_id = msg.audit_id || null;
        const selection = msg.selection || { apply_all: true };
        const wantPaths = Array.isArray(selection?.paths) ? selection.paths : null;

        // 1) Se il server ha un run_dir/audit_id → usa l'endpoint /v1/apply
        if (run_dir || audit_id) {
          const payload = { run_dir, audit_id, selection };
          const res = await postJson(`${orchestratorUrl}/v1/apply`, payload);
          panel.webview.postMessage({ type: 'applyResult', data: res });
          panel.webview.postMessage({ type: 'busy', on: false });
          
        }

        // 2) Fallback client-side: nessun run_dir/audit_id, ma forse abbiamo i file in cache
        const lastFiles = context.workspaceState.get('clike.lastFiles') || [];
        if (!Array.isArray(lastFiles) || !lastFiles.length) {
          panel.webview.postMessage({ type: 'error', message: 'Nothing to apply: no run_dir/audit_id and no cached files.' });
          panel.webview.postMessage({ type: 'busy', on: false });

        }

        // Filtra per i path selezionati (se presenti), altrimenti applica tutto
        const chosen = wantPaths
          ? lastFiles.filter(f => f && f.path && wantPaths.includes(f.path))
          : lastFiles;

        if (!chosen.length) {
          panel.webview.postMessage({ type: 'error', message: 'No files selected to apply.' });
          panel.webview.postMessage({ type: 'busy', on: false });

        }

        try {
          const paths = await saveGeneratedFiles(chosen, { phase: 'apply', runId: lastRun?.runId || lastRun?.run_id || lastRun?.audit_id });
          // Pulizia cache per non ri-applicare accidentalmente
          try { await context.workspaceState.update('clike.lastFiles', []); } catch {}
          panel.webview.postMessage({ type: 'applyResult', data: { applied: paths } });
        } catch (e) {
          panel.webview.postMessage({ type: 'error', message: 'Apply (local) failed: ' + (e?.message || String(e)) });
        }
       
      }
      // 7) CANCEL
      if (msg.type === 'cancel') {
        if (inflightController) inflightController.abort();
        inflightController = null;
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

        const MAX_INLINE = 64 * 1024;
        const TEXT_EXT = new Set(['.md','.txt','.log','.json','.yml','.yaml','.csv','.tsv','.py','.js','.ts','.java','.go','.rs','.c','.cpp','.cs','.sql','.ini','.toml','.cfg']);
        const atts = [];

        for (const uri of uris) {
          try {
            const stat = await vscode.workspace.fs.stat(uri);
            const size = stat.size || 0;
            const rel  = vscode.workspace.asRelativePath(uri);
            const fsPath = uri.fsPath || rel;
            const baseName = fsPath.split(/[\\/]/).pop() || 'file';
            const ext = (baseName.match(/\.[^.]+$/)?.[0] || '').toLowerCase();

            if (size <= MAX_INLINE) {
              const bytes = await vscode.workspace.fs.readFile(uri);
              if (TEXT_EXT.has(ext)) {
                atts.push({
                  origin: 'workspace',
                  source: 'workspace',
                  name: baseName,
                  path: rel,
                  content: Buffer.from(bytes).toString('utf8'),
                  size,
                  mime: 'text/plain'
                });
              } else {
                atts.push({
                  origin: 'workspace',
                  source: 'workspace',
                  name: baseName,
                  path: rel,
                  bytes_b64: Buffer.from(bytes).toString('base64'),
                  size,
                  mime: 'application/octet-stream'
                });
              }
            } else {
              atts.push({
                origin: 'workspace',
                source: 'workspace',
                name: baseName,
                path: rel,
                size,
                mime: 'application/octet-stream'
              });
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

        // Heuristics
        const MAX_INLINE = 64 * 1024;
        const TEXT_EXT = { '.md':1,'.txt':1,'.log':1,'.json':1,'.yml':1,'.yaml':1,'.csv':1,'.tsv':1,
                          '.py':1,'.js':1,'.ts':1,'.java':1,'.go':1,'.rs':1,'.c':1,'.cpp':1,'.cs':1,
                          '.sql':1,'.ini':1,'.toml':1,'.cfg':1 };
        function extOf(name) {
          const m = /(\.[^.]+)$/.exec((name || '').toLowerCase());
          return m ? m[1] : '';
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
            const e = extOf(baseName);
            const isText = !!TEXT_EXT[e];

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
              mime: isText ? 'text/plain' : 'application/octet-stream'
            };

            // 4) Optionally also include inline content for small files (kept in case you need it)
            if (size <= MAX_INLINE) {
              if (isText) {
                atts.push(Object.assign({}, common, { content: Buffer.from(bytes).toString('utf8') }));
              } else {
                atts.push(Object.assign({}, common, { bytes_b64: Buffer.from(bytes).toString('base64') }));
              }
            } else {
              atts.push(common);
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
  });
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
    // Persisti per i riavvii successivi della chat
    await context.workspaceState.update('clike.initSummary', msgTxt);
    // opzionale: rinomina per non ripetere
    const donePath = path.join(ws, '.clike', 'last_init_summary.done.json');
    await fs.rename(p, donePath).catch(async () => {
    // se rename fallisce (es. cross-device), fallback: delete
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
    // piccolo o già in memoria
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
  const f = (typeof fetch === 'function')
    ? fetch
    : ((...args) => import('node-fetch').then(({ default: ff }) => ff(...args)));
  const res = await f(url, { signal });
  if (!res.ok) throw new Error(`GET ${url} -> ${res.status}`);
  return await res.json();
}

async function postJson(url, body, { signal } = {}) {
  const f = (typeof fetch === 'function')
    ? fetch
    : ((...args) => import('node-fetch').then(({ default: ff }) => ff(...args)));
  const res = await f(url, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify(body),
    signal
  });
  if (!res.ok) {
    const txt = await res.text().catch(() => '');
    throw new Error(`POST ${url} -> ${res.status} ${txt}`);
  }
  return await res.json();
}

// Timeout soft lato estensione
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
