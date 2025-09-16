// extension.js — Clike Orchestrator+Gateway integration GOOGDDDD
const vscode = require('vscode');
const { applyPatch } = require('diff');
const { exec } = require('child_process');
const https = require('https');
const http = require('http');
const { URL } = require('url');

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

// Helper: mode corrente e modello corrente
const currentMode = () => document.getElementById('mode').value;   // 'free'|'coding'|'harper'
const currentModel = () => document.getElementById('model').value; // es. 'llama3'
const out = vscode.window.createOutputChannel('Clike');

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
    historyScope: c.get('clike.chat.historyScope', 'singleModel') // <-- NEW
  };
}

function effectiveHistoryScope(context) {
  const cfg = vscode.workspace.getConfiguration();
  const def = cfg.get('clike.chat.historyScope', 'singleModel');   // default da settings VS
  const ui = context.workspaceState.get('clike.uiState') || {};
  // Se l'utente ha scelto runtime un override, usalo; altrimenti usa default
  return ui.historyScopeOverride || def;
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
  } catch {  }
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
      ragSearch: '/rag/search',
      ragReindex: '/rag/reindex',
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

/** ---------- APPLY “HARDENED” ---------- */
// FIX: cambia firma — ora accetta (targetUri, newContent, lang?, intent?)
// in passato veniva chiamata per errore con “context”
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
  // FIX: sanifica new_content dal preambolo (“Here is the updated code:”) o blocchi ```
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
  const o = await postOrchestrator(routes.orchestrator.health, {});
  const g = await postGateway(routes.gateway.health, {});
  vscode.window.showInformationMessage(`Health — Orchestrator: ${o.status || 'err'} | Gateway: ${g.status || 'err'}`);
}

async function cmdRagReindex() {
  const { routes } = cfg();
  const confirm = await vscode.window.showWarningMessage('Rindicizzare l’intero progetto?', 'Sì', 'No');
  if (confirm !== 'Sì') return;
  const resp = await postOrchestrator(routes.orchestrator.ragReindex, {});
  if (!resp.ok) return vscode.window.showErrorMessage(`Clike Reindex: HTTP ${resp.status}`);
  vscode.window.showInformationMessage('Clike: RAG reindex avviato.');
}

