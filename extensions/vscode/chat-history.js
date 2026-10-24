'use strict';
// The chat's history of conversations per mode: the current one is .clike/sessions/<mode>.jsonl
// (as before); "New chat" archives it under .clike/sessions/archive/<mode>/ instead of deleting it,
// and an archived conversation can be reopened (the current one is archived in its place).
// Nothing is lost by switching. No VS Code API: unit-tested.

const fs = require('fs');
const path = require('path');

const ID_RE = /^[A-Za-z0-9_.-]{1,80}$/;
const safeMode = (mode) => String(mode || 'free').replace(/[^\w.-]/g, '_');
const currentFile = (dir, mode) => path.join(dir, `${safeMode(mode)}.jsonl`);
const archiveDir = (dir, mode) => path.join(dir, 'archive', safeMode(mode));

function readLines(file) {
  let text = '';
  try { text = fs.readFileSync(file, 'utf8'); } catch { return []; }
  const out = [];
  for (const line of text.split(/\r?\n/)) {
    if (!line.trim()) continue;
    try { out.push(JSON.parse(line)); } catch { /* a broken line is skipped */ }
  }
  return out;
}

// summaries by file, valid while its size and modification time are the same (archives pile up)
const cache = new Map();

/** Title, dates and size of a conversation file. */
function summarize(file, id) {
  let stat;
  try { stat = fs.statSync(file); } catch { return null; }
  const hit = cache.get(file);
  if (hit && hit.mtimeMs === stat.mtimeMs && hit.size === stat.size) return hit.summary && { ...hit.summary, id };
  const summary = summarizeNow(file, id);
  cache.set(file, { mtimeMs: stat.mtimeMs, size: stat.size, summary });
  return summary;
}

function summarizeNow(file, id) {
  const lines = readLines(file);
  if (!lines.length) return null;
  const firstUser = lines.find((l) => l.role === 'user' && String(l.content || '').trim());
  const title = String((firstUser || lines[0]).content || '').trim().split('\n')[0].slice(0, 90) || '(empty)';
  const ts = lines.map((l) => Number(l.ts) || 0).filter(Boolean);
  return { id, title, first_ts: ts.length ? Math.min(...ts) : 0, last_ts: ts.length ? Math.max(...ts) : 0, count: lines.length };
}

/** The archived conversations of a mode, newest first, and the current one. */
function listConversations(dir, mode, limit = 40) {
  let names = [];
  try { names = fs.readdirSync(archiveDir(dir, mode)).filter((n) => n.endsWith('.jsonl')); } catch { /* none yet */ }
  const archived = names
    .map((n) => summarize(path.join(archiveDir(dir, mode), n), n.replace(/\.jsonl$/, '')))
    .filter(Boolean)
    .sort((a, b) => b.last_ts - a.last_ts)
    .slice(0, limit);
  return { current: summarize(currentFile(dir, mode), 'current'), archived };
}

/** Moves the current conversation to the archive; its id, or null when it was empty. */
function archiveCurrent(dir, mode, now = Date.now()) {
  const file = currentFile(dir, mode);
  const info = summarize(file, 'current');
  if (!info) {
    try { fs.unlinkSync(file); } catch { /* nothing to remove */ }
    return null;
  }
  fs.mkdirSync(archiveDir(dir, mode), { recursive: true });
  const stamp = new Date(info.first_ts || now).toISOString().replace(/[:]/g, '-').replace(/\..*$/, '');
  let id = stamp;
  for (let i = 2; fs.existsSync(path.join(archiveDir(dir, mode), `${id}.jsonl`)); i += 1) id = `${stamp}-${i}`;
  fs.renameSync(file, path.join(archiveDir(dir, mode), `${id}.jsonl`));
  return id;
}

function archivedFile(dir, mode, id) {
  if (!ID_RE.test(String(id || ''))) throw new Error(`invalid conversation id: ${id}`);
  const file = path.join(archiveDir(dir, mode), `${id}.jsonl`);
  if (!fs.existsSync(file)) throw new Error(`no conversation ${id} in ${safeMode(mode)}`);
  return file;
}

/** Makes an archived conversation the current one; the current one goes to the archive. */
function openConversation(dir, mode, id) {
  const file = archivedFile(dir, mode, id);
  const archived = archiveCurrent(dir, mode);
  fs.renameSync(file, currentFile(dir, mode));
  return { archived };
}

function deleteConversation(dir, mode, id) {
  fs.unlinkSync(archivedFile(dir, mode, id));
}

module.exports = { listConversations, archiveCurrent, openConversation, deleteConversation, currentFile, archiveDir };
