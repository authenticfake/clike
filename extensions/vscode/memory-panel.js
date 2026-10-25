'use strict';
// The Memory panel: a panel of its own, next to the chat, to query the project's RAG memory and the
// CLike guide in natural language (any language) and to see what each holds. It does not interact
// with the chat: each panel has a button that opens (or reveals) the other, nothing else. Files are
// added to the memory from the chat (📎 Attach); here they are listed.

const fs = require('fs');
const path = require('path');
const { GUIDE_PROJECT_ID, guideRoot } = require('./memory-guide');

const RECENT_KEY = 'clike.memory.recent';
const MAX_RECENT = 10;
const TOP_K = 12;

const PROJECT_GROUPS = [
  { key: 'harper', label: 'Harper documents', test: (p) => p.startsWith('docs/harper/') },
  { key: 'kits', label: 'REQ KITs', test: (p) => p.startsWith('runs/kit/') },
  { key: 'reports', label: 'Eval and gate reports', test: (p) => p.startsWith('runs/eval/') || p.startsWith('runs/gate/') },
  { key: 'other', label: 'Attachments and other files', test: () => true },
];

/** Project sources [{ path, chunks }] → groups [{ key, label, files, chunks, items }] (empty ones dropped). */
function groupProjectSources(sources) {
  const groups = PROJECT_GROUPS.map((g) => ({ key: g.key, label: g.label, files: 0, chunks: 0, items: [] }));
  for (const s of sources || []) {
    const p = String(s.path || '').replace(/\\/g, '/');
    if (!p) continue;
    const i = PROJECT_GROUPS.findIndex((g) => g.test(p));
    const g = groups[i];
    g.items.push({ path: p, chunks: Number(s.chunks) || 0 });
    g.files += 1;
    g.chunks += Number(s.chunks) || 0;
  }
  return groups.filter((g) => g.files);
}

/** Search hits → one result per file (its best chunk), best first. */
function bestPerFile(hits) {
  const best = new Map();
  for (const h of hits || []) {
    const p = String(h.path || '');
    if (!p) continue;
    const cur = best.get(p);
    if (!cur || Number(h.score) > Number(cur.score)) best.set(p, { path: p, score: Number(h.score) || 0, text: String(h.text || '') });
  }
  return [...best.values()].sort((a, b) => b.score - a.score);
}

function addRecent(list, scope, query) {
  const q = String(query || '').trim();
  if (!q) return list || [];
  return [{ scope, query: q }, ...(list || []).filter((r) => !(r.scope === scope && r.query === q))].slice(0, MAX_RECENT);
}

let current = null;

/**
 * Open the Memory panel, or reveal it. deps: { context, extensionRoot, post(url, body), orchestratorUrl(), projectId(),
 * workspaceRoot() (fsPath or ''), openChat(), guide: { status(), refresh() } }.
 */
