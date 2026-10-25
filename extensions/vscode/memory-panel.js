'use strict';
// The Memory panel: a panel of its own, next to the chat, to query the project's RAG memory and the
// CLike guide in natural language (any language) and to see what each holds. It does not interact
// with the chat: each panel has a button that opens (or reveals) the other, nothing else. Files are
// added to the memory from the chat (📎 Attach); here they are listed.

const fs = require('fs');
const path = require('path');
const { GUIDE_PROJECT_ID, guideRoot } = require('./memory-guide');
const { pickSources, buildAskPrompt, parseAskAnswer, pendingTestPatches, nowSuggestions, stateContext, lastRunFailures } = require('./memory-ask');

const RECENT_KEY = 'clike.memory.recent';
const MAX_RECENT = 10;
// candidates fetched from the store, then reranked; results shown (one per file)
const CANDIDATES = 40;
const MAX_RESULTS = 12;
const SNIPPET_LINES = 6;
// weight of the exact words of the question against the semantic score
const LEXICAL_WEIGHT = 0.15;

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

/** The words of a question worth matching exactly: lowercased, 3+ characters, flags and paths kept whole. */
function queryTerms(query) {
  const terms = String(query || '').toLowerCase().match(/[\p{L}\p{N}][\p{L}\p{N}_./-]*|--?[\p{L}\p{N}][\p{L}\p{N}_-]*|\/[\p{L}\p{N}][\p{L}\p{N}_-]*/gu) || [];
  return [...new Set(terms.map((t) => t.replace(/[.]+$/, '')).filter((t) => t.length >= 3))];
}

// a question word as a whole word ("che" is not in "checks"; "--accept" is a word)
const termPatterns = new Map();
function hasTerm(text, term) {
  if (!termPatterns.has(term)) {
    // the characters special in a regular expression; '-' and '/' are literal outside a class
    const body = term.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
    termPatterns.set(term, new RegExp(`(?<![\\p{L}\\p{N}_])${body}(?![\\p{L}\\p{N}_])`, 'u'));
  }
  return termPatterns.get(term).test(text);
}

/**
 * Semantic hits reranked with the question's exact words. A word counts by how rare it is among the
 * candidates (common words weigh little, `--accept` a lot); a word no candidate contains (another
 * language) is ignored, so a question in any language keeps its semantic ranking.
 */
function rerank(hits, query) {
  const terms = queryTerms(query);
  const docs = (hits || []).map((h) => String(h.text || '').toLowerCase());
  const n = docs.length;
  const weight = {};
  for (const t of terms) {
    const df = docs.filter((d) => hasTerm(d, t)).length;
    if (df) weight[t] = Math.log(1 + n / df);
  }
  const total = Object.values(weight).reduce((a, b) => a + b, 0);
  return (hits || []).map((h, i) => {
    const matched = total ? Object.keys(weight).filter((t) => hasTerm(docs[i], t)).reduce((a, t) => a + weight[t], 0) / total : 0;
    return { ...h, score: (Number(h.score) || 0) + LEXICAL_WEIGHT * matched };
  });
}

/**
 * The question's words that tell results apart: in at most half of the candidates (a word in all of
 * them — "the", "what", "come" — says nothing). Any language: rarity, not a word list.
 */
function distinctiveTerms(hits, query) {
  const docs = (hits || []).map((h) => String(h.text || '').toLowerCase());
  const limit = Math.max(1, Math.floor(docs.length / 2));
  return queryTerms(query).filter((t) => {
    const df = docs.filter((d) => hasTerm(d, t)).length;
    return df > 0 && df <= limit;
  });
}

/** The lines of a chunk that answer the question: the window around the line with most question words. */
function focusSnippet(text, terms, lines = SNIPPET_LINES) {
  const all = String(text || '').split(/\r?\n/);
  let best = 0;
  let bestHits = -1;
  all.forEach((line, i) => {
    const l = line.toLowerCase();
    const hits = terms.reduce((a, t) => a + (hasTerm(l, t) ? 1 : 0), 0);
    if (hits > bestHits) { best = i; bestHits = hits; }
  });
  // a chunk starts anywhere: without a match, skip its first (cut) line
  const start = bestHits > 0 ? Math.max(0, best - 1) : Math.min(1, all.length - 1);
  return all.slice(start, start + lines).join('\n').trim();
}

