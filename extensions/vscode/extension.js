// extension.js — Clike Orchestrator+Gateway integration, Hardened Apply, Diff Preview, Auto-Commit+PR
const vscode = require('vscode');
const { applyPatch } = require('diff');
const { exec } = require('child_process');
const https = require('https');
const http = require('http');
const { URL } = require('url');

let __clike_lastTargetUriCache = null;

const out = vscode.window.createOutputChannel('Clike');

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

function mapUseAiFlagsToPayload(flags) {
  return {
    'use.ai.docstring': !!flags.useAiDocstring,
    'use.ai.refactor':  !!flags.useAiRefactor,
    'use.ai.tests':     !!flags.useAiTests,
    'use.ai.fix_errors':!!flags.useAiFixErrors,
  };
}

// Costruisce il payload rispettando le firme lato orchestrator (text = intero file, selection = selezione)
function mapDocContextToPayload(ctx, op, useContent = false) {
  const { useAiDocstring, useAiRefactor, useAiTests, useAiFixErrors } = cfg();
  const aiFlags = mapUseAiFlagsToPayload({ useAiDocstring, useAiRefactor, useAiTests, useAiFixErrors });

  const prompt = (ctx.selection && ctx.selection.trim()) ? ctx.selection.trim() : '';
  const payload = {
    op,
    intent: mapOpToIntent(op),
    path: ctx.file_path,
    text: ctx.text,                  // intero file (richiesto dall’orchestrator)
    language: ctx.language,
    selection: ctx.selection || '',  // selezione corrente (eventuale)
    prompt,
    fallback: true,                  // richiesto
    ...aiFlags,
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
      health: '/health'
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

  out.appendLine(`[REQ] POST ${url} ct=application/json len=${bodyStr.length} keys=${Object.keys(body).join(',')}`);
  const res = await httpPostJson(url, body);
  const keys = res && res.json ? Object.keys(res.json) : (res ? Object.keys(res) : []);
  out.appendLine(`[RES] POST ${url} -> ${res && res.status} keys=${(keys||[]).join(',')}`);
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

async function cmdCheckServices() {
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
    { label: '$(wand) Refactor (AI)', cmd: 'clike.refactor' },
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

function activate(context) {
  const reg = (id, fn) => context.subscriptions.push(vscode.commands.registerCommand(id, () => fn(context)));

  reg('clike.ping', () => cmdPing());
  reg('clike.codeAction', () => cmdCodeAction());

  reg('clike.applyUnifiedDiffHardened', cmdApplyUnifiedDiffHardened);
  reg('clike.applyUnifiedDiff', cmdApplyUnifiedDiff);
  reg('clike.applyNewContent', cmdApplyNewContent);
  reg('clike.applyLastPatch', cmdApplyLastPatch);

  reg('clike.addDocstring', cmdAddDocstring);
  reg('clike.refactor', cmdRefactor);
  reg('clike.generateTests', cmdGenerateTests);
  reg('clike.fixErrors', cmdFixErrors);

  reg('clike.listModels', () => cmdListModels());
  reg('clike.checkServices', () => cmdCheckServices());
  reg('clike.ragReindex', () => cmdRagReindex());
  reg('clike.ragSearch', () => cmdRagSearch());

  reg('clike.gitCreateBranch', () => vscode.commands.executeCommand('git.createBranch'));
  reg('clike.gitCommitPatch', () => vscode.commands.executeCommand('git.commit'));
  reg('clike.gitOpenPR', () => vscode.commands.executeCommand('github.createPullRequest'));
  reg('clike.gitSmartPR', async () => { await vscode.commands.executeCommand('git.commit'); await vscode.commands.executeCommand('github.createPullRequest'); });

  vscode.window.setStatusBarMessage('Clike: orchestrator+gateway integration ready', 2000);
}

function deactivate() {}
module.exports = { activate, deactivate };
