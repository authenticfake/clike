'use strict';
// Service token for the CLike Orchestrator and Gateway (WP3).
//
// The token lives in VS Code SecretStorage and is attached ONLY to requests
// whose origin is the configured orchestrator or gateway URL (never to other
// hosts). The pure helpers do not require 'vscode' so they can be unit-tested.

const crypto = require('crypto');

const SERVICE_TOKEN_SECRET = 'clike.serviceToken';
const DEFAULT_SERVICE_URLS = ['http://localhost:8080', 'http://localhost:8000'];
const LOOPBACK_HOSTS = new Set(['localhost', '127.0.0.1', '[::1]', '::1']);

let cachedToken = '';
let lastAuthWarningAt = 0;

function generateServiceToken() {
  return crypto.randomBytes(32).toString('hex');
}

function setCachedServiceToken(token) {
  cachedToken = String(token || '').trim();
}

function getCachedServiceToken() {
  return cachedToken;
}

function normalizedOrigin(rawUrl) {
  let u;
  try {
    u = new URL(String(rawUrl));
  } catch {
    return null;
  }
  if (u.protocol !== 'http:' && u.protocol !== 'https:') return null;
  const host = LOOPBACK_HOSTS.has(u.hostname) ? 'loopback' : u.hostname.toLowerCase();
  const port = u.port || (u.protocol === 'https:' ? '443' : '80');
  return `${u.protocol}//${host}:${port}`;
}

function isServiceUrl(url, serviceBaseUrls) {
  const origin = normalizedOrigin(url);
  if (!origin) return false;
  return (serviceBaseUrls || []).some((base) => normalizedOrigin(base) === origin);
}

function configuredServiceUrls() {
  try {
    const vscode = require('vscode');
    const c = vscode.workspace.getConfiguration('clike');
    return [c.get('orchestratorUrl') || DEFAULT_SERVICE_URLS[0], c.get('gatewayUrl') || DEFAULT_SERVICE_URLS[1]];
  } catch {
    return DEFAULT_SERVICE_URLS;
  }
}

// Headers to merge into a request for `url`. Empty for non-service URLs or when no token is set.
function serviceAuthHeaders(url, serviceBaseUrls = configuredServiceUrls(), token = cachedToken) {
  if (!token || !isServiceUrl(url, serviceBaseUrls)) return {};
  return { Authorization: `Bearer ${token}` };
}

async function initServiceAuth(context) {
  const secrets = context.secrets;
  setCachedServiceToken(await secrets.get(SERVICE_TOKEN_SECRET));
  context.subscriptions.push(
    secrets.onDidChange(async (e) => {
      if (e.key === SERVICE_TOKEN_SECRET) setCachedServiceToken(await secrets.get(SERVICE_TOKEN_SECRET));
    })
  );
}

async function storeServiceToken(context, token) {
  const value = String(token || '').trim();
  if (value) await context.secrets.store(SERVICE_TOKEN_SECRET, value);
  else await context.secrets.delete(SERVICE_TOKEN_SECRET);
  setCachedServiceToken(value);
}

const SERVICE_AUTH_CODES = new Set(['unauthorized', 'auth_not_configured']);

// True when a 401/503 comes from the service-token middleware. Other 503s (e.g. a provider with
// no API key on the gateway: code "provider_not_configured") must not send the user to fix the
// service token. Without a readable body the status alone decides (older services).
function isServiceAuthFailure(status, bodyText) {
  if (status !== 401 && status !== 503) return false;
  if (bodyText === undefined || bodyText === null || bodyText === '') return true;
  try {
    const parsed = JSON.parse(bodyText);
    const code = parsed && typeof parsed === 'object' ? parsed.code : undefined;
    return typeof code === 'string' ? SERVICE_AUTH_CODES.has(code) : status === 401;
  } catch {
    return status === 401;
  }
}

// Call when a service answers 401/503: tells the user how to fix it (throttled).
function notifyServiceAuthFailure(status, url, bodyText) {
  if (!isServiceAuthFailure(status, bodyText)) return;
  if (!isServiceUrl(url, configuredServiceUrls())) return;
  const now = Date.now();
  if (now - lastAuthWarningAt < 30000) return;
  lastAuthWarningAt = now;
  try {
    const vscode = require('vscode');
    const msg =
      status === 503
        ? 'CLike: the service has no CLIKE_API_TOKEN configured. Set it in the stack .env and restart.'
        : cachedToken
          ? 'CLike: the service token was rejected. Make sure it matches CLIKE_API_TOKEN of the stack.'
          : 'CLike: no service token configured. Run "CLike: Set Service Token".';
    vscode.window.showWarningMessage(msg, 'Set Service Token').then((choice) => {
      if (choice) vscode.commands.executeCommand('clike.setServiceToken');
    });
  } catch {
    /* not running inside VS Code */
  }
}

module.exports = {
  SERVICE_TOKEN_SECRET,
  generateServiceToken,
  setCachedServiceToken,
  getCachedServiceToken,
  isServiceUrl,
  serviceAuthHeaders,
  configuredServiceUrls,
  initServiceAuth,
  storeServiceToken,
  notifyServiceAuthFailure,
  isServiceAuthFailure,
};
