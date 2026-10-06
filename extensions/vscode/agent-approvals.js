'use strict';
// Interactive approvals in the agent chat (H1 phase 2). In Coding mode with
// clike.agentChat.approvals = "ask", every edit or command of the agent waits for the developer:
//  - Claude Code asks through --permission-prompt-tool, answered by a one-turn local MCP server;
//  - Codex runs through `codex app-server`, whose approval requests are answered here.
// One policy for both agents: writes outside the Coding output root are denied without asking;
// everything else asks (Allow / Allow all this turn / Deny).
const crypto = require('crypto');
const http = require('http');
const path = require('path');
const { validateLocalMcpRequest } = require('./mcp-request-guard');

const CLAUDE_WRITE_TOOLS = new Set(['Edit', 'Write', 'MultiEdit', 'NotebookEdit']);
const APPROVAL_SERVER = 'clike_approval';
const APPROVAL_TOOL = 'approve';

function isUnder(root, candidate) {
  const rel = path.relative(root, path.resolve(root, String(candidate || '')));
  return rel === '' || (!rel.startsWith('..') && !path.isAbsolute(rel));
}

/**
 * The approval gate of one turn. ask(request) shows the question and returns
 * 'allow' | 'allowAll' | 'deny'. request: { kind: 'edit'|'command'|'tool', summary, paths }.
 * Returns { allow, reason, auto }.
 */
function createApprovalGate({ ask, workspaceRoot, writeRoot, onEvent = null }) {
  let allowAll = false;
  const emit = (label) => { if (typeof onEvent === 'function') onEvent({ kind: 'tool', label }); };
  // paths are shown relative to the project
  const shorten = (text) => (workspaceRoot ? String(text || '').split(workspaceRoot + path.sep).join('') : String(text || '')).split(path.sep).join('/');
  async function check(request) {
    const paths = Array.isArray(request.paths) ? request.paths.filter(Boolean) : [];
    const outside = writeRoot ? paths.filter((p) => !isUnder(writeRoot, path.resolve(workspaceRoot || writeRoot, p))) : [];
    if (outside.length) {
      const where = (path.relative(workspaceRoot || '', writeRoot) || writeRoot).split(path.sep).join('/');
      return { allow: false, auto: true, reason: `CLike Coding mode writes only under ${where}/ (blocked: ${outside.map(shorten).join(', ')})` };
    }
    if (allowAll) return { allow: true, auto: true, reason: 'allowed for this turn' };
    const choice = await ask({ ...request, paths });
    if (choice === 'allowAll') allowAll = true;
    const allow = choice === 'allow' || choice === 'allowAll';
    return { allow, auto: false, reason: allow ? '' : 'denied by the developer' };
  }
  return async function decide(request) {
    const shown = { ...request, summary: shorten(request.summary) };
    emit(`⏸ approval: ${shown.summary.slice(0, 160)}`);
    const decision = await check(shown);
    emit(`${decision.allow ? '✔ allowed' : '✖ denied'}${decision.reason ? ` (${decision.reason})` : ''}`);
    return decision;
  };
}

function describeClaudeRequest(toolName, input) {
  const i = input || {};
  if (CLAUDE_WRITE_TOOLS.has(toolName)) {
    const file = i.file_path || i.notebook_path || i.path || '';
    return { kind: 'edit', summary: `${toolName} ${file}`, paths: file ? [file] : [] };
  }
  if (toolName === 'Bash') return { kind: 'command', summary: String(i.command || ''), paths: [] };
  return { kind: 'tool', summary: `${toolName} ${JSON.stringify(i).slice(0, 300)}`, paths: [] };
}

function describeCodexRequest(method, params, item) {
  const p = params || {};
  if (method === 'item/fileChange/requestApproval') {
    const paths = ((item && item.changes) || []).map((c) => c.path).filter(Boolean);
    return { kind: 'edit', summary: `Edit ${paths.join(', ') || '(files)'}${p.reason ? ` — ${p.reason}` : ''}`, paths };
  }
  return { kind: 'command', summary: `${p.command || ''}${p.reason ? ` — ${p.reason}` : ''}`, paths: [] };
}

function sendJson(res, status, body) {
  if (body === null) {
    res.writeHead(status);
    return res.end();
  }
  const raw = JSON.stringify(body);
  res.writeHead(status, { 'content-type': 'application/json; charset=utf-8', 'content-length': Buffer.byteLength(raw) });
  return res.end(raw);
}