/** Search hits → one result per file (its best chunk after reranking), best first, focused snippets. */
function bestPerFile(hits, query = '') {
  const terms = distinctiveTerms(hits, query);
  const best = new Map();
  for (const h of rerank(hits, query)) {
    const p = String(h.path || '');
    if (!p) continue;
    const cur = best.get(p);
    if (!cur || h.score > cur.score) best.set(p, { path: p, score: h.score, text: String(h.text || '') });
  }
  return [...best.values()]
    .sort((a, b) => b.score - a.score)
    .slice(0, MAX_RESULTS)
    .map((r) => ({ path: r.path, score: r.score, text: focusSnippet(r.text, terms), terms }));
}

// a file inside a hidden folder of any KIT (ci/.tmp copies, caches) never belongs to the memory
const HIDDEN_KIT_PATH = /^runs\/kit\/[^/]+\/(?:[^/]+\/)*\.[^/]+\//;

/**
 * Memory paths to remove after a REQ's KIT is indexed: its files the KIT no longer has (kept: the
 * paths just indexed), and files in hidden folders of any KIT, indexed by earlier versions.
 */
function staleKitPaths(sources, reqId, keptPaths) {
  const req = String(reqId || '').toUpperCase();
  const prefix = req ? `runs/kit/${req}/` : null;
  const kept = new Set((keptPaths || []).map((p) => String(p).replace(/\\/g, '/')));
  return (sources || []).map((s) => String(s.path || ''))
    .filter((p) => !kept.has(p) && ((prefix && p.startsWith(prefix)) || HIDDEN_KIT_PATH.test(p)));
}

function addRecent(list, scope, query) {
  const q = String(query || '').trim();
  if (!q) return list || [];
  return [{ scope, query: q }, ...(list || []).filter((r) => !(r.scope === scope && r.query === q))].slice(0, MAX_RECENT);
}

let current = null;

