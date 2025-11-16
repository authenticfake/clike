const vscode = require('vscode');
const out = vscode.window.createOutputChannel('Clike.theme');

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

function getChatTheme() {
  try {
    // Settings → "clike.chat.theme": "classic" | "panel" | "paper"
    return vscode.workspace
      .getConfiguration('clike')
      .get('chat.theme', 'classic');
  } catch {
    return 'classic';
  }
}

function getWebviewHtml(orchestratorUrl, themeName = 'classic') {
  const nonce = String(Math.random()).slice(2);
  const safeTheme = themeName || 'classic';

  return `<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; img-src https: data:; style-src 'unsafe-inline'; script-src 'nonce-${nonce}';">
<meta name="viewport" content="width=device-width, initial-scale=1.0" />
<title>CLike Chat</title>
<style>
  :root {
    --bg:#0f1419;
    --fg:#e6eaf0;
    --fg-dim:#aeb8c4;
    --card:#161b22;
    --border:#30363d;
    --accent:#58a6ff;
    --bubble-user:#1f6feb;
    --bubble-ai:#2d333b;
    --bubble-max-width:78%;
  }

  /* Classic: legacy CLike style (layout ping-pong, tonde) */
  body[data-theme="classic"] {
    --bg:#0f1419;
    --fg:#e6eaf0;
    --fg-dim:#aeb8c4;
    --card:#161b22;
    --border:#30363d;
    --accent:#58a6ff;
    --bubble-user:#1f6feb;
    --bubble-ai:#2d333b;
    --bubble-max-width:78%;
  }

  /* Pro: doc-style, neutro scuro, più contrasto */
  body[data-theme="pro"] {
    --bg: var(--vscode-editor-background);
    --fg: var(--vscode-editor-foreground);
    --fg-dim: var(--vscode-descriptionForeground);
    --card: var(--vscode-editorHoverWidget-background);
    --border: var(--vscode-panel-border);
    --accent: var(--vscode-textLink-foreground);
    --bubble-user: rgba(37, 99, 235, 0.22);   /* user: leggermente più acceso */
    --bubble-ai: rgba(15, 23, 42, 0.92);      /* assistant: blocco doc scuro */
    --bubble-max-width:100%;
  }

  /* Studio: dark console leggibile, con border-left "signal" */
  body[data-theme="studio"] {
    --bg:#020617;              /* sfondo quasi nero/blu */
    --fg:#e5e7eb;
    --fg-dim:#9ca3af;
    --card:#020617;
    --border:#1f2937;
    --accent:#38bdf8;          /* ciano dev */
    --bubble-user:#020617;     /* stesso tono base */
    --bubble-ai:#020617;
    --bubble-max-width:100%;
  }

  /* Paper: light morbido, non abbagliante */
  body[data-theme="paper"] {
    --bg:#f3f4f6;              /* grigio chiaro caldo */
    --fg:#111827;
    --fg-dim:#6b7280;
    --card:#ffffff;
    --border:#e5e7eb;
    --accent:#2563eb;
    --bubble-user:#e6eefc;     /* azzurrino molto soft */
    --bubble-ai:#ffffff;
    --bubble-max-width:100%;
  }

  body {
    background:var(--bg);
    color:var(--fg);
    font-family: ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, sans-serif;
    padding:12px;
  }

  .row {
    display:flex;
    gap:8px;
    align-items:center;
    margin-bottom:8px;
  }

  select,
  input,
  textarea,
  button {
    font-size:13px;
    background:var(--card);
    color:var(--fg);
    border:1px solid var(--border);
    border-radius:6px;
    padding:6px 8px;
  }

  #clikeHelpOverlay {
    position: fixed;
    inset: 0;
    background: rgba(0,0,0,.6);
    display: none;
    z-index: 9999;
    align-items: center;
    justify-content: center;
  }

  #clikeHelpCard {
    background: var(--vscode-editor-background);
    color: var(--vscode-editor-foreground);
    border: 1px solid var(--vscode-panel-border);
    border-radius: 8px;
    max-width: 720px;
    width: 92%;
    max-height: 80vh;
    overflow: auto;
    box-shadow: 0 10px 30px rgba(0,0,0,.35);
    padding: 16px;
    line-height: 1.4;
  }

  #clikeHelpCard h2 {
    margin: 0 0 8px 0;
    font-size: 18px;
  }

  #clikeHelpCard code {
    background: var(--vscode-editorHoverWidget-background);
    padding: 2px 6px;
    border-radius: 6px;
  }

  #clikeHelpClose {
    float: right;
    cursor: pointer;
  }

  #clikeHelpList li {
    margin: 6px 0;
  }

  .chip {
    display:inline-block;
    padding:2px 6px;
    border-radius:10px;
    border:1px solid #ccc;
    cursor:pointer;
    user-select:none;
  }

  #attach-toolbar {
    position:relative;
  }

  button {
    cursor:pointer;
  }

  textarea {
    width:100%;
    min-height:80px;
  }

  .toolbar {
    display:flex;
    gap:8px;
    align-items:center;
  }

  #status {
    margin-left:auto;
    opacity:.7;
  }

  .spinner {
    display:none;
    margin-left:8px;
  }

  .spinner.active {
    display:inline-block;
    animation: spin 1s linear infinite;
  }

  @keyframes spin {
    from { transform:rotate(0); }
    to   { transform:rotate(360deg); }
  }

  .chat {
    border:1px solid var(--border);
    border-radius:8px;
    padding:10px;
    background:var(--card);
    height:260px;
    overflow:auto;
  }

  .msg {
    margin:8px 0;
    display:flex;
    justify-content:flex-start; /* default: colonna unica */
  }

  /* Classic mantiene il ping-pong laterale */
  body[data-theme="classic"] .msg.user {
    justify-content:flex-end;
  }
  body[data-theme="classic"] .msg.ai {
    justify-content:flex-start;
  }

  .bubble {
    max-width:var(--bubble-max-width);
    padding:10px 12px;
    border-radius:8px; /* default: card più squadrata */
    white-space:pre-wrap;
    word-break:break-word;
    position:relative; /* per il cestino assoluto */
  }

  .user .bubble {
    background:var(--bubble-user);
    color:white;
  }

  .ai .bubble {
    background:var(--bubble-ai);
    color:var(--fg);
  }
  
  /* Paper: user bubble text must stay dark for proper contrast */
  body[data-theme="paper"] .user .bubble {
    color:#111827;   /* quasi nero, leggibilissimo sul celestino */
  }

  /* Rende il classic “fumettoso”: angoli più tondi e un lato smussato */
  body[data-theme="classic"] .bubble {
    border-radius:14px;
  }
  body[data-theme="classic"] .user .bubble {
    border-top-right-radius:4px;
  }
  body[data-theme="classic"] .ai .bubble {
    border-top-left-radius:4px;
  }

  /* Pro: più contrasto fra user/assistant via bordi */
  body[data-theme="pro"] .user .bubble {
    border:1px solid rgba(37, 99, 235, 0.45);
  }
  body[data-theme="pro"] .ai .bubble {
    border:1px solid rgba(148, 163, 184, 0.25);
  }

  /* Studio: card console con border-left “signal” */
  body[data-theme="studio"] .ai .bubble {
    border:1px solid #1f2937;
    border-left:3px solid var(--accent);
  }
  body[data-theme="studio"] .user .bubble {
    border:1px solid #111827;
    border-left:3px solid #6366f1;
  }

  /* Paper: chiaro morbido con bordi delicati */
  body[data-theme="paper"] .ai .bubble,
  body[data-theme="paper"] .user .bubble {
    border:1px solid #e5e7eb;
  }

  /* Pulsante cestino: nascosto finché non c’è hover sulla bubble */
  .bubble-delete {
    position:absolute;
    top:6px;
    right:6px;
    width:18px;
    height:18px;
    padding:0;
    border:none;
    border-radius:999px;
    font-size:11px;
    line-height:18px;
    text-align:center;
    background:rgba(0,0,0,.35);
    color:var(--fg-dim);
    cursor:pointer;
    opacity:0;
    transition:opacity .15s ease-out, background .15s ease-out, transform .1s ease-out;
  }

  .msg:hover .bubble-delete {
    opacity:.9;
  }

  .bubble-delete:hover {
    background:rgba(0,0,0,.55);
    color:var(--fg);
    transform:scale(1.05);
  }

  .meta {
    font-size:11px;
    opacity:.7;
    margin-top:3px;
  }


  .meta {
    font-size:11px;
    opacity:.7;
    margin-top:3px;
  }

  .badge {
    display:inline-block;
    font-size:10px;
    padding:2px 6px;
    border-radius:10px;
    border:1px solid var(--border);
    margin-right:6px;
    background:var(--card);
    color:var(--fg-dim);
  }

  .tabs {
    margin-top:10px;
    display:flex;
    gap:6px;
  }

  .tab {
    padding:6px 10px;
    border:1px solid var(--border);
    border-bottom:none;
    cursor:pointer;
    border-top-left-radius:6px;
    border-top-right-radius:6px;
  }

  .tab.active {
    background:var(--card);
  }

  .panel {
    border:1px solid var(--border);
    padding:8px;
    min-height:150px;
    background:var(--card);
  }

  pre {
    white-space: pre-wrap;
    word-wrap: break-word;
  }
</style>

</head>
<body data-theme="${safeTheme}">

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
  {cmd:'/idea <name>'},
  {cmd:'/init <name> [--path <abs>] [--force]', desc:'Initializes the Harper project in the workspace'},
  {cmd:'/status', desc:'Shows the Harper project/context status'},
  {cmd:'/where', desc:'Shows the Harper workspace/doc-root path'},
  {cmd:'/switch <name|path>', desc:'Switches to another Harper project'},
  {cmd:'/spec [file|testo]', desc:'Generates/Updates SPEC.md from the IDEA'},
  {cmd:'/plan [spec_path]', desc:'Generates/Updates PLAN.md from the SPEC'},
  {cmd:'/kit [REQ-ID]', desc:'Generates/Updates KIT.md and PLAN.md'},
  { cmd: '/eval <REQ-ID>', desc: 'Performs an eval of plan/kit/finalize' },
  { cmd: '/gate <REQ-ID>', desc: 'Performs a gate of plan|kit|finalize' },
  {cmd:'/finalize', desc:'Final gates and project closure (Harper)'},
  {cmd:'/rag <query>', desc:'Cerca nel RAG (mostra i top risultati) (cross)'},
  {cmd:'/rag +<N>', desc:'Adds RAG result #N from the last search to the attached files (cross)'},
  {cmd:'/rag list', desc:'Shows current attached files (inline+RAG) (cross).'},
  {cmd:'/rag clear', desc:'Svuota gli allegati correnti (cross)'},
  { cmd: '/ragIndex [glob]', desc: 'Manually indexes into the RAG. Examples:/ragIndex docs/**/*.md  |  /ragIndex **/*' },
  { cmd: '/ragSearch <query>', desc: 'Searches the RAG (shows top results) (cross).' },
  
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
  if (!window.attachmentsByMode) window.attachmentsByMode = {};
  if (!attachmentsByMode[mode]) attachmentsByMode[mode] = [];
  return attachmentsByMode[mode];
}
// Count what's inline vs rag in a given list
function _analyzeAttachments(list) {
  let inlineN = 0, ragN = 0, noneN = 0;
  for (var i = 0; i < (list || []).length; i++) {
    var a = list[i] || {};
    if (a && (a.content || a.bytes_b64)) inlineN++;
    else if (a && a.path) ragN++;
    else noneN++;
  }
  return { inlineN, ragN, noneN };
}
function debugBucket(mode, label) {
  try {
    const bucket = ensureBucket(mode);
    const stats = _analyzeAttachments(bucket);
    console.log('CLike DEBUG', label || 'bucket', { mode, stats, first: bucket[0] });
  } catch (e) { /* ignore */ }
}
function renderAttachmentChips() {
  var wrap = document.getElementById('attach-chips');
  if (!wrap) return;

  // Usa escapeHtml se esiste, altrimenti fallback locale
  var esc = (typeof escapeHtml === 'function')
    ? escapeHtml
    : function (s) {
        s = String(s == null ? '' : s);
        s = s.replace(/&/g, '&amp;');
        s = s.replace(/</g, '&lt;');
        s = s.replace(/>/g, '&gt;');
        s = s.replace(/"/g, '&quot;');
        s = s.replace(/'/g, '&#39;');
        return s;
      };

  var list = ensureBucket(currentMode());

  var html = list.map(function (a, i) {
    var name = (a && (a.name || a.path || a.id)) ? (a.name || a.path || a.id) : 'file';
    var isInline = !!(a && (a.content || a.bytes_b64));
    var hasPath  = !!(a && a.path);
    var meta = isInline ? ' (inline)' : (hasPath ? ' (path: ' + a.path + ')' : '');
    var label = name + meta;
    var safe = esc(label);
    return '<span class="chip" data-i="' + i + '" title="' + safe + '">' + safe + ' ✕</span>';
  }).join(' ');

  wrap.innerHTML = html;

  // Re-bind remove handlers
  var chips = wrap.querySelectorAll('.chip');
  for (var j = 0; j < chips.length; j++) {
    chips[j].addEventListener('click', function () {
      var idx = parseInt(this.getAttribute('data-i') || '-1', 10);
      if (idx >= 0) {
        var bucket = ensureBucket(currentMode());
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
 
  if (cmd === '/eval' || cmd === '/gate') {
    const rest = parts.slice(1).map(x => String(x).trim()).filter(Boolean);
    const testMode = (rest.slice(1))? rest.slice(1)[0] : 'auto';
    const modeContent = (rest.slice(2))? rest.slice(2)[0] : 'pass';
    
    let targets = null;
    if (!rest.length) {
      targets = ''; //findNextOpenReq in runCommand
    } else {
      // assumiamo REQ-ID singolo (o più REQ-ID separati da spazio)
      const isReq = (s) => /^req-\d+/i.test(s);
      const onlyReqs = rest.every(isReq);
      targets = onlyReqs ? rest : [rest[0]];

    }
    console.log('cmd evals targets:', targets);
    return { cmd, args: { targets, testMode, modeContent } };
  }
  if (cmd === '/kit' ) {
    // Sintassi:
    //   /kit               → findNextOpenReq in runKitCommand open REQ (batch=1)
    //   /kit REQ-02        → target specifico
    
    const rest = parts.slice(1).map(x => String(x).trim()).filter(Boolean);
    let targets = null;
    if (!rest.length) {
      targets = ''; //findNextOpenReq in runKitCommand
    } else {
      // assumiamo REQ-ID singolo (o più REQ-ID separati da spazio)
      const isReq = (s) => /^req-\d+/i.test(s);
      const onlyReqs = rest.every(isReq);
      targets = onlyReqs ? rest : [rest[0]];
    }
    return { cmd, args: { targets } };
  }
  if (cmd === '/plan' || cmd === '/spec') {
    // Sintassi:
    //   /spec | /plan (no args)
    let targets = '';
    return { cmd, args: { targets } };
  }
  if (cmd === '/idea') {
    console.log('cmd init parsed:');
    const name = parts[1]; 
    return { cmd, args: { name } };
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
  if (slash.cmd === '/idea' || slash.cmd === '/spec' || slash.cmd === '/plan' || slash.cmd === '/kit'  || slash.cmd === '/finalize') {
    // attachments della mode corrente (se li usi)
    var modeVal  = (mode  && mode.value)  ? mode.value  : 'harper';
    var key      = modeVal;
    var atts = [];
    try {
      if (typeof attachmentsByMode !== 'undefined' && attachmentsByMode && attachmentsByMode[key]) {
        atts = attachmentsByMode[key].slice(0);
      }
    } catch {}    
    try { bubble('user', slash.cmd + (slash.args?.targets ? (' ' + slash.args.targets) : ''), (model && model.value) ? model.value : 'auto', atts); } catch {}
    
    const msg = { type: 'harperRun', cmd: slash.cmd.slice(1), attachments: atts };
    if (slash.cmd === '/kit') {
      msg.targets = slash.args?.targets ?? null; // 'next' | ['REQ-01', ...]
    } 
    else if (slash.cmd === '/idea') {
      msg.name = slash.args.name || ''
    }
    vscode.postMessage(msg);
    //  SVUOTA ALLEGATI DELLA MODE CORRENTE DOPO L’INVIO
    attachmentsByMode[currentMode()] = [];
    renderAttachmentChips();
    
    return true;
  }
  //EVALS
  if (slashCmd === '/eval' || slashCmd === '/gate') {
    // mappa su handler host esistente (eval)
    var atts = [];
    try {
      if (typeof attachmentsByMode !== 'undefined' && attachmentsByMode && attachmentsByMode[key]) {
        atts = attachmentsByMode[key].slice(0);
      }
    } catch {}    
    //Eval‑Driven Development - EDD
    const path_ltc_json = "runs/kit/" + slash.args?.targets+"/ci/LTC.json"
    console.log("slash.args", slash.args);
    try { bubble('user', slash.cmd + (slash.args?.targets ? (' ' + slash.args?.targets) : ''), (model && model.value) ? model.value : 'auto', atts); } catch {}
    const msg = { type: 'harperEDD', cmd: slash.cmd.slice(1), attachments: atts, argument: slash.args.targets || ''  };
    msg.targets = slash.args?.targets ?? null; // 'next' | ['REQ-01', ...]
    msg.running = slash.args?.testMode ?? null;
    msg.modeContent = slash.args?.modeContent ?? null;
    msg.path=path_ltc_json
    vscode.postMessage(msg);
    attachmentsByMode[currentMode()] = [];
    renderAttachmentChips();
    return;
  }
  // Fallback: slash non riconosciuto → mostro help
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
  // pulsante cestino → chiede al backend di eliminare il messaggio anche dal file JSONL
  if (role === 'user' || role === 'assistant') {
    const del = document.createElement('button');
    del.className = 'bubble-delete';
    del.textContent = '🗑';           // icona cestino
    del.title = 'Remove from history';
    del.addEventListener('click', function (ev) {
      ev.stopPropagation(); // non triggera altri handler
      vscode.postMessage({
        type: 'deleteBubble',
        mode: currentMode(),
        role,
        model: modelName || '',
        content: String(content || '')
      });
    });
    b.appendChild(del);
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
  if (n.startsWith('gpt')) {
    console.log("GPT", n);
    return 'openai';
  }
  if (/(llama|ollama|codellama|mistral|mixtral|phi|qwen|deepseek|granite|yi|gemma|llava)/.test(n)) return 'ollama';
  if(n.startsWith('claude')) return 'anthropic';
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
    console.log('sendChat event');

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
  attachmentsByMode[m] = [];
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
    const o = document.createElement('option');
    o.value = 'auto';
    o.textContent = 'auto';
    model.appendChild(o);
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
  
  
  // --- PRESERVE INLINE FIELDS WHEN ADDING ATTACHMENTS ---
  if (msg && msg.type === 'attachmentsAdded') {
    var bucket = ensureBucket(currentMode());
    var incoming = Array.isArray(msg.attachments) ? msg.attachments : [];
    for (var k = 0; k < incoming.length; k++) {
      var a = incoming[k] || {};
      bucket.push({
        name:      a.name || a.path || a.id || 'file',
        path:      (a.path != null ? a.path : null),
        id:        (a.id != null ? a.id : null),
        origin:    (a.origin != null ? a.origin : null),
        source:    (a.source != null ? a.source : (a.path ? 'workspace' : 'external')),
        content:   (a.content != null ? a.content : null),
        bytes_b64: (a.bytes_b64 != null ? a.bytes_b64 : null),
        size:      (a.size != null ? a.size : null),
        mime:      (a.mime != null ? a.mime : null)
      });
    }
    renderAttachmentChips();
    debugBucket(currentMode(), 'attachmentsAdded');
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
  if (msg.type === 'files') {






    selectedPaths = new Set();
    const data_file = msg.data || {};
    const files = Array.isArray(data_file) ? data_file : [];
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


module.exports = { getChatTheme, getWebviewHtml };