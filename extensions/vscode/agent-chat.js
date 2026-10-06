'use strict';
// Native agent chat (H1): the CLike chat talks to Claude Code / Codex as one continuous session per
// (mode, agent): the first message starts a session, the next ones resume it, and the agent's
// events are streamed into the chat. CLike keeps the governance: the mode decides what the agent may
// do (free: read-only; coding and harper: writes under the generated root).
const crypto = require('crypto');

function sessionKey(mode, executorId) {
  return `${String(mode || 'free').toLowerCase()}:${String(executorId || '')}`;
}

/** A new session descriptor (Claude: we choose the id; Codex: the id comes from thread.started). */
function newSession(executorId) {
  return executorId === 'claude_code'
    ? { id: crypto.randomUUID(), started: false }
    : { id: '', started: false };
}

// Coding and Harper free text may write (under the generated root); Free is read-only.
function isWritableMode(mode) {
  return mode === 'coding' || mode === 'harper';
}

function codexSandbox(mode) {
  return isWritableMode(mode) ? 'workspace-write' : 'read-only';
}

/**
 * CLI arguments of a chat turn. `session` is { id, started } or null (one-shot).
 * Claude: -p, streamed JSON events with partial text, --session-id on the first turn, --resume after.
 * Codex: exec --json with the mode's sandbox; resume via `exec resume <id> -` (prompt on stdin).
 * With approvals (Coding) Claude asks for edits; Codex runs through app-server instead (agent-approvals.js).
 */
function buildAgentChatArgs({ executorId, mode, executorConfig = {}, modelArgs = [], session = null, approvals = false }) {
  if (executorId === 'claude_code') {
    const args = [executorConfig.printModeFlag || '-p', '--output-format', 'stream-json', '--verbose', '--include-partial-messages', ...modelArgs];
    // with approvals the edits are asked (--permission-prompt-tool, see agent-approvals.js)
    if (isWritableMode(mode)) args.push('--permission-mode', approvals ? 'default' : (executorConfig.permissionMode || 'acceptEdits'));
    if (session && session.id) args.push(session.started ? '--resume' : '--session-id', session.id);
    return args;
  }
  const sandbox = codexSandbox(mode);
  if (session && session.started && session.id) {
    // `exec resume` has no --sandbox flag: the sandbox is passed as config.
    return ['exec', 'resume', session.id, '-', '--json', '-c', `sandbox_mode="${sandbox}"`, '--skip-git-repo-check', ...modelArgs];
  }
  return ['exec', '--json', '--sandbox', sandbox, '--skip-git-repo-check', ...modelArgs];
}

function toolLabel(name, input) {
  const i = input || {};
  const detail = i.file_path || i.path || i.command || i.pattern || i.url || '';
  return detail ? `${name} ${String(detail).slice(0, 160)}` : String(name || 'tool');
}

/**
 * Parser of the agent's stdout lines. feed(line) returns chat events:
 *   { kind: 'session', id } | { kind: 'delta', text } | { kind: 'tool', label }
 *   | { kind: 'result', text, model, usage, cost, durationMs } | { kind: 'error', text }
 * Non-JSON lines are ignored (the final text is also in the result event).
 */
function createAgentStreamParser(executorId) {
  const state = { text: '', streamed: false, model: '', usage: {} };

  function feedClaude(event) {
    const out = [];
    if (event.type === 'system' && event.subtype === 'init') {
      if (event.model) state.model = event.model;
      if (event.session_id) out.push({ kind: 'session', id: event.session_id });
    } else if (event.type === 'stream_event') {
      const delta = event.event && event.event.delta;
      if (delta && delta.type === 'text_delta' && delta.text) {
        state.streamed = true;
        state.text += delta.text;
        out.push({ kind: 'delta', text: delta.text });
      }
    } else if (event.type === 'assistant' && event.message) {
      for (const block of event.message.content || []) {
        if (block.type === 'tool_use') out.push({ kind: 'tool', label: toolLabel(block.name, block.input) });
        else if (block.type === 'text' && block.text && !state.streamed) {
          state.text += block.text;
          out.push({ kind: 'delta', text: block.text });
        }
      }
    } else if (event.type === 'result') {
      const usage = event.usage || {};
      out.push({
        kind: event.is_error ? 'error' : 'result',
        text: String(event.result || state.text || ''),
        model: Object.keys(event.modelUsage || {}).join(',') || state.model,
        usage: {
          input_tokens: usage.input_tokens || 0,
          output_tokens: usage.output_tokens || 0,
          cache_read_input_tokens: usage.cache_read_input_tokens || 0,
          cache_creation_input_tokens: usage.cache_creation_input_tokens || 0,
        },
        cost: Number(event.total_cost_usd) || null,
        durationMs: Number(event.duration_ms) || null,
        sessionId: event.session_id || '',
      });
    }
    return out;
  }

  function feedCodex(event) {
    const out = [];
    const item = event.item || {};
    if (event.type === 'thread.started' && event.thread_id) {
      out.push({ kind: 'session', id: event.thread_id });
    } else if (event.type === 'item.completed' && item.type === 'agent_message' && item.text) {
      state.text += (state.text ? '\n' : '') + item.text;
      out.push({ kind: 'delta', text: (state.text === item.text ? '' : '\n') + item.text });
    } else if (event.type === 'item.started' && item.type === 'command_execution') {
      out.push({ kind: 'tool', label: toolLabel('Run', { command: item.command }) });
    } else if (event.type === 'item.completed' && item.type === 'file_change') {
      const paths = (item.changes || []).map((c) => c.path).filter(Boolean);
      out.push({ kind: 'tool', label: `Edit ${paths.join(', ')}` });
    } else if (event.type === 'turn.completed') {
      const u = event.usage || {};
      for (const [k, v] of [['input_tokens', u.input_tokens], ['cache_read_input_tokens', u.cached_input_tokens], ['output_tokens', u.output_tokens]]) {
        state.usage[k] = (state.usage[k] || 0) + (Number(v) || 0);
      }
      out.push({ kind: 'result', text: state.text, model: '', usage: { ...state.usage }, cost: null, durationMs: null });
    } else if (event.type === 'error' || event.type === 'turn.failed') {
      out.push({ kind: 'error', text: String(event.message || (event.error && event.error.message) || 'agent error') });
    }
    return out;
  }

  return {
    feed(line) {
      const raw = String(line || '').trim();
      if (!raw.startsWith('{')) return [];
      let event;
      try { event = JSON.parse(raw); } catch { return []; }
      if (!event || typeof event !== 'object') return [];
      return executorId === 'claude_code' ? feedClaude(event) : feedCodex(event);
    },
    text() { return state.text; },
  };
}

module.exports = { buildAgentChatArgs, codexSandbox, createAgentStreamParser, newSession, sessionKey };