/**
 * Open the Memory panel, or reveal it. deps: { context, extensionRoot, post(url, body), orchestratorUrl(), projectId(),
 * workspaceRoot() (fsPath or ''), openChat(), guide: { status(), refresh() },
 * projectState() (the cockpit state or null), ask(prompt) → { text, by } (the chat's cloud model or
 * the local agent, read-only), copy(text) }.
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
      now: now(),
    });
  }

  function now() {
    let state = null;
    try { state = deps.projectState(); } catch { state = null; }
    const root = deps.workspaceRoot();
    const patches = pendingTestPatches(root);
    return { suggestions: nowSuggestions(state, patches), context: stateContext(state, patches, lastRunFailures(root, state && state.last_run)) };
  }

  async function candidates(scope, q) {
    try {
      const res = await deps.post(`${deps.orchestratorUrl()}/v1/rag/search`, { project_id: collection(scope), query: q, top_k: CANDIDATES });
      return rerank(res?.hits || [], q);
    } catch {
      return [];
    }
  }

  // when a project file was last changed: the answer prefers newer sources over outdated ones
  function modifiedOf(rel) {
    try {
      const base = path.resolve(deps.workspaceRoot());
      const abs = path.resolve(base, ...String(rel).split('/'));
      if (!abs.startsWith(base + path.sep)) return '';
      return fs.statSync(abs).mtime.toISOString().slice(0, 16).replace('T', ' ');
    } catch { return ''; }
  }

  // Ask: the best chunks of the chosen memories → an answer written only from them
  async function ask(query, scopes) {
    const q = String(query || '').trim();
    if (!q) return;
    const which = (scopes || []).filter((x) => x === 'project' || x === 'guide');
    const use = which.length ? which : ['project', 'guide'];
    await deps.context.workspaceState.update(RECENT_KEY, addRecent(recent(), use.length === 1 ? use[0] : 'both', q));
    send({ type: 'asking', query: q, recent: recent() });
    const found = {};
    await Promise.all(use.map(async (scope) => { found[scope] = await candidates(scope, q); }));
    const limits = use.length === 1 ? { [use[0]]: 8 } : { project: 5, guide: 4 };
    const sources = pickSources(found, limits).map((src) => ({ ...src, modified: src.collection === 'project' ? modifiedOf(src.path) : '' }));
    const terms = distinctiveTerms([...(found.project || []), ...(found.guide || [])], q);
    const shown = sources.map((src) => ({ n: src.n, collection: src.collection, path: src.path, modified: src.modified, score: src.score, text: focusSnippet(src.text, terms), terms }));
    if (!sources.length) {
      send({ type: 'answer', query: q, sources: [], answer: { answer: 'Nothing in the memory matches this question.', steps: [], confidence: 'low', confidence_reason: 'no source found', sources_used: [], followups: [], not_in_memory: true }, by: '' });
      return;
    }
    try {
      const reply = await deps.ask(buildAskPrompt(q, sources, now().context));
      send({ type: 'answer', query: q, sources: shown, answer: parseAskAnswer(reply.text, sources), by: reply.by || '' });
    } catch (e) {
      send({ type: 'answer', query: q, sources: shown, error: String(e?.message || e), by: '' });
    }
  }

  async function search(scope, query) {
    const q = String(query || '').trim();
    if (!q) return;
    await deps.context.workspaceState.update(RECENT_KEY, addRecent(recent(), scope, q));
    try {
      const res = await deps.post(`${deps.orchestratorUrl()}/v1/rag/search`, { project_id: collection(scope), query: q, top_k: CANDIDATES });
      send({ type: 'results', scope, query: q, results: bestPerFile(res?.hits, q), recent: recent() });
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
    if (msg.type === 'ask') return ask(msg.query, msg.scopes);
    if (msg.type === 'copy') { deps.copy(String(msg.text || '')); return send({ type: 'notice', text: 'Copied.', ok: true }); }
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
  :root { --acc: #7c3aed; --acc2: #a78bfa; --line: var(--vscode-panel-border, #34314a); --card: var(--vscode-editorWidget-background, #24222e); }
  body { margin: 0; padding: 10px 12px; color: var(--vscode-foreground); background: var(--vscode-editor-background); font: 13px var(--vscode-font-family); }
  button { font: inherit; cursor: pointer; color: inherit; }
  .head { display: flex; align-items: center; gap: 10px; padding: 8px 12px; border-radius: 8px; background: linear-gradient(90deg, rgba(124,58,237,.28), rgba(124,58,237,.04)); }
  .head .t { font-weight: 800; letter-spacing: .05em; }
  .led { width: 8px; height: 8px; border-radius: 50%; background: #9ca3af; display: inline-block; }
  .led.ok { background: #22c55e; box-shadow: 0 0 6px #22c55e; } .led.bad { background: #ef4444; }
  .dim { opacity: .7; } .small { font-size: 11.5px; }
  .tabs { display: flex; gap: 4px; margin-left: 12px; }
  .tabs button { border: 0; background: transparent; padding: 4px 12px; border-radius: 7px; font-weight: 600; opacity: .7; }
  .tabs button.on { background: var(--acc); color: #fff; opacity: 1; }
  .chatBtn { margin-left: auto; border: 1px solid var(--acc); background: transparent; border-radius: 7px; padding: 3px 10px; }
  .grid { display: grid; grid-template-columns: 240px 1fr; margin-top: 10px; }
  .nav { border-right: 1px solid var(--line); padding-right: 10px; }
  .nav h5 { margin: 12px 0 6px; font-size: 11px; letter-spacing: .06em; opacity: .7; }
  .nav .it { display: flex; gap: 6px; padding: 3px 6px; border-radius: 4px; cursor: pointer; }
  .nav .it:hover { background: var(--vscode-list-hoverBackground, rgba(255,255,255,.06)); }
  .nav .it.sub { padding-left: 20px; }
  .nav .n { margin-left: auto; opacity: .7; font-size: 11px; white-space: nowrap; }
  .main { padding-left: 16px; min-width: 0; }
  .omni { display: flex; align-items: center; gap: 8px; padding: 9px 10px 9px 14px; border-radius: 12px; border: 1px solid rgba(124,58,237,.6); background: var(--vscode-input-background); box-shadow: 0 0 0 4px rgba(124,58,237,.10); }
  .omni input { flex: 1; border: 0; outline: 0; background: transparent; color: var(--vscode-input-foreground); font: inherit; font-size: 14px; }
  .scopes { display: flex; gap: 4px; }
  .scopes button { border: 1px solid #52525b; background: transparent; border-radius: 12px; padding: 2px 10px; font-size: 11.5px; opacity: .6; }
  .scopes button.on { border-color: var(--acc); background: rgba(124,58,237,.35); opacity: 1; }
  .go { border: 0; background: var(--acc); color: #fff; border-radius: 8px; padding: 5px 14px; font-weight: 600; }
  .kbd { font-size: 10.5px; opacity: .6; border: 1px solid #52525b; border-radius: 4px; padding: 0 5px; }
  .now { display: flex; gap: 6px; flex-wrap: wrap; margin: 10px 0 0; }
  .now button { border: 1px dashed rgba(167,139,250,.7); background: transparent; border-radius: 14px; padding: 3px 11px; font-size: 12px; }
  .now button b { color: #fbbf24; margin-right: 5px; font-size: 11px; }
  .now button:hover { background: rgba(124,58,237,.18); }
  .cols { display: grid; grid-template-columns: 1.3fr 1fr; gap: 12px; margin-top: 12px; }
  .card { background: var(--card); border: 1px solid var(--line); border-radius: 10px; padding: 12px 14px; min-width: 0; }
  .card h3 { margin: 0 0 8px; font-size: 13px; display: flex; gap: 8px; align-items: center; }
  .pill { font-size: 10.5px; font-weight: 700; border-radius: 10px; padding: 1px 8px; background: rgba(124,58,237,.45); }
  .pill.g { background: #14532d; color: #bbf7d0; } .pill.a { background: #713f12; color: #fde68a; } .pill.r { background: #7f1d1d; color: #fecaca; }
  .ans { line-height: 1.6; white-space: pre-wrap; }
  .ans code { font-family: var(--vscode-editor-font-family, monospace); font-size: 12px; background: rgba(0,0,0,.25); border-radius: 4px; padding: 0 4px; }
  sup.c { color: var(--acc2); font-weight: 700; cursor: pointer; }
  ol.steps { margin: 10px 0 0; padding: 0; list-style: none; counter-reset: s; }
  ol.steps li { counter-increment: s; margin: 7px 0; padding-left: 26px; position: relative; line-height: 1.5; }
  ol.steps li::before { content: counter(s); position: absolute; left: 0; top: 1px; width: 18px; height: 18px; border-radius: 50%; background: var(--acc); color: #fff; font-size: 11px; text-align: center; line-height: 18px; }
  .cmd { display: inline-flex; align-items: center; gap: 6px; margin-top: 3px; font-family: var(--vscode-editor-font-family, monospace); font-size: 12px; background: rgba(0,0,0,.25); border: 1px solid rgba(124,58,237,.6); border-radius: 6px; padding: 2px 4px 2px 8px; max-width: 100%; }
  .cmd span { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .cmd button { border: 0; background: rgba(124,58,237,.35); border-radius: 4px; font-size: 11px; padding: 1px 6px; }
  .conf { display: flex; gap: 10px; align-items: center; margin-top: 12px; font-size: 11.5px; opacity: .85; }
  .meter { flex: 0 0 110px; height: 6px; background: rgba(255,255,255,.12); border-radius: 3px; overflow: hidden; }
  .meter i { display: block; height: 100%; background: linear-gradient(90deg, #7c3aed, #22c55e); }
  .follow { display: flex; gap: 6px; flex-wrap: wrap; margin-top: 10px; }
  .follow button { border: 1px solid rgba(124,58,237,.6); background: transparent; border-radius: 12px; padding: 2px 10px; font-size: 11.5px; }
  .warn { margin-top: 8px; padding: 6px 10px; border-radius: 6px; border: 1px solid #b45309; font-size: 12px; }
  .src { padding: 7px 4px; border-bottom: 1px solid var(--line); font-size: 12px; border-radius: 4px; }
  .src:last-child { border-bottom: 0; }
  .src.hl { background: rgba(124,58,237,.18); }
  .src.unused { opacity: .55; }
  .src .top { display: flex; gap: 8px; align-items: center; }
  .src .n { color: var(--acc2); font-weight: 800; width: 16px; }
  .src .p { font-family: var(--vscode-editor-font-family, monospace); font-size: 11.5px; flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .tag { font-size: 10px; font-weight: 700; border-radius: 4px; padding: 0 5px; }
  .tag.guide { background: #713f12; color: #fde68a; } .tag.project { background: #312e81; color: #c4b5fd; }
  .snip { margin: 4px 0 2px 24px; opacity: .8; white-space: pre-wrap; line-height: 1.4; max-height: 4.2em; overflow: hidden; font-size: 11.5px; }
  mark { background: rgba(124,58,237,.45); color: inherit; border-radius: 2px; }
  .link { color: var(--vscode-textLink-foreground); cursor: pointer; font-size: 11.5px; margin-left: 24px; }
  .thinking { margin-top: 14px; padding: 14px; border-radius: 10px; border: 1px solid var(--line); background: linear-gradient(90deg, rgba(124,58,237,.06), rgba(124,58,237,.22), rgba(124,58,237,.06)); background-size: 200% 100%; animation: sh 1.6s linear infinite; }
  @keyframes sh { from { background-position: 200% 0; } to { background-position: -200% 0; } }
  .empty { margin-top: 18px; opacity: .75; line-height: 1.6; }
  .row { display: flex; gap: 8px; padding: 3px 4px; border-radius: 4px; cursor: pointer; font-size: 12.5px; }
  .row:hover { background: var(--vscode-list-hoverBackground, rgba(255,255,255,.06)); }
  .row .p { flex: 1; font-family: var(--vscode-editor-font-family, monospace); font-size: 12px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  h4 { margin: 14px 0 4px; font-size: 12px; letter-spacing: .04em; opacity: .75; }
  .notice { margin-top: 10px; padding: 6px 10px; border-radius: 6px; border: 1px solid #b45309; font-size: 12px; }
  .notice.ok { border-color: #15803d; }
  .filter { width: 100%; margin-top: 6px; padding: 5px 8px; border-radius: 6px; border: 1px solid var(--vscode-input-border, #3f3f46); background: var(--vscode-input-background); color: var(--vscode-input-foreground); font: inherit; }
  .hidden { display: none; }
  @media (max-width: 900px) { .grid { grid-template-columns: 1fr; } .nav { display: none; } .main { padding-left: 0; } .cols { grid-template-columns: 1fr; } }
</style></head>
<body>
  <div class="head"><span class="t">🧠 MEMORY</span><span id="led" class="led"></span><span id="sum" class="dim small">loading…</span>
    <div class="tabs"><button data-tab="ask" class="on">Ask</button><button data-tab="search">Search</button></div>
    <button id="chat" class="chatBtn" title="Open the CLike chat (or bring it to the front)">💬 Chat</button></div>
  <div class="grid">
    <div class="nav">
      <h5>CONTENTS</h5><div id="contents"></div>
      <h5>RECENT</h5><div id="recent"></div>
    </div>
    <div class="main">
      <div class="omni"><span>✦</span><input id="q" placeholder="Ask anything, in any language">
        <div class="scopes" id="scopes"><button data-scope="project" class="on">Project</button><button data-scope="guide" class="on">CLike Guide</button></div>
        <span class="kbd">⌘K</span><button id="go" class="go">Ask</button></div>
      <div class="now" id="now"></div>
      <div id="notice"></div>
      <div id="view"></div>
    </div>
  </div>
<script>
  const vscode = acquireVsCodeApi();
  const $ = (id) => document.getElementById(id);
  let tab = 'ask';
  let state = null;
  const scopes = new Set(['project', 'guide']);
  const esc = (s) => String(s == null ? '' : s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  function el(tag, cls, html) { const e = document.createElement(tag); if (cls) e.className = cls; if (html != null) e.innerHTML = html; return e; }
  // the question's words in a snippet (already escaped text; terms escaped the same way)
  function mark(html, terms) {
    const words = (terms || []).filter((t) => !/^(amp|quot|#39)$/.test(t)).map((t) => esc(t).replace(/\\W/g, (c) => '\\\\' + c)).filter(Boolean);
    if (!words.length) return html;
    return html.replace(new RegExp('(' + words.join('|') + ')', 'gi'), '<mark>$1</mark>');
  }
  function setTab(t) {
    tab = t;
    document.querySelectorAll('.tabs button').forEach((b) => b.classList.toggle('on', b.dataset.tab === t));
    $('go').textContent = t === 'ask' ? 'Ask' : 'Search';
    $('q').placeholder = t === 'ask' ? 'Ask anything, in any language' : 'Search the memory, in any language';
    $('now').classList.toggle('hidden', t !== 'ask');
    if (t === 'search' && scopes.size === 2) { scopes.delete('guide'); drawScopes(); }
  }
  function drawScopes() { document.querySelectorAll('#scopes button').forEach((b) => b.classList.toggle('on', scopes.has(b.dataset.scope))); }
  function navItem(label, n, cls, onClick) {
    const it = el('div', 'it' + (cls ? ' ' + cls : ''), esc(label) + '<span class="n">' + esc(n) + '</span>');
    it.addEventListener('click', onClick);
    return it;
  }
  function showList(title, sc, items) {
    const v = $('view'); v.innerHTML = '';
    v.appendChild(el('h4', '', esc(title) + ' · ' + items.length + ' file(s)'));
    const f = el('input', 'filter'); f.placeholder = 'Filter by name…'; v.appendChild(f);
    const box = el('div'); v.appendChild(box);
    const draw = () => {
      box.innerHTML = '';
      const k = f.value.toLowerCase();
      items.filter((i) => !k || i.path.toLowerCase().includes(k)).slice(0, 500).forEach((i) => {
        const r = el('div', 'row', '<span class="p">' + esc(i.path) + '</span><span class="dim small">' + i.chunks + ' chunk(s)</span>');
        r.addEventListener('click', () => vscode.postMessage({ type: 'open', scope: sc, path: i.path }));
        box.appendChild(r);
      });
    };
    f.addEventListener('input', draw); draw();
  }
  function renderNow(now) {
    const box = $('now'); box.innerHTML = '';
    (now && now.suggestions || []).forEach((s, i) => {
      const b = el('button', '', (i < 2 && s.why !== 'CLike guide' ? '<b>NOW</b>' : '') + esc(s.label));
      b.title = s.why || '';
      b.addEventListener('click', () => { setTab('ask'); $('q').value = s.query; go(); });
      box.appendChild(b);
    });
  }
  function renderState(s) {
    state = s;
    const ok = s.project.ok && s.guide.ok;
    $('led').className = 'led ' + (ok ? 'ok' : 'bad');
    $('sum').textContent = ok
      ? s.project.name + ' · ' + s.project.chunks + ' + ' + s.guide.chunks + ' chunks'
      : 'the memory service does not answer: ' + (s.project.error || 'unreachable');
    const c = $('contents'); c.innerHTML = '';
    const gi = s.guide.indexing || {};
    c.appendChild(navItem('📘 CLike Guide', gi.status === 'indexing' ? 'indexing…' : s.guide.items.length + ' files', '', () => showList('CLike Guide', 'guide', s.guide.items)));
    if (gi.status === 'failed' || gi.status === 'missing') c.appendChild(navItem('⚠ guide not indexed — retry', '', 'sub', () => vscode.postMessage({ type: 'reindexGuide' })));
    const all = s.project.groups.reduce((a, g) => a.concat(g.items), []);
    c.appendChild(navItem('📁 Project', all.length + ' files', '', () => showList('Project', 'project', all)));
    s.project.groups.forEach((g) => c.appendChild(navItem(g.label, g.files, 'sub', () => showList(g.label, 'project', g.items))));
    renderRecent(s.recent);
    renderNow(s.now);
    if (!$('view').innerHTML) $('view').innerHTML = '<div class="empty">Ask what the project holds or how CLike works — in any language.<br>The answer is written only from the memory, with its sources numbered; the questions above come from the project as it is now.</div>';
  }
  function renderRecent(list) {
    const r = $('recent'); r.innerHTML = '';
    (list || []).forEach((x) => r.appendChild(navItem(x.query, x.scope === 'guide' ? 'guide' : x.scope === 'both' ? '' : 'project', 'sub', () => { $('q').value = x.query; go(); })));
  }
  function cite(html, used) {
    return html.replace(/\\[(\\d+)\\]/g, (m, n) => '<sup class="c" data-n="' + n + '">' + n + '</sup>');
  }
  function renderAnswer(m) {
    const v = $('view'); v.innerHTML = '';
    renderRecent(m.recent || (state && state.recent));
    if (m.error) v.appendChild(el('div', 'warn', 'The answer could not be written: ' + esc(m.error) + ' — the sources found are below.'));
    const cols = el('div', 'cols'); v.appendChild(cols);
    const a = m.answer;
    if (a) {
      const card = el('div', 'card');
      const level = { high: ['g', 86], medium: ['a', 58], low: ['r', 28] }[a.confidence] || ['r', 28];
      card.appendChild(el('h3', '', 'Answer' + (a.not_in_memory ? ' <span class="pill a">not in the memory</span>' : '')));
      card.appendChild(el('div', 'ans', cite(esc(a.answer))));
      if (a.steps.length) {
        const ol = el('ol', 'steps');
        a.steps.forEach((st) => {
          const li = el('li', '', cite(esc(st.text)));
          if (st.command) {
            const c = el('div', 'cmd', '<span>' + esc(st.command) + '</span><button>copy</button>');
            c.querySelector('button').addEventListener('click', () => vscode.postMessage({ type: 'copy', text: st.command }));
            li.appendChild(el('br')); li.appendChild(c);
          }
          ol.appendChild(li);
        });
        card.appendChild(ol);
      }
      card.appendChild(el('div', 'conf', 'Confidence <div class="meter"><i style="width:' + level[1] + '%"></i></div><span class="pill ' + level[0] + '">' + esc(a.confidence) + '</span> ' + esc(a.confidence_reason) + (m.by ? ' · ' + esc(m.by) : '')));
      if (a.followups.length) {
        const f = el('div', 'follow');
        a.followups.forEach((q) => { const b = el('button', '', esc(q)); b.addEventListener('click', () => { $('q').value = q; go(); }); f.appendChild(b); });
        card.appendChild(f);
      }
      cols.appendChild(card);
    }
    const sc = el('div', 'card');
    sc.appendChild(el('h3', '', 'Sources <span class="dim small">' + m.sources.length + '</span>'));
    const used = new Set(a ? a.sources_used : []);
    m.sources.forEach((s) => {
      const d = el('div', 'src' + (a && used.size && !used.has(s.n) ? ' unused' : ''),
        '<div class="top"><span class="n">' + s.n + '</span><span class="tag ' + s.collection + '">' + (s.collection === 'guide' ? 'GUIDE' : 'PROJECT') + '</span><span class="p">' + esc(s.path) + '</span>' + (s.modified ? '<span class="dim small">' + esc(s.modified.slice(0, 10)) + '</span>' : '') + '</div>' +
        '<div class="snip">' + mark(esc(s.text.slice(0, 500)), s.terms) + '</div><span class="link">Open</span>');
      d.id = 'src' + s.n;
      d.querySelector('.link').addEventListener('click', () => vscode.postMessage({ type: 'open', scope: s.collection, path: s.path }));
      sc.appendChild(d);
    });
    cols.appendChild(sc);
    v.querySelectorAll('sup.c').forEach((x) => x.addEventListener('click', () => {
      const t = $('src' + x.dataset.n); if (!t) return;
      document.querySelectorAll('.src.hl').forEach((e) => e.classList.remove('hl'));
      t.classList.add('hl'); t.scrollIntoView({ block: 'nearest' });
    }));
  }
  function renderResults(m) {
    const v = $('view'); v.innerHTML = '';
    if (m.error) { v.appendChild(el('div', 'notice', esc(m.error))); return; }
    v.appendChild(el('h4', '', (m.scope === 'guide' ? 'CLike Guide' : 'Project') + ' · ' + m.results.length + ' result(s) for “' + esc(m.query) + '”'));
    if (!m.results.length) v.appendChild(el('div', 'dim small', 'Nothing relevant found. Try other words, or the other memory.'));
    m.results.forEach((h) => {
      const card = el('div', 'card', '<div class="src" style="border:0"><div class="top"><span class="p">' + esc(h.path) + '</span><span class="dim small">' + h.score.toFixed(2) + '</span></div>' +
        '<div class="snip" style="margin-left:0;max-height:7em">' + mark(esc(h.text.slice(0, 600)), h.terms) + '</div><span class="link" style="margin-left:0">Open</span></div>');
      card.style.marginTop = '8px';
      card.querySelector('.link').addEventListener('click', () => vscode.postMessage({ type: 'open', scope: m.scope, path: h.path }));
      v.appendChild(card);
    });
    renderRecent(m.recent);
  }
  function go() {
    const q = $('q').value.trim();
    if (!q) return;
    if (tab === 'ask') {
      vscode.postMessage({ type: 'ask', query: q, scopes: [...scopes] });
    } else {
      $('view').innerHTML = '<div class="thinking">Searching…</div>';
      vscode.postMessage({ type: 'search', scope: scopes.has('project') ? 'project' : 'guide', query: q });
    }
  }
  document.querySelectorAll('.tabs button').forEach((b) => b.addEventListener('click', () => setTab(b.dataset.tab)));
  document.querySelectorAll('#scopes button').forEach((b) => b.addEventListener('click', () => {
    const sc = b.dataset.scope;
    if (tab === 'search') { scopes.clear(); scopes.add(sc); }
    else if (scopes.has(sc) && scopes.size > 1) scopes.delete(sc); else scopes.add(sc);
    drawScopes();
  }));
  $('go').addEventListener('click', go);
  $('q').addEventListener('keydown', (e) => { if (e.key === 'Enter') go(); });
  document.addEventListener('keydown', (e) => { if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') { e.preventDefault(); $('q').focus(); $('q').select(); } });
  $('chat').addEventListener('click', () => vscode.postMessage({ type: 'openChat' }));
  window.addEventListener('message', (e) => {
    const m = e.data || {};
    if (m.type === 'state') renderState(m);
    else if (m.type === 'asking') { $('view').innerHTML = '<div class="thinking">Reading the memory and writing the answer…</div>'; renderRecent(m.recent); }
    else if (m.type === 'answer') renderAnswer(m);
    else if (m.type === 'results') renderResults(m);
    else if (m.type === 'notice') { $('notice').innerHTML = '<div class="notice' + (m.ok ? ' ok' : '') + '">' + esc(m.text) + '</div>'; setTimeout(() => { $('notice').innerHTML = ''; }, m.ok ? 1500 : 6000); }
  });
  vscode.postMessage({ type: 'ready' });
</script>
</body></html>`;
}

module.exports = { openMemoryPanel, groupProjectSources, bestPerFile, rerank, queryTerms, distinctiveTerms, focusSnippet, staleKitPaths, addRecent, memoryHtml };
