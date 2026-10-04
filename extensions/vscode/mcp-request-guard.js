'use strict';
// Request validation for the extension's local operational MCP server (WP3).
//
// The server can trigger Harper phases that make local agents write files, so
// it must not be reachable from web pages:
//  - a token is always required (no anonymous mode);
//  - any request carrying an Origin header is rejected (browsers always send
//    it on cross-origin requests; MCP clients do not);
//  - the Host header must be a loopback name with the server port (DNS
//    rebinding protection);
//  - POST bodies must be declared as JSON (blocks text/plain form tricks).

const crypto = require('crypto');

const LOOPBACK_HOSTS = new Set(['127.0.0.1', 'localhost', '[::1]']);

function tokensEqual(a, b) {
  const x = Buffer.from(String(a || ''), 'utf8');
  const y = Buffer.from(String(b || ''), 'utf8');
  return x.length > 0 && x.length === y.length && crypto.timingSafeEqual(x, y);
}

function hostAllowed(hostHeader, port) {
  const host = String(hostHeader || '').trim().toLowerCase();
  if (!host) return false;
  const idx = host.lastIndexOf(':');
  const name = idx > 0 && !host.endsWith(']') ? host.slice(0, idx) : host;
  const hostPort = idx > 0 && !host.endsWith(']') ? host.slice(idx + 1) : '';
  return LOOPBACK_HOSTS.has(name) && hostPort === String(port);
}

function validateLocalMcpRequest(req, { token, port }) {
  const headers = req.headers || {};
  if (!String(token || '').trim()) {
    return { ok: false, status: 503, error: 'token_not_configured' };
  }
  if (headers.origin !== undefined) {
    return { ok: false, status: 403, error: 'origin_not_allowed' };
  }
  if (!hostAllowed(headers.host, port)) {
    return { ok: false, status: 403, error: 'host_not_allowed' };
  }
  const auth = String(headers.authorization || '').trim();
  const presented = auth.toLowerCase().startsWith('bearer ') ? auth.slice(7).trim() : '';
  if (!tokensEqual(presented, String(token).trim())) {
    return { ok: false, status: 401, error: 'unauthorized' };
  }
  if (req.method === 'POST') {
    const ct = String(headers['content-type'] || '').toLowerCase();
    if (!ct.startsWith('application/json')) {
      return { ok: false, status: 415, error: 'unsupported_media_type' };
    }
  }
  return { ok: true };
}

module.exports = { validateLocalMcpRequest, hostAllowed, tokensEqual };