function openMemoryPanel(deps) {
  const vscode = require('vscode');
  if (current) {
    try { current.reveal(); return current; } catch { current = null; }
  }
  const panel = vscode.window.createWebviewPanel('clikeMemory', 'CLike Memory', vscode.ViewColumn.Beside,
    { enableScripts: true, retainContextWhenHidden: true });
  current = panel;
  panel.onDidDispose(() => { if (current === panel) current = null; });
  panel.webview.html = memoryHtml();
  const send = (msg) => panel.webview.postMessage(msg);
  const recent = () => deps.context.workspaceState.get(RECENT_KEY) || [];
  const collection = (scope) => (scope === 'guide' ? GUIDE_PROJECT_ID : deps.projectId());

  async function sources(scope) {
    try {
      return await deps.post(`${deps.orchestratorUrl()}/v1/rag/sources`, { project_id: collection(scope) });
    } catch (e) {
      return { ok: false, sources: [], total_chunks: 0, error: String(e?.message || e) };
    }
  }

  async function sendState() {
    const [project, guide] = await Promise.all([sources('project'), sources('guide')]);
    send({
      type: 'state',
      project: { name: deps.projectId(), ok: project.ok !== false, error: project.error || '', chunks: project.total_chunks || 0, groups: groupProjectSources(project.sources) },
      guide: { ok: guide.ok !== false, chunks: guide.total_chunks || 0, items: (guide.sources || []).map((s) => ({ path: s.path, chunks: s.chunks })), indexing: deps.guide.status() },
      recent: recent(),
    });
  }

  async function search(scope, query) {
    const q = String(query || '').trim();
    if (!q) return;
    await deps.context.workspaceState.update(RECENT_KEY, addRecent(recent(), scope, q));
    try {
      const res = await deps.post(`${deps.orchestratorUrl()}/v1/rag/search`, { project_id: collection(scope), query: q, top_k: TOP_K });
      send({ type: 'results', scope, query: q, results: bestPerFile(res?.hits), recent: recent() });
    } catch (e) {
      send({ type: 'results', scope, query: q, results: [], error: String(e?.message || e), recent: recent() });
    }
  }

  async function open(scope, rel) {
    const root = scope === 'guide' ? guideRoot(deps.extensionRoot) : deps.workspaceRoot();
    const base = root ? path.resolve(root) : '';
    const abs = base ? path.resolve(base, ...String(rel || '').split('/')) : '';
    if (!abs || !abs.startsWith(base + path.sep) || !fs.existsSync(abs)) {
      send({ type: 'notice', text: `${rel} is not a file of ${scope === 'guide' ? 'the guide' : 'the workspace'} (indexed from an attachment or since removed).` });
      return;
    }
    const uri = vscode.Uri.file(abs);
    if (abs.toLowerCase().endsWith('.md')) await vscode.commands.executeCommand('markdown.showPreview', uri);
    else await vscode.window.showTextDocument(uri, { preview: true, viewColumn: vscode.ViewColumn.One });
  }

  panel.webview.onDidReceiveMessage(async (msg) => {
    if (!msg) return;
    if (msg.type === 'ready' || msg.type === 'refresh') return sendState();
    if (msg.type === 'search') return search(msg.scope === 'guide' ? 'guide' : 'project', msg.query);
    if (msg.type === 'open') return open(msg.scope === 'guide' ? 'guide' : 'project', msg.path);
    if (msg.type === 'openChat') return deps.openChat();
    if (msg.type === 'reindexGuide') {
      send({ type: 'notice', text: 'Indexing the CLike guide…' });
      await deps.guide.refresh();
      return sendState();
    }
    return undefined;
  });
  return panel;
}

