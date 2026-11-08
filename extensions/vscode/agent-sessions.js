'use strict';
// Repair in the KIT's session: the agent that wrote a REQ's KIT keeps its session id, and the
// auto-eval repair of the same REQ resumes it (forked, so the KIT session stays as it was) instead of
// starting cold and re-reading the workspace — a warm context and prompt cache, the code it wrote
// already known. Claude Code: --resume <id> --fork-session; Codex: exec resume <id> (the forms the
// agent chat uses). A session older than the TTL, of another executor or of another REQ is not used.
const SESSION_TTL_MS = 24 * 3600 * 1000;

/** The session id an agent run printed: Claude's result/system events, Codex's thread.started. */
function extractSessionId(executorId, stdout) {
  let found = '';
  for (const line of String(stdout || '').split('\n')) {
    const text = line.trim();
    if (!text.startsWith('{')) continue;
    let event;
    try { event = JSON.parse(text); } catch { continue; }
    if (!event || typeof event !== 'object') continue;
    if (executorId === 'claude_code' && typeof event.session_id === 'string' && event.session_id) found = event.session_id;
    if (executorId === 'gpt_codex' && event.type === 'thread.started' && typeof event.thread_id === 'string' && event.thread_id) {
      return event.thread_id;
    }
  }
  return found;
}

const sessionKey = (reqId, executorId) => `${String(reqId || '').toUpperCase()}:${executorId}`;

/** The KIT session to resume for this REQ and executor, or '' (none, expired). */
function sessionToResume(store, reqId, executorId, now = Date.now()) {
  const entry = store && store[sessionKey(reqId, executorId)];
  if (!entry || !entry.id || typeof entry.at !== 'number' || now - entry.at > SESSION_TTL_MS) return '';
  return entry.id;
}

function rememberSession(store, reqId, executorId, id, now = Date.now()) {
  const next = { ...(store || {}) };
  for (const [key, entry] of Object.entries(next)) {
    if (!entry || now - Number(entry.at || 0) > SESSION_TTL_MS) delete next[key];
  }
  if (id) next[sessionKey(reqId, executorId)] = { id, at: now };
  return next;
}

/** The launcher arguments of a run that resumes `sessionId`. */
function resumeArgs(executorId, args, sessionId) {
  const list = Array.isArray(args) ? [...args] : [];
  if (!sessionId) return list;
  if (executorId === 'claude_code') {
    if (list.includes('--resume') || list.includes('-r')) return list;
    return [...list, '--resume', sessionId, '--fork-session'];
  }
  if (executorId === 'gpt_codex') {
    const at = list.indexOf('exec');
    if (at < 0 || list[at + 1] === 'resume') return list;
    const rest = [...list.slice(0, at), ...list.slice(at + 1)];
    // `exec resume` has no --sandbox flag: the sandbox goes as config (as in the agent chat)
    const out = [];
    for (let i = 0; i < rest.length; i += 1) {
      if (rest[i] === '--sandbox' && i + 1 < rest.length) {
        out.push('-c', `sandbox_mode="${rest[i + 1]}"`);
        i += 1;
      } else if (rest[i].startsWith('--sandbox=')) {
        out.push('-c', `sandbox_mode="${rest[i].slice('--sandbox='.length)}"`);
      } else {
        out.push(rest[i]);
      }
    }
    return ['exec', 'resume', sessionId, ...(out.includes('--json') ? [] : ['--json']), ...out];
  }
  return list;
}

module.exports = { SESSION_TTL_MS, extractSessionId, sessionToResume, rememberSession, resumeArgs };
