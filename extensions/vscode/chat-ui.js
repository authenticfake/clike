const vscode = require('vscode');
const { buildBrowserSlashParserSource } = require('./slash-parser');
const { buildBrowserSlashCompleteSource } = require('./slash-complete');

const CHAT_THEMES = ['classic', 'pro', 'studio', 'paper', 'cockpit'];

/**
 * Custom logging function that writes to both channels.
 * @param {...any} args Messages or objects to log.
 */


function getChatTheme() {
  try {
    // Settings → "clike.chat.theme": "cockpit" (default) | "classic" | "pro" | "studio" | "paper"
    const theme = vscode.workspace
      .getConfiguration('clike')
      .get('chat.theme', 'cockpit');
    return CHAT_THEMES.includes(theme) ? theme : 'cockpit';
  } catch {
    return 'cockpit';
  }
}

function getWebviewHtml(orchestratorUrl, themeName = 'cockpit') {
  const nonce = require('crypto').randomBytes(16).toString('hex');
  const safeTheme = CHAT_THEMES.includes(themeName) ? themeName : 'cockpit';
  const layoutOptions = CHAT_THEMES
    .map((t) => `<option value="${t}"${t === safeTheme ? ' selected' : ''}>${t}</option>`).join('');

  return `<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; img-src data:; style-src 'unsafe-inline'; script-src 'nonce-${nonce}';">
<meta name="viewport" content="width=device-width, initial-scale=1.0" />
<title>Chat CLike</title>
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

  button:disabled,
  select:disabled,
  textarea:disabled,
  input:disabled {
    cursor:not-allowed;
    opacity:.55;
  }

  body.clike-busy .toolbar,
  body.clike-busy #attach-toolbar,
  body.clike-busy .tabs,
  body.clike-busy #attach-chips,
  body.clike-busy .bubble-delete {
    pointer-events:none;
  }
  /* the Memory panel is separate from the chat: it opens while a command runs too */
  body.clike-busy #memoryBtn { pointer-events:auto; }

  body.clike-busy .tab {
    opacity:.55;
  }

  body.clike-busy #cancel {
    pointer-events:auto;
    opacity:1;
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

  /* Pulsante copia: accanto al cestino, sempre utilizzabile (anche durante un run) */
  .bubble-copy {
    position:absolute;
    top:6px;
    right:28px;
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

  .msg:hover .bubble-copy {
    opacity:.9;
  }

  .bubble-copy:hover {
    background:rgba(0,0,0,.55);
    color:var(--fg);
    transform:scale(1.05);
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
  /* /help overlay: VS Code theme colours, grouped commands */
  #clikeHelpOverlay { position:fixed; inset:0; display:none; z-index:99999; background:rgba(0,0,0,.45); }
  #clikeHelpCard {
    max-width:760px; max-height:84vh; margin:6vh auto; display:flex; flex-direction:column;
    background:var(--vscode-editorWidget-background, #1e1e1e); color:var(--vscode-editorWidget-foreground, #e6e6e6);
    border:1px solid var(--vscode-editorWidget-border, var(--vscode-widget-border, #454545));
    border-radius:10px; box-shadow:0 8px 32px rgba(0,0,0,.45);
    font-family:var(--vscode-font-family, system-ui); font-size:var(--vscode-font-size, 13px);
  }
  #clikeHelpCard .help-head { display:flex; align-items:center; gap:10px; padding:14px 16px 10px; border-bottom:1px solid var(--vscode-editorWidget-border, #454545); }
  #clikeHelpCard .help-head h2 { margin:0; font-size:15px; font-weight:600; flex:1; }
  #clikeHelpFilter {
    flex:0 1 240px; padding:4px 8px; border-radius:4px;
    background:var(--vscode-input-background, #2a2a2a); color:var(--vscode-input-foreground, #e6e6e6);
    border:1px solid var(--vscode-input-border, var(--vscode-editorWidget-border, #555));
  }
  #clikeHelpClose { width:28px; height:28px; border:none; border-radius:6px; cursor:pointer; font-size:18px; line-height:1;
    background:transparent; color:var(--vscode-editorWidget-foreground, #e6e6e6); }
  #clikeHelpClose:hover { background:var(--vscode-toolbar-hoverBackground, rgba(128,128,128,.25)); }
  #clikeHelpList { overflow:auto; padding:6px 16px 14px; }
  #clikeHelpList h3 { margin:14px 0 6px; font-size:11px; font-weight:600; letter-spacing:.06em; text-transform:uppercase;
    color:var(--vscode-descriptionForeground, #9da5b4); }
  #clikeHelpList .help-row { display:grid; grid-template-columns:minmax(180px, 38%) 1fr; gap:4px 14px; padding:5px 0;
    border-top:1px solid var(--vscode-editorWidget-border, rgba(128,128,128,.2)); }
  #clikeHelpList .help-cmd { font-family:var(--vscode-editor-font-family, monospace); font-size:12px; word-break:break-word;
    color:var(--vscode-textPreformat-foreground, var(--vscode-textLink-foreground, #4fc1ff)); }
  #clikeHelpList .help-desc { line-height:1.4; color:var(--vscode-editorWidget-foreground, #e6e6e6); }
  #clikeHelpList .help-empty { padding:12px 0; color:var(--vscode-descriptionForeground, #9da5b4); }

  /* ---------- every layout: the toolbar wraps instead of overflowing a narrow panel ---------- */
  .toolbar { flex-wrap:wrap; row-gap:6px; }
  #bmadBadge { border-color:#7c3aed; color:#c4b5fd; }

  /* ---------- every layout: slash-command autocompletion above the prompt ---------- */
  #promptRow { position:relative; }
  #acBox { position:absolute; left:0; right:0; bottom:100%; margin-bottom:4px; z-index:60; display:none;
    font-size:12.5px; }
  #acBox.open { display:block; }
  #acSig { font-family:var(--vscode-editor-font-family, ui-monospace, Menlo, monospace); font-size:12px; color:var(--fg-dim);
    background:var(--card); border:1px solid var(--border); border-radius:6px; padding:4px 8px; margin-bottom:4px;
    white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
  #acSig b { color:#fff; background:#7c3aed; border-radius:3px; padding:0 3px; font-weight:600; }
  #acErr { border:1px solid #b91c1c; background:rgba(127,29,29,.35); color:#fecaca; border-radius:6px; padding:4px 8px;
    margin-bottom:4px; display:none; }
  #acErr .ac-fix { color:#86efac; cursor:pointer; margin-left:6px; text-decoration:underline; }
  #acMenu { background:var(--vscode-editorSuggestWidget-background, var(--card)); border:1px solid var(--vscode-editorSuggestWidget-border, var(--border));
    border-radius:8px; overflow:auto; max-height:min(42vh, 300px); box-shadow:0 8px 24px rgba(0,0,0,.4); }
  #acMenu:empty { display:none; }
  .ac-it { display:grid; grid-template-columns:minmax(120px, max-content) minmax(0, 1fr) auto; gap:10px; padding:4px 10px;
    align-items:baseline; cursor:pointer; }
  .ac-it .ac-k { font-family:var(--vscode-editor-font-family, ui-monospace, Menlo, monospace); white-space:nowrap; color:var(--fg); }
  .ac-it .ac-k em { font-style:normal; font-weight:700; color:#c4b5fd; }
  .ac-it .ac-d { color:var(--fg-dim); white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
  .ac-it .ac-w { color:#fcd34d; font-size:11px; white-space:nowrap; }
  .ac-it .ac-g { color:var(--fg-dim); opacity:.7; font-size:11px; white-space:nowrap; }
  .ac-it.on { background:var(--vscode-editorSuggestWidget-selectedBackground, #312e81); }
  .ac-it.next .ac-k { color:#c4b5fd; }
  .ac-foot { display:flex; gap:12px; padding:3px 10px; font-size:11px; color:var(--fg-dim); border-top:1px solid var(--border); }
  @media (max-width: 520px) { .ac-it { grid-template-columns:minmax(0, 1fr) auto; } .ac-it .ac-d, .ac-it .ac-g { display:none; } .ac-foot { display:none; } }

  /* ---------- every layout: log cards and model answers ---------- */
  .bubble.log-card { width:min(100%, 760px); max-width:100%; padding:6px 10px 8px; border-left:3px solid #7c3aed; white-space:normal; }
  .log-head { display:flex; align-items:center; gap:8px; font-size:11.5px; color:var(--fg-dim); margin-bottom:4px; }
  .log-title { font-weight:600; color:var(--fg); }
  .log-stats { flex:1; }
  .log-more, .log-copy { border:none; background:transparent; color:var(--fg-dim); cursor:pointer; padding:0 4px; font-size:11.5px; }
  .log-more { text-decoration:underline; }
  .log-row { display:grid; grid-template-columns:auto minmax(0, 1fr) auto; gap:8px; align-items:baseline; padding:2px 0;
    border-top:1px solid rgba(127,127,127,.12); font-size:12.5px; }
  .log-row:first-child { border-top:none; }
  .log-time { font-family:var(--vscode-editor-font-family, ui-monospace, Menlo, monospace); font-size:11px; color:var(--fg-dim); white-space:nowrap; }
  .log-text { white-space:pre-wrap; overflow-wrap:anywhere; }
  .log-row.ok .log-text { color:#86efac; } .log-row.ko .log-text { color:#fca5a5; } .log-row.warn .log-text { color:#fcd34d; }
  .log-row.run .log-text { color:#c4b5fd; } .log-row.stop .log-text { color:#cbd5e1; }
  body[data-theme="paper"] .log-row.ok .log-text { color:#15803d; } body[data-theme="paper"] .log-row.ko .log-text { color:#b91c1c; }
  body[data-theme="paper"] .log-row.warn .log-text { color:#a16207; } body[data-theme="paper"] .log-row.run .log-text { color:#6d28d9; }
  body[data-theme="paper"] .log-row.stop .log-text { color:#475569; }
  .log-del { border:none; background:transparent; color:var(--fg-dim); cursor:pointer; opacity:0; padding:0 4px; }
  .log-row:hover .log-del { opacity:.8; }
  body.clike-busy .log-del { pointer-events:none; }
  .md-code { background:rgba(0,0,0,.28); border:1px solid rgba(127,127,127,.25); border-radius:6px; padding:6px 8px; margin:6px 0;
    white-space:pre; overflow:auto; font-family:var(--vscode-editor-font-family, ui-monospace, Menlo, monospace); font-size:12px; }
  .md-inline { background:rgba(127,127,127,.18); border-radius:4px; padding:0 4px; font-family:var(--vscode-editor-font-family, ui-monospace, Menlo, monospace); font-size:12px; }
  .md-h { display:inline-block; font-weight:700; margin-top:4px; }
  body[data-theme="paper"] .md-code { background:#f8fafc; }

  /* ---------- every layout: the card of the command in flight ---------- */
  #runCard { display:none; margin:0 0 8px; border:1px solid #7c3aed; border-radius:10px; padding:8px 10px;
    background:linear-gradient(180deg, rgba(124,58,237,.14), rgba(124,58,237,.04)); color:var(--fg); font-size:12.5px; }
  #runCard.open { display:block; }
  #runCard.ended.ok { border-color:#16a34a; background:rgba(22,163,74,.08); }
  #runCard.ended.failed { border-color:#b91c1c; background:rgba(185,28,28,.08); }
  #runCard.ended.cancelled { border-color:#6b7280; background:rgba(107,114,128,.10); }
  .rc-top { display:flex; align-items:baseline; gap:8px; flex-wrap:wrap; }
  .rc-title { font-weight:700; overflow-wrap:anywhere; }
  .rc-sub { color:var(--fg-dim); }
  .rc-time { margin-left:auto; color:#a78bfa; font-variant-numeric:tabular-nums; white-space:nowrap; }
  .rc-steps { display:flex; gap:4px; align-items:center; flex-wrap:wrap; margin:7px 0; }
  .rc-step { border-radius:11px; padding:2px 9px; font-size:11.5px; font-weight:600; white-space:nowrap; background:#3f3f46; color:#d1d5db; }
  .rc-step.ok { background:#14532d; color:#bbf7d0; } .rc-step.failed { background:#7f1d1d; color:#fecaca; }
  .rc-step.cancelled { background:transparent; border:1px dashed #6b7280; color:#9ca3af; }
  .rc-step.done { background:#334155; color:#e2e8f0; }
  .rc-step.running { background:#7c3aed; color:#fff; box-shadow:0 0 0 3px rgba(124,58,237,.35); animation: rcPulse 1.6s ease-in-out infinite; }
  .rc-step.next { background:transparent; border:1px dashed #6b7280; color:#9ca3af; }
  @keyframes rcPulse { 50% { box-shadow:0 0 0 5px rgba(124,58,237,.15); } }
  .rc-arrow { color:#6b7280; font-size:11px; }
  .rc-bar { height:7px; background:rgba(127,127,127,.25); border-radius:4px; overflow:hidden; position:relative; }
  .rc-bar > i { position:absolute; top:0; bottom:0; left:0; border-radius:4px; background:#22c55e; transition:width .6s ease; }
  .rc-bar > i.p { background:#7c3aed; }
  .rc-bar.indet > i { width:30% !important; background:repeating-linear-gradient(45deg, #7c3aed 0 10px, #8b5cf6 10px 20px); animation: rcSlide 1.4s linear infinite; }
  @keyframes rcSlide { from { left:-30%; } to { left:100%; } }
  .rc-line { margin-top:5px; color:var(--fg-dim); overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
  .rc-line b { color:var(--fg); font-weight:600; }
  .rc-actions { display:flex; gap:6px; margin-top:8px; flex-wrap:wrap; align-items:center; }
  .rc-actions button { font-size:12px; padding:3px 10px; }
  .rc-actions .danger { border-color:#b91c1c; color:#fecaca; background:rgba(127,29,29,.35); }
  .rc-actions .primary { border-color:#7c3aed; background:#7c3aed; color:#fff; }
  .rc-hint { color:var(--fg-dim); font-size:11px; }
  .rc-confirm { margin-top:8px; border:1px solid #b91c1c; background:rgba(127,29,29,.22); border-radius:8px; padding:7px 9px; line-height:1.45; }
  .rc-confirm b { color:#fecaca; }
  .rc-armed { margin-top:8px; border:1px dashed #a78bfa; border-radius:8px; padding:5px 9px; color:#ddd6fe; }
  .rc-sum { margin:6px 0 0 16px; padding:0; line-height:1.55; }
  .rc-x { margin-left:6px; border:none; background:transparent; color:var(--fg-dim); cursor:pointer; font-size:14px; padding:0 4px; }
  body[data-theme="paper"] .rc-step.running, body[data-theme="paper"] .rc-actions .primary { color:#fff; }
  body[data-theme="paper"] .rc-confirm b { color:#991b1b; }
  body[data-theme="paper"] .rc-armed { color:#5b21b6; }
  @media (max-width: 420px) { .rc-hint { display:none; } .rc-step { padding:1px 6px; } }

  /* ---------- cockpit layout ---------- */
  body[data-theme="cockpit"] {
    --bg:#1e1e1e; --fg:#e5e7eb; --fg-dim:#9ca3af; --card:#252526; --card2:#2d2d30; --border:#3f3f46;
    --accent:#7c3aed; --ok:#16a34a; --ok-l:#86efac; --ko-l:#fca5a5; --info-l:#93c5fd;
    --bubble-user:#0e639c; --bubble-ai:#2d2d30; --bubble-max-width:82%;
    padding:0; height:100vh; overflow:hidden; font-size:13px;
  }
  #ckSide, #ckHead, #ckStrip, #ckDrawerBtn, #ckScrim { display:none; }
  body[data-theme="cockpit"] #ckShell { display:grid; grid-template-columns:minmax(0, 1fr) 360px; gap:10px; height:100vh; padding:10px; box-sizing:border-box; }
  body[data-theme="cockpit"] #ckMain { display:flex; flex-direction:column; min-width:0; min-height:0; background:var(--card); border-radius:8px; padding:8px 10px 10px; box-sizing:border-box; }
  body[data-theme="cockpit"] #ckSide { display:block; min-height:0; overflow:auto; background:var(--card); border-radius:8px; padding:4px 12px 10px; box-sizing:border-box; }
  body[data-theme="cockpit"] .toolbar.ck-moved { display:none; }
  body[data-theme="cockpit"] #ckHead { display:flex; align-items:center; gap:8px; padding:6px 8px; margin-bottom:8px; background:var(--card2); border-radius:6px; min-width:0; }
  body[data-theme="cockpit"] .chat { flex:1 1 auto; height:auto; min-height:120px; background:transparent; border:none; padding:4px 2px; }
  body[data-theme="cockpit"] .msg.user { justify-content:flex-end; }
  body[data-theme="cockpit"] .bubble { border-radius:10px; border:1px solid #3f3f46; }
  body[data-theme="cockpit"] .user .bubble { border-color:#0e639c; }
  body[data-theme="cockpit"] textarea#prompt { min-height:54px; max-height:30vh; resize:vertical; background:#3c3c3c; border-color:#3c3c3c; border-radius:8px; }
  body[data-theme="cockpit"] #sendChat { background:#0e639c; border-color:#0e639c; color:#fff; }
  body[data-theme="cockpit"] #cancel:not(:disabled) { background:#3b1219; border-color:#b91c1c; color:#fecaca; }
  body[data-theme="cockpit"] #ckActions { display:flex; gap:6px; align-items:center; flex-wrap:wrap; margin:0; }
  body[data-theme="cockpit"] #attach-toolbar { flex-wrap:wrap; }
  body[data-theme="cockpit"] #ckOutput { margin-top:8px; border-radius:6px; background:var(--card2); }
  body[data-theme="cockpit"] #ckOutput > summary { cursor:pointer; padding:5px 10px; color:var(--fg-dim); font-size:12px; user-select:none; }
  body[data-theme="cockpit"] #ckOutput[open] > summary { color:var(--fg); }
  body[data-theme="cockpit"] #ckOutput .tabs { margin:0 8px; }
  body[data-theme="cockpit"] #ckOutput .panel { margin:0 8px 8px; max-height:32vh; overflow:auto; min-height:60px; }
  body[data-theme="cockpit"] #panel-text { height:auto !important; }
  .ck-mode { font-weight:700; letter-spacing:.04em; white-space:nowrap; }
  .ck-mode.harper { color:#c4b5fd; } .ck-mode.coding { color:#93c5fd; } .ck-mode.free { color:#86efac; }
  .ck-chips { display:flex; gap:6px; margin-left:auto; min-width:0; overflow:hidden; flex-wrap:nowrap; align-items:center; }
  .ck-chip { background:#3f3f46; border-radius:10px; padding:1px 9px; font-size:11.5px; color:#e5e7eb; white-space:nowrap; cursor:pointer; border:none; }
  .ck-chip.purple { background:#4c1d95; color:#ede9fe; }
  .ck-dim { color:var(--fg-dim); white-space:nowrap; overflow:hidden; text-overflow:ellipsis; min-width:0; }
  body[data-theme="cockpit"] #status { margin-left:0; font-size:11.5px; }
  .ck-sec { padding:8px 0; border-bottom:1px solid #333338; }
  .ck-sec:last-child { border-bottom:none; }
  .ck-sec > summary, .ck-h { list-style:none; display:flex; align-items:center; gap:6px; font-weight:700; color:#fff; font-size:12.5px; margin-bottom:6px; cursor:pointer; user-select:none; }
  .ck-sec > summary::-webkit-details-marker { display:none; }
  .ck-sec > summary::before { content:"▸"; color:#6b7280; font-size:10px; }
  .ck-sec[open] > summary::before { content:"▾"; }
  .ck-aside { margin-left:auto; font-weight:400; color:var(--fg-dim); font-size:11.5px; }
  .ck-seg { display:grid; grid-template-columns:repeat(3, 1fr); background:#1e1e1e; border-radius:8px; padding:3px; gap:3px; }
  .ck-seg.two { grid-template-columns:1fr 1fr; }
  .ck-seg button { border:none; background:transparent; color:var(--fg-dim); font-weight:600; padding:5px 0; border-radius:6px; }
  .ck-seg button.on.free { background:#16a34a; color:#fff; } .ck-seg button.on.coding { background:#0e639c; color:#fff; }
  .ck-seg button.on.harper, .ck-seg button.on.bmad, .ck-seg button.on.native { background:#7c3aed; color:#fff; }
  .ck-form { display:grid; grid-template-columns:96px minmax(0, 1fr); gap:6px 8px; align-items:center; margin-top:8px; }
  .ck-form > label { color:var(--fg-dim); font-size:12px; }
  .ck-form select, .ck-form input { width:100%; min-width:0; box-sizing:border-box; background:#1e1e1e; border-color:#3f3f46; }
  .ck-pair { display:flex; gap:6px; min-width:0; align-items:center; }
  .ck-pair.wrap { flex-wrap:wrap; }
  .ck-pair > * { min-width:0; flex:1 1 auto; }
  .ck-pair > button { flex:0 0 auto; }
  .ck-roles { display:grid; grid-template-columns:64px minmax(0, 1fr); gap:4px 8px; font-size:12px; margin-top:8px; align-items:center; }
  .ck-roles .ph { color:var(--fg-dim); font-weight:600; font-size:11px; }
  .ck-rc { display:flex; gap:4px; flex-wrap:wrap; }
  .ck-rc button, .ck-rc span { border:1px solid #4b5563; border-radius:10px; padding:1px 8px; color:var(--fg-dim); font-size:11.5px; background:transparent; }
  .ck-rc .on { border-color:#7c3aed; background:#4c1d95; color:#fff; }
  .ck-rc span { border-style:dashed; }
  .ck-bar { height:9px; background:#3f3f46; border-radius:5px; overflow:hidden; position:relative; }
  .ck-bar > i { position:absolute; top:0; bottom:0; left:0; border-radius:5px; }
  .ck-bar .g { background:#22c55e; } .ck-bar .p { background:repeating-linear-gradient(45deg, #7c3aed 0 10px, #8b5cf6 10px 20px); }
  .ck-pills { display:flex; gap:5px; flex-wrap:wrap; margin-top:8px; }
  .ck-pill { border-radius:12px; padding:3px 10px; font-weight:700; font-size:11px; }
  .ck-pill.done { background:#16a34a; color:#fff; } .ck-pill.active { background:#7c3aed; color:#fff; box-shadow:0 0 0 3px rgba(124,58,237,.3); } .ck-pill.todo { background:#3f3f46; color:#9ca3af; }
  .ck-filter { display:flex; gap:4px; }
  .ck-filter button { border:none; background:transparent; color:var(--fg-dim); padding:0 4px; font-size:11.5px; }
  .ck-filter button.on { color:#fff; text-decoration:underline; }
  .ck-reqs { max-height:min(32vh, 260px); overflow:auto; font-size:12.5px; }
  .ck-req { display:flex; gap:6px; padding:3px 6px; border-radius:4px; cursor:pointer; min-width:0; }
  .ck-req:hover { background:#2d2d30; }
  .ck-req .t { flex:1; min-width:0; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
  .ck-req .n { white-space:nowrap; font-size:11.5px; }
  .ck-req.done { color:#86efac; } .ck-req.in_progress { background:#312e81; color:#c4b5fd; } .ck-req.ready { color:#d1d5db; }
  .ck-req.ready .n { color:#9ca3af; } .ck-req.wait, .ck-req.deferred { color:#6b7280; }
  .ck-next { border:1px solid #7c3aed; background:#1f2937; border-radius:8px; padding:8px 10px; }
  .ck-next code { font-family:var(--vscode-editor-font-family, ui-monospace, Menlo, monospace); color:#e5e7eb; background:none; padding:0; }
  .ck-btns { display:flex; gap:6px; margin-top:7px; flex-wrap:wrap; }
  .ck-btn { border:1px solid #4b5563; background:#2d2d30; color:#e5e7eb; border-radius:6px; padding:3px 11px; font-size:12px; }
  .ck-btn.primary { background:#7c3aed; border-color:#7c3aed; color:#fff; }
  .ck-alt { display:flex; align-items:center; gap:8px; margin-top:4px; min-width:0; }
  .ck-alt code { flex:1; min-width:0; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; font-family:var(--vscode-editor-font-family, ui-monospace, Menlo, monospace); font-size:12px; color:#ddd6fe; background:none; padding:0; }
  .ck-alt .ck-btn { padding:1px 9px; }
  #ckDrawerClose { display:none; }
  .ck-blockers { margin:6px 0 2px 16px; padding:0; font-size:12px; color:#fcd34d; line-height:1.5; }
  .ck-blockers b { color:#fde68a; }
  .ck-blockers li { cursor:help; }
  .ck-hist-top { display:flex; align-items:center; gap:8px; margin-bottom:6px; min-width:0; }
  .ck-hist { display:flex; align-items:center; gap:6px; padding:3px 6px; border-radius:4px; cursor:pointer; font-size:12.5px; min-width:0; }
  .ck-hist:hover { background:#2d2d30; }
  .ck-hist .t { flex:1; min-width:0; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
  .ck-hist .n { color:var(--fg-dim); font-size:11.5px; white-space:nowrap; }
  .ck-hist .ck-btn { padding:0 6px; font-size:11px; }
  .ck-x { border:none; background:transparent; color:var(--fg-dim); cursor:pointer; padding:0 4px; opacity:0; }
  .ck-hist:hover .ck-x { opacity:.8; }
  .ck-kv { color:var(--fg-dim); font-size:12px; line-height:1.6; overflow-wrap:anywhere; }
  .ck-kv b { color:var(--fg); font-weight:600; }
  .ck-ok { color:#86efac; } .ck-ko { color:#fca5a5; } .ck-warn { color:#fcd34d; }
  .ck-empty { color:var(--fg-dim); font-size:12px; }

  /* medium: a compact side panel */
  @media (max-width: 1000px) {
    body[data-theme="cockpit"] #ckShell { grid-template-columns:minmax(0, 1fr) 300px; gap:8px; padding:8px; }
    body[data-theme="cockpit"] .ck-form { grid-template-columns:minmax(0, 1fr); gap:2px 0; }
    body[data-theme="cockpit"] .ck-form > label { margin-top:4px; }
    body[data-theme="cockpit"] .ck-chips .ck-chip.opt { display:none; }
  }
  /* narrow (the chat beside the editor): one column, the cockpit is a drawer, a status strip stays */
  @media (max-width: 720px) {
    body[data-theme="cockpit"] #ckShell { grid-template-columns:minmax(0, 1fr); padding:6px; }
    body[data-theme="cockpit"] #ckSide { display:none; position:fixed; top:0; right:0; bottom:0; width:min(84vw, 340px); z-index:80;
      border-radius:0; box-shadow:-8px 0 24px rgba(0,0,0,.5); padding-top:0; }
    body[data-theme="cockpit"] #ckDrawerClose { display:flex; position:sticky; top:0; z-index:2; justify-content:space-between; align-items:center;
      background:var(--card); padding:8px 0 6px; border-bottom:1px solid #333338; font-weight:700; }
    body[data-theme="cockpit"].ck-drawer #ckSide { display:block; }
    body[data-theme="cockpit"].ck-drawer #ckScrim { display:block; position:fixed; inset:0; background:rgba(0,0,0,.35); z-index:70; }
    body[data-theme="cockpit"] #ckDrawerBtn { display:inline-block; }
    body[data-theme="cockpit"] #ckStrip { display:flex; }
    body[data-theme="cockpit"] .ck-chips .ck-chip { display:none; }
    body[data-theme="cockpit"] #ckMain { padding:6px; }
  }
  #ckStrip { align-items:center; gap:6px; flex-wrap:wrap; margin:-2px 0 6px; font-size:12px; }
  #ckStrip .ck-pill { padding:1px 7px; font-size:10.5px; }
  #ckStrip .ck-btn { padding:1px 8px; }
  /* very narrow: icons for the secondary actions */
  @media (max-width: 420px) {
    body[data-theme="cockpit"] .ck-lbl { display:none; }
    body[data-theme="cockpit"] #ckStrip .ck-pills { display:none; }
  }
  /* short panels: the transcript keeps the space */
  @media (max-height: 520px) {
    body[data-theme="cockpit"] textarea#prompt { min-height:34px; }
    body[data-theme="cockpit"] #ckOutput .panel { max-height:22vh; }
  }
</style>

</head>
<body data-theme="${safeTheme}">
<div id="ckShell"><div id="ckMain">
  <div id="ckHead"></div>
  <div id="ckStrip"></div>

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
    <button id="refresh"> ↻ </button>
    <label>Execution</label>
    <select id="execution">
      <option value="cloud_only">cloud only</option>
      <option value="prefer_local_agent">prefer agent</option>
      <option value="local_agent_only">agent only</option>
    </select>


    <button id="newChat" title="Starts a new conversation in this mode; the current one goes to the history (cockpit: History)">＋ New chat</button>
    <button id="clear">Clear Session</button>
    <button id="memoryBtn" title="Open the CLike Memory panel (project RAG and CLike guide), or bring it to the front">🧠 Memory</button>

    <label class="ctl">
      Scope
      <select id="historyScope">
        <option value="singleModel">Model</option>
        <option value="allModels">All</option>
      </select>
    </label>
    <label class="ctl">
      Layout
      <select id="layout" title="Chat layout (clike.chat.theme)">${layoutOptions}</select>
    </label>
    <span id="bmadBadge" class="badge" style="display:none" title="Harper commands run with the BMAD methodology (set in the cockpit layout)">BMAD</span>
    <span id="status">Ready</span>
    <span id="sp" class="spinner">⏳</span>
  </div>
  <div id="runCard" role="status" aria-live="polite"></div>

  <div id="chat" class="chat" aria-label="Chat transcript"></div>

  <div class="row" id="promptRow">
    <div id="acBox" aria-live="polite"><div id="acSig"></div><div id="acErr"></div><div id="acMenu" role="listbox"></div></div>
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
  <div class="row" id="ckActions">
    <button id="sendChat">Send</button>
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
</div><aside id="ckSide" aria-label="Cockpit"></aside><div id="ckScrim"></div></div>

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
  {cmd:'Docs', desc:'docs/INSTALL.md (install, agents, MCP for Claude Code / Codex) and docs/GET_STARTED.md (first project, agent chat, auto-eval)'},
  {cmd:'/adopt [--area <name>] [--dry-run]', desc:'Brings an existing project (not built with CLike) into CLike, after /init: surveys its areas (the services of a monorepo), stack, commands, runtimes, CI, documentation and git history; writes the areas to .clike/project.json and the code map docs/harper/CODEMAP.md; runs the tests each area already has in the eval sandbox (the baseline); indexes the documentation and the code into the project memory; then the analysis writes IDEA, SPEC, PLAN with the adopted REQs, TECH_CONSTRAINTS, lane guides, HOWTO_RUN and integrates the root README (every existing section kept). Reports: docs/harper/ADOPT_<date>.md and the EXTEND report. --area adopts one area at a time; --dry-run writes only the report. The code of the project is never changed. See docs/adopt.md'},
  {cmd:'/init [<name> [<parent folder>] [--force]]', desc:'Initializes the Harper project. With no parameters: the folder open in VS Code, in place (existing files kept). With a name: <parent folder>/<name> (--force: into a non-empty folder, existing files kept). A repository that already has its own review / PR / CI process keeps it: the CLike CODEOWNERS, PR template and workflow go to .clike/proposals/'},
  {cmd:'/status', desc:'Shows the Harper project/context status'},
  {cmd:'/where', desc:'Shows the Harper workspace/doc-root path'},
  {cmd:'/switch <name|path>', desc:'Switches to another Harper project'},
  {cmd:'/idea', desc:'Formalizes the IDEA.md (optional)'},
  {cmd:'/idea --methodology bmad --agent analyst', desc:'Frames IDEA.md with BMAD analyst guidance'},
  {cmd:'/idea --extend [--from attachment] [--release vN] [--dry-run]', desc:'Next release of a delivered project. Inputs: the files in docs/inputs/vN/ (background in docs/reference/vN/), no attachment needed; attach more files to add to them; with docs/inputs/vN/ empty an attachment is required. They are merged into IDEA, SPEC and TECH_CONSTRAINTS; PLAN gets new REQs typed ADDED / MODIFIED / REMOVED; delivered REQs read-only; EXTEND report with CLike verification; baseline tagged harper/v<N-1>. Then /kit /eval /gate the new REQs and /finalize'},
  {cmd:'/idea --extend --methodology bmad --agent analyst|pm|architect|ux', desc:'Next release with BMAD guidance: the role leads the angle (analyst: intent and scope, pm: requirements, default; architect: REQ slicing and supersedes; ux: new screens, guidance only)'},
  {cmd:'/spec [file|text]', desc:'Generates/Updates SPEC.md from the IDEA; ordinary choices the IDEA leaves open are decided with the simplest reasonable option in Assumptions, only questions the owner must answer stay open (OPEN-01); with Use Cases: every production journey as numbered steps (UC-01.1…), error flows, the production data path and the prerequisites it implies (e.g. an authenticated API implies sign-in, session expiry, roles), in scope or provided by someone named'},
  {cmd:'/spec --methodology bmad --agent pm', desc:'Builds SPEC guidance with BMAD product management focus'},
  {cmd:'/plan [spec_path]', desc:'Generates/Updates PLAN.md from the SPEC; each REQ lists the use-case steps it implements (covers) and CLike then reports every SPEC step no REQ covers (⚠ USE CASES); each REQ says whether it is KIT-ready (kit_ready, blockers: only questions the owner must answer, ordinary choices are decided in the SPEC Assumptions) and CLike lists those that wait (⚠ KIT READINESS)'},
  {cmd:'/extend [REQ-ID] "<title>" | --after REQ-ID [--from attachment]', desc:'Appends new REQs to PLAN.md/plan.json without modifying consolidated REQs'},
  {cmd:'/add-req', desc:'Alias for /extend'},
  {cmd:'/kit [REQ-ID] [--integrity|--hardener|--promotion-eval|--phases=...]', desc:'Runs base KIT by default, or explicit follow-up KIT phases on an existing/generated candidate. Candidate in runs/kit/<REQ>/ (src/, test/, ci/, docs/, root/ for repository-root files like scripts/ or deploy/); --repair uses the latest eval failures'},
  {cmd:'/kit <REQ-ID> (clike.kit.acceptanceFirst)', desc:'Acceptance-first: tests and eval profile from SPEC/PLAN written and locked first, then the code against them'},
  {cmd:'/kit REQ-001 --repair --methodology bmad --agent developer', desc:'Runs a governed BMAD developer repair pass inside KIT candidate roots'},
  {cmd:'/autopilot [N] [--executor cloud|codex|claude] [--methodology bmad] | stop | status', desc:'Runs the REQs of the plan unattended, in dependency order: /kit → /eval --fix → /gate for each, with the configured executor (cloud model, Codex or Claude Code; --executor chooses it for this run, then the previous one is restored; --methodology bmad runs the KIT as BMAD developer and the eval with the QA advisory) and the same locks, gate and audit as by hand. It knows where it is: a REQ resumes at /kit, /gate (its last eval passed on the current files) or /eval --fix; a parked REQ stays parked until you change its files. An interrupted run (VS Code closed, crash) resumes by itself when VS Code opens again (clike.autopilot.resumeOnStartup). A REQ the plan marks not KIT-ready is parked before /kit with its questions; a REQ that needs you (eval or gate not passing, --accept, a missing tool or value) is parked with its reason and the REQs that do not depend on it go on; a provider quota/rate limit or CLike services down wait and retry (clike.autopilot.quotaWaitMinutes, quotaRetries). N = stop after N promoted REQs; stop = after the current step (Cancel = now). Ends at /finalize, which stays yours. Report: runs/autopilot/report.md (REQs promoted, parked and why, repair cycles, test fixes to review). Needs clike.gate.autoPromote merge or off. From Claude Code / Codex / a terminal: MCP tool harper_autopilot and scripts/clike-autopilot.sh (.ps1)'},
  {cmd:'/tools [search <text> | add <tool[@version]>… | update [tool…] | remove <tool>…]', desc:'Native tools of the eval sandbox (kcat, mysqldump, aws, az, kubectl, terraform, jdk@17…). CLike installs what an eval needs on its own (it asks first, clike.evalTools.install); /tools lists the catalog and what is installed with versions (and reminds you after 30 days), add installs and approves for this project (.clike/eval-tools.yaml), update rebuilds them at the latest versions and shows what changed (the previous version stays if one fails), remove withdraws the approval. Versions are locked: a new tools volume is rebuilt identical; ./rebuild.sh --update-tools updates them with the stack'},
  {cmd:'/eval <REQ-ID>', desc:'Runs the REQ acceptance checks (LTC) in the eval sandbox; with clike.eval.regression also the checks of the promoted REQs. A promoted REQ test that fails once and passes on a re-run is a nondeterministic warning, not a regression; a regression caused by files the candidate replaced names them, with a short diff, for the repair'},
  {cmd:'/eval <REQ-ID> --fix ["hint"]', desc:'Auto-eval: eval, then on failure a KIT repair from the real failures, then eval again (max clike.autoEval.maxCycles, default 2, plus up to clike.autoEval.extraCyclesOnProgress while the failures decrease). Tests stay locked. Re-run it to continue; the optional hint guides the fix. It stops instead of repairing when the failure is not the code: sandbox out of resources (restart it), a native tool missing (/tools), a workspace CLike could not prepare'},
  {cmd:'/eval <REQ-ID> --supersede REQ-x#<check|path::test> "reason"', desc:'Declare a check or test of a delivered REQ that this open REQ changes on purpose (the release extends what it pins: a field set, the last migration…), then run the eval: written to the plan (supersedes, amends) and recorded in runs/extend/declared-supersedes.jsonl. A repair never changes the plan: this is your decision'},
  {cmd:'/eval <REQ-ID> --accept "reason"', desc:'Accept a deliberate edit of the REQ tests or ci/ (e.g. a promoted REQ LTC completed by hand) without a new /kit: recorded with your name and reason in the audit log; an edit that removes or weakens a check or adds a skip still needs /kit'},
  {cmd:'/eval REQ-001 --methodology bmad --agent qa', desc:'Runs canonical eval, then attaches BMAD QA advisory guidance'},
  {cmd:'/gate <REQ-ID> [--auto-merge|--ask|--no-promote] [--fix ["hint"]]', desc:'Promotion gate: PASS if the checks (and the regression checks) pass — when nothing changed since a passing /eval its verdict is reused, no second run; warnings do not block unless clike.gate.strictWarnings. With --fix a failing gate gets the same KIT repair as /eval --fix (tests stay locked, same cycle limits), then a full gate again. On PASS the REQ is promoted by auto-merge (3-way per file, conflicts never written) with a report in runs/kit/<REQ>/promotion/ (clike.gate.autoPromote: merge | ask | off); --auto-merge forces it, --ask shows the strategy list (auto-merge first), --no-promote skips it'},
  {cmd:'/plan --methodology bmad --agent architect', desc:'Plans with BMAD architecture guidance while CLike owns PLAN.md and plan.json'},
  {cmd:'/plan --methodology bmad --agent pm', desc:'Plans with BMAD product slicing and acceptance guidance'},
  {cmd:'/spec --methodology bmad --agent ux', desc:'Builds SPEC guidance with UX journeys, states, and accessibility focus'},
  {cmd:'/agent-session [new|new all]', desc:'Agent chat sessions: shows them; new starts a new conversation with the agent in the current mode (new all: every mode)'},
  {cmd:'/agent-model list', desc:'Lists the models you can set: Codex from your Codex login, Claude Code its aliases (opus, sonnet, haiku) and the Claude ids of the catalog; (cloud too) marks a model the cloud selector has as well. The cloud model is chosen in the chat model selector, separately'},
  {cmd:'/agent-model [claude|codex] [model]', desc:'Without arguments: shows the execution (cloud/agent), the default agent and the models in use. With arguments: sets the model of the local agent (claude: opus, sonnet, haiku or an exact id; codex: a model id). Applies to chat and Harper phases; saved in the workspace settings'},
  {cmd:'/agent-default codex|claude|auto', desc:'Sets the preferred local agent executor (works in Free, Coding and Harper; does not change mode)'},
  {cmd:'Agent chat (execution = agent)', desc:'Free: questions only, nothing is written. Coding and Harper free text: the agent can also create files, only under generated/<id>/ (Harper artifacts change only through /spec, /plan, /kit, ...)'},
  {cmd:'Settings (agent chat)', desc:'clike.agentChat.approvals: ask (default) — in Coding and Harper every edit/command of Claude Code or Codex waits for Allow / Allow all this turn / Deny, writes outside generated/ are denied; auto — no questions'},
  {cmd:'Settings (eval tools)', desc:'clike.evalTools.install: ask (default) — before an eval or gate CLike finds the native tools the REQ needs (environment.tools in ci/LTC.json, programs the code runs, a check that stopped on a missing program) and asks Install / Always for this project / No; always installs from the catalog without asking; never does not install. .clike/eval-tools.yaml: tools approved for the project (installed without asking) and custom conda-forge entries — see docs/auto-eval.md'},
  {cmd:'Settings (auto-eval)', desc:'clike.autoEval.maxCycles (2), clike.autoEval.extraCyclesOnProgress (3), clike.autoEval.afterKit, clike.autoEval.agentEvalChecks (8: re-runs of failed checks a local agent may do in the sandbox while it repairs), clike.eval.regression (on), clike.gate.strictWarnings, clike.kit.acceptanceFirst — see docs/auto-eval.md'},
  {cmd:'/finalize', desc:'Brings the promoted solution to running and configured (asks first if some REQs are not promoted). The REQ tests are not run again (the gates did): CLike installs, builds, configures, starts and smoke-checks the solution in the sandbox, repairing until it passes. Writes docs/harper/FINALIZE_REPORT.md (how to start and see it, configuration, missing information, what changed and why), scripts/setup_local + start_solution_local, docs/harper/SOLUTION_EVAL.md; then offers to configure and start it locally'},
  {cmd:'/finalize --methodology bmad --agent tech-writer', desc:'Finalizes with BMAD documentation guidance'},
  {cmd:'/rag <query>', desc:'Searches the RAG and shows top results'},
  {cmd:'/rag +<N>', desc:'Adds RAG result #N from the last search to the attached files'},
  {cmd:'/rag list', desc:'Shows current attached files (inline + RAG)'},
  {cmd:'/rag clear', desc:'Clears the current attached files'},
  {cmd:'/ragIndex [glob]', desc:'Manually indexes files into the RAG. Examples: /ragIndex docs/**/*.md | /ragIndex **/*'},
  {cmd:'/ragSearch <query>', desc:'Searches the RAG and shows top results'}
];

// --- Bootstrap sync: select the model only when the UI is fully ready ---
const boot = { gotInit:false, gotModels:false, gotHydrate:false, done:false, savedModel:null };
// Last /rag results, used by /rag +N.
let lastRagHits = [];

function finalizeBootIfReady() {
  if (boot.done) return;
  // Wait for all initial state, models, and first hydration.
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
  // Includiamo anche executionPreference così lo stato persistito lato extension
  // coincide col valore mostrato nel selettore già dal primo comando.
  vscode.postMessage({
    type: 'uiChanged',
    mode: mode.value,
    model: model.value,
    ...(execution && execution.value ? { executionPreference: execution.value } : {}),
  });

  boot.done = true;
}


function ensureHelpDOM() {
  var overlay = document.getElementById('clikeHelpOverlay');
  if (!overlay) {
    overlay = document.createElement('div');
    overlay.id = 'clikeHelpOverlay';
    // a click on the backdrop closes the help
    overlay.addEventListener('click', function (ev) { if (ev.target === overlay) closeHelpOverlay(); });
    document.body.appendChild(overlay);
  } else {
    overlay.innerHTML = '';
  }

  var card = document.createElement('div');
  card.id = 'clikeHelpCard';

  var head = document.createElement('div');
  head.className = 'help-head';
  var h2 = document.createElement('h2');
  h2.textContent = 'CLike — Quick help';
  var filter = document.createElement('input');
  filter.id = 'clikeHelpFilter';
  filter.type = 'search';
  filter.placeholder = 'Filter commands…';
  filter.addEventListener('input', function () { renderHelpList(filter.value); });
  var btn = document.createElement('button');
  btn.id = 'clikeHelpClose';
  btn.setAttribute('aria-label', 'Close');
  btn.textContent = '×';
  btn._bound = true;
  btn.addEventListener('click', closeHelpOverlay);
  head.appendChild(h2);
  head.appendChild(filter);
  head.appendChild(btn);

  var list = document.createElement('div');
  list.id = 'clikeHelpList';

  card.appendChild(head);
  card.appendChild(list);
  overlay.appendChild(card);
}

function openHelpOverlay() {
  ensureHelpDOM();
  try { renderHelpList(''); } catch {}
  var overlay = document.getElementById('clikeHelpOverlay');
  if (overlay) overlay.style.display = 'block';
  var filter = document.getElementById('clikeHelpFilter');
  if (filter) filter.focus();
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
  if (ev.key === 'Escape') {
    var overlay = document.getElementById('clikeHelpOverlay');
    if (overlay && overlay.style.display === 'block') closeHelpOverlay();
  }
});


const attachmentsByMode = { free: [], harper: [], coding: [] };
function currentMode() { return document.getElementById('mode').value; }
function currentModel() { return document.getElementById('model').value; }
function currentExecution() {
  const el = document.getElementById('execution');
  return el ? el.value : 'local_agent_only';
}

// Q1: 'agent only' is always the default executor. When no cloud provider key
// is configured (providers.any_cloud === false) every other Execution option is
// disabled, leaving only local-agent execution selectable.
let lastProviders = null;
function applyExecutionGating(providers) {
  if (providers) lastProviders = providers;
  const eff = providers || lastProviders;
  const sel = document.getElementById('execution');
  if (!sel) return;
  const hasCloud = !eff || eff.any_cloud !== false;
  Array.from(sel.options).forEach(opt => {
    opt.disabled = (opt.value !== 'local_agent_only') && !hasCloud;
  });
  if (!hasCloud && sel.value !== 'local_agent_only') {
    sel.value = 'local_agent_only';
    try {
      post('uiChanged', {
        mode: document.getElementById('mode').value,
        model: document.getElementById('model').value,
        executionPreference: 'local_agent_only'
      });
    } catch {}
  }
}
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
const execution = el('execution');
const prompt = el('prompt');
const btnRefresh = el('refresh');
const btnClear = el('clear');
const btnChat = el('sendChat');
const btnApply = el('apply');
const btnCancel = el('cancel');
const btnHelp = el('helpBtn');
const historyScope = el('historyScope');
const btnAttach = el('btnAttach');
const btnAttachMenu = el('attach-menu');
const btnAttachWs = el('attach-menu-ws');
const btnAttachExt = el('attach-menu-ext');
const statusEl = el('status');
const sp = el('sp');
const chat = el('chat');
const preText = el('text');
const preDiffs = el('diffs');
const preFiles = el('files');

let selectedPaths = new Set();
let lastRun = null;
let uiBusy = false;
let harperCommandInFlight = false;

function lockHarperUi() {
  harperCommandInFlight = true;
  setBusy(true);
}

function unlockHarperUi() {
  harperCommandInFlight = false;
  setBusy(false);
}

function isBusy() {
  return uiBusy;
}

function setNodeDisabled(node, disabled) {
  if (!node) return;

  if (disabled) {
    if (!Object.prototype.hasOwnProperty.call(node.dataset, 'prevDisabled')) {
      node.dataset.prevDisabled = node.disabled ? '1' : '0';
    }
    node.disabled = true;
    return;
  }

  const prevDisabled = node.dataset.prevDisabled === '1';
  node.disabled = prevDisabled;
  delete node.dataset.prevDisabled;
}

function postAndLock(type, payload = {}) {
  setBusy(true);
  vscode.postMessage({ type, ...payload });
}

function isHarperBlockingSlashCommand(cmd) {
  return new Set([
    '/init',
    '/adopt',
    '/idea',
    '/spec',
    '/plan',
    '/kit',
    '/eval',
    '/gate',
    '/finalize'
  ]).has(String(cmd || '').toLowerCase());
}

function lockHarperSlashIfNeeded(slash) {
  if (!slash) return false;
  if (currentMode() !== 'harper') return false;
  if (!isHarperBlockingSlashCommand(slash.cmd)) return false;

  lockHarperUi();
  return true;
}
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
  // Keep placeholders and button labels consistent.
  if (isHarper) {
    prompt.placeholder = 'Harper bot — type /help for commands...';
  } else {
    prompt.placeholder = 'Type your prompt...';
  }
  // Single send button. The mode decides the route on submit:
  // free -> chat (Q&A), coding -> code generation, harper -> chat (Q&A);
  // Harper phase generation is driven by slash commands.
  const c1 = document.getElementById('sendChat');
  if (c1) c1.textContent = 'Send';
}

// --- Slash commands: parsed by the shared slash-parser.js (injected below) ---
${buildBrowserSlashParserSource()}
${buildBrowserSlashCompleteSource()}

function getHelpItems() {
  var fallback = HELP_COMMANDS;
  try {
    var g = (typeof window !== 'undefined') ? window.HELP_COMMANDS : undefined;
    if (Array.isArray(g) && g.length) return g;
  } catch {}
  return fallback;
}

// Help sections, matched on the command text in this order.
function helpStartsWith(c, prefixes) {
  for (var i = 0; i < prefixes.length; i++) { if (c.indexOf(prefixes[i]) === 0) return true; }
  return false;
}
var HELP_GROUPS = [
  { title: 'Start & project', test: function (c) { return helpStartsWith(c, ['/help', 'Docs', '/init', '/adopt', '/status', '/where', '/switch']); } },
  { title: 'Agents', test: function (c) { return helpStartsWith(c, ['/agent-', 'Agent chat', 'Settings (agent']); } },
  { title: 'Eval & gate', test: function (c) { return helpStartsWith(c, ['/eval', '/gate', '/autopilot', '/tools', 'Settings (auto-eval', 'Settings (eval tools']); } },
  { title: 'Harper phases', test: function (c) { return helpStartsWith(c, ['/idea', '/spec', '/plan', '/extend', '/add-req', '/kit', '/finalize']); } },
  { title: 'RAG', test: function (c) { return helpStartsWith(c, ['/rag']); } },
  { title: 'Other', test: function () { return true; } },
];

function renderHelpList(query) {
  var list = document.getElementById('clikeHelpList');
  if (!list) return;
  var q = String(query || '').trim().toLowerCase();
  var items = getHelpItems().filter(function (it) {
    if (!it || !it.cmd) return false;
    return !q || (String(it.cmd) + ' ' + String(it.desc || '')).toLowerCase().indexOf(q) >= 0;
  });
  var buckets = HELP_GROUPS.map(function () { return []; });
  items.forEach(function (it) {
    var c = String(it.cmd);
    for (var g = 0; g < HELP_GROUPS.length; g++) {
      if (HELP_GROUPS[g].test(c)) { buckets[g].push(it); break; }
    }
  });
  var html = '';
  HELP_GROUPS.forEach(function (group, g) {
    if (!buckets[g].length) return;
    html += '<h3>' + escapeHtml(group.title) + '</h3>';
    buckets[g].forEach(function (it) {
      html += '<div class="help-row"><div class="help-cmd">' + escapeHtml(String(it.cmd)) +
        '</div><div class="help-desc">' + escapeHtml(String(it.desc || '')) + '</div></div>';
    });
  });
  list.innerHTML = html || '<div class="help-empty">No command matches “' + escapeHtml(q) + '”.</div>';
}


function getHelpListSafe() {
  try {
    var maybe = (typeof window !== 'undefined') ? window.HELP_COMMANDS : undefined;
    if (Array.isArray(maybe) && maybe.length) return maybe;
  } catch (e) { /* ignore */ }
  return HELP_COMMANDS;
}

function stringifyUiErrorMessage(value) {
  if (typeof value === 'string') return value;
  if (value instanceof Error) return value.message || String(value);
  try {
    return JSON.stringify(value || 'unknown', null, 2);
  } catch {
    return String(value || 'unknown');
  }
}

function handleSlash(slash) {
  if (!slash) return;

  if (slash.error) {
    const errorText = stringifyUiErrorMessage(slash.error || 'Invalid slash command.');
    const text = 'Error: ' + errorText;
    try { bubble('assistant', text, 'system'); } catch {}
    try {
      const pre = document.getElementById('text');
      if (pre) pre.textContent = text;
      setTab('text');
    } catch {}
    return true;
  }

  const slashCmd = String(slash.cmd || '').toLowerCase();
  // Harper-only commands: project utilities and all Harper phase commands.
  // /agent-default is intentionally NOT here — it sets the preferred local
  // executor and must be usable in Free (Q&A) and Coding too.
  const isHarperModeOnlyCommand = new Set([
    '/init',
    '/adopt',
    '/status',
    '/where',
    '/switch',
    '/idea',
    '/spec',
    '/plan',
    '/kit',
    '/eval',
    '/gate',
    '/tools',
    '/autopilot',
    '/finalize',
    '/extend',
    '/add-req',
  ]).has(slashCmd);

  if (isHarperModeOnlyCommand && currentMode() !== 'harper') {
    bubble('assistant', 'This command is available only in Harper mode.', 'system');
    try { prompt.value = ''; } catch {}
    return;
  }
  lockHarperSlashIfNeeded(slash);
  // dry 'Text' and 'Diffs' panels
  try { clearTextPanel(); clearDiffsPanel(); clearFilesPanel(); } catch {}

  // help: open overlay local
  if (slashCmd === '/help') {
    var items = getHelpListSafe();
    var listText = '';
    try {
      // Use a safe list: prefer window.HELP_COMMANDS, otherwise use the local fallback.
      var items;
      try {
        items = (typeof window !== 'undefined' && Array.isArray(window.HELP_COMMANDS))
          ? window.HELP_COMMANDS
          :  [];
      } catch (e0) {
        items = (typeof HELP_COMMANDS !== 'undefined' && Array.isArray(HELP_COMMANDS)) ? HELP_COMMANDS : [];
      }
      // Normalize to a real array without touching .length on unusual objects.
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
    // 2) /rag +N adds the Nth hit as a RAG attachment.
    if (a.action === 'addByIndex' && Number.isFinite(a.index)) {
      const idx = a.index - 1;
      const hit = Array.isArray(lastRagHits) ? lastRagHits[idx] : null;
      const index = a.index || 1;
      if (!hit) {
        
        bubble('assistant', "No result #"+index+" is available. Run /rag <query> first.", "system");
        return true;
      }
      const doc_index = "doc" + index;
      // Normalize the hit to a RAG attachment by id or path.
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
      bubble('assistant', lines.length ? "Attachments:\\n"+ lines.join('\\n') : 'No attachments.', 'system');
      return true;
    }
    // 4) /rag clear clears attachments.
    if (a.action === 'clear') {
      attachmentsByMode[currentMode()] = [];
      renderAttachmentChips();
      bubble('assistant', 'Attachments cleared.', 'system');
      return true;
    }
    // help/fallback
    bubble('assistant', 'Usage: /rag <query> | /rag +N | /rag list | /rag clear', 'system');
    return true;
  }

  if (slashCmd === '/adopt') {
    vscode.postMessage({ type: 'adopt', area: slash.args.area || '', dryRun: !!slash.args.dryRun });
    return;
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
      // glob già estratto da parseSlash
      var gl = (slash.args && typeof slash.args.glob === 'string')
        ? slash.args.glob
        : '';
      
      vscode.postMessage({ type: 'ragIndex', glob: gl || '' });
      try {
        bubble(
          'user',
          slash.cmd + (gl ? (' ' + gl) : ''),
          (model && model.value) ? model.value : 'auto'
        );
      } catch {}
      try { prompt.value = ''; } catch {}
      return true;
    }

    if (cmdLower === '/ragsearch') {
      // query già estratta da parseSlash
      var q = '';
      if (slash.args) {
        if (typeof slash.args.query === 'string') {
          q = slash.args.query;
        } else if (slash.args.name) {
          q = String(slash.args.name || '');
        }
      }

      vscode.postMessage({ type: 'ragSearch', q: q || '' });
      try {
        bubble(
          'user',
          '/ragSearch ' + (q || ''),
          (model && model.value) ? model.value : 'auto'
        );
      } catch {}
      try { prompt.value = ''; } catch {}
      return true;
    }


  } catch (eRagSlash) { console.warn('rag slash err', eRagSlash); }
  if (slash.cmd === '/where') {
    vscode.postMessage({ type: 'where' });
    return;
  }
  if (slash.cmd === '/autopilot') {
    try { bubble('user', prompt.value || '/autopilot', 'system'); } catch {}
    vscode.postMessage({ type: 'autopilot', action: slash.args.action, max: slash.args.max || 0,
      executor: slash.args.executor || '', methodology: slash.args.methodology || '' });
    try { prompt.value = ''; } catch {}
    return;
  }
  if (slash.cmd === '/tools') {
    try { bubble('user', '/tools ' + [slash.args.action].concat(slash.args.names || []).join(' '), 'system'); } catch {}
    vscode.postMessage({ type: 'evalTools', action: slash.args.action, names: slash.args.names || [] });
    try { prompt.value = ''; } catch {}
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
    if (
    slash.cmd === '/idea' ||
    slash.cmd === '/spec' ||
    slash.cmd === '/plan' ||
    slash.cmd === '/extend' ||
    slash.cmd === '/add-req' ||
    slash.cmd === '/kit' ||
    slash.cmd === '/finalize' ||
    slash.cmd === '/agent-default' ||
    slash.cmd === '/agent-model' ||
    slash.cmd === '/agent-session'
  ) {
    var modeVal = (mode && mode.value) ? mode.value : 'harper';
    var key = modeVal;
    var atts = [];

    try {
      if (typeof attachmentsByMode !== 'undefined' && attachmentsByMode && attachmentsByMode[key]) {
        atts = attachmentsByMode[key].slice(0);
      }
    } catch {}

    var rawCommand = '';
    try {
      rawCommand = (typeof prompt !== 'undefined' && prompt && typeof prompt.value === 'string')
        ? String(prompt.value || '').trim()
        : '';
    } catch {}

    var firstTarget = '';
    var targetText = '';
    var phaseSuffix = '';

    try {
      if (Array.isArray(slash.args?.targets) && slash.args.targets.length > 0) {
        firstTarget = String(slash.args.targets[0] || '').trim().toUpperCase();
        targetText = slash.args.targets.join(' ');
      } else if (typeof slash.args?.targets === 'string' && slash.args.targets.trim()) {
        firstTarget = slash.args.targets.trim().toUpperCase();
        targetText = firstTarget;
      }

      if (Array.isArray(slash.args?.phases) && slash.args.phases.length) {
        phaseSuffix = ' --phases=' + slash.args.phases.join(',');
      }

      bubble(
        'user',
        rawCommand || (slash.cmd + (targetText ? (' ' + targetText) : '') + phaseSuffix),
        (model && model.value) ? model.value : 'auto',
        atts
      );
    } catch {}

    const msg = {
      type: 'harperRun',
      cmd: slash.cmd === '/add-req' ? 'extend' : slash.cmd.slice(1),
      attachments: atts,
      rawCommand: rawCommand || null
    };
    if (slash.args?.methodology) msg.methodology = slash.args.methodology;
    if (slash.args?.agent) msg.agent = slash.args.agent;
    if (slash.args?.methodology_context) msg.methodology_context = slash.args.methodology_context;

    if (slash.cmd === '/agent-session') {
      msg.sessionAction = slash.args?.action || '';
    }
    if (slash.cmd === '/agent-model') {
      msg.agentName = slash.args?.agent || '';
      msg.agentModel = slash.args?.model || '';
    }
    if (slash.cmd === '/agent-default') {
      msg.value = slash.args?.value || '';
      console.log('[CLike][chat-ui][/agent-default] value =', JSON.stringify(msg.value));

    }

    if (slash.cmd === '/kit') {
      msg.targets = slash.args?.targets ?? null;
      msg.targetReqId = firstTarget || null;
      msg.phases = slash.args?.phases ?? null;
      msg.repair = !!slash.args?.repair;
    } else if (slash.cmd === '/extend' || slash.cmd === '/add-req') {
      msg.anchorReq = slash.args?.anchorReq || '';
      msg.explicitReq = slash.args?.explicitReq || '';
      msg.fromAttachment = !!slash.args?.fromAttachment;
      msg.rawInput = slash.args?.rawInput || '';
      msg.alias = slash.args?.alias || null;
    } else if (slash.cmd === '/idea' && slash.args?.extend) {
      // /idea --extend runs the extend phase in cascade mode (IDEA → SPEC → PLAN delta)
      msg.cmd = 'extend';
      msg.extendMode = 'cascade';
      msg.fromAttachment = !!slash.args.fromAttachment;
      msg.dryRun = !!slash.args.dryRun;
      msg.release = slash.args.release || '';
      msg.rawInput = slash.args.rawInput || '';
    } else if (slash.cmd === '/idea') {
      msg.name = slash.args.name || '';
    } else if (slash.cmd === '/finalize' && slash.args?.verifyOnly) {
      msg.verifyOnly = true;
    } 

    console.log('[CLike][chat-ui][harperRun] cmd =', JSON.stringify(slash.cmd));
    console.log('[CLike][chat-ui][harperRun] rawCommand =', JSON.stringify(rawCommand));
    console.log('[CLike][chat-ui][harperRun] slash.args =', JSON.stringify(slash.args));
    console.log('[CLike][chat-ui][harperRun] firstTarget =', firstTarget);
    console.log('[CLike][chat-ui][harperRun] msg.targets =', JSON.stringify(msg.targets));
    console.log('[CLike][chat-ui][harperRun] msg.targetReqId =', JSON.stringify(msg.targetReqId));
    console.log('[CLike][chat-ui][harperRun] msg.phases =', JSON.stringify(msg.phases));

    if (slash.cmd === '/agent-default' || slash.cmd === '/agent-model' || slash.cmd === '/agent-session') {
      post(msg.type, msg);
    } else {
      postAndLock(msg.type, msg);
    }

    attachmentsByMode[currentMode()] = [];
    renderAttachmentChips();

    return true;

    return true;
  }
  
  //EVALS
  if (slashCmd === '/eval' || slashCmd === '/gate') {
    var modeVal = (mode && mode.value) ? mode.value : 'harper';
    var key = modeVal;
    var atts = [];
    try {
      if (typeof attachmentsByMode !== 'undefined' && attachmentsByMode && attachmentsByMode[key]) {
        atts = attachmentsByMode[key].slice(0);
      }
    } catch {}

    var firstTarget = '';
    if (Array.isArray(slash.args?.targets) && slash.args.targets.length > 0) {
      firstTarget = String(slash.args.targets[0] || '').trim().toUpperCase();
    } else if (typeof slash.args?.targets === 'string' && slash.args.targets.trim()) {
      firstTarget = slash.args.targets.trim().toUpperCase();
    }

    const path_ltc_json = 'runs/kit/' + firstTarget + '/ci/LTC.json';
    console.log('slash.args', slash.args);

    try {
      const targetText = Array.isArray(slash.args?.targets)
        ? slash.args.targets.join(' ')
        : (slash.args?.targets || '');

      // the command as typed (every flag, e.g. --methodology bmad --agent qa); rebuilt when not typed
      var typed = '';
      try {
        typed = (typeof prompt !== 'undefined' && prompt && typeof prompt.value === 'string') ? String(prompt.value || '').trim() : '';
      } catch {}
      if (typed.toLowerCase().split(/\\s+/)[0] !== slashCmd) typed = '';
      bubble(
        'user',
        typed || (slash.cmd + (targetText ? (' ' + targetText) : '') + (slash.args?.fix ? ' --fix' + (slash.args.hint ? ' "' + slash.args.hint + '"' : '') : '') + (slash.args?.accept !== undefined ? ' --accept' + (slash.args.accept ? ' "' + slash.args.accept + '"' : '') : '') +
          (slash.args?.methodology ? ' --methodology ' + slash.args.methodology : '') + (slash.args?.agent ? ' --agent ' + slash.args.agent : '')),
        (model && model.value) ? model.value : 'auto',
        atts
      );
    } catch {}

    const msg = {
      type: 'harperEDD',
      cmd: slash.cmd.slice(1),
      attachments: atts,
      argument: firstTarget || ''
    };
    if (slash.args?.methodology) msg.methodology = slash.args.methodology;
    if (slash.args?.agent) msg.agent = slash.args.agent;
    if (slash.args?.methodology_context) msg.methodology_context = slash.args.methodology_context;

    msg.targets = slash.args?.targets ?? null;
    msg.targetReqId = firstTarget || null;
    msg.running = slash.args?.testMode ?? null;
    msg.modeContent = slash.args?.modeContent ?? null;
    if (slash.args?.fix) msg.fix = { hint: slash.args.hint || '' };
    if (slash.args?.promote) msg.promote = slash.args.promote;
    if (slash.args?.accept !== undefined) msg.accept = { reason: slash.args.accept };
    if (slash.args?.supersede) msg.supersede = slash.args.supersede;
    msg.path=path_ltc_json
    postAndLock(msg.type, msg);
    attachmentsByMode[currentMode()] = [];
    renderAttachmentChips();
    return true;
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

// Image previews from server files: raster types only, built as DOM nodes (no HTML strings).
var PREVIEW_IMAGE_TYPES = ['image/png', 'image/jpeg', 'image/gif', 'image/webp'];
function appendImagePreviews(container, images) {
  if (!Array.isArray(images)) return;
  images.forEach(function (f) {
    var mime = String((f && f.mime) || '').toLowerCase();
    var b64 = String((f && f.content_base64) || '');
    if (PREVIEW_IMAGE_TYPES.indexOf(mime) === -1 || !/^[A-Za-z0-9+/=]+$/.test(b64)) return;
    var img = document.createElement('img');
    img.src = 'data:' + mime + ';base64,' + b64;
    img.alt = String((f && f.path) || 'image');
    img.style.cssText = 'max-width:160px;max-height:120px;margin:4px;border:1px solid #ddd;border-radius:6px';
    container.appendChild(img);
  });
}

// Native agent chat: a live bubble fed by the agent's streamed events (text as it is written, the
// tools it uses); the final answer bubble replaces it when the turn ends.
var agentLive = null;
function agentLiveEnd() {
  if (agentLive && agentLive.wrap.parentNode) agentLive.wrap.parentNode.removeChild(agentLive.wrap);
  agentLive = null;
}
function agentLiveStart(label) {
  agentLiveEnd();
  const wrap = document.createElement('div');
  wrap.className = 'msg ai';
  const b = document.createElement('div');
  b.className = 'bubble agent-live';
  const badge = document.createElement('span');
  badge.className = 'badge';
  badge.textContent = String(label || 'agent') + ' · live';
  const steps = document.createElement('div');
  steps.className = 'meta';
  const text = document.createElement('div');
  text.style.whiteSpace = 'pre-wrap';
  b.appendChild(badge);
  b.appendChild(steps);
  b.appendChild(text);
  wrap.appendChild(b);
  chat.appendChild(wrap);
  chat.scrollTop = chat.scrollHeight;
  agentLive = { wrap: wrap, steps: steps, text: text };
}
function agentLiveEvent(ev) {
  if (!ev) return;
  if (ev.kind === 'start') { agentLiveStart(ev.label); return; }
  if (ev.kind === 'end') { agentLiveEnd(); return; }
  if (!agentLive) return;
  if (ev.kind === 'delta') {
    agentLive.text.textContent += String(ev.text || '');
  } else if (ev.kind === 'tool' || ev.kind === 'error') {
    const line = document.createElement('div');
    line.textContent = (ev.kind === 'error' ? '⚠ ' : '↳ ') + String(ev.label || ev.text || '');
    agentLive.steps.appendChild(line);
  }
  chat.scrollTop = chat.scrollHeight;
}

// ---- answers as cards: what CLike says while a command runs is one log card (a line per message,
// with its time); a model's answer gets light markdown (escaped first, then code, bold, titles) ----
var LOG_GAP_MS = 30 * 60000;
function logKind(text) {
  var c = String(text || '').trim().charAt(0);
  if (c === '✔') return 'ok';
  if (c === '✖' || /^Error:/.test(text)) return 'ko';
  if (c === '⚠') return 'warn';
  if (c === '▶' || c === '↻') return 'run';
  if (c === '⏹' || c === '⏸' || c === '⏱' || c === '⏳') return 'stop';
  return 'info';
}
function logTime(ms) {
  var d = new Date(ms);
  return String(d.getHours()).padStart(2, '0') + ':' + String(d.getMinutes()).padStart(2, '0') + ':' + String(d.getSeconds()).padStart(2, '0');
}
function logCard(tsMs) {
  var wrap = document.createElement('div');
  wrap.className = 'msg ai';
  var b = document.createElement('div');
  b.className = 'bubble log-card';
  var head = document.createElement('div');
  head.className = 'log-head';
  var title = document.createElement('span');
  title.className = 'log-title';
  var stats = document.createElement('span');
  stats.className = 'log-stats';
  var more = document.createElement('button');
  more.className = 'log-more';
  more.style.display = 'none';
  var copyAll = document.createElement('button');
  copyAll.className = 'log-copy';
  copyAll.textContent = '⧉';
  copyAll.title = 'Copy the whole log';
  head.appendChild(title); head.appendChild(stats); head.appendChild(more); head.appendChild(copyAll);
  var rows = document.createElement('div');
  rows.className = 'log-rows';
  b.appendChild(head); b.appendChild(rows);
  wrap.appendChild(b);
  chat.appendChild(wrap);
  var log = { wrap: wrap, rows: rows, title: title, stats: stats, more: more, firstTs: tsMs, lastTs: tsMs, lines: [], expanded: false };
  wrap._log = log;
  copyAll.addEventListener('click', function (ev) {
    ev.stopPropagation();
    vscode.postMessage({ type: 'copyText', text: log.lines.map(function (l) { return logTime(l.ts) + '  ' + l.text; }).join('\\n') });
    copyAll.textContent = '✓';
    setTimeout(function () { copyAll.textContent = '⧉'; }, 1200);
  });
  more.addEventListener('click', function () { log.expanded = !log.expanded; logRefresh(log); });
  return log;
}
function logRefresh(log) {
  var d = new Date(log.firstTs);
  log.title.textContent = 'CLike · ' + d.toLocaleDateString() + ' ' + logTime(log.firstTs);
  var span = Math.max(0, Math.round((log.lastTs - log.firstTs) / 1000));
  log.stats.textContent = log.lines.length + ' message' + (log.lines.length === 1 ? '' : 's') +
    (span >= 60 ? ' · ' + Math.floor(span / 60) + ' min ' + (span % 60) + ' s' : span ? ' · ' + span + ' s' : '');
  var hidden = log.expanded ? 0 : Math.max(0, log.lines.length - 8);
  Array.prototype.forEach.call(log.rows.children, function (row, i) { row.style.display = i < hidden ? 'none' : ''; });
  log.more.style.display = log.lines.length > 8 ? '' : 'none';
  log.more.textContent = log.expanded ? 'show the last 8' : 'show ' + hidden + ' earlier';
}
function logLine(role, content, ts) {
  var tsMs = ts ? new Date(ts).getTime() : Date.now();
  var last = chat.lastElementChild;
  var log = last && last._log && Math.abs(tsMs - last._log.lastTs) < LOG_GAP_MS ? last._log : logCard(tsMs);
  var text = String(content || '');
  var row = document.createElement('div');
  row.className = 'log-row ' + logKind(text);
  var t = document.createElement('span');
  t.className = 'log-time';
  t.textContent = logTime(tsMs);
  t.title = new Date(tsMs).toLocaleString();
  var body = document.createElement('span');
  body.className = 'log-text';
  body.textContent = text;
  var del = document.createElement('button');
  del.className = 'log-del';
  del.textContent = '×';
  del.title = 'Remove from history';
  del.addEventListener('click', function (ev) {
    ev.stopPropagation();
    vscode.postMessage({ type: 'deleteBubble', mode: currentMode(), role: role, model: 'system', content: text });
  });
  row.appendChild(t); row.appendChild(body); row.appendChild(del);
  log.rows.appendChild(row);
  log.lines.push({ ts: tsMs, text: text });
  log.lastTs = Math.max(log.lastTs, tsMs);
  logRefresh(log);
  chat.scrollTop = chat.scrollHeight;
}
var BT3 = String.fromCharCode(96, 96, 96);
var BT = String.fromCharCode(96);
var MD_INLINE_CODE = new RegExp(BT + '([^' + BT + '\\n]+)' + BT, 'g');
function renderMd(text) {
  var parts = escapeHtml(String(text || '')).split(BT3);
  return parts.map(function (part, i) {
    if (i % 2) {
      var nl = part.indexOf('\\n');
      return '<pre class="md-code">' + (nl >= 0 ? part.slice(nl + 1) : part).replace(/\\n$/, '') + '</pre>';
    }
    return (i ? part.replace(/^\\n/, '') : part)
      .replace(MD_INLINE_CODE, '<code class="md-inline">$1</code>')
      .replace(/\\*\\*([^*\\n]+)\\*\\*/g, '<b>$1</b>')
      .replace(/^#{1,4} (.+)$/gm, '<span class="md-h">$1</span>');
  }).join('');
}

function bubble(role, content, modelName, attachments, ts, opts) {
  if (role !== 'user' && String(modelName || '') === 'system' && !(opts && opts.images && opts.images.length)) {
    logLine(role === 'system' ? 'system' : 'assistant', content, ts);
    return;
  }
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
  b.innerHTML = meta + badge + (role === 'assistant' ? renderMd(content) : escapeHtml(String(content || '')));
  
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
  // pulsante copia → il testo della bubble negli appunti (tramite l'estensione: vale in ogni webview)
  const copy = document.createElement('button');
  copy.className = 'bubble-copy';
  copy.textContent = '⧉';
  copy.title = 'Copy';
  copy.addEventListener('click', function (ev) {
    ev.stopPropagation();
    vscode.postMessage({ type: 'copyText', text: String(content || '') });
    copy.textContent = '✓';
    setTimeout(function () { copy.textContent = '⧉'; }, 1200);
  });
  b.appendChild(copy);
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

  appendImagePreviews(b, opts && opts.images);
  wrap.appendChild(b);
  chat.appendChild(wrap);
  chat.scrollTop = chat.scrollHeight;
}


function setBusy(on) {
  const disabled = !!on;
  uiBusy = disabled;

  document.body.classList.toggle('clike-busy', disabled);
  document.body.setAttribute('aria-busy', disabled ? 'true' : 'false');

  [
    mode,
    model,
    execution,
    historyScope,
    prompt,
    btnHelp,
    btnRefresh,
    btnClear,
    btnChat,
    btnApply,
    btnAttach,
    btnAttachWs,
    btnAttachExt,
    document.getElementById('layout'),
    document.getElementById('newChat'),
  ].forEach((node) => setNodeDisabled(node, disabled));
  document.querySelectorAll('.ck-ctl').forEach((node) => { node.disabled = disabled; });
  if (disabled) { try { acClose(); } catch {} }

  if (btnAttachMenu && disabled) {
    btnAttachMenu.style.display = 'none';
    _attachMenuOpen = false;
  }

  document.querySelectorAll('.tab').forEach((tab) => {
    tab.style.pointerEvents = disabled ? 'none' : '';
    tab.style.opacity = disabled ? '.55' : '';
  });

  document.querySelectorAll('#attach-chips .chip, .bubble-delete').forEach((node) => {
    node.style.pointerEvents = disabled ? 'none' : '';
    node.style.opacity = disabled ? '.55' : '';
  });

  btnCancel.disabled = !disabled;
  btnCancel.style.pointerEvents = disabled ? 'auto' : '';
  btnCancel.style.opacity = disabled ? '1' : '';

  sp.classList.toggle('active', disabled);
  statusEl.textContent = disabled ? 'Waiting response…' : 'Ready';
  if (!disabled && prompt) {
  setTimeout(() => {
    try {
      prompt.focus();
    } catch {}
  }, 0);
}
}
function post(type, payload={}) { vscode.postMessage({type, ...payload}); }
function setTab(name) {
  document.querySelectorAll('.tab').forEach(t => t.classList.toggle('active', t.dataset.tab === name));
  document.getElementById('panel-text').style.display = name==='text' ? 'block':'none';
  document.getElementById('panel-diffs').style.display = name==='diffs' ? 'block':'none';
  document.getElementById('panel-files').style.display = name==='files' ? 'block':'none';
}
function clearTextPanel() {
  // Clear the Text tab and select it.
  preText.textContent = '';
  setTab('text');
}
function clearDiffsPanel() {
  // Clear the Diffs tab and select it.
  preDiffs.textContent = '';
  setTab('diffs');
}
function clearFilesPanel() {
  // Clear the Files tab.
  preFiles.innerHTML = '';
}
document.querySelectorAll('.tab').forEach(t => t.addEventListener('click', () => setTab(t.dataset.tab)));

mode.addEventListener('change', ()=>{
  if (isBusy()) return;
  renderAttachmentChips();
  post('uiChanged', {
    mode: mode.value,
    model: model.value,
    executionPreference: currentExecution()
  });
});

model.addEventListener('change', ()=> {
  if (isBusy()) return;
  post('uiChanged', {
    mode: mode.value,
    model: model.value,
    executionPreference: currentExecution()
  });
});

if (execution) {
  execution.addEventListener('change', ()=> {
    if (isBusy()) return;
    post('uiChanged', {
      mode: mode.value,
      model: model.value,
      executionPreference: currentExecution()
    });
  });
}
btnRefresh.addEventListener('click', ()=> {
  if (isBusy()) return;
  postAndLock('fetchModels');
});
btnClear.addEventListener('click', () => {
  post('clearSession', {
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
  if(n.startsWith('deepseek')) return 'deepseek';
  if (/(llama|ollama|codellama|mistral|mixtral|phi|qwen|granite|yi|gemma|llava)/.test(n)) return 'ollama';
  if(n.startsWith('claude')) return 'anthropic';
  if(n.startsWith('vllm')) return 'vllm';
  return 'openai'; // fallback conservativo
}
function runHarperCommandFromEnter() {
  if (currentMode() !== 'harper') return false;

  const text = String(prompt.value || '');
  if (!text.trim()) return false;

  const slash = parseSlash(text);
  if (!slash) return false;

  handleSlash(slash);
  prompt.value = '';
  return true;
}
function dispatchSlashFromInput(slash) {
  if (!slash || isBusy()) return false;

  handleSlash(slash);

  try {
    prompt.value = '';
  } catch {}

  return true;
}

function dispatchHarperSlashText(text) {
  if (!isHarperSlashText(text)) return false;

  const slash = parseSlash(text);
  if (!slash) {
    handleSlash({
      cmd: '/' + (getHarperSlashCommandName(text) || 'harper'),
      error: 'Invalid Harper command.'
    });
    try { prompt.value = ''; } catch {}
    return true;
  }

  if (slash.error) {
    handleSlash({
      ...slash,
      error: 'Invalid Harper command: ' + stringifyUiErrorMessage(slash.error)
    });
    try { prompt.value = ''; } catch {}
    return true;
  }

  dispatchSlashFromInput(slash);
  return true;
}

// Single "Send" entry point. Routing is decided by the input and the mode:
//   - slash command  -> dispatched (Harper phase commands act only in Harper,
//                       /agent-default and utility slashes per their own rules);
//   - plain text      -> coding mode = code generation (/v1/generate),
//                        free/harper mode = chat Q&A (/v1/chat).
function onSend() {
  // Harper commands get the cockpit's methodology when none was typed (the bubble shows it)
  const typed = prompt.value;
  if (!typed.trim()) return;
  const text = typed.trim().charAt(0) === '/' ? withCockpitMethodology(typed) : typed;
  if (text !== typed) prompt.value = text;
  rememberCommand(text);
  try { acClose(); } catch {}

  if (dispatchHarperSlashText(text)) {
    return;
  }

  const slash = parseSlash(text);
  if (slash) {        // <-- SLASH → non è una chat normale
    dispatchSlashFromInput(slash);
    prompt.value = '';
    return;
  }

  const isCoding = mode.value === 'coding';
  const routeMode = isCoding ? 'coding' : mode.value; // free/harper -> chat; coding -> generate
  const atts = attachmentsByMode[routeMode] ? [...attachmentsByMode[routeMode]] : [];
  const selectedOpt = model.options[model.selectedIndex];
  const _provider = (selectedOpt && selectedOpt.dataset && selectedOpt.dataset.provider) || inferProvider(model.value);

  bubble('user', text, model.value, atts);
  setBusy(true);
  prompt.value = '';
  clearTextPanel();        // Clear the Text tab.
  clearDiffsPanel();        // Clear the Diffs tab.
  clearFilesPanel();        // Clear the Files tab.

  if (isCoding) {
    setTab('diffs');
    post('sendGenerate', { mode: routeMode, model: model.value, provider: _provider, prompt: text, attachments: atts });
  } else {
    post('sendChat', { mode: routeMode, model: model.value, provider: _provider, prompt: text, attachments: atts });
  }

  attachmentsByMode[routeMode] = [];
  renderAttachmentChips();
}

btnChat.addEventListener('click', onSend);

prompt.addEventListener('keydown', (ev) => {
  const isEnter = ev.key === 'Enter' || ev.key === 'Return';
  if (!isEnter) return;

  if (ev.shiftKey || ev.altKey || ev.ctrlKey || ev.metaKey || ev.isComposing) {
    return;
  }

  // Enter submits only in Harper mode (Harper commands and Q&A chat).
  // In Free/Coding, Enter is a newline; use the "Send" button to send.
  if (currentMode() !== 'harper') return;

  ev.preventDefault();
  ev.stopPropagation();

  onSend();
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
btnCancel.addEventListener('click', () => {
  try {
    vscode.postMessage({ type: 'cancel' });
  } catch {}

  try {
    harperCommandInFlight = false;
    setBusy(false);
    bubble('assistant', 'Cancelled by user.', 'system');
  } catch {}
});

window.addEventListener('message', (event) => {
  const msg = event.data;

  if (msg.type === 'agentRunSlash') {
    const command = String(msg.command || '').trim();
    if (!command) return;

    try {
      if (
        command.startsWith('/idea') ||
        command.startsWith('/spec') ||
        command.startsWith('/plan') ||
        command.startsWith('/kit') ||
        command.startsWith('/eval') ||
        command.startsWith('/gate') ||
        command.startsWith('/finalize') ||
        command.startsWith('/extend') ||
        command.startsWith('/add-req') ||
        command.startsWith('/ragIndex') ||
        command.startsWith('/ragSearch')
      ) {
        if (mode && mode.value !== 'harper') {
          mode.value = 'harper';
          try { vscode.postMessage({ type: 'uiChanged', mode: mode.value, model: model.value }); } catch {}
        }
      }

      if (prompt) {
        prompt.value = command;
      }

      const slash = parseSlash(command);
      if (!slash) {
        bubble('assistant', 'Invalid agent command: ' + command, 'system');
        return;
      }

      bubble('assistant', 'Agent requested: ' + command, 'system');

      if (currentMode() === 'harper' && isHarperBlockingSlashCommand(slash.cmd)) {
        lockHarperUi();
      }

      handleSlash(slash);

      if (prompt) {
        prompt.value = '';
      }
    } catch (e) {
      bubble('assistant', 'Agent command failed in webview: ' + String(e && e.message || e), 'system');
    }

    return;
  }

  if (msg.type === 'openHelpOverlay') { renderHelpList(); openHelpOverlay(); }
  // Echo → mostra un bubble "assistant" (anche per i riepiloghi post-init)
  if (msg.type === 'agentStream') { agentLiveEvent(msg.event); return; }
  if (msg.type === 'echo') {
    console.log('[webview] echo', msg);
    const text = stringifyUiErrorMessage(msg.message || '');
    try { bubble('assistant', text, 'system'); } catch (e) { console.warn('[webview] bubble echo failed', e); }
    const pre = document.getElementById('text');
    if (pre) pre.textContent = text;
    return;
  }
  if (msg.type === 'hydrateAppend') {
    try {
      var m = msg.message || {};
      var role = m.role || 'assistant';
      var content = m.content || '';
      var provider = m.provider || 'system';
      bubble(role, content, provider);
    } catch (e) {
      console.warn('[webview] hydrateAppend failed', e);
    }
    return;
  }
  // Generic text payload (es. RAG search summary)
  if (msg.type === 'text') {
    const pre = document.getElementById('text');
    if (pre) {
      pre.textContent = String(msg.text || '');
      setTab('text');
    }
    return;
  }
  // --- RAG results (mostra i risultati di /rag e /ragSearch) ---
  if (msg.type === 'ragResults') {
    var hits = [];
    try {
      if (Array.isArray(msg.results)) {
        hits = msg.results;
      } else if (Array.isArray(msg.hits)) {
        hits = msg.hits;
      } else {
        hits = [];
      }
    } catch (e) {
      console.warn('[webview] ragResults parse failed', e);
      hits = [];
    }

    // salva per /rag +N
    try {
      lastRagHits = hits;
    } catch (e2) {
      console.warn('[webview] lastRagHits assign failed', e2);
    }

    if (!hits.length) {
      try { bubble('assistant', 'RAG: no results.', 'system'); } catch (e3) {
        console.warn('[webview] rag no-results bubble failed', e3);
      }
      return;
    }

    var max = Math.min(hits.length, 10); // non più di 10 righe
    var lines = [];
    lines.push('RAG results for: ' + (msg.query || 'query'));
    lines.push('Files found: ' + hits.length);
    lines.push('');
    for (var i = 0; i < max; i++) {
      var h = hits[i] || {};
      var path = h.path || h.source || h.name || 'doc';

      var score = '';
      if (typeof h.score === 'number') {
        score = ' [score ' + h.score.toFixed(3) + ']';
      }

      var rawText = '';
      if (typeof h.text === 'string' && h.text) {
        rawText = h.text;
      } else if (typeof h.chunk_text === 'string' && h.chunk_text) {
        rawText = h.chunk_text;
      }

      var preview = '';
      if (rawText) {
        preview = ' — ' + rawText.replace(/\\s+/g, ' ').slice(0, 160) + '…';
      }

      lines.push((i + 1) + '. ' + path + score + preview);
    }

    try {
      var msgText =
          'RAG results:\\n' +
          lines.join('\\n') +
          '\\n\\nUse "/rag +N" to attach one hit to the next call.'+
          '"/rag list" to list attachments, or "/rag clear" to reset.';
      bubble(
        'assistant  ',
        msgText,  
        'system'
      );
    } catch (e4) {
      console.warn('[webview] ragResults bubble failed', e4);
    }

    return;
  }

  if (msg.type === 'busy') {
    if (msg.on) {
      setBusy(true);
      return;
    }

    harperCommandInFlight = false;
    setBusy(false);
    return;
  }

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
    if (execution) {
      execution.value = (msg.state && msg.state.executionPreference) || 'local_agent_only';
      try { applyExecutionGating(null); } catch {}
    }
    
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
      o.value = name; // Keep the model name as the option value.
      //o.textContent = (provider && provider !== 'unknown') ? (provider + ':' + name) : name;
      o.textContent = name;
     
      o.dataset.provider = provider; // Carry the provider on the option.
      // LA NUOVA CONDIZIONE QUI:
      if (name === prev) {
        o.selected = true;
      }
      model.appendChild(o);
    });
    try { applyExecutionGating(msg.providers || null); } catch {}
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
    //unlockHarperUi();
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
    if (text) bubble('assistant', text, modelName, attachments, Date.now(), { ragUsed: ragUsed, citations: citations });
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
      // N13: images are appended as DOM nodes; bubble() escapes text content.
      bubble('assistant', String(assistantText || ''), model.value, [], undefined, { images: imgs.slice(0, 3) });

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
      // N13: images are appended as DOM nodes; bubble() escapes text content.
      bubble('assistant', String(assistantText || ''), model.value, [], undefined, { images: imgs.slice(0, 3) });

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
    const lines = files.map((f, i) => {
      // paths come from the server/LLM: escape them; ids are positional (btoa breaks on non-Latin-1)
      const p = escapeHtml(String((f && f.path) || ''));
      const safeId = 'f_' + i;
      return '<div class="row">'
        + '<input type="checkbox" class="file-chk" id="' + safeId + '" data-path="' + p + '">'
        + '<label for="' + safeId + '" class="file-open" data-path="' + p + '" style="cursor:pointer;text-decoration:underline;">' + p + '</label>'
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
    const lines = files.map((f, i) => {
      // paths come from the server/LLM: escape them; ids are positional (btoa breaks on non-Latin-1)
      const p = escapeHtml(String((f && f.path) || ''));
      const safeId = 'f_' + i;
      return '<div class="row">'
        + '<input type="checkbox" class="file-chk" id="' + safeId + '" data-path="' + p + '">'
        + '<label for="' + safeId + '" class="file-open" data-path="' + p + '" style="cursor:pointer;text-decoration:underline;">' + p + '</label>'
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
    if (msg.activate) setTab('files');

  }
  if (msg.type === 'applyResult') {
    setTab('text');
    preText.textContent = "Applied files:\\n" + JSON.stringify(msg.data?.applied || [], null, 2);
  }

  if (msg.type === 'error') {
    const text = 'Error: ' + stringifyUiErrorMessage(msg.message || 'unknown');
    //try { bubble('assistant', text, 'system'); } catch {}
    const pre = document.getElementById('text');
    if (pre) pre.textContent = text;
    setTab('text');
    return;
  }

});

// ===================== Cockpit layout and autocompletion =====================
// The cockpit moves the existing controls (same ids, same handlers) into its side panel; every
// layout gets the autocompletion and the Layout selector. The state comes from the extension
// ('cockpitState': project, agent, preferences, tools).
var COCKPIT = document.body.getAttribute('data-theme') === 'cockpit';
var ck = { state: null, reqFilter: 'all' };
var BMAD_ROLE_CHOICES = [
  ['IDEA', 'idea', ['analyst']], ['SPEC', 'spec', ['pm', 'ux']], ['PLAN', 'plan', ['architect', 'pm']],
  ['EXTEND', 'extend', ['pm', 'analyst', 'architect', 'ux']], ['KIT', 'kit', ['developer']],
  ['EVAL', 'eval', ['qa', 'developer']], ['GATE', 'gate', []], ['FINALIZE', 'finalize', ['tech-writer']]
];

function ckEl(tag, cls, text) {
  var n = document.createElement(tag);
  if (cls) n.className = cls;
  if (text !== undefined && text !== null) n.textContent = String(text);
  return n;
}
function ckPrefs() { return (ck.state && ck.state.prefs) || { methodology: '', roles: {} }; }
function ckProject() { return (ck.state && ck.state.project) || null; }

/** The command with the cockpit methodology (BMAD and the role per phase) in Harper mode. */
function withCockpitMethodology(text) {
  var t = String(text || '').trim();
  if (currentMode() !== 'harper') return t;
  try { return CLIKE_SLASH_COMPLETE.withMethodology(t, ckPrefs()); } catch (e) { return t; }
}

// --- command history (per webview state: kept across reloads of the panel) ---
var cmdHistory = ((vscode.getState && vscode.getState()) || {}).cmdHistory || [];
var histIdx = -1;
function rememberCommand(text) {
  var t = String(text || '').trim();
  if (!t || t.charAt(0) !== '/') return;
  cmdHistory = cmdHistory.filter(function (x) { return x !== t; });
  cmdHistory.unshift(t);
  cmdHistory = cmdHistory.slice(0, 50);
  histIdx = -1;
  try { vscode.setState(Object.assign({}, vscode.getState() || {}, { cmdHistory: cmdHistory })); } catch (e) {}
}

// --- autocompletion ---
var ac = { items: [], idx: 0, replaceFrom: 0, fix: '', suppressed: false, navigated: false };
var acBox = el('acBox'), acSig = el('acSig'), acErr = el('acErr'), acMenu = el('acMenu');

function acContext() {
  var p = ckProject() || {};
  var agent = (ck.state && ck.state.agent) || {};
  return { mode: currentMode(), reqs: p.reqs || [], next: p.next || null, releases: p.releases || [],
    tools: (ck.state && ck.state.tools) || [], models: agent.models || {} };
}
function acClose() {
  ac.items = []; ac.fix = '';
  acBox.classList.remove('open');
  acMenu.innerHTML = ''; acSig.innerHTML = ''; acErr.style.display = 'none';
}
function acRender() {
  if (isBusy() || ac.suppressed) { acClose(); return; }
  var text = prompt.value;
  if (!/^\\s*\\//.test(text)) { acClose(); return; }
  var res;
  try { res = CLIKE_SLASH_COMPLETE.complete(text, prompt.selectionStart, acContext(), parseSlash); } catch (e) { acClose(); return; }
  ac.items = res.items || [];
  ac.replaceFrom = res.replaceFrom;
  ac.fix = res.fix || '';
  if (ac.idx >= ac.items.length) ac.idx = 0;
  // signature
  acSig.innerHTML = '';
  if (res.signature) {
    acSig.appendChild(document.createTextNode(res.signature.command + ' '));
    res.signature.parts.forEach(function (p) {
      var node = p.active ? ckEl('b', '', p.text) : document.createTextNode(p.text);
      acSig.appendChild(node);
      acSig.appendChild(document.createTextNode(' '));
    });
  }
  acSig.style.display = res.signature && res.signature.parts.length ? 'block' : 'none';
  // error, with its fix
  acErr.innerHTML = '';
  if (res.error) {
    acErr.appendChild(document.createTextNode('✖ ' + res.error));
    if (ac.fix) {
      var f = ckEl('span', 'ac-fix', '→ ' + ac.fix + '  (Tab)');
      f.addEventListener('mousedown', function (ev) { ev.preventDefault(); acApplyFix(); });
      acErr.appendChild(f);
    }
    acErr.style.display = 'block';
  } else {
    acErr.style.display = 'none';
  }
  // suggestions
  acMenu.innerHTML = '';
  var typedTok = text.slice(res.replaceFrom, prompt.selectionStart).toLowerCase();
  ac.items.forEach(function (it, i) {
    var row = ckEl('div', 'ac-it' + (i === ac.idx ? ' on' : '') + (it.kind === 'next' ? ' next' : ''));
    row.setAttribute('role', 'option');
    var k = ckEl('span', 'ac-k');
    var label = String(it.label || '');
    if (typedTok && label.toLowerCase().indexOf(typedTok) === 0) {
      k.appendChild(ckEl('em', '', label.slice(0, typedTok.length)));
      k.appendChild(document.createTextNode(label.slice(typedTok.length)));
    } else {
      k.textContent = (it.kind === 'next' ? '★ ' : '') + label;
    }
    row.appendChild(k);
    row.appendChild(ckEl('span', 'ac-d', it.sig ? it.sig + ' — ' + (it.detail || '') : (it.detail || '')));
    row.appendChild(ckEl('span', it.warn ? 'ac-w' : 'ac-g', it.warn || it.group || ''));
    row.addEventListener('mousedown', function (ev) { ev.preventDefault(); ac.idx = i; acAccept(); });
    acMenu.appendChild(row);
  });
  if (ac.items.length) {
    var foot = ckEl('div', 'ac-foot');
    ['↑↓ choose', 'Tab / ↵ insert', 'Esc close', '⌘/ help'].forEach(function (x) { foot.appendChild(ckEl('span', '', x)); });
    acMenu.appendChild(foot);
  }
  var any = ac.items.length || res.error || (res.signature && res.signature.parts.length);
  acBox.classList.toggle('open', !!any);
}
function acAccept() {
  var it = ac.items[ac.idx];
  if (!it) return false;
  var out = CLIKE_SLASH_COMPLETE.accept(prompt.value, prompt.selectionStart, ac.replaceFrom, it);
  prompt.value = out.text;
  prompt.setSelectionRange(out.caret, out.caret);
  ac.idx = 0; ac.navigated = false;
  acRender();
  return true;
}
function acApplyFix() {
  if (!ac.fix) return false;
  prompt.value = ac.fix + ' ';
  prompt.setSelectionRange(prompt.value.length, prompt.value.length);
  acRender();
  return true;
}
prompt.addEventListener('input', function () { ac.suppressed = false; ac.navigated = false; ac.idx = 0; histIdx = -1; acRender(); });
prompt.addEventListener('click', acRender);
prompt.addEventListener('keyup', function (ev) { if (ev.key === 'ArrowLeft' || ev.key === 'ArrowRight' || ev.key === 'Home' || ev.key === 'End') acRender(); });
prompt.addEventListener('blur', function () { setTimeout(acClose, 120); });
prompt.addEventListener('focus', acRender);
// capture: runs before the Enter-to-send handler of Harper mode
prompt.addEventListener('keydown', function (ev) {
  var open = acBox.classList.contains('open');
  var hasItems = open && ac.items.length > 0;
  if (ev.key === 'Escape' && open) { ac.suppressed = true; acClose(); ev.preventDefault(); ev.stopImmediatePropagation(); return; }
  if (hasItems && (ev.key === 'ArrowDown' || ev.key === 'ArrowUp')) {
    ac.idx = (ac.idx + (ev.key === 'ArrowDown' ? 1 : ac.items.length - 1)) % ac.items.length;
    ac.navigated = true;
    acRender();
    ev.preventDefault(); ev.stopImmediatePropagation(); return;
  }
  if (ev.key === 'Tab' && !ev.shiftKey) {
    if (hasItems ? acAccept() : acApplyFix()) { ev.preventDefault(); ev.stopImmediatePropagation(); }
    return;
  }
  if ((ev.key === 'Enter' || ev.key === 'Return') && hasItems && !ev.shiftKey && !ev.altKey && !ev.isComposing) {
    // ↵ inserts while a token is being typed or a suggestion was chosen; otherwise it sends as before
    var it = ac.items[ac.idx];
    var typedTok = prompt.value.slice(ac.replaceFrom, prompt.selectionStart);
    if (it && (ac.navigated || (typedTok && String(it.insert) !== typedTok))) {
      acAccept();
      ev.preventDefault(); ev.stopImmediatePropagation();
    }
    return;
  }
  // ↑ / ↓ in an empty prompt (or while browsing): the commands already used
  if ((ev.key === 'ArrowUp' || ev.key === 'ArrowDown') && !hasItems && cmdHistory.length) {
    var browsing = histIdx >= 0 && prompt.value === cmdHistory[histIdx];
    if (!prompt.value || browsing) {
      histIdx = ev.key === 'ArrowUp' ? Math.min(histIdx + 1, cmdHistory.length - 1) : histIdx - 1;
      prompt.value = histIdx >= 0 ? cmdHistory[histIdx] : '';
      prompt.setSelectionRange(prompt.value.length, prompt.value.length);
      ev.preventDefault(); ev.stopImmediatePropagation();
    }
  }
}, true);

// --- Memory (every layout): opens the Memory panel, or brings it to the front ---
(function () {
  var mb = el('memoryBtn');
  if (mb) mb.addEventListener('click', function () { post('openMemory'); });
})();

// --- New chat (every layout): the current conversation goes to the history ---
(function () {
  var nb = el('newChat');
  if (nb) nb.addEventListener('click', function () { if (!isBusy()) post('historyNew'); });
})();

// --- Layout selector (every layout) ---
var layoutSel = el('layout');
if (layoutSel) {
  layoutSel.addEventListener('change', function () {
    if (isBusy()) { layoutSel.value = document.body.getAttribute('data-theme'); return; }
    post('setTheme', { theme: layoutSel.value });
  });
}

// --- the cockpit itself ---
function ckRow(form, label, nodes) {
  var l = ckEl('label', '', label);
  form.appendChild(l);
  var box = ckEl('div', 'ck-pair');
  nodes.forEach(function (n) { if (n) box.appendChild(n); });
  form.appendChild(box);
  return box;
}
function ckSection(id, title, open) {
  var d = ckEl('details', 'ck-sec');
  d.id = id;
  var saved = ((vscode.getState && vscode.getState()) || {}).ckOpen || {};
  d.open = saved[id] !== undefined ? !!saved[id] : open !== false;
  var s = ckEl('summary', '', title);
  d.appendChild(s);
  d.addEventListener('toggle', function () {
    try {
      var st = vscode.getState() || {};
      var o = Object.assign({}, st.ckOpen || {});
      o[id] = d.open;
      vscode.setState(Object.assign({}, st, { ckOpen: o }));
    } catch (e) {}
  });
  return d;
}
function ckSetMode(value) {
  if (isBusy() || mode.value === value) return;
  mode.value = value;
  mode.dispatchEvent(new Event('change'));
  ckRenderAll();
}
function ckRunCommand(cmd) {
  if (isBusy() || !cmd) return;
  ckToggleDrawer(false);
  if (currentMode() !== 'harper') ckSetMode('harper');
  var hole = cmd.indexOf(' <');
  if (hole > 0) {
    // a value only the developer has (e.g. /init <name>): written in the prompt, not sent
    prompt.value = cmd.slice(0, hole) + ' ';
    ckToggleDrawer(false);
    prompt.focus();
    prompt.setSelectionRange(prompt.value.length, prompt.value.length);
    acRender();
    return;
  }
  prompt.value = cmd;
  onSend();
}
function ckToggleDrawer(open) {
  document.body.classList.toggle('ck-drawer', open === undefined ? !document.body.classList.contains('ck-drawer') : !!open);
}

function ckBuild() {
  var side = el('ckSide');
  var head = el('ckHead');
  var toolbar = document.querySelector('.toolbar');
  // header of the chat column: mode, summary chips, status, drawer button
  head.appendChild(ckEl('span', 'ck-mode', ''));
  head.appendChild(ckEl('span', 'ck-dim', ''));
  var chips = ckEl('span', 'ck-chips');
  head.appendChild(chips);
  head.appendChild(el('sp'));
  head.appendChild(el('status'));
  var drawerBtn = ckEl('button', 'ck-chip purple', '☰');
  drawerBtn.id = 'ckDrawerBtn';
  drawerBtn.title = 'Cockpit: mode, settings, project';
  drawerBtn.addEventListener('click', function () { ckToggleDrawer(); });
  var memBtn = el('memoryBtn');
  if (memBtn) { memBtn.className = 'ck-chip'; head.appendChild(memBtn); }
  head.appendChild(drawerBtn);
  el('ckScrim').addEventListener('click', function () { ckToggleDrawer(false); });

  // narrow panels: the drawer always shows how to close it (and Esc, the area on its left)
  var closeBar = ckEl('div'); closeBar.id = 'ckDrawerClose';
  closeBar.appendChild(ckEl('span', '', 'Cockpit'));
  var closeBtn = ckEl('button', 'ck-btn', '✕ Close');
  closeBtn.addEventListener('click', function () { ckToggleDrawer(false); });
  closeBar.appendChild(closeBtn);
  side.appendChild(closeBar);
  document.addEventListener('keydown', function (ev) {
    if (ev.key === 'Escape' && document.body.classList.contains('ck-drawer')) { ckToggleDrawer(false); ev.stopPropagation(); }
  }, true);
  // back to a wide panel: no drawer
  try {
    window.matchMedia('(max-width: 720px)').addEventListener('change', function (mq) { if (!mq.matches) ckToggleDrawer(false); });
  } catch (e) {}

  // mode + settings: the existing controls are moved here
  var secCfg = ckSection('ckSecCfg', 'Mode & settings', true);
  var seg = ckEl('div', 'ck-seg');
  seg.id = 'ckModeSeg';
  [['free', 'Free'], ['coding', 'Coding'], ['harper', 'Harper']].forEach(function (m) {
    var b = ckEl('button', 'ck-ctl ' + m[0], m[1]);
    b.dataset.mode = m[0];
    b.addEventListener('click', function () { ckSetMode(m[0]); });
    seg.appendChild(b);
  });
  secCfg.appendChild(seg);
  var form = ckEl('div', 'ck-form');
  ckRow(form, 'Execution', [execution]);
  ckRow(form, 'Cloud model', [model, btnRefresh]);
  var agentSel = ckEl('select', 'ck-ctl');
  agentSel.id = 'ckAgent';
  [['gpt_codex', 'Codex'], ['claude_code', 'Claude Code'], ['auto', 'auto']].forEach(function (o) {
    var opt = ckEl('option', '', o[1]); opt.value = o[0]; agentSel.appendChild(opt);
  });
  agentSel.addEventListener('change', function () {
    var v = { gpt_codex: 'codex', claude_code: 'claude', auto: 'auto' }[agentSel.value];
    post('harperRun', { cmd: 'agent-default', value: v, attachments: [] });
  });
  ckRow(form, 'Agent', [agentSel]);
  // the models the agent's CLI accepts (a select: every one visible, none it would refuse); a text
  // field only when the list is unknown (no Codex run yet on this machine)
  var agentModel = ckEl('select', 'ck-ctl');
  agentModel.id = 'ckAgentModel';
  var agentModelText = ckEl('input', 'ck-ctl');
  agentModelText.id = 'ckAgentModelText';
  agentModelText.setAttribute('spellcheck', 'false');
  agentModelText.placeholder = 'model id';
  var sendAgentModel = function (v) {
    var who = agentModel.dataset.agent || 'codex';
    v = String(v || '').trim();
    if (v) post('harperRun', { cmd: 'agent-model', agentName: who, agentModel: v, attachments: [] });
  };
  agentModel.addEventListener('change', function () { sendAgentModel(agentModel.value); });
  agentModelText.addEventListener('change', function () { sendAgentModel(agentModelText.value); });
  var amRow = ckRow(form, 'Agent model', [agentModel, agentModelText]);
  amRow.id = 'ckAgentModelRow';
  ckRow(form, 'History', [historyScope]);
  ckRow(form, 'Layout', [layoutSel]);
  var helpBtnNode = el('helpBtn');
  helpBtnNode.appendChild(document.createTextNode(' Help'));
  var clearNode = btnClear;
  ckRow(form, 'Session', [el('newChat'), clearNode, helpBtnNode]).classList.add('wrap');
  secCfg.appendChild(form);
  // the native mode select stays in the DOM (handlers, state), hidden
  mode.style.display = 'none';
  secCfg.appendChild(mode);
  side.appendChild(secCfg);

  // methodology (Harper)
  var secMeth = ckSection('ckSecMeth', 'Methodology', true);
  secMeth.classList.add('ck-harper');
  var mseg = ckEl('div', 'ck-seg two');
  [['', 'Harper native', 'native'], ['bmad', 'BMAD', 'bmad']].forEach(function (m) {
    var b = ckEl('button', 'ck-ctl ' + m[2], m[1]);
    b.dataset.meth = m[0];
    b.addEventListener('click', function () {
      if (isBusy()) return;
      var p = ckPrefs();
      post('cockpitPrefs', { methodology: m[0], roles: p.roles || {} });
    });
    mseg.appendChild(b);
  });
  secMeth.appendChild(mseg);
  var roles = ckEl('div', 'ck-roles');
  roles.id = 'ckRoles';
  secMeth.appendChild(roles);

  // project (Harper)
  var secProj = ckSection('ckSecProj', 'Project', true);
  secProj.classList.add('ck-harper');
  var proj = ckEl('div'); proj.id = 'ckProject';
  secProj.appendChild(proj);

  var secNext = ckSection('ckSecNext', 'Next action', true);
  secNext.classList.add('ck-harper');
  var next = ckEl('div'); next.id = 'ckNext';
  secNext.appendChild(next);
  // the next action first: in Harper it is what the developer acts on most
  side.appendChild(secNext);
  side.appendChild(secProj);

  var secReq = ckSection('ckSecReq', 'REQ', true);
  secReq.classList.add('ck-harper');
  var filter = ckEl('span', 'ck-filter ck-aside');
  [['all', 'all'], ['open', 'open'], ['active', 'in progress']].forEach(function (f) {
    var b = ckEl('button', '', f[1]);
    b.dataset.f = f[0];
    b.addEventListener('click', function (ev) { ev.preventDefault(); ck.reqFilter = f[0]; ckRenderReqs(); });
    filter.appendChild(b);
  });
  secReq.querySelector('summary').appendChild(filter);
  var reqs = ckEl('div', 'ck-reqs'); reqs.id = 'ckReqs';
  secReq.appendChild(reqs);
  side.appendChild(secReq);
  side.appendChild(secMeth);

  // free / coding: the Harper project in one line
  var secSum = ckSection('ckSecSum', 'Harper project', true);
  secSum.classList.add('ck-nonharper');
  var sum = ckEl('div'); sum.id = 'ckSummary';
  secSum.appendChild(sum);
  side.appendChild(secSum);

  var secAgent = ckSection('ckSecAgent', 'Last run & agent', true);
  var agentBox = ckEl('div'); agentBox.id = 'ckAgentBox';
  secAgent.appendChild(agentBox);
  side.appendChild(secAgent);

  // the conversations of this mode: the current one and the archived ones (New chat archives)
  var secHist = ckSection('ckSecHist', 'History', true);
  var hist = ckEl('div'); hist.id = 'ckHistory';
  secHist.appendChild(hist);
  side.appendChild(secHist);

  // output tabs in a drawer under the composer: open by itself when there is something to read
  var out = ckEl('details'); out.id = 'ckOutput';
  out.appendChild(ckEl('summary', '', 'Output · Text · Diffs · Files'));
  var main = el('ckMain');
  var tabs = document.querySelector('.tabs');
  main.insertBefore(out, tabs);
  out.appendChild(tabs);
  ['panel-text', 'panel-diffs', 'panel-files'].forEach(function (id) { out.appendChild(el(id)); });

  // short labels for very narrow panels
  [[btnAttach, '📎', ' Attach'], [btnApply, '✔', ' Apply'], [btnCancel, '⏹', ' Cancel']].forEach(function (b) {
    if (!b[0]) return;
    b[0].textContent = '';
    b[0].appendChild(document.createTextNode(b[1]));
    b[0].appendChild(ckEl('span', 'ck-lbl', b[2]));
  });

  if (toolbar) toolbar.classList.add('ck-moved');
}

function ckPill(p, label) { return ckEl('span', 'ck-pill ' + p.state, label || p.label); }

function ckRenderHead() {
  var head = el('ckHead');
  if (!head.firstChild) return;
  var m = currentMode();
  var badge = head.children[0];
  badge.className = 'ck-mode ' + m;
  badge.textContent = { free: 'FREE', coding: 'CODING', harper: 'HARPER' }[m] || m.toUpperCase();
  var p = ckProject();
  var dim = head.children[1];
  dim.textContent = m === 'harper' && p && p.harper
    ? ((p.release ? p.release + ' · ' : '') + p.progress_pct + '% · ' + (p.counts ? p.counts.done + '/' + p.counts.total + ' REQ' : ''))
    : (m === 'coding' ? 'writes only under generated/<id>/' : 'questions only, nothing is written');
  var chips = head.querySelector('.ck-chips');
  chips.innerHTML = '';
  var a = (ck.state && ck.state.agent) || {};
  var exec = currentExecution();
  var who = exec === 'cloud_only' ? ('☁ ' + (model.value || 'auto'))
    : ('🤖 ' + ({ gpt_codex: 'Codex', claude_code: 'Claude Code' }[a.executor] || 'agent') +
       (a.executor === 'gpt_codex' && a.codex_model ? ' · ' + a.codex_model : a.executor === 'claude_code' && a.claude_model ? ' · ' + a.claude_model : ''));
  var c1 = ckEl('button', 'ck-chip', who); c1.title = 'Execution and agent';
  c1.addEventListener('click', function () { ckFocusSection('ckSecCfg'); });
  chips.appendChild(c1);
  if (m === 'harper' && ckPrefs().methodology === 'bmad') {
    var c2 = ckEl('button', 'ck-chip purple opt', 'BMAD'); c2.title = 'Methodology';
    c2.addEventListener('click', function () { ckFocusSection('ckSecMeth'); });
    chips.appendChild(c2);
  }
}
function ckFocusSection(id) {
  if (window.matchMedia('(max-width: 720px)').matches) ckToggleDrawer(true);
  var s = el(id);
  if (s) { s.open = true; s.scrollIntoView({ block: 'nearest' }); }
}

function ckRenderConfig() {
  var m = currentMode();
  document.querySelectorAll('#ckModeSeg button').forEach(function (b) { b.classList.toggle('on', b.dataset.mode === m); });
  var a = (ck.state && ck.state.agent) || {};
  var agentSel = el('ckAgent');
  if (agentSel && a.executor) agentSel.value = a.executor;
  var am = el('ckAgentModel');
  var amText = el('ckAgentModelText');
  if (am && document.activeElement !== am && document.activeElement !== amText) {
    var who = a.executor === 'claude_code' ? 'claude' : 'codex';
    var current = who === 'claude' ? (a.claude_model || '') : (a.codex_model || '');
    var list = ((a.models || {})[who]) || [];
    am.dataset.agent = who;
    am.title = 'Model of ' + (who === 'claude' ? 'Claude Code' : 'Codex') + ' (/agent-model ' + who + ' <model>)';
    am.innerHTML = '';
    if (list.length) {
      if (current && list.indexOf(current) < 0) {
        var bad = ckEl('option', '', current + ' ⚠ not available');
        bad.value = current;
        am.appendChild(bad);
      }
      if (!current) { var def = ckEl('option', '', '(CLI default)'); def.value = ''; am.appendChild(def); }
      list.forEach(function (x) { var o = ckEl('option', '', x); o.value = x; am.appendChild(o); });
      am.value = current;
      am.style.display = '';
      amText.style.display = 'none';
    } else {
      am.style.display = 'none';
      amText.style.display = '';
      amText.value = current;
      amText.title = who === 'codex' ? 'The models of the Codex login appear after a first Codex run (~/.codex/models_cache.json)' : '';
    }
  }
  var cloudOnly = currentExecution() === 'cloud_only';
  var amRow = el('ckAgentModelRow');
  if (amRow) amRow.style.opacity = cloudOnly ? '.5' : '';
  model.title = cloudOnly || currentExecution() === 'prefer_local_agent' ? 'Cloud model' : 'Cloud model (not used: agent only)';
}

function ckRenderMethodology() {
  var p = ckPrefs();
  document.querySelectorAll('#ckSecMeth .ck-seg button').forEach(function (b) { b.classList.toggle('on', (b.dataset.meth || '') === (p.methodology || '')); });
  var roles = el('ckRoles');
  if (!roles) return;
  roles.innerHTML = '';
  roles.style.display = p.methodology === 'bmad' ? '' : 'none';
  BMAD_ROLE_CHOICES.forEach(function (r) {
    roles.appendChild(ckEl('span', 'ph', r[0]));
    var box = ckEl('div', 'ck-rc');
    if (!r[2].length) box.appendChild(ckEl('span', '', 'CLike only'));
    var current = (p.roles || {})[r[1]] || r[2][0];
    r[2].forEach(function (role) {
      if (r[2].length === 1) { box.appendChild(ckEl('span', 'on', role)); return; }
      var b = ckEl('button', 'ck-ctl' + (role === current ? ' on' : ''), role);
      b.addEventListener('click', function () {
        if (isBusy()) return;
        var next = Object.assign({}, p.roles || {}); next[r[1]] = role;
        post('cockpitPrefs', { methodology: 'bmad', roles: next });
      });
      box.appendChild(b);
    });
    roles.appendChild(box);
  });
}

function ckRenderProject() {
  var box = el('ckProject');
  if (!box) return;
  box.innerHTML = '';
  var p = ckProject();
  if (!p || !p.harper) {
    box.appendChild(ckEl('div', 'ck-empty', 'No Harper project in this workspace: /init <name> creates one.'));
    return;
  }
  var h = ckEl('div', 'ck-h', (p.release ? 'Release ' + p.release + ' · ' : '') + p.counts.total + ' REQ');
  h.appendChild(ckEl('span', 'ck-aside', p.progress_pct + '%'));
  box.appendChild(h);
  var bar = ckEl('div', 'ck-bar');
  var g = ckEl('i', 'g'); g.style.width = p.progress_pct + '%'; bar.appendChild(g);
  if (p.counts.in_progress && p.counts.total) {
    var pr = ckEl('i', 'p');
    pr.style.left = p.progress_pct + '%';
    pr.style.width = Math.max(2, Math.round(100 * p.counts.in_progress / p.counts.total)) + '%';
    bar.appendChild(pr);
  }
  box.appendChild(bar);
  box.appendChild(ckEl('div', 'ck-kv', p.counts.done + ' done · ' + p.counts.in_progress + ' in progress · ' + p.counts.open + ' open' + (p.counts.deferred ? ' · ' + p.counts.deferred + ' deferred' : '')));
  var pills = ckEl('div', 'ck-pills');
  p.phases.forEach(function (ph) {
    pills.appendChild(ckPill(ph, ph.id === 'kit' && p.counts.total ? 'KIT ' + p.counts.done + '/' + p.counts.total : ph.label));
  });
  box.appendChild(pills);
}

function ckReqCommand(r) {
  if (r.status === 'in_progress' && /^next: \\//.test(r.note)) {
    var step = r.note.replace('next: /', '');
    return step === 'eval' ? '/eval ' + r.id + ' --fix' : '/' + step + ' ' + r.id;
  }
  if (r.status === 'done') return '/eval ' + r.id;
  return '/kit ' + r.id;
}
function ckRenderReqs() {
  var box = el('ckReqs');
  if (!box) return;
  box.innerHTML = '';
  document.querySelectorAll('#ckSecReq .ck-filter button').forEach(function (b) { b.classList.toggle('on', b.dataset.f === ck.reqFilter); });
  var p = ckProject();
  var list = (p && p.reqs) || [];
  if (ck.reqFilter === 'open') list = list.filter(function (r) { return r.status === 'open' || r.status === 'in_progress'; });
  if (ck.reqFilter === 'active') list = list.filter(function (r) { return r.status === 'in_progress'; });
  if (!list.length) { box.appendChild(ckEl('div', 'ck-empty', p && p.counts && p.counts.total ? 'No REQ in this filter.' : 'No plan yet: /plan creates the REQs.')); return; }
  list.forEach(function (r) {
    var cls = r.blockers && r.blockers.length ? 'wait' : r.status === 'open' ? (r.waiting && r.waiting.length ? 'wait' : 'ready') : r.status;
    var row = ckEl('div', 'ck-req ' + cls);
    row.title = r.id + ' ' + r.title + ' — click: ' + ckReqCommand(r);
    row.appendChild(ckEl('span', '', r.status === 'done' ? '●' : r.status === 'in_progress' ? '◐' : '○'));
    row.appendChild(ckEl('span', 't', r.id + ' ' + r.title));
    row.appendChild(ckEl('span', 'n', r.note));
    row.addEventListener('click', function () {
      if (isBusy()) return;
      if (currentMode() !== 'harper') ckSetMode('harper');
      prompt.value = ckReqCommand(r) + ' ';
      ckToggleDrawer(false);
      prompt.focus();
      prompt.setSelectionRange(prompt.value.length, prompt.value.length);
      acRender();
    });
    box.appendChild(row);
  });
}

function ckRenderNext() {
  var box = el('ckNext');
  if (!box) return;
  box.innerHTML = '';
  var p = ckProject();
  var n = p && p.next;
  var wrap = ckEl('div', 'ck-next');
  if (!n) { wrap.appendChild(ckEl('div', 'ck-empty', 'Open a Harper project.')); box.appendChild(wrap); return; }
  var line = ckEl('div', 'ck-kv');
  if (n.command) {
    var cmd = n.command.indexOf(' <') > 0 ? n.command : withCockpitMethodology(n.command);
    line.appendChild(document.createTextNode('Next: '));
    line.appendChild(ckEl('code', '', cmd));
  } else {
    line.textContent = n.message;
  }
  wrap.appendChild(line);
  if (n.command) wrap.appendChild(ckEl('div', 'ck-kv', n.message));
  // the decisions the plan leaves open (what to decide in the tooltip)
  if (Array.isArray(n.blockers) && n.blockers.length) {
    var ul = ckEl('ul', 'ck-blockers');
    n.blockers.forEach(function (b) {
      var li = ckEl('li');
      li.appendChild(ckEl('b', '', b.id));
      li.appendChild(document.createTextNode(' ' + (b.subject || '')));
      if (b.required) li.title = b.required;
      ul.appendChild(li);
    });
    wrap.appendChild(ul);
  }
  var btns = ckEl('div', 'ck-btns');
  if (n.command) {
    var needsValue = n.command.indexOf(' <') > 0;
    var run = ckEl('button', 'ck-btn primary ck-ctl', needsValue ? 'Write it' : 'Run');
    run.title = needsValue ? 'Puts ' + n.command + ' in the prompt: complete it and send' : 'Runs ' + withCockpitMethodology(n.command) + ' as if typed';
    run.addEventListener('click', function () { ckRunCommand(n.command); });
    btns.appendChild(run);
  }
  if (p.counts && p.counts.total && (p.counts.open || p.counts.in_progress)) {
    var auto = ckEl('button', 'ck-btn ck-ctl', '▶ Autopilot');
    auto.title = 'Every REQ unattended: /kit → /eval --fix → /gate (stops before /finalize)';
    auto.addEventListener('click', function () { ckRunCommand('/autopilot'); });
    btns.appendChild(auto);
  }
  wrap.appendChild(btns);
  // BMAD: the roles of a phase that have not run yet are a choice too (SPEC by ux, PLAN by pm…)
  var alts = (p.alternatives || []);
  if (alts.length) {
    wrap.appendChild(ckEl('div', 'ck-kv', 'Or:'));
    alts.forEach(function (alt) {
      var row = ckEl('div', 'ck-alt');
      var code = ckEl('code', '', alt.command);
      code.title = alt.message;
      row.appendChild(code);
      var b = ckEl('button', 'ck-btn ck-ctl', 'Run');
      b.title = alt.message;
      b.addEventListener('click', function () { ckRunCommand(alt.command); });
      row.appendChild(b);
      wrap.appendChild(row);
    });
  }
  box.appendChild(wrap);
}

function ckAgo(ts) {
  var s = Math.max(0, Math.round((Date.now() - Number(ts || 0)) / 1000));
  if (s < 90) return s + ' s ago';
  if (s < 5400) return Math.round(s / 60) + ' min ago';
  if (s < 172800) return Math.round(s / 3600) + ' h ago';
  return Math.round(s / 86400) + ' days ago';
}
function ckRenderAgent() {
  var box = el('ckAgentBox');
  if (!box) return;
  box.innerHTML = '';
  var p = ckProject();
  var r = p && p.last_run;
  if (r) {
    var l = ckEl('div', 'ck-kv');
    l.appendChild(ckEl('b', '', (r.phase === 'gate' ? 'Gate ' : 'Eval ') + r.req_id + ' '));
    l.appendChild(ckEl('span', /^PASS/.test(r.status) ? 'ck-ok' : 'ck-ko', r.status));
    l.appendChild(document.createTextNode(' · ' + ckAgo(r.ts)));
    box.appendChild(l);
    var c = ckEl('div', 'ck-kv');
    c.appendChild(ckEl('span', 'ck-ok', r.passed + ' ✔'));
    c.appendChild(document.createTextNode('  '));
    c.appendChild(ckEl('span', 'ck-ko', r.failed + ' ✖'));
    c.appendChild(document.createTextNode('  '));
    c.appendChild(ckEl('span', 'ck-warn', r.warnings + ' ⚠'));
    box.appendChild(c);
  }
  var a = (ck.state && ck.state.agent) || {};
  var exec = currentExecution();
  var who = exec === 'cloud_only' ? 'cloud · ' + (model.value || 'auto')
    : ({ gpt_codex: 'Codex', claude_code: 'Claude Code', auto: 'auto' }[a.executor] || 'agent') +
      ' · ' + (a.executor === 'claude_code' ? a.claude_model : a.codex_model || '') + (exec === 'prefer_local_agent' ? ' (cloud fallback: ' + (model.value || 'auto') + ')' : '');
  var w = ckEl('div', 'ck-kv');
  w.appendChild(document.createTextNode('Writes: '));
  w.appendChild(ckEl('b', '', who));
  box.appendChild(w);
  var ses = ck.session;
  if (ses && (ses.cost || ses.tokens)) {
    var c2 = ckEl('div', 'ck-kv');
    c2.appendChild(document.createTextNode('This session: '));
    c2.appendChild(ckEl('b', '', (ses.cost ? '$' + ses.cost.toFixed(2) + ' · ' : '') + rcTokens(ses.tokens) + ' tokens'));
    c2.title = 'Cost of the agent and cloud runs since VS Code opened (API-equivalent for subscriptions); per run and phase: telemetry portal';
    box.appendChild(c2);
  }
}

var ckHistDelete = null;
function ckRenderHistory() {
  var box = el('ckHistory');
  if (!box) return;
  box.innerHTML = '';
  var h = ck.state && ck.state.history;
  if (!h) { box.appendChild(ckEl('div', 'ck-empty', 'Open a folder to keep the conversations.')); return; }
  var top = ckEl('div', 'ck-hist-top');
  var nb = ckEl('button', 'ck-btn primary ck-ctl', '＋ New chat');
  nb.title = 'The current conversation goes to the history; with the agent, a new agent session starts too';
  nb.addEventListener('click', function () { if (!isBusy()) post('historyNew'); });
  top.appendChild(nb);
  top.appendChild(ckEl('span', 'ck-dim', (h.mode || '').toUpperCase() + (h.current ? ' · now: ' + h.current.count + ' messages' : ' · new conversation')));
  box.appendChild(top);
  if (!h.archived.length) { box.appendChild(ckEl('div', 'ck-empty', 'No earlier conversation in this mode.')); return; }
  h.archived.forEach(function (c) {
    var row = ckEl('div', 'ck-hist');
    row.title = c.title + ' — ' + new Date(c.first_ts).toLocaleString() + ' → ' + new Date(c.last_ts).toLocaleString() + ' · click: reopen it (the current one is kept in the history)';
    var t = ckEl('span', 't', c.title);
    var n = ckEl('span', 'n', ckAgo(c.last_ts) + ' · ' + c.count);
    row.appendChild(t); row.appendChild(n);
    if (ckHistDelete === c.id) {
      var yes = ckEl('button', 'ck-btn ck-ctl', 'delete');
      yes.addEventListener('click', function (ev) { ev.stopPropagation(); ckHistDelete = null; post('historyDelete', { id: c.id }); });
      var no = ckEl('button', 'ck-btn', 'keep');
      no.addEventListener('click', function (ev) { ev.stopPropagation(); ckHistDelete = null; ckRenderHistory(); });
      row.appendChild(yes); row.appendChild(no);
    } else {
      var x = ckEl('button', 'ck-x ck-ctl', '×');
      x.title = 'Delete this conversation';
      x.addEventListener('click', function (ev) { ev.stopPropagation(); ckHistDelete = c.id; ckRenderHistory(); });
      row.appendChild(x);
    }
    row.addEventListener('click', function () { if (!isBusy()) { ckToggleDrawer(false); post('historyOpen', { id: c.id }); } });
    box.appendChild(row);
  });
}

function ckRenderSummary() {
  var box = el('ckSummary');
  if (!box) return;
  box.innerHTML = '';
  var p = ckProject();
  if (!p || !p.harper) {
    box.appendChild(ckEl('div', 'ck-empty', 'No Harper project in this workspace.'));
    var init = ckEl('button', 'ck-btn primary ck-ctl', '/init <name>');
    init.title = 'Creates the Harper project here (Harper mode)';
    init.addEventListener('click', function () { ckRunCommand('/init <name>'); });
    box.appendChild(init);
    return;
  }
  var bar = ckEl('div', 'ck-bar');
  var g = ckEl('i', 'g'); g.style.width = p.progress_pct + '%'; bar.appendChild(g);
  box.appendChild(bar);
  var cur = (p.reqs || []).filter(function (r) { return r.status === 'in_progress'; })[0];
  var l = ckEl('div', 'ck-kv', (p.release ? p.release + ' · ' : '') + p.progress_pct + '% · ' +
    (cur ? cur.id + ' in progress (' + cur.note + ')' : (p.next && p.next.command ? 'next: ' + p.next.command : '')));
  box.appendChild(l);
  var go = ckEl('button', 'ck-btn ck-ctl', 'Go to Harper');
  go.addEventListener('click', function () { ckSetMode('harper'); });
  box.appendChild(go);
}

// narrow panels: one line with the phases and the next action, always visible
function ckRenderStrip() {
  var strip = el('ckStrip');
  if (!strip) return;
  strip.innerHTML = '';
  var p = ckProject();
  if (currentMode() !== 'harper' || !p || !p.harper) return;
  var pills = ckEl('span', 'ck-pills');
  pills.style.marginTop = '0';
  p.phases.forEach(function (ph) { pills.appendChild(ckPill(ph, ph.id === 'finalize' ? 'FIN' : ph.label)); });
  strip.appendChild(pills);
  if (p.next && p.next.command) {
    strip.appendChild(ckEl('code', 'ck-dim', p.next.command + ((p.alternatives || []).length ? '  (+' + p.alternatives.length + ' ☰)' : '')));
    var run = ckEl('button', 'ck-btn primary ck-ctl', 'Run');
    run.addEventListener('click', function () { ckRunCommand(p.next.command); });
    strip.appendChild(run);
  }
}

function ckRenderAll() {
  var badge = el('bmadBadge');
  if (badge) badge.style.display = ckPrefs().methodology === 'bmad' ? 'inline-block' : 'none';
  if (!COCKPIT) return;
  var harper = currentMode() === 'harper';
  document.querySelectorAll('#ckSide .ck-harper').forEach(function (n) { n.style.display = harper ? '' : 'none'; });
  document.querySelectorAll('#ckSide .ck-nonharper').forEach(function (n) { n.style.display = harper ? 'none' : ''; });
  ckRenderHead(); ckRenderConfig(); ckRenderMethodology(); ckRenderProject(); ckRenderReqs(); ckRenderNext();
  ckRenderAgent(); ckRenderSummary(); ckRenderHistory(); ckRenderStrip();
  ckApplyBusy();
}
// the cockpit's own controls follow the busy state (they are rebuilt on every state)
function ckApplyBusy() {
  var b = isBusy();
  document.querySelectorAll('.ck-ctl').forEach(function (n) { n.disabled = b; });
}

if (COCKPIT) {
  try { ckBuild(); } catch (e) { console.warn('[cockpit] build failed', e); }
}
[mode, model, execution].forEach(function (n) { if (n) n.addEventListener('change', function () { ckRenderAll(); acRender(); }); });

window.addEventListener('message', function (event) {
  var msg = event.data || {};
  if (msg.type === 'cockpitState') {
    ck.state = msg.state || null;
    if (layoutSel && msg.state && msg.state.theme && !isBusy()) layoutSel.value = document.body.getAttribute('data-theme');
    ckRenderAll();
    if (document.activeElement === prompt) acRender();
    return;
  }
  if (msg.type === 'initState' || msg.type === 'models') { ckRenderAll(); return; }
  if (msg.type === 'busy') { if (msg.on) acClose(); ckRenderAll(); return; }
  if (!COCKPIT) return;
  // the output drawer opens by itself when there is something to read in it
  var out = el('ckOutput');
  if (out && (msg.type === 'generateResult' || msg.type === 'applyResult' || msg.type === 'error' || msg.type === 'text' ||
      (msg.type === 'files' && msg.activate))) out.open = true;
});

// ===================== Run card (every layout) and smart Cancel =====================
// 'runProgress' from the extension: the command in flight with its real steps, the eval's live
// progress, what is happening now, its cost. Stop now asks first and says what it loses; "after
// this step" ends the --fix loop (or the autopilot) at the next step boundary.
var rc = { run: null, confirmUntil: 0, dismissed: {}, hideTimer: null };
var runCard = el('runCard');

function rcClock(ms) {
  var s = Math.max(0, Math.round((ms || 0) / 1000));
  var h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), sec = s % 60;
  return (h ? h + ':' + String(m).padStart(2, '0') : m) + ':' + String(sec).padStart(2, '0');
}
function rcTokens(n) { n = Number(n) || 0; return n >= 1e6 ? (n / 1e6).toFixed(1) + 'M' : Math.round(n / 1000) + 'k'; }
function rcIsAgent(run) { return run && run.executor && run.executor.indexOf('cloud') !== 0; }
function rcResumeCommand(run) {
  var req = run.req || '';
  if (run.kind === 'eval') return '/eval ' + req + ' --fix';
  if (run.kind === 'gate') return '/gate ' + req + (run.fix ? ' --fix' : '');
  if (run.kind === 'autopilot') return '/autopilot';
  return run.title;
}
/** What "Stop now" loses, said before doing it. */
function rcStopText(run) {
  var cur = run.current || {};
  var who = run.executor || 'the agent';
  if (run.kind === 'autopilot' && !cur.kind) return 'The autopilot ends for good (it will not resume at startup).';
  var lines = [];
  if (cur.kind === 'eval' || cur.kind === 'gate') {
    var ep = run.evalProgress;
    lines.push('The sandbox stops the running check and skips the others: this ' + cur.label +
      ' leaves no report' + (ep && ep.checks_total ? ' (' + ep.checks_done + '/' + ep.checks_total + ' checks done)' : '') + '. Code and tests do not change.');
    var left = cur.eta_ms ? cur.eta_ms - (Date.now() - cur.startedAt) : null;
    if (left !== null && left > 0 && left < 3 * 60000) lines.push('Tip: "after this step" lets it finish (~' + rcClock(left) + ') and keeps the report.');
  } else if (rcIsAgent(run)) {
    lines.push(who + ' is stopped with the processes it started. Files it already wrote stay where they are' +
      (cur.req && cur.req !== 'SOLUTION' ? ' (runs/kit/' + cur.req + '/)' : '') + ', uncommitted; what it returns is not used and there is no cloud fallback.');
  } else {
    lines.push('The request to the model is closed: its answer is discarded, nothing is written or committed.');
  }
  if (run.fix && run.fix.cycle) lines.push('The earlier cycles and their reports stay.');
  if (run.kind === 'autopilot') lines.push('The autopilot ends for good (it will not resume at startup).');
  return lines.join(' ');
}

function rcButton(label, cls, onClick, title) {
  var b = ckEl('button', cls || '', label);
  if (title) b.title = title;
  b.addEventListener('click', function (ev) { ev.preventDefault(); onClick(); });
  return b;
}

function rcStopNow() {
  rc.confirmUntil = 0;
  try { btnCancel.disabled = false; btnCancel.click(); } catch (e) { post('cancel'); }
}

function rcRender() {
  var run = rc.run;
  if (!runCard) return;
  if (!run || rc.dismissed[run.id]) { runCard.className = ''; runCard.innerHTML = ''; return; }
  var ended = run.ended;
  runCard.className = 'open' + (ended ? ' ended ' + ended.outcome : '');
  runCard.innerHTML = '';
  var now = Date.now();

  // title, cycle, time
  var top = ckEl('div', 'rc-top');
  var icon = ended ? ({ ok: '✔', failed: '✖', cancelled: '⏹' }[ended.outcome] || '✓') : '▶';
  top.appendChild(ckEl('span', 'rc-title', icon + ' ' + run.title));
  if (run.fix && !ended) {
    top.appendChild(ckEl('span', 'rc-sub', 'cycle ' + Math.max(1, run.fix.cycle) + ' of ' + run.fix.maxCycles +
      (run.fix.extraCycles ? ' (+' + run.fix.extraCycles + ' while failures drop)' : '')));
  }
  var cur = run.current;
  var timeTxt = '⏱ ' + rcClock((ended ? ended.at : now) - run.startedAt);
  if (!ended && cur && cur.eta_ms) {
    var left = cur.eta_ms - (now - cur.startedAt);
    timeTxt += left > 0 ? ' · ~' + rcClock(left) + ' left in ' + cur.label : ' · longer than last time';
  }
  timeTxt += ' · ' + run.executor;
  top.appendChild(ckEl('span', 'rc-time', timeTxt));
  if (ended) {
    var x = rcButton('×', 'rc-x', function () { rc.dismissed[run.id] = true; rcRender(); }, 'Close');
    top.appendChild(x);
  }
  runCard.appendChild(top);

  // steps
  var steps = ckEl('div', 'rc-steps');
  (run.steps || []).forEach(function (st, i) {
    if (i) steps.appendChild(ckEl('span', 'rc-arrow', '→'));
    var txt = st.label + (run.kind === 'autopilot' && st.req ? ' ' + st.req : '');
    if (st.counts) txt += ' · ' + st.counts.passed + ' ✔' + (st.counts.failed ? ' ' + st.counts.failed + ' ✖' : '');
    else if (st.state !== 'running' && st.endedAt) txt += ' · ' + rcClock(st.endedAt - st.startedAt);
    steps.appendChild(ckEl('span', 'rc-step ' + st.state, txt + (st.state === 'running' ? ' ●' : '')));
  });
  if (!ended && run.stopAfterStep) {
    steps.appendChild(ckEl('span', 'rc-arrow', '→'));
    steps.appendChild(ckEl('span', 'rc-step next', '⏸ stop'));
  } else if (!ended && (run.kind === 'eval' || run.kind === 'gate') && run.fix) {
    steps.appendChild(ckEl('span', 'rc-arrow', '→'));
    steps.appendChild(ckEl('span', 'rc-step next', run.kind === 'eval' ? 'then: /gate' : 'then: promote'));
  }
  runCard.appendChild(steps);

  // bar: the eval's checks when the sandbox reports them, else the estimate, else indeterminate
  if (!ended) {
    var bar = ckEl('div', 'rc-bar');
    var fill = ckEl('i');
    var ep = run.evalProgress;
    var line = '';
    if (ep && ep.phase === 'checks' && ep.checks_total) {
      fill.style.width = Math.round(100 * ep.checks_done / ep.checks_total) + '%';
      line = 'checks ' + ep.checks_done + '/' + ep.checks_total + (ep.current ? ' · now: ' + ep.current : '') +
        (ep.failed ? ' · ' + ep.failed + ' ✖ so far' : '');
    } else if (ep && ep.phase === 'regression' && ep.regression_total) {
      fill.style.width = Math.round(100 * ep.regression_done / ep.regression_total) + '%';
      line = 'regression of the promoted REQs ' + ep.regression_done + '/' + ep.regression_total +
        ((ep.regression_current || []).length ? ' · now: ' + ep.regression_current.join(', ') : '');
    } else if (ep && ep.phase === 'setup') {
      bar.classList.add('indet');
      line = 'preparing the eval environment (dependencies, services)…';
    } else if (cur && cur.eta_ms) {
      fill.className = 'p';
      fill.style.width = Math.min(95, Math.round(100 * (now - cur.startedAt) / cur.eta_ms)) + '%';
    } else {
      bar.classList.add('indet');
    }
    bar.appendChild(fill);
    runCard.appendChild(bar);
    if (line) runCard.appendChild(ckEl('div', 'rc-line', line));
  }
  if (run.live && !ended) {
    var live = ckEl('div', 'rc-line');
    live.appendChild(ckEl('b', '', 'Now: '));
    live.appendChild(document.createTextNode(run.live));
    live.title = run.live;
    runCard.appendChild(live);
  }
  if (run.autopilot) {
    var ap = run.autopilot;
    runCard.appendChild(ckEl('div', 'rc-line', 'Promoted: ' + (ap.promoted.join(', ') || 'none') +
      (ap.parked.length ? ' · parked: ' + ap.parked.join(', ') : '') + (ap.current ? ' · at: ' + ap.current : '')));
  }
  if (run.cost && (run.cost.usd || run.cost.tokens)) {
    runCard.appendChild(ckEl('div', 'rc-line', 'Cost of this run: ' + (run.cost.usd ? '$' + run.cost.usd.toFixed(2) + ' (API-equivalent) · ' : '') +
      rcTokens(run.cost.tokens) + ' tokens'));
  }

  if (!ended) {
    // stop: after this step (or REQ), or now with a confirmation that says what is lost
    if (rc.confirmUntil > now) {
      var conf = ckEl('div', 'rc-confirm');
      var secs = Math.ceil((rc.confirmUntil - now) / 1000);
      conf.appendChild(ckEl('b', '', 'Stop now? '));
      conf.appendChild(document.createTextNode(rcStopText(run)));
      var a = ckEl('div', 'rc-actions');
      a.appendChild(rcButton('⏹ Yes, stop now', 'danger', rcStopNow));
      a.appendChild(rcButton('Keep going (' + secs + ')', '', function () { rc.confirmUntil = 0; rcRender(); }));
      if (!run.stopAfterStep) a.appendChild(rcButton('⏸ After this step instead', 'primary', function () { rc.confirmUntil = 0; post('cancelAfterStep'); }));
      conf.appendChild(a);
      runCard.appendChild(conf);
    } else if (run.stopAfterStep || run.stopAfterReq) {
      var stepName = run.kind === 'autopilot' && run.autopilot && run.autopilot.current ? run.autopilot.current : (cur ? cur.label : 'this step');
      var armed = ckEl('div', 'rc-armed', '⏸ Stops at the end of ' + (run.stopAfterReq ? 'the current REQ' : stepName) +
        ': ' + (cur && (cur.kind === 'eval' || cur.kind === 'gate') ? 'the report is kept, ' : '') + 'nothing new starts. ');
      armed.appendChild(rcButton('undo', '', function () { post('cancelUndoStop'); }));
      armed.appendChild(document.createTextNode(' '));
      armed.appendChild(rcButton('⏹ Stop now', 'danger', function () { rc.confirmUntil = Date.now() + 8000; rcRender(); }));
      runCard.appendChild(armed);
    } else {
      var acts = ckEl('div', 'rc-actions');
      acts.appendChild(rcButton('⏸ After this step', '', function () { post('cancelAfterStep'); },
        'Lets the current step finish (its result is kept), then stops: no new repair, eval or REQ starts.'));
      if (run.kind === 'autopilot') {
        acts.appendChild(rcButton('⏸ After this REQ', '', function () { post('cancelAfterReq'); },
          'The current REQ goes to its gate, then the autopilot stops.'));
      }
      acts.appendChild(rcButton('⏹ Stop now', 'danger', function () { rc.confirmUntil = Date.now() + 8000; rcRender(); },
        'Asks first and says what is lost (Esc)'));
      acts.appendChild(ckEl('span', 'rc-hint', 'Esc = stop now (asks first)'));
      runCard.appendChild(acts);
    }
  } else {
    // the summary: what was done, what was interrupted, how to go on
    var ul = ckEl('ul', 'rc-sum');
    var done = (run.steps || []).filter(function (st) { return st.state !== 'cancelled'; });
    var cut = (run.steps || []).filter(function (st) { return st.state === 'cancelled'; });
    if (done.length) ul.appendChild(ckEl('li', '', 'Done: ' + done.map(function (st) {
      return st.label + (st.counts ? ' (' + st.counts.passed + ' ✔' + (st.counts.failed ? ', ' + st.counts.failed + ' ✖' : '') + ')' : ' ' + ({ ok: '✔', failed: '✖' }[st.state] || ''));
    }).join(' → ')));
    if (cut.length) ul.appendChild(ckEl('li', '', 'Stopped: ' + cut.map(function (st) { return st.label + ' after ' + rcClock(st.endedAt - st.startedAt); }).join(', ')));
    var wrote = (run.steps || []).some(function (st) { return (st.kind === 'kit' || st.kind === 'repair') && st.state === 'cancelled'; });
    if (wrote && rcIsAgent(run)) ul.appendChild(ckEl('li', '', 'Files the agent wrote before the stop stay uncommitted: check them in Source Control.'));
    if (ul.children.length) runCard.appendChild(ul);
    var acts2 = ckEl('div', 'rc-actions');
    if (ended.outcome !== 'ok' && run.kind !== 'idea' && run.kind !== 'spec' && run.kind !== 'plan') {
      var resume = rcResumeCommand(run);
      acts2.appendChild(rcButton('↻ ' + resume, 'primary', function () {
        if (isBusy()) return;
        prompt.value = resume;
        rc.dismissed[run.id] = true;
        onSend();
      }, 'Run it now'));
    }
    if (wrote) acts2.appendChild(rcButton('Show changes', '', function () { post('showChanges'); }));
    if (acts2.children.length) runCard.appendChild(acts2);
  }
}

// Esc while a command runs: Stop now, with its confirmation
document.addEventListener('keydown', function (ev) {
  if (ev.key !== 'Escape' || !rc.run || rc.run.ended || !isBusy()) return;
  var overlay = document.getElementById('clikeHelpOverlay');
  if (overlay && overlay.style.display === 'block') return;
  if (rc.confirmUntil > Date.now()) { rc.confirmUntil = 0; } else { rc.confirmUntil = Date.now() + 8000; }
  rcRender();
});
// the clock and the confirmation countdown
setInterval(function () { if (rc.run && (!rc.run.ended || rc.confirmUntil)) rcRender(); }, 1000);

window.addEventListener('message', function (event) {
  var msg = event.data || {};
  if (msg.type !== 'runProgress') return;
  var prev = rc.run;
  rc.run = msg.run || null;
  if (rc.run && rc.run.session) { ck.session = rc.run.session; try { ckRenderAgent(); } catch (e) {} }
  if (rc.run && prev && prev.id !== rc.run.id) rc.confirmUntil = 0;
  clearTimeout(rc.hideTimer);
  if (rc.run && rc.run.ended && rc.run.ended.outcome === 'ok') {
    var id = rc.run.id;
    rc.hideTimer = setTimeout(function () { rc.dismissed[id] = true; rcRender(); }, 20000);
  }
  rcRender();
});

// init
post('fetchModels');
post('cockpitRefresh');
</script>
<div id="clikeHelpOverlay" role="dialog" aria-modal="true" aria-label="CLike Help">
  <div id="clikeHelpCard">
    <span id="clikeHelpClose">✖</span>
    <h2>CLike — Slash Commands in Harper Mode</h2>
    <ul id="clikeHelpList"></ul>
    <p style="opacity:.8;margin-top:8px">Tip: you can attach workspace files and use <code>/spec</code>, <code>/plan</code>, and <code>/kit</code> for the Harper flow.</p>
    </div>
</div>

</body>
</html>`;
}


module.exports = { CHAT_THEMES, getChatTheme, getWebviewHtml };
