'use strict';
// The extension's operational MCP server, protocol side (no VS Code API: unit-tested).
// Streamable HTTP as MCP clients (Claude Code, Codex) expect it: JSON-RPC over POST, 202 without
// a body for notifications, 405 for GET (no server-initiated stream), ping, protocol version
// negotiated, 404 for OAuth discovery so a client without the token reports a missing header
// instead of a failed OAuth registration.
const SUPPORTED_PROTOCOL_VERSIONS = ['2025-06-18', '2025-03-26', '2024-11-05'];
const OAUTH_DISCOVERY_RE = /^\/(\.well-known\/(oauth-protected-resource|oauth-authorization-server|openid-configuration)(\/.*)?|register)$/;

/** Paths answered before authentication: OAuth discovery does not exist here. */
function preAuthRoute(method, pathname) {
  if (OAUTH_DISCOVERY_RE.test(String(pathname || ''))) {
    return { status: 404, body: { ok: false, error: 'not_found', detail: 'no OAuth: send Authorization: Bearer <extension MCP token>' } };
  }
  return null;
}

/** HTTP routing after authentication: { status, body } or null for a JSON-RPC POST. */
function postAuthRoute(method, pathname) {
  const isMcp = pathname === '/mcp' || pathname === '/';
  if (isMcp && method === 'GET') return { status: 405, headers: { Allow: 'POST' }, body: { ok: false, error: 'method_not_allowed' } };
  if (isMcp && method === 'POST') return null;
  return { status: 404, body: { ok: false, error: 'not_found', path: pathname } };
}

const rpcResult = (id, result) => ({ jsonrpc: '2.0', id, result });
const rpcError = (id, code, message) => ({ jsonrpc: '2.0', id: id ?? null, error: { code, message } });

function textResult(id, payload, isError) {
  return rpcResult(id, {
    content: [{ type: 'text', text: typeof payload === 'string' ? payload : JSON.stringify(payload, null, 2) }],
    ...(isError ? { isError: true } : {}),
  });
}

/**
 * One JSON-RPC message → response object, or null for a notification (HTTP 202, no body).
 * ctx: { serverInfo, instructions, tools: () => [...], callTool: async (name, args) => result }
 */
async function handleRpc(body, ctx) {
  if (!body || typeof body !== 'object' || Array.isArray(body)) return rpcError(null, -32600, 'Invalid Request');
  const { id, method } = body;
  const isNotification = id === undefined || id === null;
  if (String(method || '').startsWith('notifications/')) return null;
  if (isNotification) return null;
  if (method === 'initialize') {
    const requested = String(body?.params?.protocolVersion || '');
    return rpcResult(id, {
      protocolVersion: SUPPORTED_PROTOCOL_VERSIONS.includes(requested) ? requested : SUPPORTED_PROTOCOL_VERSIONS[0],
      capabilities: { tools: {} },
      serverInfo: ctx.serverInfo,
      ...(ctx.instructions ? { instructions: ctx.instructions } : {}),
    });
  }
  if (method === 'ping') return rpcResult(id, {});
  if (method === 'tools/list') return rpcResult(id, { tools: ctx.tools() });
  if (method === 'tools/call') {
    const name = String(body?.params?.name || '').trim();
    const args = body?.params?.arguments || {};
    try {
      return textResult(id, await ctx.callTool(name, args), false);
    } catch (err) {
      return textResult(id, { ok: false, tool: name, error: String(err?.message || err) }, true);
    }
  }
  return rpcError(id, -32601, `Unsupported MCP method: ${method}`);
}

/**
 * The next Harper action from plan.json REQs: the first open REQ whose dependencies are all done,
 * else the first in-progress one, else /finalize when everything is done; `blocked` when open
 * REQs wait for dependencies that are not done.
 */
function nextActionFromPlan(reqs) {
  const list = Array.isArray(reqs) ? reqs.filter((r) => r && r.id) : [];
  const status = (r) => String(r.status || 'open').trim().toLowerCase();
  const byId = new Map(list.map((r) => [String(r.id).toUpperCase(), r]));
  const deps = (r) => (Array.isArray(r.dependsOn) ? r.dependsOn : []).map((d) => String(d).trim().toUpperCase()).filter(Boolean);
  const pending = (r) => deps(r).filter((d) => status(byId.get(d) || { status: 'open' }) !== 'done');
  const pick = (r, policy, message) => ({
    ok: true, action: 'run_req', selection_policy: policy, next_phase: 'kit',
    req_id: String(r.id).toUpperCase(), req: r, dependsOn: deps(r), message,
  });
  const inProgress = list.find((r) => status(r) === 'in_progress');
  if (inProgress) return pick(inProgress, 'first_in_progress', `Continue ${String(inProgress.id).toUpperCase()} (in progress).`);
  const open = list.filter((r) => status(r) === 'open');
  const ready = open.find((r) => !pending(r).length);
  if (ready) return pick(ready, 'first_open_with_dependencies_done', `Next REQ is ${String(ready.id).toUpperCase()}: its dependencies are done.`);
  if (open.length) {
    return {
      ok: true, action: 'blocked', next_phase: null, req_id: null,
      blocked: open.map((r) => ({ req_id: String(r.id).toUpperCase(), waiting_for: pending(r) })),
      message: 'Every open REQ waits for dependencies that are not done.',
    };
  }
  return { ok: true, action: 'finalize_only', next_phase: 'finalize', req_id: null, selection_policy: 'all_done', message: 'All REQs are done. Only /finalize is available.' };
}

/** Bounded registry of MCP runs: the newest `max` are kept, running ones never dropped. */
function pruneRuns(runs, max = 50) {
  const entries = [...runs.entries()];
  const done = entries.filter(([, r]) => r.status !== 'running');
  for (const [runId] of done.slice(0, Math.max(0, entries.length - max))) runs.delete(runId);
  return runs;
}

module.exports = { SUPPORTED_PROTOCOL_VERSIONS, preAuthRoute, postAuthRoute, handleRpc, nextActionFromPlan, pruneRuns };