async function readJson(req) {
  const chunks = [];
  for await (const chunk of req) chunks.push(Buffer.from(chunk));
  return JSON.parse(Buffer.concat(chunks).toString('utf8') || '{}');
}

/**
 * Claude: a local MCP server living for one turn, with the single tool Claude calls for
 * permission (--permission-prompt-tool). Returns { args, close }.
 */
async function startClaudeApprovalServer(decide) {
  const token = crypto.randomBytes(24).toString('hex');
  let port = 0;
  const server = http.createServer(async (req, res) => {
    try {
      const verdict = validateLocalMcpRequest(req, { token, port });
      if (!verdict.ok) return sendJson(res, verdict.status, { error: verdict.error });
      if (req.method !== 'POST') return sendJson(res, 405, { error: 'method_not_allowed' });
      const body = await readJson(req);
      const id = body.id;
      if (id === undefined || id === null) return sendJson(res, 202, null); // notification
      if (body.method === 'initialize') {
        return sendJson(res, 200, {
          jsonrpc: '2.0', id,
          result: {
            protocolVersion: (body.params && body.params.protocolVersion) || '2025-06-18',
            capabilities: { tools: {} },
            serverInfo: { name: 'CLike approvals', version: '1' },
          },
        });
      }
      if (body.method === 'tools/list') {
        return sendJson(res, 200, {
          jsonrpc: '2.0', id,
          result: {
            tools: [{
              name: APPROVAL_TOOL,
              description: 'CLike asks the developer to allow or deny a tool use.',
              inputSchema: {
                type: 'object',
                properties: { tool_name: { type: 'string' }, input: { type: 'object' }, tool_use_id: { type: 'string' } },
                required: ['tool_name', 'input'],
              },
            }],
          },
        });
      }
      if (body.method === 'tools/call') {
        const args = (body.params && body.params.arguments) || {};
        const decision = await decide(describeClaudeRequest(String(args.tool_name || ''), args.input));
        const answer = decision.allow
          ? { behavior: 'allow', updatedInput: args.input || {} }
          : { behavior: 'deny', message: decision.reason || 'denied' };
        return sendJson(res, 200, { jsonrpc: '2.0', id, result: { content: [{ type: 'text', text: JSON.stringify(answer) }] } });
      }
      return sendJson(res, 200, { jsonrpc: '2.0', id, error: { code: -32601, message: `Unsupported method: ${body.method}` } });
    } catch (err) {
      return sendJson(res, 500, { error: String((err && err.message) || err) });
    }
  });
  await new Promise((resolve, reject) => {
    server.once('error', reject);
    server.listen(0, '127.0.0.1', resolve);
  });
  port = server.address().port;
  const mcpConfig = {
    mcpServers: {
      // localhost, not 127.0.0.1: managed Claude Code policies commonly allow `http://localhost*` only
      [APPROVAL_SERVER]: { type: 'http', url: `http://localhost:${port}/mcp`, headers: { Authorization: `Bearer ${token}` } },
    },
  };
  return {
    args: ['--mcp-config', JSON.stringify(mcpConfig), '--permission-prompt-tool', `mcp__${APPROVAL_SERVER}__${APPROVAL_TOOL}`],
    close: () => new Promise((resolve) => server.close(() => resolve())),
  };
}

/**
 * Codex: drives one chat turn over `codex app-server` (JSON-RPC lines on stdio).
 * Call attach(stdin) when the process starts and feed(line) with each stdout line.
 * Emits the chat events of agent-chat.js (session, delta, tool, result, error) and answers
 * approval requests through decide(). done resolves when the turn ends.
 */