async function cmdRagSearch() {
  const { routes } = cfg();
  const q = await vscode.window.showInputBox({ placeHolder: 'Prompt/Query RAG', ignoreFocusOut: true });
  if (!q) return;
  const resp = await postOrchestrator(routes.orchestrator.ragSearch, { query: q });
  if (!resp.ok) return vscode.window.showErrorMessage(`Clike RAG Search: HTTP ${resp.status}`);
  const hits = resp.json && (resp.json.hits || resp.json.results || []);
  const items = (Array.isArray(hits) ? hits : [hits]).map((h, i) => ({
    label: h.title ? `${i + 1}. ${h.title}` : `${i + 1}. result`,
    detail: (h.score != null ? `score=${h.score} ` : '') + (h.path || h.id || '')
  }));
  await vscode.window.showQuickPick(items.length ? items : [{ label: 'Nessun risultato' }], { placeHolder: 'RAG Results' });
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

async function cmdPing() { vscode.window.showInformationMessage('Clike: extension alive and well.'); }

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
    <label>Model</label>
    <select id="model"></select>
    <button id="refresh">↻ Models</button>
    <button id="clear">Clear Session</button>

    <label class="ctl">
      History scope
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
const HELP_COMMANDS = [
  {cmd:'/help', desc:'Mostra questa guida rapida'},
  {cmd:'/init <name> [--path <abs>] [--force]', desc:'Inizializza il progetto Harper nel workspace'},
  {cmd:'/status', desc:'Mostra stato progetto/contesto'},
  {cmd:'/where', desc:'Mostra percorso del workspace/doc-root'},
  {cmd:'/switch <name|path>', desc:'Passa ad un altro progetto'},
  {cmd:'/spec [file|testo]', desc:'Genera/Aggiorna SPEC.md dalla IDEA'},
  {cmd:'/plan [spec_path]', desc:'Genera/Aggiorna PLAN.md dallo SPEC'},
  {cmd:'/kit [spec] [plan]', desc:'Genera/Aggiorna KIT.md'},
  {cmd:'/build [n]', desc:'Applica batch di TODO dal PLAN; produce diff & test'},
  {cmd:'/finalize [--tag vX.Y.Z] [--archive]', desc:'Esegue i gate finali e chiude il progetto'}
];
function openHelpOverlay(){
  const el = document.getElementById('clikeHelpOverlay');
  const ul = document.getElementById('clikeHelpList');
  ul.innerHTML = '';
  for (const it of HELP_COMMANDS) {
    const li = document.createElement('li');
    li.innerHTML = '<code>' + escapeHtml(it.cmd) + '</code> — ' + escapeHtml(it.desc);
    ul.appendChild(l"i);
  }
  el.style.display = 'flex';
}
function closeHelpOverlay(){
  const el = document.getElementById('clikeHelpOverlay');
  el.style.display = 'none';
}
document.getElementById('clikeHelpClose').onclick = closeHelpOverlay;
/ Hook slash command
// Nel click handler del bottone "Send" (free) o dove leggi input:
if (text === '/help') {
  openHelpOverlay();
  prompt.value = '';
  return;
}

// (Facoltativo) scorciatoia tastiera: F1-like
document.addEventListener('keydown', (ev)=>{
  if ((ev.ctrlKey || ev.metaKey) && ev.key === '/') {
    openHelpOverlay();
    ev.preventDefault();
  }
});

// Hard guard: surface any webview errors as bubbles instead of silently freezing
window.addEventListener('error', (ev) => {
  const msg = (ev && ev.error && (ev.error.stack || ev.error.message)) || String(ev.message || 'Unknown error');
  try { bubble('assistant', '⚠️ Webview error:\n' + msg, 'system'); } catch {}
});

window.addEventListener('unhandledrejection', (ev) => {
  const msg = (ev && ev.reason && (ev.reason.stack || ev.reason.message)) || String(ev.reason || 'Unhandled rejection');
  try { bubble('assistant', '⚠️ Promise error:\n' + msg, 'system'); } catch {}
}); 

const attachmentsByMode = { free: [], harper: [], coding: [] };
function currentMode() { return document.getElementById('mode').value; }
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

function bubble(role, content, modelName, attachments, ts) {
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

mode.addEventListener('change', ()=> post('uiChanged', { mode: mode.value, model: model.value }));
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


btnChat.addEventListener('click', ()=>{
  btnChat.disabled = true;
  console.log('[webview] sendChat click');
  const text = prompt.value;
  if (!text.trim()) return;
  // --- Slash commands (bot-mode minimal) ---
  if (text.startsWith('/init')) {
    // /init <name> [--path <abs>] [--force]
    const m = text.match(/^\/init\s+([^\s]+)(?:\s+--path\s+(.+?))?(?:\s+--force)?$/i);
    const name = m && m[1] || '';
    const path = m && m[2] || '';
    const force = /--force/i.test(text);
    post('harperInit', { name, path, force });
    prompt.value = '';
    return;
  }
  if (text === '/status') {
    post('echo', { message: 'Status: ready. Use /spec, /plan, /kit for Harper generation; /apply to write files.' });
    prompt.value = '';
    return;
  }
  if (text === '/where') {
    post('where');
    prompt.value = '';
    return;
  }
  if (text.startsWith('/switch ')) {
    const name = text.replace('/switch', '').trim();
    post('switchProject', { name });
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
  post('sendChat', { mode: mode.value, model: model.value, prompt: text, attachments: atts });
  attachmentsByMode[currentMode()] = [];
  renderAttachmentChips();
  btnChat.disabled = false;
  });

btnGen.addEventListener('click', ()=>{
  console.log('[webview] sendGen click');

  const text = prompt.value;
  if (!text) return;
  btnGen.disabled = true;
  // /spec|/plan|/kit → Harper mode
  const specCmd = raw.startsWith('/spec');
  const planCmd = raw.startsWith('/plan');
  const kitCmd  = raw.startsWith('/kit');

  if (specCmd || planCmd || kitCmd) {
    const userPrompt = text.replace(/^\/(spec|plan|kit)\s*/i, '').trim();
    const atts = attachmentsByMode.harper ? [...attachmentsByMode.harper] : [];

    // rimaniamo minimali: passiamo userPrompt come content; l'orchestrator harper-mode già forza schema JSON
    post('sendGenerate', {
      mode: 'harper',
      model: model.value,
      prompt: userPrompt || 'Follow the Harper step and emit JSON files only.',
      attachments: atts
    });
    attachmentsByMode.harper = [];
    renderAttachmentChips();
    return;
  }
  const m = (mode.value === 'free') ? 'coding' : mode.value;   // /v1/generate vuole coding/harper

  const atts = attachmentsByMode[m] ? [...attachmentsByMode[m]] : [];

  if (!text.trim()) return;
  bubble('user', text,model.value, atts);
  setBusy(true);
  prompt.value = '';
  clearTextPanel();        // <— svuota tab Text
  clearDiffsPanel();        // <— svuota tab Diffs
  clearFilesPanel();        // <— svuota tab Files
  setTab('diffs');

  post('sendGenerate', { mode: m, model: model.value, prompt: text, attachments: atts });
  attachmentsByMode[currentMode()] = [];
  renderAttachmentChips();
  btnGen.disabled = false;
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
  if (msg.type === 'prefill') {
    const text = (msg.text || '');
    prompt.value = text;
    prompt.focus();
  }
  if (msg.type === 'busy') { setBusy(!!msg.on); return; }
  if (msg.type === 'initState' && msg.state) {
    const hs = msg.state && msg.state.historyScope || 'singleModel';
    const sel = document.getElementById('historyScope');
    if (sel) {
      sel.addEventListener('change', () => {
        const value = sel.value === 'allModels' ? 'allModels' : 'singleModel';
        vscode.postMessage({ type: 'setHistoryScope', value });
      });
      sel.value = hs;
    }
    
    if (msg.state.mode)  mode.value  = msg.state.mode;
    if (msg.state.model) model.value = msg.state.model;
  }
  if (msg.type === 'attachmentsCleared') {
    const m = msg.mode || currentMode();
    attachmentsByMode[m] = [];
    renderAttachmentChips();
  }

  if (msg.type === 'hydrateSession' && Array.isArray(msg.messages)) {
    chat.innerHTML = '';
    for (const m of msg.messages) bubble(m.role, m.content, m.model, m.attachments || [], m.ts);
  }
  if (msg.type === 'models') {
    model.innerHTML = '';
    (msg.models||[]).forEach(m=>{
      const o = document.createElement('option'); o.value = m; o.textContent = m; model.appendChild(o);
    });
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
    bubble('assistant', text, modelName);

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
    const summary = Array.isArray(data.files) && data.files.length
      ? 'Generated files:\\n' + data.files.map(f => '- ' + f.path).join('\\n')
      : JSON.stringify(data, null, 2);
    bubble('assistant', summary, model.value);
    
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
    lastRun = { run_dir: data.run_dir, audit_id: data.audit_id };
    btnApply.disabled = !lastRun?.run_dir && !lastRun?.audit_id;
  }
  if (msg.type === 'applyResult') {
    setBusy(false);
    setTab('text');
    preText.textContent = "Applied files:\\n" + JSON.stringify(msg.data?.applied || [], null, 2);
  }
  if (msg.type === 'error') {
    setBusy(false);
    setTab('text');
    preText.textContent = 'Error: ' + msg.message;
  }
});

// init
post('fetchModels');
</script>

<div id="clikeHelpOverlay" role="dialog" aria-modal="true" aria-label="CLike Help">
  <div id="clikeHelpCard">
    <span id="clikeHelpClose">✖</span>
    <h2>CLike — Slash Commands</h2>
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
  out.appendLine(`cmdOpenChat panel created ${panel}`);
  const c = vscode.workspace.getConfiguration();
  out.appendLine(`cmdOpenChat conf read ${c}`);
  const orchestratorUrl = c.get('clike.orchestratorUrl') || 'http://localhost:8080';
  out.appendLine(`cmdOpenChat orchestratorUrl ${orchestratorUrl}`);

  panel.webview.html = getWebviewHtml(orchestratorUrl);
  out.appendLine(`cmdOpenChat getWebviewHtml done`);
  panel.webview.postMessage({ type: 'busy', on: false });
  out.appendLine(`cmdOpenChat postMessage done`);
  // Stato iniziale (mode/model)
  const savedState = context.workspaceState.get('clike.uiState') || { mode: 'free', model: 'auto' };

  savedState.historyScope= effectiveHistoryScope(context),
  panel.webview.postMessage({ type: 'initState', state: savedState });
  out.appendLine(`cmdOpenChat savedState done`);

  // HYDRATE per MODE (non per model)
  // Hydrate chat dal FS per il modello selezionato
  try {
    
    const scope = effectiveHistoryScope(context);
    const modeCur  = (savedState?.mode ?? newState?.mode ?? 'free');
    const modelCur = (savedState?.model ?? newState?.model ?? 'auto');

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

  function renderChat() {
  const key = sessionKey();
  const hist = state.history[key] || [];
  const chatEl = document.getElementById('chat');
  if (!chatEl) return;
  chatEl.innerHTML = hist.map(m => {
    const who = m.role === 'user' ? 'me' : 'bot';
    const badge = m.role === 'assistant' ? `<span class="chip">${m.model || model.value}</span>` : '';
    return `<div class="bubble ${who}">${badge}${escapeHtml(m.text)}</div>`;
  }).join('');
  chatEl.scrollTop = chatEl.scrollHeight;
}
function escapeHtml(s){return s.replace(/[&<>"']/g, m=>({ "&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;","'":"&#39;"}[m]))}

  // Ascolto eventi dalla webview
  panel.webview.onDidReceiveMessage(async (msg) => {
    out.appendLine(`[webview] recv ${msg && msg?.type}`);

    try {
      // --- Harper Init: crea struttura progetto nel workspace corrente ---
      if (msg.type === 'harperInit') {
        try {
          const ws = vscode.workspace.workspaceFolders && vscode.workspace.workspaceFolders[0];
          if (!ws) { vscode.window.showErrorMessage('CLike: open a folder first.'); return; }
          const root = vscode.Uri.joinPath(ws.uri, '.'); // base
          const projectName = (msg.name || 'harper_project').replace(/[^\w\-\.]/g, '_');
          const target = msg.path
            ? vscode.Uri.file(msg.path)
            : vscode.Uri.joinPath(root, 'docs', 'harper'); // cartella condivisa come da tua richiesta

          // crea cartelle base
          const runsDir = vscode.Uri.joinPath(root, 'runs');
          await vscode.workspace.fs.createDirectory(target);
          await vscode.workspace.fs.createDirectory(runsDir);

          // file seed
          const idea = vscode.Uri.joinPath(target, 'IDEA.md');
          const spec = vscode.Uri.joinPath(target, 'SPEC.md');
          const plan = vscode.Uri.joinPath(target, 'PLAN.md');
          const pb   = vscode.Uri.joinPath(target, 'PLAYBOOK_PLAN.md');
          const evalf= vscode.Uri.joinPath(target, 'EVAL.md');
          const readme = vscode.Uri.joinPath(root, 'README.md');

          const enc = (s)=>Buffer.from(s, 'utf8');
          const now = new Date().toISOString().slice(0,19).replace('T',' ');
          await vscode.workspace.fs.writeFile(idea,  enc(`# IDEA (${projectName})\n\n- Created: ${now}\n- Business/Tech context:\n\n`));
          await vscode.workspace.fs.writeFile(spec,  enc(`# SPEC (${projectName})\n\n- Constraints (business/economic/strategy):\n- Quality gates:\n\n`));
          await vscode.workspace.fs.writeFile(plan,  enc(`# PLAN (${projectName})\n\n- Steps / milestones:\n- Risks & mitigations:\n\n`));
          await vscode.workspace.fs.writeFile(pb,    enc(`# PLAYBOOK_PLAN\n\n(Generated/maintained by the bot per Harper approach)\n\n`));
          await vscode.workspace.fs.writeFile(evalf, enc(`# EVAL\n\n- Phase gates and checks:\n- Passing criteria:\n\n`));

          // README (append se esiste)
          try {
            const cur = await vscode.workspace.fs.readFile(readme).then(b=>b.toString('utf8')).catch(()=> '');
            const add = `\n\n## Harper Project Bootstrap\n- Docs: docs/harper/\n- Runs: runs/\n- Open Chat: Command Palette → "CLike: Open Chat"\n`;
            await vscode.workspace.fs.writeFile(readme, enc(cur + add));
          } catch {}

          // aggiorna stato / feedback UI
          await appendSessionJSONL('free', { role:'assistant', content:`Harper project initialized at ${target.fsPath}`, model:'system' });
          panel.webview.postMessage({ type: 'attachmentsCleared', mode: 'harper' });
          vscode.window.showInformationMessage(`CLike: Harper project initialized at ${target.fsPath}`);
        } catch (e) {
          vscode.window.showErrorMessage(`CLike: /init failed: ${e}`);
        }
        return;
      }

      // opzionale utility
      if (msg.type === 'echo') {
        await appendSessionJSONL('free', { role:'assistant', content:String(msg.message||''), model:'system' });
        return;
      }
      if (msg.type === 'where') {
        const ws = vscode.workspace.workspaceFolders && vscode.workspace.workspaceFolders[0];
        const p = ws ? ws.uri.fsPath : '(no workspace)';
        await appendSessionJSONL('free', { role:'assistant', content:`Workspace: ${p}`, model:'system' });
        return;
      }
      if (msg.type === 'switchProject') {
        // Nota: per multi-progetto potremo salvare un puntatore in .clike/config.json
        await appendSessionJSONL('free', { role:'assistant', content:`(placeholder) Switched project to: ${String(msg.name||'')}`, model:'system' });
        return;
      }
      if (msg.type === 'webview_ready') {
        out.appendLine('[ext] got webview_ready');
        const savedState = context.workspaceState.get('clike.uiState') || { mode: 'free', model: 'auto' };
        savedState.historyScope= effectiveHistoryScope(context),
        panel.webview.postMessage({ type: 'initState', state: savedState });

        try {
          const scope = effectiveHistoryScope(context);
          const modeCur  = (savedState?.mode ?? newState?.mode ?? 'free');
          const modelCur = (savedState?.model ?? newState?.model ?? 'auto');

          const msgs = (scope === 'allModels')
            ? await loadSession(modeCur).catch(() => [])
            : await loadSessionFiltered(modeCur, modelCur, 200).catch(() => []);

          panel.webview.postMessage({ type: 'hydrateSession', messages: msgs });
        } catch {}

        const lastRun = context.workspaceState.get('clike.lastRun');
        if (lastRun) panel.webview.postMessage({ type: 'lastRun', data: lastRun });

        // avvia anche subito la fetch dei modelli
        try {
          const orchestratorUrl = vscode.workspace.getConfiguration().get('clike.orchestratorUrl') || 'http://localhost:8080';
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
        } catch (e) {
          out.appendLine(`[ext] models fetch on ready failed: ${e.message}`);
        }

      }
      if (msg.type === 'setHistoryScope') {
        const value = (msg.value === 'allModels') ? 'allModels' : 'singleModel';
        const ui = context.workspaceState.get('clike.uiState') || {};
        ui.historyScopeOverride = value;
        await context.workspaceState.update('clike.uiState', ui);
        // Re-hydrate subito
        const s = context.workspaceState.get('clike.uiState') || { mode:'free', model:'auto' };
        const msgs = (value === 'allModels')
          ? await loadSession(s.mode, 200)
          : await loadSessionFiltered(s.mode, s.model, 200);
        panel.webview.postMessage({ type: 'hydrateSession', messages: msgs });

        vscode.window.setStatusBarMessage(`CLike: history scope = ${value}`, 2000);
        return;
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
        return;
      }

      // 2) CAMBIO UI (Mode/Model)
      if (msg.type === 'uiChanged') {
        const prev = context.workspaceState.get('clike.uiState') || { mode: 'free', model: 'auto' };
        const newState = { mode: msg.mode, model: msg.model };
        await context.workspaceState.update('clike.uiState', newState);

        // Se è cambiato SOLO il modello, NON re-idratare la chat
        if (prev.mode === newState.mode && prev.model !== newState.model) {
          return;
        }

        // Se è cambiato il mode (o entrambi), re-idrata in base allo scope
        const scope   = effectiveHistoryScope(context);
        const modeCur = newState.mode || 'free';
        const modelCur= newState.model || 'auto';

        const msgs = (scope === 'allModels')
          ? await loadSession(modeCur).catch(() => [])
          : await loadSessionFiltered(modeCur, modelCur, 200).catch(() => []);

        panel.webview.postMessage({ type: 'hydrateSession', messages: msgs });
        return;
      }

      // 3) CLEAR SESSION (solo mode corrente)
      if (msg.type === 'clearSession') {
        const st = context.workspaceState.get('clike.uiState') || { mode: 'free', model: 'auto' };
        const modeCur   = msg.mode  || st.mode  || 'free';
        const modelCur  = msg.model || st.model || 'auto';

        const scope = effectiveHistoryScope(context); // usa l’override UI oppure il default dalle settings
        if (scope === 'allModels') {
          // cancella tutto il MODE (file intero)
          await clearSession(modeCur);
          panel.webview.postMessage({ type: 'hydrateSession', messages: [] });
          vscode.window.setStatusBarMessage(`CLike: cleared ALL messages in mode "${modeCur}"`, 2500);
        } else {
         // singleModel → ripulisci SOLO le righe del modello corrente
          await pruneSessionByModel(modeCur, modelCur);

          // NEW: dopo la pulizia, mostra subito le altre conversazioni del mode
          const allLeft = await loadSession(modeCur, 200);
          const others  = allLeft.filter(e => (e.model || 'auto') !== modelCur);

          // Se vuoi anche aggiornare il selettore in UI a "All models", puoi salvare l'override:
          if (others.length > 0) {
            const ui = context.workspaceState.get('clike.uiState') || {};
            ui.historyScopeOverride = 'allModels';
            await context.workspaceState.update('clike.uiState', ui);
            panel.webview.postMessage({ type: 'initState', state: { ...ui, mode: modeCur, model: modelCur, historyScope: 'allModels' } });
          }

          // Idrata la webview con i messaggi rimanenti (tutti gli altri modelli)
          panel.webview.postMessage({ type: 'hydrateSession', messages: others });

          vscode.window.setStatusBarMessage(`CLike: cleared messages for model "${modelCur}" in mode "${modeCur}"`, 2500);

        }
        return;
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
        return;
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

        // Persisti l’input dell’utente nella sessione del MODE (e mostreremo badge del modello in render)
        await appendSessionJSONL(activeMode, {
          role: 'user',
          content: String(msg.prompt || ''),
          model: activeModel,
          attachments: Array.isArray(msg.attachments) ? msg.attachments : []
        });

        // Partiziona allegati SOLO QUI (N.B.: niente variabili globali!)
        const atts = Array.isArray(msg.attachments) ? msg.attachments : [];
        const { inline_files, rag_files } = partitionAttachments(atts);
        // History del MODE corrente
        const historyScope  = effectiveHistoryScope(context);
        // History per conversazione “stateless”: carico SOLO le bolle del MODE corrente
        const history = await loadSession(activeMode).catch(() => []);
        // Filtra eventualmente per modello se vuoi inviare solo il sotto-filo di quel model:
        const historyForThisModel = history.filter(b => !b.model || b.model === activeModel);

        const source = (historyScope === 'allModels')
        ? history
        : historyForThisModel;
       
        const messages = source.map(b => ({ role: b.role, content: b.content }));

        // Costruisci payload
        const basePayload = { mode: activeMode, model: activeModel, messages, inline_files, rag_files, attachments: atts };
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
          await appendSessionJSONL(activeMode, { role: 'assistant', content: `Error: ${emsg}`, model: activeModel });
          panel.webview.postMessage({ type: 'error', message: emsg });
        } finally {
          panel.webview.postMessage({ type: 'busy', on: false });
          inflightController = null;
        }
        return;
      }

      // 6) APPLY
      if (msg.type === 'apply') {
        const payload = {
          run_dir: msg.run_dir || null,
          audit_id: msg.audit_id || null,
          selection: msg.selection || { apply_all: true }
        };
        const res = await postJson(`${orchestratorUrl}/v1/apply`, payload);
        panel.webview.postMessage({ type: 'applyResult', data: res });
        return;
      }

      // 7) CANCEL
      if (msg.type === 'cancel') {
        if (inflightController) inflightController.abort();
        inflightController = null;
        panel.webview.postMessage({ type: 'busy', on: false });
        return;
      }
      // --- PICK WORKSPACE FILES ----------------------------------------------------
      if (msg.type === 'pickWorkspaceFiles') {
        const folders = vscode.workspace.workspaceFolders || [];
        const base = folders.length ? folders[0].uri : undefined;

        const uris = await vscode.window.showOpenDialog({
          canSelectFiles: true, canSelectFolders: false, canSelectMany: true,
          openLabel: 'Attach', defaultUri: base
        });
        if (!uris) return;

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
              // grande: passa solo il path → il server farà RAG
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
        return;
      }

      if (msg.type === 'pickExternalFiles') {
        const uris = await vscode.window.showOpenDialog({
          canSelectFiles: true, canSelectFolders: false, canSelectMany: true,
          openLabel: 'Attach'
        });
        if (!uris) return;

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
        return;
      }
    } catch (err) {
      panel.webview.postMessage({ type: 'error', message: String(err) });
    }
  });
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
