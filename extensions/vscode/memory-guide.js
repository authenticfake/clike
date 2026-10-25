'use strict';
// The CLike guide in the Memory panel: CLike's own documentation ships inside the extension
// (guide/, copied from docs/ when the package is built) and is indexed in its own RAG collection
// when CLike starts, again only when the documentation changes. Any project can then ask how CLike
// works, in any language (the search is semantic).

const crypto = require('crypto');
const fs = require('fs');
const path = require('path');

const GUIDE_PROJECT_ID = 'clike-guide';
const GUIDE_STATE_KEY = 'clike.memory.guide';
// not documentation of CLike: private analyses, sample ideas, images, API dumps
const SKIP_DIRS = new Set(['_private', 'IDEAs', 'images', 'openapi', 'clike_postman_bundle', 'contracts', 'tech_costraints', 'harper']);
const MAX_FILE_BYTES = 400 * 1024;

/** The packaged guide (guide/), or the repository docs/ when the extension runs from the sources. */
function guideRoot(extensionRoot) {
  const packaged = path.join(extensionRoot, 'guide');
  if (fs.existsSync(packaged)) return packaged;
  const sources = path.join(extensionRoot, '..', '..', 'docs');
  return fs.existsSync(sources) ? sources : null;
}

/** Markdown files of the guide: [{ path (relative, posix), abs }], sorted. */
function listGuideFiles(root) {
  const out = [];
  if (!root) return out;
  const walk = (dir) => {
    let entries = [];
    try { entries = fs.readdirSync(dir, { withFileTypes: true }); } catch { return; }
    for (const entry of entries.sort((a, b) => a.name.localeCompare(b.name))) {
      const abs = path.join(dir, entry.name);
      if (entry.isDirectory()) {
        if (!entry.name.startsWith('.') && !SKIP_DIRS.has(entry.name)) walk(abs);
      } else if (entry.isFile() && entry.name.toLowerCase().endsWith('.md')) {
        try { if (fs.statSync(abs).size > MAX_FILE_BYTES) continue; } catch { continue; }
        out.push({ path: path.relative(root, abs).split(path.sep).join('/'), abs });
      }
    }
  };
  walk(root);
  return out;
}

function readGuide(files) {
  return files
    .map((f) => {
      try { return { path: f.path, text: fs.readFileSync(f.abs, 'utf8') }; } catch { return null; }
    })
    .filter((f) => f && f.text.trim());
}

function fingerprint(items) {
  const h = crypto.createHash('sha1');
  for (const it of items) h.update(`${it.path}\0${it.text}\0`);
  return h.digest('hex');
}

/**
 * Index the guide when it changed since the last indexing (state: a vscode Memento).
 * post(url, body) → JSON. Returns { status: 'current' | 'indexed' | 'missing' | 'failed', files, error? }.
 */
async function ensureGuideIndexed({ extensionRoot, state, post, orchestratorUrl }) {
  const items = readGuide(listGuideFiles(guideRoot(extensionRoot)));
  if (!items.length) return { status: 'missing', files: 0 };
  const fp = fingerprint(items);
  const prev = state.get(GUIDE_STATE_KEY) || {};
  if (prev.fingerprint === fp) return { status: 'current', files: items.length };
  const res = await post(`${orchestratorUrl}/v1/rag/index`, { project_id: GUIDE_PROJECT_ID, items });
  if (!res || res.ok === false) return { status: 'failed', files: items.length, error: String(res?.error || 'index failed') };
  // files removed from the guide leave the collection
  const now = new Set(items.map((i) => i.path));
  for (const old of (prev.paths || []).filter((p) => !now.has(p))) {
    try { await post(`${orchestratorUrl}/v1/rag/purge`, { project_id: GUIDE_PROJECT_ID, path_prefix: old }); } catch { /* next indexing */ }
  }
  await state.update(GUIDE_STATE_KEY, { fingerprint: fp, paths: [...now], at: Date.now() });
  return { status: 'indexed', files: items.length };
}

module.exports = { GUIDE_PROJECT_ID, GUIDE_STATE_KEY, guideRoot, listGuideFiles, readGuide, fingerprint, ensureGuideIndexed };
