'use strict';
// Single HTTP client for the CLike services (WP7.16).
//
// One place for: service base URLs, the service token (service-auth), timeouts (total deadline
// and AbortSignal), and error mapping. It uses node:http(s) rather than fetch because Harper
// phases can run for many minutes and fetch (undici) aborts after 300 s without response headers.
// Callers keep their historical return contracts through thin wrappers.

const http = require('http');
const https = require('https');
const { serviceAuthHeaders, notifyServiceAuthFailure } = require('./service-auth');

const DEFAULT_URLS = { orchestrator: 'http://localhost:8080', gateway: 'http://localhost:8000' };

class ServiceHttpError extends Error {
  constructor(message, { status = 0, body = '', url = '', cause } = {}) {
    super(message, cause ? { cause } : undefined);
    this.name = 'ServiceHttpError';
    this.status = status;
    this.body = body;
    this.url = url;
  }
}

function trimBase(url, fallback) {
  return String(url || fallback).replace(/\/+$/, '');
}

function serviceBaseUrls() {
  try {
    const c = require('vscode').workspace.getConfiguration('clike');
    return {
      orchestrator: trimBase(c.get('orchestratorUrl'), DEFAULT_URLS.orchestrator),
      gateway: trimBase(c.get('gatewayUrl'), DEFAULT_URLS.gateway),
    };
  } catch {
    return { ...DEFAULT_URLS };
  }
}

const orchestratorUrl = (path = '') => `${serviceBaseUrls().orchestrator}${path}`;
const gatewayUrl = (path = '') => `${serviceBaseUrls().gateway}${path}`;

// Low-level request. Resolves with { ok, status, url, text, json() } for any HTTP status;
// rejects with ServiceHttpError (status 0) on network errors, timeout or abort.
function request(method, url, { body, headers = {}, timeoutMs = 0, signal } = {}) {
  return new Promise((resolve, reject) => {
    let u;
    try {
      u = new URL(url);
    } catch (e) {
      reject(new ServiceHttpError(`invalid URL: ${url}`, { url, cause: e }));
      return;
    }
    const payload = body === undefined ? undefined : typeof body === 'string' ? body : JSON.stringify(body);
    const reqHeaders = {
      ...(payload !== undefined ? { 'Content-Type': 'application/json', 'Content-Length': Buffer.byteLength(payload) } : {}),
      ...headers,
      ...serviceAuthHeaders(url), // the service token is never overridden by callers
    };
    const lib = u.protocol === 'https:' ? https : http;
    let settled = false;
    let timer = null;
    const finish = (fn, value) => {
      if (settled) return;
      settled = true;
      if (timer) clearTimeout(timer);
      if (signal) signal.removeEventListener('abort', onAbort);
      fn(value);
    };
    const req = lib.request(
      { method, hostname: u.hostname, port: u.port || (u.protocol === 'https:' ? 443 : 80), path: u.pathname + u.search, headers: reqHeaders },
      (res) => {
        let data = '';
        res.setEncoding('utf8');
        res.on('data', (chunk) => { data += chunk; });
        res.on('error', (e) => finish(reject, new ServiceHttpError(`${method} ${url} failed: ${e.message}`, { url, cause: e })));
        res.on('end', () => {
          notifyServiceAuthFailure(res.statusCode, url, data);
          finish(resolve, {
            ok: res.statusCode >= 200 && res.statusCode < 300,
            status: res.statusCode,
            url,
            text: data,
            json() { return JSON.parse(data || 'null'); },
          });
        });
      }
    );
    const onAbort = () => req.destroy(new ServiceHttpError(`${method} ${url} aborted`, { url }));
    req.on('error', (e) => finish(reject, e instanceof ServiceHttpError ? e : new ServiceHttpError(`${method} ${url} failed: ${e.message}`, { url, cause: e })));
    if (timeoutMs > 0) {
      timer = setTimeout(() => req.destroy(new ServiceHttpError(`Request timeout after ${timeoutMs}ms`, { url })), timeoutMs);
    }
    if (signal) {
      if (signal.aborted) { onAbort(); } else { signal.addEventListener('abort', onAbort, { once: true }); }
    }
    if (payload !== undefined) req.write(payload);
    req.end();
  });
}

function errorDetail(res) {
  try {
    const parsed = JSON.parse(res.text);
    const d = parsed && (parsed.detail ?? parsed.message ?? parsed.error);
    if (d) return typeof d === 'string' ? d : JSON.stringify(d);
  } catch { /* not JSON */ }
  return res.text;
}

// JSON request: resolves with the parsed body, throws ServiceHttpError on non-2xx.
async function requestJson(method, url, options = {}) {
  const res = await request(method, url, options);
  if (!res.ok) {
    throw new ServiceHttpError(`HTTP ${res.status}: ${errorDetail(res) || 'request failed'}`, { status: res.status, body: res.text, url });
  }
  try {
    return res.json();
  } catch (e) {
    throw new ServiceHttpError(`invalid JSON from ${url}`, { status: res.status, body: res.text, url, cause: e });
  }
}

module.exports = { ServiceHttpError, serviceBaseUrls, orchestratorUrl, gatewayUrl, request, requestJson };