function createCodexAppServerTurn({ cwd, prompt, session, model, sandbox, approvalPolicy, decide, onEvent, clientVersion = '1' }) {
  const emit = (event) => { if (typeof onEvent === 'function') onEvent(event); };
  const pending = new Map();
  const items = new Map();
  const usage = { input_tokens: 0, cache_read_input_tokens: 0, output_tokens: 0 };
  let stdin = null;
  let nextId = 0;
  let text = '';
  let threadId = (session && session.id) || '';
  let finish;
  const done = new Promise((resolve) => { finish = resolve; });
  let finished = false;
  const end = (outcome) => {
    if (finished) return;
    finished = true;
    if (stdin) { try { stdin.end(); } catch { /* the process may be gone */ } }
    finish(outcome);
  };

  const write = (message) => { if (stdin && !finished) stdin.write(JSON.stringify({ jsonrpc: '2.0', ...message }) + '\n'); };
  const request = (method, params) => new Promise((resolve, reject) => {
    const id = ++nextId;
    pending.set(id, { resolve, reject });
    write({ id, method, params });
  });

  async function answer(message) {
    const { id, method, params } = message;
    if (method === 'item/commandExecution/requestApproval' || method === 'item/fileChange/requestApproval') {
      const decision = await decide(describeCodexRequest(method, params, items.get(params && params.itemId)));
      write({ id, result: { decision: decision.allow ? 'accept' : 'decline' } });
      return;
    }
    // Other requests (extra permissions, elicitations, user input) are not granted from the chat.
    write({ id, error: { code: -32601, message: `CLike chat does not handle ${method}` } });
  }

  function onNotification(method, params) {
    const p = params || {};
    const item = p.item || {};
    if (method === 'item/started' && item.id) items.set(item.id, item);
    if (method === 'item/agentMessage/delta' && p.delta) {
      text += p.delta;
      emit({ kind: 'delta', text: p.delta });
    } else if (method === 'item/started' && item.type === 'commandExecution') {
      emit({ kind: 'tool', label: `Run ${String(item.command || '').slice(0, 160)}` });
    } else if (method === 'item/started' && item.type === 'fileChange') {
      emit({ kind: 'tool', label: `Edit ${(item.changes || []).map((c) => c.path).join(', ')}` });
    } else if (method === 'thread/tokenUsage/updated') {
      const last = (p.tokenUsage && p.tokenUsage.last) || {};
      usage.input_tokens += Number(last.inputTokens) || 0;
      usage.cache_read_input_tokens += Number(last.cachedInputTokens) || 0;
      usage.output_tokens += Number(last.outputTokens) || 0;
    } else if (method === 'turn/completed') {
      const turn = p.turn || {};
      if (turn.status === 'failed' || turn.error) {
        const message = (turn.error && turn.error.message) || 'Codex turn failed';
        emit({ kind: 'error', text: message });
        end({ ok: false, error: message, text, threadId, usage });
      } else {
        emit({ kind: 'result', text, model: model || '', usage: { ...usage }, cost: null, durationMs: turn.durationMs || null });
        end({ ok: true, text, threadId, usage });
      }
    } else if (method === 'error' && p.error && !p.willRetry) {
      emit({ kind: 'error', text: String(p.error.message || 'Codex error') });
    }
  }

  async function start() {
    await request('initialize', { clientInfo: { name: 'clike', version: clientVersion } });
    write({ method: 'initialized' });
    const threadParams = { cwd, sandbox, approvalPolicy, ...(model ? { model } : {}) };
    const opened = threadId && session && session.started
      ? await request('thread/resume', { threadId, ...threadParams })
      : await request('thread/start', threadParams);
    threadId = (opened && opened.thread && opened.thread.id) || threadId;
    emit({ kind: 'session', id: threadId });
    await request('turn/start', { threadId, input: [{ type: 'text', text: prompt }] });
  }

  return {
    done,
    attach(stream) {
      stdin = stream;
      start().catch((err) => {
        const message = String((err && err.message) || err);
        emit({ kind: 'error', text: message });
        end({ ok: false, error: message, text, threadId, usage });
      });
    },
    feed(line) {
      const raw = String(line || '').trim();
      if (!raw.startsWith('{')) return;
      let message;
      try { message = JSON.parse(raw); } catch { return; }
      if (message.id !== undefined && message.id !== null && !message.method) {
        const waiter = pending.get(message.id);
        if (!waiter) return;
        pending.delete(message.id);
        if (message.error) waiter.reject(new Error(message.error.message || 'Codex app-server error'));
        else waiter.resolve(message.result);
        return;
      }
      if (message.method && message.id !== undefined && message.id !== null) {
        answer(message).catch(() => write({ id: message.id, result: { decision: 'decline' } }));
        return;
      }
      if (message.method) onNotification(message.method, message.params);
    },
    // the process exited before the turn ended
    closed(exitCode) {
      end({ ok: false, error: `Codex app-server exited (code ${exitCode}) before the turn completed`, text, threadId, usage });
    },
  };
}

module.exports = {
  createApprovalGate,
  createCodexAppServerTurn,
  describeClaudeRequest,
  describeCodexRequest,
  isUnder,
  startClaudeApprovalServer,
};
