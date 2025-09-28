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
const os = require('os');


//const { activateTestController } = require('./testController');
const { registerCommands } = require('./commands/registerCommands');
const { handlePlanUpdate, handleSync, handleGate, handleEval } = require('./commands/slashBot');
const { buildHarperBody } = require('./utility')
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

// Wire these to your existing chat system:
function onHarperChatInput(callback) {
  // TODO: connect this to your actual chat input emitter.
  // Return a disposable-like object: { dispose() {} }
  return { dispose() {} };
}
function postToChat(text) {
  // TODO: send `text` to your chat panel.
}
function getWorkspaceRoot() {
  return vscode.workspace.workspaceFolders?.[0]?.uri?.fsPath || '.';
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

function log(...args) { console.log(...args); out.appendLine(args.join(' ')); } 
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

// --- generic Harper runner (spec/plan/kit/build) ---
async function callHarper(cmd, payload, headers) {
  const base = vscode.workspace.getConfiguration().get('clike.orchestratorUrl') || 'http://localhost:8080';
  const url  = `${base}/v1/harper/${cmd}`;
  const res  = await fetch(url, { method: 'POST', headers: headers, body: JSON.stringify(payload) });
  if (!res.ok) {
    const txt = await res.text().catch(()=> '');
    throw new Error(`orchestrator ${cmd} ${res.status}: ${txt || 'error'}`);
  }
  return res.json();
}

// ---------- Session & FS helpers ----------
function wsRoot() {
  const ws = vscode.workspace.workspaceFolders && vscode.workspace.workspaceFolders[0];
  if (!ws) throw new Error('Apri una workspace per usare CLike chat.');
  return ws.uri;
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

function effectiveHistoryScope(context) {
  try {
    const ui = context.workspaceState.get('clike.uiState') || {};
    return (ui.historyScope === 'allModels') ? 'allModels' : 'singleModel';
  } catch {
    return 'singleModel';
  }
}

function sessionsDirUri() {
  const root = wsRoot();
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
}async function loadSessionFiltered(mode, model, limit = 200) {
  const all = await loadSession(mode, limit);
  return all.filter(e => !model || (e.model || 'auto') === model);
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

async function saveGeneratedFiles(files) {
  if (!Array.isArray(files) || !files.length) return [];
  const root = wsRoot();
  const written = [];
  for (const f of files) {
    if (!f || !f.path || typeof f.content !== 'string') continue;
    const uri = vscode.Uri.joinPath(root, f.path.replace(/^\.?\//,''));
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
    return vscode.window.showErrorMessage(`Clike ${label}: ${msg}`);
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
  const c = vscode.workspace.getConfiguration();

  const routes = c.get('clike.routes', {
    orchestrator: {
      code: '/agent/code',
      ragSearch: '/v1/rag/search',  
      ragIndex: '/v1/rag/ingest',
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
    // URL base (presenti)
    orchestratorUrl: c.get('clike.orchestratorUrl', 'http://localhost:8080').replace(/\/+$/, ''),
    gatewayUrl:      c.get('clike.gatewayUrl', 'http://localhost:8000').replace(/\/+$/, ''),

    optimizeFor: c.get('clike.optimizeFor', 'capability'),

    // policy apply
    requireCleanGit: c.get('clike.apply.requireCleanGit', false),
    backup:          c.get('clike.apply.backup', true),
    dryRunPreview:   c.get('clike.apply.dryRunPreview', true),

    // git helpers (presenti)
    gitAutoCommit:    c.get('clike.git.autoCommit', true),
    gitCommitMessage: c.get('clike.git.commitMessage', 'clike: apply patch (AI)'),
    gitOpenPR:        c.get('clike.git.openPR', true),

    // toggle AI → mappati su use.ai.*
    useAiDocstring: c.get('clike.useAi.docstring', true),
    useAiRefactor:  c.get('clike.useAi.refactor',  true),
    useAiTests:     c.get('clike.useAi.tests',     false),
    useAiFixErrors: c.get('clike.useAi.fixErrors', false),

    allowRawDiffFallback: c.get('clike.apply.allowRawDiffFallback', false),

    routes
  };
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
    out.appendLine(`[git] commit skip/failed: ${e.message}`);
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
  const editor = getActiveEditorOrThrow();
  const docInfo = documentInfoFromEditor(editor);
  await context.workspaceState.update('clike.lastTargetUri', docInfo.uriStr);

  const { routes } = cfg();
  const o = await getJson(cfg().orchestratorUrl + routes.orchestrator.health);
  const g = await getJson(cfg().gatewayUrl + routes.gateway.health);
  console.log("g", g);
  console.log("o", o);
  vscode.window.showInformationMessage(`Health — Orchestrator: ${o.status || 'err'} | Gateway: ${g.status || 'err'}`);
}

async function cmdRagReindex(glob) {
  const routes = (cfg().orchestrator && cfg().orchestrator.routes) || {};
  // preferisci route nuova, altrimenti fallback alla vecchia se l'utente ha set custom
  const url = routes.ragIndex || routes.ragReindex || '/v1/rag/ingest';
  let payload;
  if (typeof glob === 'string' && glob.trim()) {
    payload = { mode: 'glob', glob: glob.trim() };
  } else {
    const ok = await vscode.window.showWarningMessage(
      'This will re-index the whole workspace into RAG. Continue?', { modal: true }, 'Reindex'
    );
    if (ok !== 'Reindex') return;
    payload = { mode: 'full' };
 }
 // (opzionale) namespace di progetto: nome cartella root
 try {
    const ws = vscode.workspace.workspaceFolders && vscode.workspace.workspaceFolders[0];
    if (ws) payload.namespace = ws.name;
 } catch {}
 // invio
 const res = await postOrchestrator(url, payload);
 try {
    vscode.window.showInformationMessage(`RAG index ok: ${res && res.stats ? JSON.stringify(res.stats) : 'submitted'}`);
 } catch {
    vscode.window.showInformationMessage('RAG index request submitted.');
 }
}

async function cmdRagSearch(q) {
  let query = (typeof q === 'string') ? q : '';
  if (!query) {
    query = await vscode.window.showInputBox({ prompt: 'RAG search query' }) || '';
  }
  if (!query.trim()) return;
  const routes = (cfg().orchestrator && cfg().orchestrator.routes) || {};
  const url = routes.ragSearch || '/v1/rag/search';
  const payload = { q: query.trim(), k: 8 };
  try {
    const ws = vscode.workspace.workspaceFolders && vscode.workspace.workspaceFolders[0];
    if (ws) payload.namespace = ws.name;
  } catch {}
  const res = await postOrchestrator(url, payload);
  const hits = (res && res.hits) || [];
  vscode.window.showInformationMessage(`RAG results: ${hits.length}`);
  // manda in webview un riassunto semplice (pannello Text)
  try {
    const lines = hits.slice(0, 10).map((h, i) => {
      const p = (h && h.payload && (h.payload.path || h.payload.file || h.payload.source)) || '(unknown)';
      const s = (h && typeof h.score === 'number') ? h.score.toFixed(3) : '';
      return `${i+1}. ${p}  ${s ? `(score ${s})` : ''}`;
    });
    const summary = `RAG Search: "${query}"\n` + (lines.length ? lines.join('\n') : '(no results)');
    if (panel && panel.webview) {
      panel.webview.postMessage({ type: 'text', text: summary });
    }
  } catch {}
  return res;
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
    const hist = await loadSessionFiltered(s.mode, s.model, 200);
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
  out.appendLine(`activate ${context}`);
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
  registerCommands(context);

  vscode.window.setStatusBarMessage('Clike: orchestrator+gateway integration ready', 2000);
}

function getWebviewHtml(orchestratorUrl) {
  const nonce = String(Math.random()).slice(2);
  return `<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; img-src https: data:; style-src 'unsafe-inline'; script-src 'nonce-${nonce}';">
<meta name="viewport" content="width=device-width, initial-scale=1.0" />
<title>CLike Chat</title>
<style>
  :root{
    --bg:#0f1419; --fg:#e6eaf0; --fg-dim:#aeb8c4;
    --bubble-user:#1f6feb; --bubble-ai:#2d333b;
    --card:#161b22; --border:#30363d; --accent:#58a6ff;
  }
  body { background:var(--bg); color:var(--fg); font-family: ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto; padding:12px; }
  .row { display:flex; gap:8px; align-items:center; margin-bottom:8px; }
  select, input, textarea, button {
    font-size:13px; background:#0b0f14; color:var(--fg);
    border:1px solid var(--border); border-radius:6px; padding:6px 8px;
  }
    #clikeHelpOverlay {
    position: fixed; inset: 0; background: rgba(0,0,0,.6);
    display: none; z-index: 9999; align-items: center; justify-content: center;
  }
  #clikeHelpCard {
    background: var(--vscode-editor-background);
    color: var(--vscode-editor-foreground);
    border: 1px solid var(--vscode-panel-border);
    border-radius: 8px; max-width: 720px; width: 92%; max-height: 80vh; overflow: auto;
    box-shadow: 0 10px 30px rgba(0,0,0,.35); padding: 16px; line-height: 1.4;
  }
  #clikeHelpCard h2 { margin: 0 0 8px 0; font-size: 18px; }
  #clikeHelpCard code { background: var(--vscode-editorHoverWidget-background); padding: 2px 6px; border-radius: 6px; }
  #clikeHelpClose { float: right; cursor: pointer; }
  #clikeHelpList li { margin: 6px 0; }
  .chip { display:inline-block; padding:2px 6px; border-radius:10px; border:1px solid #ccc; cursor:pointer; user-select:none; }
  #attach-toolbar { position:relative; } /* per l’absolute del menu */
  button { cursor:pointer; }
  textarea { width:100%; min-height:80px; }
  .toolbar { display:flex; gap:8px; align-items:center; }
  #status { margin-left:auto; opacity:.7; }
  .spinner { display:none; margin-left:8px; }
  .spinner.active { display:inline-block; animation: spin 1s linear infinite; }
  @keyframes spin { from {transform:rotate(0)} to {transform:rotate(360deg)} }

  .chat { border:1px solid var(--border); border-radius:8px; padding:10px; background:var(--card); height:260px; overflow:auto; }
  .msg { margin:8px 0; display:flex; }
  .msg.user { justify-content:flex-end; }
  .bubble { max-width:78%; padding:10px 12px; border-radius:14px; white-space:pre-wrap; word-break:break-word; }
  .user .bubble { background:var(--bubble-user); color:white; border-top-right-radius:4px; }
  .ai .bubble { background:var(--bubble-ai); color:var(--fg); border-top-left-radius:4px; }
  .meta { font-size:11px; opacity:.7; margin-top:3px; }
  .badge { display:inline-block; font-size:10px; padding:2px 6px; border-radius:10px; border:1px solid var(--border); margin-right:6px; background:#0b0f14; color:var(--fg-dim); }

  .tabs { margin-top:10px; display:flex; gap:6px; }
  .tab { padding:6px 10px; border:1px solid var(--border); border-bottom:none; cursor:pointer; border-top-left-radius:6px; border-top-right-radius:6px; }
  .tab.active { background:var(--card); }
  .panel { border:1px solid var(--border); padding:8px; min-height: 150px; background:var(--card); }
  pre { white-space: pre-wrap; word-wrap: break-word; }
</style>
</head>
<body>
  <div class="row toolbar">
    <label>Mode</label>
    <select id="mode">
      <option value="free">free (Q&A)</option>
      <option value="harper">harper</option>
      <option value="coding">coding</option>
    </select>
     <button id="helpBtn" title="Slash help" style="margin-left:4px;"><span id="botBadge" class="badge" style="display:none">🤖</span></button>
    <label>Model</label>
    <select id="model"></select>
    <button id="refresh">↻ Models</button>
    <button id="clear">Clear Session</button>

    <label class="ctl">
      Scope
      <select id="historyScope">
        <option value="singleModel">Model</option>
        <option value="allModels">All models</option>
      </select>
    </label>
    <span id="status">Ready</span>
    <span id="sp" class="spinner">⏳</span>
  </div>

  <div id="chat" class="chat" aria-label="Chat transcript"></div>

  <div class="row">
    <textarea id="prompt" placeholder="Type your prompt..."></textarea>
  </div>
  <!-- Toolbar allegati -->
  <div id="attach-toolbar" style="display:flex; gap:6px; align-items:center;">
    <button id="btnAttach" title="Allega file">📎 Attach</button>
    <div id="attach-menu" style="display:none; position:absolute; margin-top:28px; padding:6px; border:1px solid #ccc; background:#fff; z-index:10;">
      <button id="attach-menu-ws">+ Workspace files</button>
      <button id="attach-menu-ext" style="margin-left:6px;">+ External files</button>
    </div>
    <div id="attach-chips" style="margin-left:8px; display:flex; flex-wrap:wrap; gap:6px;"></div>
  </div>
  <div class="row">
    <button id="sendChat">Send (free)</button>
    <button id="sendGen">Generate (harper/coding)</button>
    <button id="apply" disabled>Apply</button>
    <button id="cancel" disabled>Cancel</button>
  </div>

  <div class="tabs">
    <div class="tab active" data-tab="text">Text</div>
    <div class="tab" data-tab="diffs">Diffs</div>
    <div class="tab" data-tab="files">Files</div>
  </div>

  <div class="panel" id="panel-text" style="height:280px;overflow:auto;">
    <pre id="text"></pre>
  </div>
  <div class="panel" id="panel-diffs" style="display:none;"><pre id="diffs"></pre></div>
  <div class="panel" id="panel-files" style="display:none;"><pre id="files"></pre></div>

<script nonce="${nonce}">
const vscode = acquireVsCodeApi();
// segnala all'estensione che la webview è pronta a ricevere messaggi
try { 
  vscode.postMessage(
    { type: 'webview_ready',ts: Date.now() }
  );
} catch (e) {}
 // --- Help overlay (/help) ---
var HELP_COMMANDS = [
  {cmd:'/help', desc:'Shows this quick guide'},
  {cmd:'/init <name> [--path <abs>] [--force]', desc:'Initializes the Harper project in the workspace'},
  {cmd:'/status', desc:'Shows the Harper project/context status'},
  {cmd:'/where', desc:'Shows the Harper workspace/doc-root path'},
  {cmd:'/switch <name|path>', desc:'Switches to another Harper project'},
  {cmd:'/spec [file|testo]', desc:'Generates/Updates SPEC.md from the IDEA'},
  {cmd:'/plan [spec_path]', desc:'Generates/Updates PLAN.md from the SPEC'},
  {cmd:'/kit [spec] [plan]', desc:'Generates/Updates KIT.md'},
  {cmd:'/build [n]', desc:'Applies a batch of TODOs from the PLAN; produces diffs & tests (Harper)'},
  {cmd:'/finalize [--tag vX.Y.Z] [--archive]', desc:'Final gates and project closure (Harper)'},
  {cmd:'/rag <query>', desc:'Cerca nel RAG (mostra i top risultati) (cross)'},
  {cmd:'/rag +<N>', desc:'Adds RAG result #N from the last search to the attached files (cross)'},
  {cmd:'/rag list', desc:'Shows current attached files (inline+RAG) (cross).'},
  {cmd:'/rag clear', desc:'Svuota gli allegati correnti (cross)'},
  { cmd: '/ragIndex [glob]', desc: 'Manually indexes into the RAG. Examples:/ragIndex docs/**/*.md  |  /ragIndex **/*' },
  { cmd: '/ragSearch <query>', desc: 'Searches the RAG (shows top results) (cross).' },
  { cmd: '/eval <spec|plan|kit|finalize>', desc: 'Performs an eval of spec/plan/kit/finalize' },
  { cmd: '/gate <spec|plan|kit|finalize>', desc: 'Performs a gate of spec/plan|kit|finalize' },
  { cmd: '/syncConstraints [path] — sync', desc: 'Syncs Technology Constraints from IDEA/SPEC, regenerates canonical JSON' },
  { cmd: '/planUpdate <REQ-ID> [runs/.../eval/kit.report.json]', desc: 'Check off the PLAN item after a passing KIT eval' }
];

// --- bootstrap sync: seleziona modello SOLO quando tutto è pronto ---
const boot = { gotInit:false, gotModels:false, gotHydrate:false, done:false, savedModel:null };
// Ultimi risultati di /rag per consentire /rag +N
let lastRagHits = [];

function finalizeBootIfReady() {
  if (boot.done) return;
  // Aspetta TUTTO: stato iniziale + modelli + prima hydrate
  if (!(boot.gotInit && boot.gotModels && boot.gotHydrate)) return;

  // Elenco modelli disponibili nella combo
  const names = Array.from(model.options).map(o => o.value);

  // Scelta definitiva:
  // 1) savedModel se esiste e non è 'auto'
  // 2) 'llama3' se disponibile
  // 3) 'auto' se disponibile
  // 4) primo della lista
  let pick = null;
  if (boot.savedModel && boot.savedModel !== 'auto' && names.includes(boot.savedModel)) {
    pick = boot.savedModel;
  } else if (names.includes('llama3')) {
    pick = 'llama3';
  } else if (names.includes('auto')) {
    pick = 'auto';
  } else {
    pick = names[0] || '';
  }

  if (pick && model.value !== pick) {
    model.value = pick;
    updateBotBadge();
  }

  // 🔁 Rehydrate FINALE coerente con ciò che vede l’utente (mode+model correnti)
  // Non affidiamoci al timing degli eventi precedenti: chiediamo noi stessi l’idratazione coerente.
  vscode.postMessage({ type: 'uiChanged', mode: mode.value, model: model.value });

  boot.done = true;
}


function ensureHelpDOM() {
  // overlay container
  var overlay = document.getElementById('clikeHelpOverlay');
  if (!overlay) {
    overlay = document.createElement('div');
    overlay.id = 'clikeHelpOverlay';
    overlay.style.position = 'fixed';
    overlay.style.inset = '0';
    overlay.style.display = 'none';
    overlay.style.zIndex = '99999';
    overlay.style.background = 'rgba(0,0,0,.35)';
    document.body.appendChild(overlay);
  } else {
    // se qualcuno ha messo del testo dentro, pulisci
    overlay.innerHTML = '';
  }

  // card
  var card = document.createElement('div');
  card.id = 'clikeHelpCard';
  card.style.maxWidth = '720px';
  card.style.margin = '10vh auto';
  card.style.background = '#111';
  card.style.color = '#eee';
  card.style.borderRadius = '12px';
  card.style.padding = '16px 18px';
  card.style.boxShadow = '0 8px 32px rgba(0,0,0,.45)';
  card.style.fontFamily = 'ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, Arial';

  // close button
  var btn = document.createElement('button');
  btn.id = 'clikeHelpClose';
  btn.setAttribute('aria-label', 'Close');
  btn.textContent = '×';
  btn.style.float = 'right';
  btn.style.fontSize = '18px';
  btn.style.width = '32px';
  btn.style.height = '32px';
  btn.style.border = 'none';
  btn.style.borderRadius = '6px';
  btn.style.background = '#222';
  btn.style.color = '#ddd';
  btn.style.cursor = 'pointer';
  if (!btn._bound) {
    btn._bound = true;
    btn.addEventListener('click', closeHelpOverlay);
  }

  var h2 = document.createElement('h2');
  h2.textContent = 'CLike — Quick help';
  h2.style.margin = '0 0 12px 0';
  h2.style.fontSize = '18px';

  var ul = document.createElement('ul');
  ul.id = 'clikeHelpList';
  ul.style.margin = '8px 0 0 0';
  ul.style.paddingLeft = '20px';
  ul.style.lineHeight = '1.35';

  card.appendChild(btn);
  card.appendChild(h2);
  card.appendChild(ul);
  overlay.appendChild(card);
}

function openHelpOverlay() {
  ensureHelpDOM();
  try { renderHelpList(); } catch {}
  var overlay = document.getElementById('clikeHelpOverlay');
  if (overlay) overlay.style.display = 'block';
}

function closeHelpOverlay() {
  var overlay = document.getElementById('clikeHelpOverlay');
  if (overlay) overlay.style.display = 'none';
}


function bindHelpHandlersOnce() {
  const btn = document.getElementById('clikeHelpClose');
  if (!btn || btn._bound) return;
  btn._bound = true;
  btn.addEventListener('click', closeHelpOverlay);
}



// Defer fino a DOM pronto (idempotente)
(function safeInit() {
  const run = () => { ensureHelpDOM(); bindHelpHandlersOnce(); };
  try { updateBotBadge(); } catch {}
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => run(), { once: true });
  } else {
    run();
  }
})();

// Shortcut tastiera (non blocca se overlay non esiste)
document.addEventListener('keydown', (ev) => {
  if ((ev.ctrlKey || ev.metaKey) && ev.key === '/') {
    ev.preventDefault();
    openHelpOverlay();
  }
});




const attachmentsByMode = { free: [], harper: [], coding: [] };
function currentMode() { return document.getElementById('mode').value; }
function currentModel() { return document.getElementById('model').value; }
function ensureBucket(mode) {
  if (!attachmentsByMode[mode]) attachmentsByMode[mode] = [];
  return attachmentsByMode[mode];
}

function renderAttachmentChips() {
  const wrap = document.getElementById('attach-chips');
  if (!wrap) return;
  const list = ensureBucket(currentMode());

  wrap.innerHTML = list.map(function(a, i) {
    const nm = a && (a.name || a.path || a.id) ? (a.name || a.path || a.id) : 'file';
    // evito caratteri speciali non escapati in title/text
    const safe = String(nm).replace(/"/g, '&quot;');
    return '<span class="chip" data-i="' + i + '" title="' + safe + '">' + safe + ' ✕</span>';
  }).join(' ');

  // Event delegation (un solo listener, attaccato una sola volta)
  if (!wrap._delegated) {
    wrap._delegated = true;
    wrap.addEventListener('click', (ev) => {
      const el = ev.target.closest('.chip');
      if (!el) return;
      const idx = Number(el.dataset.i);
      const bucket = ensureBucket(currentMode());
      if (Number.isFinite(idx) && idx >= 0 && idx < bucket.length) {
        bucket.splice(idx, 1);
        renderAttachmentChips();
      }
    });
  }
}
// Non-bloccante: apri un piccolo "menu" in-page
let _attachMenuOpen = false;

async function vscodeApiPick() {
  const menu = document.getElementById('attach-menu');
  if (!menu) return;
  _attachMenuOpen = !_attachMenuOpen;
  menu.style.display = _attachMenuOpen ? 'block' : 'none';
}

// Hook dei bottoni del mini-menu (una sola volta)
(function initAttachMenuOnce(){
  const menu = document.getElementById('attach-menu');
  if (!menu) return; // l'HTML viene creato altrove; se non c'è, no-op
  const btnWs  = document.getElementById('attach-menu-ws');
  const btnExt = document.getElementById('attach-menu-ext');
  if (btnWs && !btnWs._bound) {
    btnWs._bound = true;
    btnWs.addEventListener('click', ()=>{
      _attachMenuOpen = false;
      menu.style.display = 'none';
      vscode.postMessage({ type:'pickWorkspaceFiles' });
    });
  }
  if (btnExt && !btnExt._bound) {
    btnExt._bound = true;
    btnExt.addEventListener('click', ()=>{
      _attachMenuOpen = false;
      menu.style.display = 'none';
      vscode.postMessage({ type:'pickExternalFiles' });
    });
  }
})();

function escapeHtml(s){
  return String(s||'').replace(/[&<>"']/g, m => ({
    '&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'
  }[m]));
}

function appendCitationsMeta(container, cits) {
  try {
    if (!Array.isArray(cits) || !cits.length) return;
    const meta = document.createElement('div');
    meta.className = 'meta';
    const label = document.createElement('span');
    label.textContent = 'Sources: ';
    meta.appendChild(label);

    for (var i = 0; i < cits.length; i++) {
      var c = cits[i] || {};
      var title = String(c.title || c.path || c.doc_id || c.chunk_id || c.url || 'source');
      var scoreTxt = (typeof c.score === 'number')
        ? ' (' + (Math.round(c.score * 100) / 100) + ')'
        : '';

      if (c.url && typeof c.url === 'string') {
        var a = document.createElement('a');
        a.href = c.url;
        a.textContent = title;
        a.target = '_blank';
        a.rel = 'noreferrer';
        meta.appendChild(a);
      } else {
        var s = document.createElement('span');
        s.textContent = title;
        meta.appendChild(s);
      }

      if (scoreTxt) {
        var sm = document.createElement('small');
        sm.textContent = scoreTxt;
        meta.appendChild(sm);
      }

      if (i < cits.length - 1) {
        var sep = document.createElement('span');
        sep.textContent = ' · ';
        meta.appendChild(sep);
      }
    }
    container.appendChild(meta);
  } catch (e) {}
}

const el = (id) => document.getElementById(id);
const mode = el('mode');
const model = el('model');
const prompt = el('prompt');
const btnRefresh = el('refresh');
const btnClear = el('clear');
const btnChat = el('sendChat');
const btnGen = el('sendGen');
const btnApply = el('apply');
const btnCancel = el('cancel');
const statusEl = el('status');
const sp = el('sp');
const chat = el('chat');
const preText = el('text');
const preDiffs = el('diffs');
const preFiles = el('files');

let selectedPaths = new Set();
let lastRun = null;

function isInitBubble(b) {
  try {
    if (!b) return false;
    const role = (b.role || '').toLowerCase();
    const text = String(b.text || b.content || '');
    return role === 'system' && /CLike: initialized/i.test(text);
  } catch { return false; }
}

function updateBotBadge() {
  const badge = document.getElementById('botBadge');
  if (!badge) return;
  const isHarper = mode.value === 'harper';
 // badge.style.display = isHarper ? 'inline-block' : 'none';
  badge.style.display = 'inline-block'
  // Placeholder e label pulsanti coerenti
  if (isHarper) {
    prompt.placeholder = 'Harper bot — digita /help per i comandi…';
  } else {
    prompt.placeholder = 'Type your prompt...';
  }
  const c1 = document.getElementById('sendChat');
  const c2 = document.getElementById('sendGen');
  if (c1) c1.textContent = isHarper ? 'Chat (harper)' : 'Send (free)';
  if (c2) c2.textContent = isHarper ? 'Generate (harper)' : 'Generate (coding)';
}

// --- Slash commands ---
function parseSlash(s) {
  const t = String(s || '').trim();
  if (!t.startsWith('/')) return null;

  // Tokenizza: "quoted strings" | 'single quoted' | blocchi non-spazio
  // ATTENZIONE: backslash doppio perché siamo dentro un template string dell'estensione
  const parts = t.match(/"([^"]*)"|'([^']*)'|[^\\s]+/g) || [];
  console.log('text parsed:', t);
  console.log('parts parsed:', parts);
  
  
  const cmd = (parts[0] || '').toLowerCase();
  console.log('cmd parsed:', cmd);

  if (cmd === '/init') {
    console.log('cmd init parsed:');
    const name = parts[1];                       // obbligatorio
    const rest = parts.slice(2);
    const force = rest.includes('--force');
    const pathTokens = rest.filter(x => x !== '--force');
    const pth = pathTokens.length ? pathTokens.join(' ') : undefined;
    console.log('cmd init parsed:', name, rest,force,pth,pathTokens);
    return { cmd, args: { name, path: pth, force } };
  }
  if (cmd === '/eval' || cmd === '/gate'|| cmd === '/syncConstraints' || cmd === '/planUpdate') {
    console.log('cmd evals parsed:', parts);
    const argId = parts[1];   
    return { cmd, args: { arg: argId } };
  }

  // /rag: 4 varianti supportate
  if (cmd === '/rag') {
    // esempi:
    // /rag my query here
    // /rag +3
    // /rag list
    // /rag clear
    const tail = (parts.slice(1) || []).join(' ').trim();
    if (!tail) return { cmd, args: { action: 'help' } };
    // nuovo (safe, senza regex)
    const s = (typeof tail === 'string' ? tail.trim() : '');
    if (s && s[0] === '+') {
      const num = parseInt(s.slice(1), 10);
      if (Number.isFinite(num) && num > 0) {
        return { cmd, args: { action: 'addByIndex', index: num } };
      }
    }
 
    if (/^(list|clear)$/i.test(tail)) {
      return { cmd, args: { action: tail.toLowerCase() } };
    }
    // default → search
    return { cmd, args: { action: 'search', query: tail } };
  }
  
  // …altri comandi slash, se presenti
  return { cmd, args: {} };
}


function getHelpItems() {
  var fallback = HELP_COMMANDS;
  try {
    var g = (typeof window !== 'undefined') ? window.HELP_COMMANDS : undefined;
    if (Array.isArray(g) && g.length) return g;
  } catch {}
  return fallback;
}

function renderHelpList() {
  var ul = document.getElementById('clikeHelpList');
  if (!ul) return;
  var items = getHelpItems();
  // costruiamo li via DOM (no innerHTML necessario, ma va bene anche innerHTML con escape)
  var html = '';
  for (var i = 0; i < items.length; i++) {
    var it = items[i] || {};
    var c = it && it.cmd ? String(it.cmd) : '';
    if (!c) continue;
    var d = it && it.desc ? String(it.desc) : '';
    html += '<li><code>' + escapeHtml(c) + '</code> - ' + escapeHtml(d) + '</li>';
  }
  ul.innerHTML = html;
}


function getHelpListSafe() {
  try {
    var maybe = (typeof window !== 'undefined') ? window.HELP_COMMANDS : undefined;
    if (Array.isArray(maybe) && maybe.length) return maybe;
  } catch (e) { /* ignore */ }
  return HELP_COMMANDS;
}

function handleSlash(slash) {
  if (!slash) return;
  // dry 'Text' and 'Diffs' panels
  try { clearTextPanel(); clearDiffsPanel(); clearFilesPanel(); } catch {}
  try { prompt.value = ''; } catch {}
  const slashCmd = slash.cmd.toLowerCase();

  // help: open overlay local
  if (slashCmd === '/help') {
    var items = getHelpListSafe();
    var listText = '';
    try {
      // Prendi una lista sicura: prima window.HELP_COMMANDS, altrimenti fallback locale
      var items;
      try {
        items = (typeof window !== 'undefined' && Array.isArray(window.HELP_COMMANDS))
          ? window.HELP_COMMANDS
          :  [];
      } catch (e0) {
        items = (typeof HELP_COMMANDS !== 'undefined' && Array.isArray(HELP_COMMANDS)) ? HELP_COMMANDS : [];
      }
      // Normalizza in un vero array senza toccare .length di oggetti strani
      var arr;
      try {
        if (Array.isArray(items)) {
          arr = items.slice(0);
        } else if (items && typeof items.length === 'number') {
          // Array-like
          arr = Array.prototype.slice.call(items);
        } else {
          arr = [];
        }
      } catch (e1) {
        arr = [];
      }
      // Costruisci il testo in modo sicuro (no em dash, niente backtick)
      var buf = [];
      for (var i = 0, n = (arr && arr.length) ? arr.length : 0; i < n; i++) {
        var it = arr[i] || {};
        var cmd  = (it && typeof it.cmd  === 'string') ? it.cmd  : '';
        var desc = (it && typeof it.desc === 'string') ? it.desc : '';
        if (!cmd) continue;
        buf.push(cmd + ' - ' + desc);
      }
      listText = buf.join('\\n');
      // Se vuoto, fai fallback
      if (!listText) listText = 'No commands available.';
    } catch (e) {
      listText = 'No commands available.';
    }
    try { openHelpOverlay(); } catch {}
    return;
  }
  if (slashCmd === '/rag') {
    const a = slash.args || {};
    // 1) /rag search
    if (a.action === 'search' && a.query) {
      // Chiedo al lato host di interrogare l’orchestrator
      vscode.postMessage({ type: 'ragSearch', query: a.query, top_k: 8 });
      // bubble utente
      const userCommand = '/rag ' + a.query;

      try { bubble('user', userCommand, (model && model.value) ? model.value : 'auto'); } catch {}
      try { prompt.value = ''; } catch {}
      return true;
    }
    // 2) /rag +N → aggiunge l’N-esimo hit come RAG attachment
    if (a.action === 'addByIndex' && Number.isFinite(a.index)) {
      const idx = a.index - 1;
      const hit = Array.isArray(lastRagHits) ? lastRagHits[idx] : null;
      const index = a.index || 1;
      if (!hit) {
        
        bubble('assistant', "Nessun risultato #"+index+" disponibile. Esegui prima /rag <query>.", "system");
        return true;
      }
      const doc_index = "doc" + index;
      // Normalizza hit → attachment RAG by id|path
      const id    = (hit.id || hit.doc_id || null);
      const path = (hit.path || hit.source_path || null);
      const name = hit.title || path || id || doc_index;  
      const bucket = attachmentsByMode[currentMode()] || [];
      bucket.push({ origin:'rag', id, path, name });
      attachmentsByMode[currentMode()] = bucket;
      renderAttachmentChips();
      bubble('assistant', "📎 Aggiunto: "+ name, 'system');
      return true;
    }
    // 3) /rag list → mostra gli allegati correnti
    if (a.action === 'list') {
      const list = attachmentsByMode[currentMode()] || [];
      const lines = list.map(function(x,i){
      const nameOrId = x.name || x.path || x.id || 'file';
      const idSuffix = x.id ? ' (id)' : '';
      const pathSuffix = x.path ? ' (path)' : '';
      return (i + 1) + '. ' + nameOrId + idSuffix + pathSuffix;
    });
      bubble('assistant', lines.length ? "Allegati:<br/>"+ lines.join('<br/>') : 'Nessun allegato.', 'system');
      return true;
    }
    // 4) /rag clear → svuota allegati
    if (a.action === 'clear') {
      attachmentsByMode[currentMode()] = [];
      renderAttachmentChips();
      bubble('assistant', 'Allegati svuotati.', 'system');
      return true;
    }
    // help/fallback
    bubble('assistant', 'Uso: /rag <query> | /rag +N | /rag list | /rag clear', 'system');
    return true;
  }

  if (slashCmd === '/init') {
    // mappa su handler host esistente (harperInit)
    vscode.postMessage({ type: 'harperInit', name: slash.args.name || '', path: slash.args.path || '', force: !!slash.args.force });
    return;
  }
  //EVALS
  if (slashCmd === '/eval' || slashCmd === '/gate' || slashCmd === '/syncconstraints' || slashCmd === '/planupdate') {
    // mappa su handler host esistente (eval)
    var atts = [];
    try {
      if (typeof attachmentsByMode !== 'undefined' && attachmentsByMode && attachmentsByMode[key]) {
        atts = attachmentsByMode[key].slice(0);
      }
    } catch {}    
    try { bubble('user', slash.cmd + (slash.args.arg ? (' ' + slash.args.arg) : ''), (model && model.value) ? model.value : 'auto', atts); } catch {}

    vscode.postMessage({ type: 'harperEvals', cmd: slash.cmd.slice(1), argument: slash.args.arg || '' });
    return;
  }
  
  // --- RAG: /ragIndex [glob], /ragSearch <query>
  try {
    var typed = (typeof prompt !== 'undefined' && prompt && typeof prompt.value === 'string') ? prompt.value : '';
    var cmdLower = (slash.cmd || '').toLowerCase();
    if (cmdLower === '/ragindex') {
      var gl = (typed || '').slice(slash.cmd.length).trim(); // tutto quello dopo /ragIndex
      vscode.postMessage({ type: 'ragIndex', glob: gl || '' });
      try { bubble('user', slash.cmd + (gl ? (' ' + gl) : ''), (model && model.value) ? model.value : 'auto'); } catch {}
      try { prompt.value = ''; } catch {}
      return;
    }
    if (cmdLower === '/ragsearch') {
      var q = (typed || '').slice(slash.cmd.length).trim();   // tutto quello dopo /ragSearch
      if (!q && slash.args && slash.args.name) q = String(slash.args.name || '');
      vscode.postMessage({ type: 'ragSearch', q: q || '' });
      try { bubble('user', '/ragSearch ' + (q || ''), (model && model.value) ? model.value : 'auto'); } catch {}
      try { prompt.value = ''; } catch {}
      return;
    }
  } catch (eRagSlash) { console.warn('rag slash err', eRagSlash); }
  if (slash.cmd === '/where') {
    vscode.postMessage({ type: 'where' });
    return;
  }
  if (slash.cmd === '/status') {
    const hs = (document.getElementById('historyScope') || { value: 'singleModel' }).value;
    vscode.postMessage({ type: 'echo', message: 'Mode=' + mode.value + ' | Model=' + model.value + ' | HistoryScope=' + hs });
    return;
  }
  if (slash.cmd === '/switch') {
    vscode.postMessage({ type: 'switchProject', name: slash.args.name || '' });
    return;
  }
  if (slash.cmd === '/spec' || slash.cmd === '/plan' || slash.cmd === '/kit' || slash.cmd === '/build') {
    // attachments della mode corrente (se li usi)
    var modeVal  = (mode  && mode.value)  ? mode.value  : 'harper';
    var key      = modeVal;
    var atts = [];
    try {
      if (typeof attachmentsByMode !== 'undefined' && attachmentsByMode && attachmentsByMode[key]) {
        atts = attachmentsByMode[key].slice(0);
      }
    } catch {}    
    try { bubble('user', slash.cmd + (slash.args.arg ? (' ' + slash.args.arg) : ''), (model && model.value) ? model.value : 'auto', atts); } catch {}
    vscode.postMessage({ type: 'harperRun', cmd: slash.cmd.slice(1), attachments: atts });

    return true;
  }
  
  
  // Fallback: slash non riconosciuto → non invio al modello, mostro help
  try {
    bubble('assistant',
      'Unknown command: ' + slash.cmd + '\\nType /help to see the available commands.',
      'system'
    );
  } catch {}
  try { prompt.focus(); } catch {}
  return;
}

function bubble(role, content, modelName, attachments, ts, opts) {

  attachments = attachments || [];
  const wrap = document.createElement('div');
  wrap.className = 'msg ' + (role === 'user' ? 'user' : 'ai');
  
  const b = document.createElement('div');
  b.className = 'bubble';
  const dt = ts ? new Date(ts) : new Date();
  const timeStr = dt.toLocaleString();
  const badge = (role === 'assistant' && modelName)
    ? '<span class="badge">' + escapeHtml(modelName) + '</span>' 
  : '';
   const meta = '<div class="meta">⏱ ' + escapeHtml(timeStr) + '</div>';
  b.innerHTML = meta + badge + escapeHtml(String(content || ''));
  
  // se utente ha allegati → riga meta con 📎
  if (role === 'user' && attachments.length) {
    const meta = document.createElement('div');
    meta.className = 'meta';
    meta.textContent = '📎 ' + attachments
      .map(a => a && (a.name || a.path || a.id) ? (a.name || a.path || a.id) : 'file')
      .join(', ');
    b.appendChild(meta);
  }

  // RAG badge + Citations (se presenti)
  try {
    opts = opts || {};
    if (opts.ragUsed) {
      const m = document.createElement('div');
      m.className = 'meta';
      m.textContent = '🔎 RAG context used';
      b.appendChild(m);
    }
    if (Array.isArray(opts.citations) && opts.citations.length) {
      appendCitationsMeta(b, opts.citations);
    }
  } catch {}

  wrap.appendChild(b);
  chat.appendChild(wrap);
  chat.scrollTop = chat.scrollHeight;
}


function setBusy(on) {
  [btnChat, btnGen, btnApply, btnRefresh, btnClear].forEach(b => b.disabled = !!on);
  btnCancel.disabled = !on;
  sp.classList.toggle('active', !!on);
  statusEl.textContent = on ? 'Waiting response…' : 'Ready';
}
function post(type, payload={}) { vscode.postMessage({type, ...payload}); }
function setTab(name) {
  document.querySelectorAll('.tab').forEach(t => t.classList.toggle('active', t.dataset.tab === name));
  document.getElementById('panel-text').style.display = name==='text' ? 'block':'none';
  document.getElementById('panel-diffs').style.display = name==='diffs' ? 'block':'none';
  document.getElementById('panel-files').style.display = name==='files' ? 'block':'none';
}
function clearTextPanel() {
  // svuota il contenuto del tab Text e selezionalo
  preText.textContent = '';
  setTab('text');
}
function clearDiffsPanel() {
  // svuota il contenuto del tab Diffs e selezionalo
  preDiffs.textContent = '';
  setTab('diffs');
}
function clearFilesPanel() {
  // svuota il contenuto del tab Fils e selezionalo
  preFiles.innerHTML = '';
}
document.querySelectorAll('.tab').forEach(t => t.addEventListener('click', () => setTab(t.dataset.tab)));

mode.addEventListener('change', ()=>{
  updateBotBadge();
  post('uiChanged', { mode: mode.value, model: model.value });
});

model.addEventListener('change', ()=> post('uiChanged', { mode: mode.value, model: model.value }));
btnRefresh.addEventListener('click', ()=> post('fetchModels'));
btnClear.addEventListener('click', () => {
  vscode.postMessage({
    type: 'clearSession',
    mode: currentMode(),
    model: document.getElementById('model').value || 'auto'
  });
});
function summarizeAttachments(inlineFiles = [], ragFiles = []) {
  const inl = (inlineFiles || []).map(f => ({
    type: 'inline',
    name: f.name || f.path || 'file',
    path: f.path || null,
    size: f.size || null
  }));
  const rag = (ragFiles || []).map(f => ({
    type: 'rag',
    name: f.name || f.path || ('doc_' + (f.id || '')),
    id:   f.id || null,
    size: f.size || null
  }));
  return [...inl, ...rag];
}
(function bindAttachOnce(){
  const btn = document.getElementById('btnAttach');
  if (btn && !btn._bound) {
    btn._bound = true;
    btn.addEventListener('click', ()=> { vscodeApiPick(); });
  }
})();

function inferProvider(modelName) {
  const n = String(modelName||'').toLowerCase();
  if (n.startsWith('gpt')) return 'openai';
  if (/(llama|ollama|codellama|mistral|mixtral|phi|qwen|deepseek|granite|yi|gemma|llava)/.test(n)) return 'ollama';
  if(n.startsWith('anthropic')) return 'anthropic';
  if(n.startsWith('vllm')) return 'vllm';
  return 'openai'; // fallback conservativo
}


btnChat.addEventListener('click', ()=>{
  console.log('[webview] sendChat click');
  const text = prompt.value;
  if (!text.trim()) return;
  const slash = parseSlash(text);
  console.log('CMD', slash?.cmd);
  console.log('ARG', slash?.args);

  if (slash) {        // <-- SLASH → non è una chat normale
    handleSlash(slash);
    prompt.value = '';
    return;
  }
  const atts = attachmentsByMode[mode.value] ? [...attachmentsByMode[mode.value]] : [];

  bubble('user', text,model.value, atts);
  setBusy(true);
  prompt.value = '';
  clearTextPanel();        // <— svuota tab Text
  clearDiffsPanel();        // <— svuota tab Diffs
  clearFilesPanel();        // <— svuota tab Files
  const selectedOpt = model.options[model.selectedIndex];
  const _provider = (selectedOpt && selectedOpt.dataset && selectedOpt.dataset.provider) || inferProvider(model.value);
  post('sendChat', { mode: mode.value, model: model.value, provider:_provider, prompt: text, attachments: atts });
  attachmentsByMode[currentMode()] = [];
  renderAttachmentChips();
  });

btnGen.addEventListener('click', ()=>{
  console.log('[webview] sendGen click');

  const text = prompt.value;
  const slash = parseSlash(text);
  if (slash) {
    handleSlash(slash);
    prompt.value = '';
    return;
  }
  const m = (mode.value === 'free') ? 'coding' : mode.value;   // /v1/generate vuole coding/harper

  const atts = attachmentsByMode[m] ? [...attachmentsByMode[m]] : [];
  const selectedOpt = model.options[model.selectedIndex];
  const _provider = (selectedOpt && selectedOpt.dataset && selectedOpt.dataset.provider) || inferProvider(model.value);
  
  if (!text.trim()) return;
  bubble('user', text,model.value, atts);
  setBusy(true);
  prompt.value = '';
  clearTextPanel();        // <— svuota tab Text
  clearDiffsPanel();        // <— svuota tab Diffs
  clearFilesPanel();        // <— svuota tab Files
  setTab('diffs');

  post('sendGenerate', { mode: m, model: model.value, provider:_provider, prompt: text, attachments: atts });
  attachmentsByMode[currentMode()] = [];
  renderAttachmentChips();
});
btnApply.addEventListener('click', ()=>{
  console.log('[webview] apply click', lastRun);
  
  if (!lastRun) return;
  clearTextPanel();
  clearDiffsPanel();
  clearFilesPanel();

  const paths = Array.from(selectedPaths);
  const selection = paths.length > 0 ? { paths } : { apply_all: true };
  setBusy(true);
  post('apply', { run_dir: lastRun.run_dir, audit_id: lastRun.audit_id, selection });
});
btnCancel.addEventListener('click', ()=> post('cancel'));

window.addEventListener('message', (event) => {
  const msg = event.data;
  if (msg.type === 'openHelpOverlay') { renderHelpList(); openHelpOverlay(); }
  // Echo → mostra un bubble "assistant" (anche per i riepiloghi post-init)
  if (msg.type === 'echo') {
    console.log('[webview] echo', msg);
    const text = String(msg.message || '');
    try { bubble('assistant', text, 'system'); } catch (e) { console.warn('[webview] bubble echo failed', e); }
    const pre = document.getElementById('text');
    if (pre) pre.textContent = text;
    return;
  }

  if (msg.type === 'busy') { setBusy(!!msg.on); return; }
  if (msg.type === 'initState' && msg.state) {
    const hs = (msg.state && msg.state.historyScope) || 'singleModel';
    const sel = document.getElementById('historyScope');
    if (sel) {
      if (!sel._bound) {
        sel._bound = true;
        sel.addEventListener('change', () => {
          const value = sel.value === 'allModels' ? 'allModels' : 'singleModel';
          vscode.postMessage({ type: 'setHistoryScope', value });
        });
      }
      sel.value = hs;
    }
    
    if (msg.state.mode)  mode.value  = msg.state.mode;
    if (msg.state.model) model.value = msg.state.model;
    
    const helpBtn = document.getElementById('helpBtn');
    if (helpBtn && !helpBtn._bound) {
      helpBtn._bound = true;
      helpBtn.addEventListener('click', ()=>{
       // renderHelpList();
        openHelpOverlay();
      });
    }
    try { updateBotBadge(); } catch {}
    boot.gotInit = true;
    boot.savedModel = (msg.state && msg.state.model) || null;
    finalizeBootIfReady();
      
  }
  if (msg.type === 'attachmentsCleared') {
    const m = msg.mode || currentMode();
    attachmentsByMode[m] = [];
    renderAttachmentChips();
  }

  if (msg.type === 'hydrateSession' && Array.isArray(msg.messages)) {
    chat.innerHTML = '';
    for (const m of msg.messages) 
      bubble(m.role, m.content, m.model, m.attachments || [], m.ts);
    boot.gotHydrate = true;
    finalizeBootIfReady();

  }

  if (msg.type === 'models') {
    const prev = model.value || '';
    console.log("models-->prev", prev);
    model.innerHTML = '';
    (msg.models||[]).forEach(m=>{
      const name = (typeof m === 'string') ? m : (m.name || m.id || m.model || 'unknown');
      console.log("models-->name", name);
      const provider = (typeof m === 'string')
        ? inferProvider(name)
        : (m.provider || 'unknown');
      const o = document.createElement('option');
      o.value = name; // il value resta il nome modello
      //o.textContent = (provider && provider !== 'unknown') ? (provider + ':' + name) : name;
      o.textContent = name;
     
      o.dataset.provider = provider; // <-- portiamo il provider nella option
      // LA NUOVA CONDIZIONE QUI:
      if (name === prev) {
        o.selected = true;
      }
      model.appendChild(o);
    });
    boot.gotModels = true;
    finalizeBootIfReady();
  }
  
  
  if (msg && msg.type === 'attachmentsAdded') {
    const bucket = ensureBucket(currentMode());
    const incoming = Array.isArray(msg.attachments) ? msg.attachments : [];
    for (const a of incoming) {
      // normalizza struttura minima {name?, path?, id?, source?}
      const norm = {
        name: a?.name || a?.path || a?.id || 'file',
        path: a?.path || null,
        id: a?.id || null,
        source: a?.source || (a?.path ? 'workspace' : 'external')
      };
      bucket.push(norm);
    }
    renderAttachmentChips();
  }
  
  if (msg.type === 'chatResult') {
    setBusy(false);
    const modelName = msg.data?.model || model.value || 'auto';
    const text = (msg.data && (msg.data.text || msg.data.content))
      ? (msg.data.text || msg.data.content)
      : JSON.stringify(msg.data, null, 2);
    // Citations & RAG flags dal backend
    var citations = [];
    try {
      var d = msg.data || {};
      if (Array.isArray(d.citations)) citations = d.citations;
      else if (Array.isArray(d.sources)) citations = d.sources;
    } catch {}

    var ragUsed = false;
    
    var attachments = Array.isArray(msg.attachments) ? msg.attachments : [];
    try {
      var d2 = msg.data || {};
      ragUsed = !!(d2.rag_used || (citations && citations.length));
    } catch {}
    if (text) bubble('assistant', text, model.value, attachments, Date.now(), { ragUsed: ragUsed, citations: citations });
    try {
      if (citations && citations.length) {
        var lines = [];
        for (var i = 0; i < citations.length; i++) {
          var c = citations[i] || {};
          var t = String(c.title || c.path || c.doc_id || c.chunk_id || c.url || 'source');
          var u = (c.url && typeof c.url === 'string') ? c.url : '';
          lines.push('- ' + t + (u ? ' <' + u + '>' : ''));
        }
        preText.textContent = String(preText.textContent || "") + "<br/><br/>Sources:<br/>" + lines.join("<br/>");
      }
    } catch {}

    const data = msg.data || {};
    const assistantText = (data.assistant_text || '').trim();
    // immagini (solo image/* con base64) – al massimo 3
    const imgs = (Array.isArray(data.files) ? data.files : []).filter(function (f) {
      return f && typeof f.mime === 'string' && f.mime.indexOf('image/') === 0 && f.content_base64;
    });
    if (Array.isArray(imgs) && imgs.length >0) {
      var html = imgs.slice(0, 3).map(function (f) {
        var src = 'data:' + f.mime + ';base64,' + f.content_base64;
        return '<img src="' + src + '" style="max-width:160px;max-height:120px;margin:4px;border:1px solid #ddd;border-radius:6px"/>';
      }).join('');
       const safeText = String(assistantText || '');
       var testo = safeText? safeText + "<br><br>":''

       bubble('assistant', testo + html, model.value);

    } else if (data.assistant_text && data.assistant_text.trim()) {
      // Mostra in chat del Mode corrente con badge "free" e modelName corrente
      bubble('assistant', data.assistant_text.trim(), /* modelName= */ model.value, /* attachments? */ []);
      // (opzionale) se vuoi forzare la Text tab a riflettere lo stesso testo
      preText.textContent = data.assistant_text.trim();
    }
    lastRun = { run_dir: msg.data?.run_dir, audit_id: msg.data?.audit_id };
    btnApply.disabled = !lastRun?.run_dir && !lastRun?.audit_id;
  }
  if (msg.type === 'generateResult') {
    setBusy(false);
    const data = msg.data || {};
    var genCitations = [];
    var genRagUsed = false;
    try {
      var gd = msg.data || {};
      if (Array.isArray(gd.citations)) genCitations = gd.citations;
      else if (Array.isArray(gd.sources)) genCitations = gd.sources;
      genRagUsed = !!(gd.rag_used || (genCitations && genCitations.length));
    } catch {}

    const summary = Array.isArray(data.files) && data.files.length
      ? 'Generated files:\\n' + data.files.map(f => '- ' + f.path).join('\\n')
      : JSON.stringify(data, null, 2);
    bubble('assistant', summary, model.value, [], Date.now(), { ragUsed: genRagUsed, citations: genCitations });
    
    const assistantText = (data.assistant_text || '').trim();
    
    try {
      if (genCitations && genCitations.length) {
        var glines = [];
        for (var i = 0; i < genCitations.length; i++) {
          var c = genCitations[i] || {};
          var t = String(c.title || c.path || c.doc_id || c.chunk_id || c.url || 'source');
          var u = (c.url && typeof c.url === 'string') ? c.url : '';
          glines.push('- ' + t + (u ? ' <' + u + '>' : ''));
        }
        preText.textContent = String(preText.textContent || '') + '\\n\\nSources:\\n' + glines.join('\\n');
      }
    } catch {}
    // immagini (solo image/* con base64) – al massimo 3
    const imgs = (Array.isArray(data.files) ? data.files : []).filter(function (f) {
      return f && typeof f.mime === 'string' && f.mime.indexOf('image/') === 0 && f.content_base64;
    });
    if (Array.isArray(imgs) && imgs.length >0) {
      var html = imgs.slice(0, 3).map(function (f) {
        var src = 'data:' + f.mime + ';base64,' + f.content_base64;
        return '<img src="' + src + '" style="max-width:160px;max-height:120px;margin:4px;border:1px solid #ddd;border-radius:6px"/>';
      }).join('');
       const safeText = String(assistantText || '');
       var testo = safeText? safeText + "<br><br>":''

       bubble('assistant', testo + html, model.value);

    } else if (data.assistant_text && data.assistant_text.trim()) {
      // Mostra in chat del Mode corrente con badge "coding" e modelName corrente
      bubble('assistant', data.assistant_text.trim(), /* modelName= */ model.value, /* attachments? */ []);
      // (opzionale) se vuoi forzare la Text tab a riflettere lo stesso testo
      preText.textContent = data.assistant_text.trim();
    }
    setTab('diffs');
    preDiffs.textContent = JSON.stringify(data.diffs || [], null, 2);
    // 2) Tab TEXT – mostra anche il "grezzo" dal server se c'è
    if (data.raw || data.text || data.raw_text) {
      preText.textContent = String(data.raw || data.raw_text || data.text || '');
      setTab('text');
    }
    selectedPaths = new Set();
    const files = Array.isArray(data.files) ? data.files : [];
    const lines = files.map(f => {
      const path = f.path;
      const safeId = 'f_' + btoa(path).replace(/=/g,'');
      return '<div class="row">'
        + '<input type="checkbox" class="file-chk" id="' + safeId + '" data-path="' + path + '">'
        + '<label for="' + safeId + '" class="file-open" data-path="' + path + '" style="cursor:pointer;text-decoration:underline;">' + path + '</label>'
        + '</div>';
    });
    preFiles.innerHTML = lines.join('\\n');
    document.querySelectorAll('.file-chk').forEach(chk => {
      chk.addEventListener('change', (e) => {
        const p = e.target.dataset.path;
        if (e.target.checked) selectedPaths.add(p); else selectedPaths.delete(p);
      });
    });
    
    document.querySelectorAll('.file-open').forEach(lbl => {
      lbl.addEventListener('click', () => {
        const p = lbl.dataset.path;
        vscode.postMessage({ type: 'openFile', path: p });
      });
    });
    // salva un ultimo run compatto
    lastRun = { run_dir: data.run_dir, audit_id: data.audit_id };

    // Abilita Apply anche se il server non ha creato un run_dir/audit_id
    // ma ci sono file strutturati da scrivere.
    const canApply = !!(data.run_dir || data.audit_id || (Array.isArray(data.files) && data.files.length));
    btnApply.disabled = !canApply;

  }
  if (msg.type === 'applyResult') {
    setBusy(false);
    setTab('text');
    preText.textContent = "Applied files:\\n" + JSON.stringify(msg.data?.applied || [], null, 2);
  }

  if (msg.type === 'error') {
    setBusy(false);
    const text = 'Error: ' + String(msg.message || 'unknown');
    //try { bubble('assistant', text, 'system'); } catch {}
    const pre = document.getElementById('text');
    if (pre) pre.textContent = text;
    setTab('text');
    return;
  }

});

// init
post('fetchModels');
</script>
<div id="clikeHelpOverlay" role="dialog" aria-modal="true" aria-label="CLike Help">
  <div id="clikeHelpCard">
    <span id="clikeHelpClose">✖</span>
    <h2>CLike — Slash Commands in Harper Mode</h2>
    <ul id="clikeHelpList"></ul>
    <p style="opacity:.8;margin-top:8px">Suggerimento: puoi allegare file dal workspace e usare i comandi <code>/spec</code>, <code>/plan</code>, <code>/kit</code> per il flusso Harper.</p>
  </div>
</div>
</body>
</html>`;
}

async function cmdOpenChat(context) {
  out.appendLine(`cmdOpenChat ${context}`);
  const panel = vscode.window.createWebviewPanel(
    'clikeChat',
    'CLike Chat',
    vscode.ViewColumn.Beside,
    { enableScripts: true, retainContextWhenHidden: true }
  );
  const c = vscode.workspace.getConfiguration();
  const orchestratorUrl = c.get('clike.orchestratorUrl') || 'http://localhost:8080';
  
  panel.webview.html = getWebviewHtml(orchestratorUrl);
  panel.webview.postMessage({ type: 'busy', on: false });
  // Stato iniziale (mode/model)
  const savedState = context.workspaceState.get('clike.uiState') || { mode: 'free', model: 'auto', historyScope:'singleModel' };
  savedState.historyScope= effectiveHistoryScope(context),
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
      : await loadSessionFiltered(modeCur, modelCur, 200).catch(() => []);

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
  await showInitSummaryIfPresent(panel);

  function escapeHtml(s){return s.replace(/[&<>"']/g, m=>({ "&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;","'":"&#39;"}[m]))}

  // Ascolto eventi dalla webview
  panel.webview.onDidReceiveMessage(async (msg) => {
    out.appendLine(`[webview] recv ${msg && msg?.type}`);
    panel.webview.postMessage({ type: 'busy', on: true });

    try {
      const state = context.workspaceState.get('clike.uiState') || { mode:'free', model:'auto', historyScope:'singleModel' };
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

          // scegli la cartella parent
          let parentUri = null;
          if (passedPath) {
            parentUri = vscode.Uri.file(path.resolve(passedPath));
          } else {
            const pick = await vscode.window.showOpenDialog({
              canSelectFiles: false, canSelectFolders: true, canSelectMany: false,
              openLabel: 'Select parent folder for new workspace'
            });
            if (!pick || !pick.length) return;
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
          
          function copyRecursive(src, dest, _name) {
            out.appendLine(`copyRecursive ${src} -> ${dest} ${_name}`);
            if (fsSync.statSync(src).isDirectory()) {
              fsSync.mkdirSync(dest, { recursive: true });
              for (const entry of fsSync.readdirSync(src)) {
                copyRecursive(path.join(src, entry), path.join(dest, entry), _name);
              }
            } else {
              if (fsSync.existsSync(dest) && !force) return;

                // 1. Leggi il contenuto del file
              let content = fsSync.readFileSync(src, 'utf-8');

              // 2. Esegui la sostituzione
              content = content.replace(/\${project.name}/g, _name);
              // 3. Scrivi il nuovo contenuto nel file di destinazione
              fsSync.writeFileSync(dest, content);
              //fs.copyFileSync(src, dest);
            }
          }
          copyRecursive(templatesDir, targetDir, name);

          // file seed
          await writeFileUtf8(path.join(targetDir, '.gitignore'),
              `node_modules/
              dist/
              .vscode/
              .env
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
              '.clike/policy.yaml',
              '.github/CODEOWNERS',
              '.github/pull_request_template.md',
              '.github/worflow/clike-ci.yaml',
              'docs/harper/PLAYBOOK.md',
              'docs/harper/IDEA.md',
              'docs/harper/SPEC.md',
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
        out.appendLine(`[harperRun] inside`);
        try {
          const { cmd, attachments = [] } = msg;
          
          const docRoot = 'docs/harper'; // default; se usi config runtime, leggila qui
          const profileHint = computeProfileHint(state.mode, state.model);
          log(`[harperRun] profileHint ...${profileHint}  ` );
          const activeProvider = (profileHint!=null) ?inferProvider(activeModel) :'';
          log(`[harperRun] activeProvider ....${activeProvider}  `);


          // Core docs per fase
          let core = [];
          if (cmd === 'spec') core = ['IDEA.md'];
          else if (cmd === 'plan') core = ['SPEC.md'];
          else if (cmd === 'kit' || cmd === 'build') core = ['SPEC.md','PLAN.md'];

          // Flags privacy (se già presenti altrove, riusale)
          const flags = {
            neverSendSourceToCloud: !!cfgChat().neverSendSourceToCloud || false,
            redaction: true
          };

          const runId = (Math.random().toString(16).slice(2) + Date.now().toString(16));
          console.log(`[harperRun] runId ...`,  runId);

          const _gen={
            temperature: 0.2,
            max_tokens: 8192,
            top_p: 0.9,
            stop: ["```SPEC_END```"],
            presence_penalty: 0.0,
            frequency_penalty: 0.2,
            seed: 42,
            tools:'',
            remote:'',
            response_format:'',
            tool_choice:''
          }
          console.log(`[harperRun] payload ...`,  JSON.stringify(_gen));

          const payload = {
            cmd,
            mode: state.mode,
            model: state.model,             // 'auto' o esplicito
            profileHint,                    // ← chiave di A3
            docRoot,
            core,
            gen: _gen,
            attachments,
            flags,
            runId,
            historyScope: state.historyScope
          };
          log(`[harperRun] payload ...`,  JSON.stringify(payload));



             // Persisti l’input dell’utente nella sessione del MODE (e mostreremo badge del modello in render)
          await appendSessionJSONL(activeMode, {
            role: 'user',
            content: `▶ ${cmd.toUpperCase()} | mode=${state.mode} model=${state.model} profile=${profileHint || '—'} core=${JSON.stringify(core)}`,
            model:  state.model || 'auto',
            attachments: Array.isArray(msg.attachments) ? msg.attachments : []
          });
          // Echo pre-run
          panel.webview.postMessage({
            type: 'echo',
            message: `▶ ${cmd.toUpperCase()} | mode=${state.mode} model=${state.model} profile=${profileHint || '—'} core=${JSON.stringify(core)} attachments=${attachments.length}`
          });
          
          const _headers = {"Content-Type": "application/json", "X-CLike-Profile": "code.strict"}
          const body = await buildHarperBody('spec', payload, wsRoot());
          if (activeProvider) _headers["X-CLike-Provider"] = activeProvider
          const outGateway = await callHarper(cmd, body, _headers);
          const _out  = outGateway.out;
          log(`[harperRun] body real out ... ${_out}`);

          // 3) POST-RUN: persisti esito (riassunto + eventuale echo/testo)
          const summary = [
            _out?.echo ? `[echo] ${_out.echo}` : null,
            (Array.isArray(_out?.diffs) && _out.diffs.length) ? `[diffs] ${_out.diffs.length}` : null,
            (Array.isArray(_out?.files) && _out.files.length) ? `[files] ${_out.files.length}` : null,
            _out?.text ? `[text] ${Math.min(String(_out.text).length, 200)} chars` : null
          ].filter(Boolean).join(' • ') || 'no artifacts';

          
          await appendSessionJSONL(activeMode, {
            ts: Date.now(),
            role: 'assistant',
            content: `✔ ${String(cmd || '').toUpperCase()} done — ${summary}`,
            model:  state.model || 'auto',
            attachments: Array.isArray(msg.attachments) ? msg.attachments : []
          });
          panel.webview.postMessage({
            type: 'echo',
            message: `✔ ${String(cmd || '').toUpperCase()} done — ${summary}`
          });
        

          // --- SCRITTURA FILES (primary path) ---
          let written = [];
          if (Array.isArray(_out?.files) && _out.files.length) {
            written = await saveGeneratedFiles(_out.files);
          }


          // Diffs
          if (Array.isArray(_out?.diffs) && _out.diffs.length) {
            panel.webview.postMessage({ type: 'diffs', diffs: _out.diffs });
          }
          // 4) UI: inoltra i pezzi alla webview (coerente con free/coding)
          if (_out?.text) {
            panel.webview.postMessage({ type: 'text', text: _out.text });
          }
          // Files (report / artifacts)
          if (Array.isArray(_out?.files) && _out.files.length) {
            panel.webview.postMessage({ type: 'files', files: _out.files });
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
            panel.webview.postMessage({ type: 'error', message: _out.errors.join(' | ') });
          }
        } catch (e) {
          panel.webview.postMessage({ type: 'error', message: (e?.message || String(e)) });
        }
        
        
      }
      //Harper Evals
      if (msg.type === 'harperEvals' ) {
         await appendSessionJSONL(activeMode, {
          role: 'user',
          content: String(msg.cmd || '') + ' ' + String(msg.argument || ''),
          model:  state.model || 'auto',
        });
        var _out
        switch (msg.cmd) {
          case 'eval':
            _out = await handleEval(msg.argument, getWorkspaceRoot() ); 
            break;
          case 'gate': 
            _out = await handleGate(msg.argument, getWorkspaceRoot() );  
            break;
          case 'syncconstraints': 
            _out = await handleSync(msg.argument);  
            break;
          case 'planupdate': 
            _out = await handlePlanUpdate(msg.argument);  
            break;
          // default: break;
        }

       // Persisti l’input dell’utente nella sessione del MODE (e mostreremo badge del modello in render)
        await appendSessionJSONL(activeMode, {
          role: 'assistant',
          content:"🧪 "+ String(_out || ''),
          model:  state.model || 'auto',
        });
        panel.webview.postMessage({ type: 'echo', message: "🧪 " + _out } );
        
        
      } 
     
      if (msg.type === 'ragIndex') {
      // opzionale: msg.glob (stringa). Riusiamo la logica del comando palette.
      try {
        await cmdRagReindex(msg.glob || '');
        panel.webview.postMessage({ type: 'echo', message: 'RAG indexing: request submitted' });
      } catch (e) {
        panel.webview.postMessage({ type: 'echo', message: 'RAG indexing error: ' + String(e && e.message || e) });
      }
      }
     
      // RAG search chiesto dalla webview (/rag <query>)
      if (msg.type === 'ragSearch') {
        try {
          const { routes } = cfg();
          const q = String(msg.query || '').trim();
          const top_k = Number.isFinite(msg.top_k) ? msg.top_k : 8;
          if (!q) throw new Error('Query vuota.');
          const resp = await postOrchestrator(routes.orchestrator.ragSearch, { query: q, top_k });
          if (!resp.ok) {
            panel.webview.postMessage({ type:'error', message: `RAG Search: HTTP ${resp.status}` });
            return;
          }
          const results = (resp.json && (resp.json.hits || resp.json.results)) || [];
          panel.webview.postMessage({ type:'ragResults', results });
        } catch (e) {
          panel.webview.postMessage({ type:'error', message: `RAG Search failed: ${e.message||String(e)}` });
        }
   
      }
      // opzionale utility
      if (msg.type === 'echo') {
        await appendSessionJSONL(state.mode, { role:'assistant', content:String(msg.message||''), model:'system' });
        
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
          const saved = context.workspaceState.get('clike.uiState') || { mode:'free', model:'auto', historyScope:'singleModel' };
          const ui = {
            mode: saved.mode || 'free',
            model: saved.model || 'auto',
            historyScope: (saved.historyScope === 'allModels') ? 'allModels' : 'singleModel'
          };
          // 2) Invia initState alla webview
          panel.webview.postMessage({ type: 'initState', state: ui });
          // 3) Hydrate dei messaggi (non bloccare su errori)
          try {
            const msgs = (ui.historyScope === 'allModels')
              ? await loadSession(ui.mode, 200).catch(() => [])
              : await loadSessionFiltered(ui.mode, ui.model, 200).catch(() => []);
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
              const raw = res.models.map(m => m.name || m.id || m.model || 'unknown');
              models = raw.filter(n => !/embed|embedding|nomic-embed/i.test(n));
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

            panel.webview.postMessage({ type: 'models', models });
            out.appendLine('[CLike] models sent: ' + models.join(', '));
          } catch (e) {
            out.appendLine('[CLike] models fetch failed: ' + (e?.message || String(e)));
            panel.webview.postMessage({ type: 'models', models: ['auto'] });
          }
        } catch (e) {
          out.appendLine('[CLike] webview_ready handler crashed: ' + (e?.message || String(e)));
          // Fallback minimo per non lasciare la webview “vuota�?
          panel.webview.postMessage({ type: 'initState', state: { mode:'free', model:'auto', historyScope:'singleModel' } });
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
          : await loadSessionFiltered(modeCur, modelCur, 200).catch(()=>[]);
        panel.webview.postMessage({ type: 'hydrateSession', messages: msgs });

        // NIENTE initState qui (evita rimbalzi della combo)
        vscode.window.setStatusBarMessage(`CLike: history scope = ${value}`, 2000);
        
      }
      // 1) MODELLI
      if (msg.type === 'fetchModels') {
        const res = await fetchJson(`${orchestratorUrl}/v1/models`);
        let models = [];
        if (Array.isArray(res?.models)) {
          let raw = res.models.map(m => m.name || m.id || m.model || 'unknown');
          const filtered = raw.filter(n => !/embed|embedding|nomic-embed/i.test(n));
          models = filtered.length ? filtered : raw;
        } else if (Array.isArray(res?.data)) {
          let raw = res.data.map(m => m.id || 'unknown');
          const filtered = raw.filter(n => !/embed|embedding|nomic-embed/i.test(n));
          models = filtered.length ? filtered : raw;
        }
        panel.webview.postMessage({ type: 'models', models });
       
      }
      // 2) CAMBIO UI (Mode/Model)
      if (msg.type === 'uiChanged') {
        const prev = context.workspaceState.get('clike.uiState') || { mode: 'free', model: 'auto',  historyScope: 'singleModel' };
        
        // MERGE: non perdere historyScope (e futuri campi)
        const newState = {
          ...prev,
          ...(typeof msg.mode  !== 'undefined' ? { mode:  msg.mode  } : {}),
          ...(typeof msg.model !== 'undefined' ? { model: msg.model } : {})
        };
        await context.workspaceState.update('clike.uiState', newState);

        // Se è cambiato SOLO il modello, NON re-idratare la chat
        if (prev.mode === newState.mode && prev.model !== newState.model) {
          const scope = (newState.historyScope === 'allModels') ? 'allModels' : 'singleModel';
          if (scope === 'singleModel') {
            const modeCur  = newState.mode  || 'free';
            const modelCur = newState.model || 'auto';
            const msgs = await loadSessionFiltered(modeCur, modelCur, 200).catch(() => []);
            panel.webview.postMessage({ type: 'hydrateSession', messages: msgs });
          }
         
        }
        // Se è cambiato il mode (o entrambi), re-idrata in base allo scope
        const scope   = (newState.historyScope === 'allModels') ? 'allModels' : 'singleModel';
        const modeCur = newState.mode || 'free';
        const modelCur= newState.model || 'auto';

        const msgs = (scope === 'allModels')
          ? await loadSession(modeCur).catch(() => [])
          : await loadSessionFiltered(modeCur, modelCur, 200).catch(() => []);

        panel.webview.postMessage({ type: 'hydrateSession', messages: msgs });
       
      }
      // 3) CLEAR SESSION (solo mode corrente)
      if (msg.type === 'clearSession') {
        const st = context.workspaceState.get('clike.uiState') || { mode: 'free', model: 'auto',historyScope: 'singleModel'  };
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
          const msgs = await loadSessionFiltered(modeCur, modelCur, 200).catch(() => []);
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
      // 5) CHAT / GENERATE
      if (msg.type === 'sendChat' || msg.type === 'sendGenerate') {
         // cancel eventuale richiesta precedente
        if (inflightController) { inflightController.abort(); inflightController = null; }
        inflightController = new AbortController();
        panel.webview.postMessage({ type: 'busy', on: true });

        const cur = context.workspaceState.get('clike.uiState') || { mode: 'free', model: 'auto' };
        const activeMode  = msg.mode  || cur.mode  || 'free';
        const activeModel = msg.model || cur.model || 'auto';
        const activeProvider = msg.provider || inferProvider(activeModel);
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
        const { inline_files, rag_files } = partitionAttachments(atts);
        // History del MODE corrente
        const historyScope  = effectiveHistoryScope(context);
        // History per conversazione “stateless�?: carico SOLO le bolle del MODE corrente
        const history = await loadSession(activeMode).catch(() => []);
        // Filtra eventualmente per modello se vuoi inviare solo il sotto-filo di quel model:
        const historyForThisModel = history.filter(b => !b.model || b.model === activeModel);

        const source = (historyScope === 'allModels')
        ? history
        : historyForThisModel;
       
        const messages = source.map(b => ({ role: b.role, content: b.content }));

        // Costruisci payload
        const basePayload = { mode: activeMode, 
            model: activeModel,  
            provider: activeProvider, 
            messages, 
            inline_files, 
            rag_files, 
            attachments: atts 
        };
        const payload = (msg.type === 'sendChat')
          ? basePayload
          : { ...basePayload, max_tokens: 1024 };

        const url = (msg.type === 'sendChat')
          ? `${orchestratorUrl}/v1/chat`
          : `${orchestratorUrl}/v1/generate`;

        try {
          const res = await withTimeout(
            postJson(url, payload, { signal: inflightController.signal }),
            240000
          );

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
              const paths = await saveGeneratedFiles(res.files);
             
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
;
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
          const paths = await saveGeneratedFiles(chosen);
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
        const folders = vscode.workspace.workspaceFolders || [];
        const base = folders.length ? folders[0].uri : undefined;

        const uris = await vscode.window.showOpenDialog({
          canSelectFiles: true, canSelectFolders: false, canSelectMany: true,
          openLabel: 'Attach', defaultUri: base
        });
        if (!uris) {
          panel.webview.postMessage({ type: 'busy', on: false });
          return;
        }

        const MAX_INLINE = 64 * 1024; // 64KB: sopra → RAG by path
        const atts = [];
        for (const uri of uris) {
          try {
            const stat = await vscode.workspace.fs.stat(uri);
            const relPath = base ? vscode.workspace.asRelativePath(uri) : uri.fsPath;

            if (stat.size <= MAX_INLINE) {
              const bytes = await vscode.workspace.fs.readFile(uri);
              atts.push({
                origin: 'workspace',
                name: relPath.split(/[\\/]/).pop(),
                path: relPath,             // utile al server per referenza
                bytes_b64: Buffer.from(bytes).toString('base64')
              });
            } else {
              // grande: passa solo il path → il server far�  RAG
              atts.push({
                origin: 'workspace',
                name: relPath.split(/[\\/]/).pop(),
                path: relPath
              });
            }
          } catch (e) {
            vscode.window.showWarningMessage(`Attach failed: ${e.message}`);
          }
        }
        panel.webview.postMessage({ type: 'attachmentsAdded', attachments: atts });
      }
      if (msg.type === 'pickExternalFiles') {
        const uris = await vscode.window.showOpenDialog({
          canSelectFiles: true, canSelectFolders: false, canSelectMany: true,
          openLabel: 'Attach'
        });
        if (!uris) {
          panel.webview.postMessage({ type: 'busy', on: false });
          return; 
        }

        const atts = [];
        for (const uri of uris) {
          try {
            const bytes = await vscode.workspace.fs.readFile(uri);
            atts.push({
              origin: 'external',
              name: uri.fsPath.split(/[\\/]/).pop(),
              bytes_b64: Buffer.from(bytes).toString('base64')
            });
          } catch (e) {
            vscode.window.showWarningMessage(`Attach failed: ${e.message}`);
          }
        }
        panel.webview.postMessage({ type: 'attachmentsAdded', attachments: atts });
      }
    } catch (err) {
      panel.webview.postMessage({ type: 'error', message: String(err) });
      panel.webview.postMessage({ type: 'busy', on: false });
    }
    panel.webview.postMessage({ type: 'busy', on: false });
  });

  async function showInitSummaryIfPresent(panel) {
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
}
function partitionAttachments(atts) {
  const inline_files = [];
  const rag_files = [];
  for (const a of (atts || [])) {
    // piccolo o gi�  in memoria
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