'use strict';
// The Memory panel: the project's RAG memory and the CLike guide, queried in natural language.
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('fs');
const os = require('os');
const path = require('path');

const { GUIDE_PROJECT_ID, GUIDE_STATE_KEY, listGuideFiles, ensureGuideIndexed } = require('../memory-guide');
const { groupProjectSources, bestPerFile, addRecent, memoryHtml } = require('../memory-panel');

function write(root, rel, text) {
  fs.mkdirSync(path.join(root, path.dirname(rel)), { recursive: true });
  fs.writeFileSync(path.join(root, rel), text);
}

function memento() {
  const data = {};
  return { get: (k) => data[k], update: async (k, v) => { data[k] = v; } };
}

test('the guide is CLike documentation only: private notes, ideas and non-Markdown files stay out', () => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'clike-guide-'));
  write(root, 'commands.md', '# Commands');
  write(root, 'architecture/ADOPT.md', '# Adopt');
  write(root, '_private/40_tracker.md', 'private');
  write(root, 'IDEAs/IDEA_X.md', 'idea');
  write(root, 'images/a.svg', '<svg/>');
  assert.deepEqual(listGuideFiles(root).map((f) => f.path), ['architecture/ADOPT.md', 'commands.md']);
});

test('the guide is indexed once, again only when it changed; removed files leave the collection', async () => {
  const ext = fs.mkdtempSync(path.join(os.tmpdir(), 'clike-ext-'));
  write(ext, 'guide/commands.md', '# Commands\n--accept applies the proposal');
  write(ext, 'guide/old.md', '# Old');
  // a fake store: what was indexed is held, until it is emptied
  let held = new Set();
  const calls = [];
  const post = async (url, body) => {
    calls.push({ url, body });
    if (url.endsWith('/index')) body.items.forEach((i) => held.add(i.path));
    if (url.endsWith('/purge')) held.delete(body.path_prefix);
    if (url.endsWith('/sources')) return { ok: true, sources: [...held].map((p) => ({ path: p, chunks: 1 })) };
    return { ok: true };
  };
  const state = memento();
  const args = { extensionRoot: ext, state, post, orchestratorUrl: 'http://o' };
  const urls = () => calls.splice(0).map((c) => c.url.replace('http://o/v1/rag/', ''));

  assert.deepEqual(await ensureGuideIndexed(args), { status: 'indexed', files: 2 });
  assert.equal(calls[0].body.project_id, GUIDE_PROJECT_ID);
  assert.deepEqual(calls[0].body.items.map((i) => i.path), ['commands.md', 'old.md']);
  assert.deepEqual(urls(), ['index']);
  // already there: checked, nothing sent
  assert.deepEqual(await ensureGuideIndexed(args), { status: 'current', files: 2 });
  assert.deepEqual(urls(), ['sources']);
  // the store was emptied (new volume): the guide goes back
  held = new Set();
  assert.deepEqual(await ensureGuideIndexed(args), { status: 'indexed', files: 2 });
  assert.deepEqual(urls(), ['sources', 'index']);
  // a file removed from the guide leaves the collection
  fs.rmSync(path.join(ext, 'guide/old.md'));
  assert.deepEqual(await ensureGuideIndexed(args), { status: 'indexed', files: 1 });
  assert.deepEqual(urls(), ['index', 'purge']);
  assert.deepEqual(state.get(GUIDE_STATE_KEY).paths, ['commands.md']);
});

test('a store that cannot say what it holds is not sent the guide again', async () => {
  const ext = fs.mkdtempSync(path.join(os.tmpdir(), 'clike-ext-'));
  write(ext, 'guide/commands.md', '# Commands');
  const state = memento();
  let indexed = 0;
  const ok = async (url) => { if (url.endsWith('/index')) indexed += 1; return { ok: true, sources: [{ path: 'commands.md' }] }; };
  await ensureGuideIndexed({ extensionRoot: ext, state, post: ok, orchestratorUrl: 'http://o' });
  const down = async (url) => { if (url.endsWith('/sources')) throw new Error('unreachable'); indexed += 1; return { ok: true }; };
  assert.equal((await ensureGuideIndexed({ extensionRoot: ext, state, post: down, orchestratorUrl: 'http://o' })).status, 'current');
  assert.equal(indexed, 1);
});

test('a failed indexing is retried at the next start (nothing recorded)', async () => {
  const ext = fs.mkdtempSync(path.join(os.tmpdir(), 'clike-ext-'));
  write(ext, 'guide/commands.md', '# Commands');
  const state = memento();
  const out = await ensureGuideIndexed({ extensionRoot: ext, state, post: async () => ({ ok: false, error: 'store down' }), orchestratorUrl: 'http://o' });
  assert.equal(out.status, 'failed');
  assert.equal(state.get(GUIDE_STATE_KEY), undefined);
});

test('project sources are grouped as the panel lists them', () => {
  const groups = groupProjectSources([
    { path: 'docs/harper/SPEC.md', chunks: 4 },
    { path: 'runs/kit/REQ-001/src/a.py', chunks: 2 },
    { path: 'runs/kit/REQ-002/test/t.py', chunks: 1 },
    { path: 'Specifiche_v1.docx', chunks: 9 },
  ]);
  assert.deepEqual(groups.map((g) => [g.label, g.files, g.chunks]), [
    ['Harper documents', 1, 4], ['REQ KITs', 2, 3], ['Attachments and other files', 1, 9],
  ]);
});

test('results show each file once, with its best chunk, best first', () => {
  const out = bestPerFile([
    { path: 'a.md', score: 0.5, text: 'weak' },
    { path: 'b.md', score: 0.7, text: 'b' },
    { path: 'a.md', score: 0.9, text: 'strong' },
  ]);
  assert.deepEqual(out.map((r) => [r.path, r.text]), [['a.md', 'strong'], ['b.md', 'b']]);
});

test('recent searches: newest first, no duplicates, bounded', () => {
  let list = [];
  for (let i = 0; i < 12; i++) list = addRecent(list, 'project', `q${i}`);
  list = addRecent(list, 'project', 'q5');
  assert.equal(list.length, 10);
  assert.deepEqual(list.slice(0, 2).map((r) => r.query), ['q5', 'q11']);
});

test('the panel is in English and opens the chat with its own button only', () => {
  const html = memoryHtml();
  assert.match(html, /💬 Chat/);
  assert.match(html, /Ask in any language/);
  assert.doesNotMatch(html, /type: 'attach'|insertIntoChat/);
});