function memoryHtml() {
  return `<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<style>
  * { box-sizing: border-box; }
  body { margin: 0; padding: 10px 12px; color: var(--vscode-foreground); background: var(--vscode-editor-background); font: 13px var(--vscode-font-family); }
  button { font: inherit; cursor: pointer; }
  .head { display: flex; align-items: center; gap: 10px; padding: 7px 10px; border-radius: 6px; background: var(--vscode-sideBarSectionHeader-background, rgba(124,58,237,.15)); }
  .head .t { font-weight: 700; letter-spacing: .04em; }
  .led { width: 8px; height: 8px; border-radius: 50%; background: #9ca3af; display: inline-block; }
  .led.ok { background: #22c55e; } .led.bad { background: #ef4444; }
  .dim { opacity: .7; } .small { font-size: 11.5px; }
  .chatBtn { margin-left: auto; border: 1px solid #7c3aed; background: transparent; color: inherit; border-radius: 6px; padding: 2px 10px; }
  .grid { display: grid; grid-template-columns: 260px 1fr; gap: 0; margin-top: 10px; min-height: 0; }
  .nav { border-right: 1px solid var(--vscode-panel-border, #333); padding-right: 10px; }
  .nav h5 { margin: 12px 0 6px; font-size: 11px; letter-spacing: .06em; opacity: .7; }
  .nav .it { display: flex; gap: 6px; padding: 3px 6px; border-radius: 4px; cursor: pointer; }
  .nav .it:hover, .nav .it.on { background: var(--vscode-list-hoverBackground, rgba(255,255,255,.06)); }
  .nav .it.sub { padding-left: 20px; }
  .nav .n { margin-left: auto; opacity: .7; font-size: 11px; }
  .main { padding-left: 16px; min-width: 0; }
  .scope { display: inline-flex; gap: 3px; padding: 3px; border-radius: 8px; background: var(--vscode-input-background); }
  .scope button { border: 0; border-radius: 6px; padding: 4px 12px; background: transparent; color: inherit; font-weight: 600; opacity: .75; }
  .scope button.on { background: #7c3aed; color: #fff; opacity: 1; }
  .ask { display: flex; gap: 8px; margin-top: 10px; }
  .ask input { flex: 1; padding: 7px 10px; border-radius: 6px; border: 1px solid var(--vscode-input-border, #3f3f46); background: var(--vscode-input-background); color: var(--vscode-input-foreground); font: inherit; }
  .ask button { border: 0; border-radius: 6px; padding: 0 14px; background: #7c3aed; color: #fff; }
  .card { border: 1px solid var(--vscode-panel-border, #3f3f46); border-radius: 8px; padding: 7px 10px; margin-top: 8px; }
  .card .top { display: flex; gap: 8px; align-items: center; }
  .card .p { font-family: var(--vscode-editor-font-family, monospace); font-size: 12px; flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .card .snip { margin-top: 4px; opacity: .8; font-size: 12px; white-space: pre-wrap; max-height: 5.5em; overflow: hidden; }
  .link { color: var(--vscode-textLink-foreground); cursor: pointer; font-size: 11.5px; }
  .row { display: flex; gap: 8px; padding: 3px 4px; border-radius: 4px; cursor: pointer; font-size: 12.5px; }
  .row:hover { background: var(--vscode-list-hoverBackground, rgba(255,255,255,.06)); }
  .row .p { flex: 1; font-family: var(--vscode-editor-font-family, monospace); font-size: 12px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  h4 { margin: 14px 0 4px; font-size: 12px; letter-spacing: .04em; opacity: .75; }
  .notice { margin-top: 10px; padding: 6px 10px; border-radius: 6px; border: 1px solid #b45309; font-size: 12px; }
  .filter { width: 100%; margin-top: 6px; padding: 5px 8px; border-radius: 6px; border: 1px solid var(--vscode-input-border, #3f3f46); background: var(--vscode-input-background); color: var(--vscode-input-foreground); font: inherit; }
</style></head>
<body>
  <div class="head"><span class="t">🧠 MEMORY</span><span id="led" class="led"></span><span id="sum" class="dim small">loading…</span>
    <button id="chat" class="chatBtn" title="Open the CLike chat (or bring it to the front)">💬 Chat</button></div>
  <div class="grid">
    <div class="nav">
      <h5>CONTENTS</h5><div id="contents"></div>
      <h5>RECENT SEARCHES</h5><div id="recent"></div>
    </div>
    <div class="main">
      <div class="scope"><button data-scope="project" class="on">Project</button><button data-scope="guide">CLike Guide</button></div>
      <div class="ask"><input id="q" placeholder="Ask in any language, e.g. how does --accept work?"><button id="go">Search</button></div>
      <div id="notice"></div>
      <div id="view"></div>
    </div>
  </div>
<script>
  const vscode = acquireVsCodeApi();
  const $ = (id) => document.getElementById(id);
  let scope = 'project';
  let state = null;
  const esc = (s) => String(s == null ? '' : s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  function setScope(s) {
    scope = s;
    document.querySelectorAll('.scope button').forEach((b) => b.classList.toggle('on', b.dataset.scope === s));
  }
  function el(tag, cls, html) { const e = document.createElement(tag); if (cls) e.className = cls; if (html != null) e.innerHTML = html; return e; }
  function navItem(label, n, cls, onClick) {
    const it = el('div', 'it' + (cls ? ' ' + cls : ''), esc(label) + '<span class="n">' + esc(n) + '</span>');
    it.addEventListener('click', onClick);
    return it;
  }
  function showList(title, sc, items) {
    setScope(sc);
    const v = $('view'); v.innerHTML = '';
    v.appendChild(el('h4', '', esc(title) + ' · ' + items.length + ' file(s)'));
    const f = el('input', 'filter'); f.placeholder = 'Filter by name…'; v.appendChild(f);
    const box = el('div'); v.appendChild(box);
    const draw = () => {
      box.innerHTML = '';
      const k = f.value.toLowerCase();
      items.filter((i) => !k || i.path.toLowerCase().includes(k)).forEach((i) => {
        const r = el('div', 'row', '<span class="p">' + esc(i.path) + '</span><span class="dim small">' + i.chunks + ' chunk(s)</span>');
        r.title = 'Open';
        r.addEventListener('click', () => vscode.postMessage({ type: 'open', scope: sc, path: i.path }));
        box.appendChild(r);
      });
    };
    f.addEventListener('input', draw); draw();
  }
  function renderState(s) {
    state = s;
    const ok = s.project.ok && s.guide.ok;
    $('led').className = 'led ' + (ok ? 'ok' : 'bad');
    $('sum').textContent = ok
      ? s.project.name + ' · project ' + s.project.chunks + ' · guide ' + s.guide.chunks + ' chunks'
      : 'the memory service does not answer: ' + (s.project.error || 'unreachable');
    const c = $('contents'); c.innerHTML = '';
    const gi = s.guide.indexing || {};
    const guideNote = gi.status === 'indexing' ? 'indexing…' : s.guide.items.length + ' files';
    c.appendChild(navItem('📘 CLike Guide', guideNote, '', () => showList('CLike Guide', 'guide', s.guide.items)));
    if (gi.status === 'failed' || gi.status === 'missing') {
      c.appendChild(navItem('⚠ guide not indexed — retry', '', 'sub', () => vscode.postMessage({ type: 'reindexGuide' })));
    }
    const all = s.project.groups.reduce((a, g) => a.concat(g.items), []);
    c.appendChild(navItem('📁 Project', all.length + ' files', '', () => showList('Project', 'project', all)));
    s.project.groups.forEach((g) => c.appendChild(navItem(g.label, g.files, 'sub', () => showList(g.label, 'project', g.items))));
    if (!all.length && s.project.ok) c.appendChild(el('div', 'it sub dim small', 'nothing indexed yet: /kit and chat attachments add to it'));
    renderRecent(s.recent);
  }
  function renderRecent(list) {
    const r = $('recent'); r.innerHTML = '';
    (list || []).forEach((x) => r.appendChild(navItem(x.query, x.scope === 'guide' ? 'guide' : '', 'sub', () => { setScope(x.scope); $('q').value = x.query; go(); })));
  }
  function renderResults(m) {
    const v = $('view'); v.innerHTML = '';
    if (m.error) { v.appendChild(el('div', 'notice', esc(m.error))); return; }
    v.appendChild(el('h4', '', (m.scope === 'guide' ? 'CLike Guide' : 'Project') + ' · ' + m.results.length + ' result(s) for “' + esc(m.query) + '”'));
    if (!m.results.length) v.appendChild(el('div', 'dim small', 'Nothing relevant found. Try other words, or the other memory.'));
    m.results.forEach((h) => {
      const card = el('div', 'card', '<div class="top"><span class="p">' + esc(h.path) + '</span><span class="dim small">' + h.score.toFixed(2) + '</span></div>' +
        '<div class="snip">' + esc(h.text.slice(0, 400)) + '</div><span class="link">Open</span>');
      card.querySelector('.link').addEventListener('click', () => vscode.postMessage({ type: 'open', scope: m.scope, path: h.path }));
      v.appendChild(card);
    });
    renderRecent(m.recent);
  }
  function go() {
    const q = $('q').value.trim();
    if (!q) return;
    $('view').innerHTML = '<div class="dim small" style="margin-top:10px">Searching…</div>';
    vscode.postMessage({ type: 'search', scope, query: q });
  }
  document.querySelectorAll('.scope button').forEach((b) => b.addEventListener('click', () => setScope(b.dataset.scope)));
  $('go').addEventListener('click', go);
  $('q').addEventListener('keydown', (e) => { if (e.key === 'Enter') go(); });
  $('chat').addEventListener('click', () => vscode.postMessage({ type: 'openChat' }));
  window.addEventListener('message', (e) => {
    const m = e.data || {};
    if (m.type === 'state') renderState(m);
    else if (m.type === 'results') renderResults(m);
    else if (m.type === 'notice') { $('notice').innerHTML = '<div class="notice">' + esc(m.text) + '</div>'; setTimeout(() => { $('notice').innerHTML = ''; }, 6000); }
  });
  vscode.postMessage({ type: 'ready' });
</script>
</body></html>`;
}

module.exports = { openMemoryPanel, groupProjectSources, bestPerFile, addRecent, memoryHtml };
