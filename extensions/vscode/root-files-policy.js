'use strict';
// Repository-root deliverables of a KIT (scripts/, deploy/, infra/, root manifests, .env.example):
// written under runs/kit/<REQ>/root/<repository path>, promoted by the gate to <repository path>,
// overlaid on the eval workspace like src/ and test/. One policy for the extension; the
// orchestrator mirrors it in orchestrator/services/root_files.py (same defaults, same denylist).
//
// .clike/project.json may add folders and files:
//   { "root_folders": ["tools"], "root_files": ["Procfile"] }
const fs = require('fs');
const path = require('path');

const KIT_ROOT_DIR = 'root';
const DEFAULT_ROOT_FOLDERS = ['scripts', 'deploy', 'infra', 'ops', 'config', 'configs', 'migrations', 'db'];
const DEFAULT_ROOT_FILES = [
  '.env.example', 'compose.yml', 'compose.yaml', 'docker-compose.yml', 'docker-compose.yaml',
  'Dockerfile', 'Makefile', 'Procfile',
];
// Never a KIT deliverable: CLike state, Harper documents, KIT layout, the canonical code roots
// (they have their own KIT dirs), private configuration and generated content.
const DENIED_FIRST_SEGMENTS = new Set([
  '.git', '.clike', 'runs', 'docs', 'src', 'test', 'tests', 'ci', 'node_modules', '.venv', 'venv',
  '__pycache__', '.cache', '.next', 'dist', 'build', 'coverage',
]);
const DENIED_NAME_RE = /^\.env(\..+)?$|\.(pem|key|p12|pfx)$|^id_(rsa|ed25519)/i;

function rootPolicy(workspaceRoot) {
  let meta = {};
  try { meta = JSON.parse(fs.readFileSync(path.join(workspaceRoot, '.clike', 'project.json'), 'utf8')) || {}; } catch { /* defaults */ }
  const list = (v) => (Array.isArray(v) ? v.map((x) => String(x || '').trim().replace(/^\.?\/+|\/+$/g, '')).filter(Boolean) : []);
  const folders = [...new Set([...DEFAULT_ROOT_FOLDERS, ...list(meta.root_folders)])].filter((f) => !f.includes('/') && !DENIED_FIRST_SEGMENTS.has(f));
  const files = [...new Set([...DEFAULT_ROOT_FILES, ...list(meta.root_files)])].filter((f) => !f.includes('/'));
  return { folders, files };
}

/** True when `rel` (repository-relative) may be delivered by a KIT root/ directory. */
function isAllowedRootPath(rel, policy) {
  const p = String(rel || '').replace(/\\/g, '/').replace(/^\.\//, '');
  if (!p || p.startsWith('/') || /^[A-Za-z]:/.test(p)) return false;
  const parts = p.split('/');
  if (parts.some((s) => !s || s === '.' || s === '..')) return false;
  const name = parts[parts.length - 1];
  if (DENIED_FIRST_SEGMENTS.has(parts[0])) return false;
  if (DENIED_NAME_RE.test(name) && name !== '.env.example') return false;
  if (parts.length === 1) return policy.files.includes(name);
  return policy.folders.includes(parts[0]);
}

module.exports = { KIT_ROOT_DIR, DEFAULT_ROOT_FOLDERS, DEFAULT_ROOT_FILES, rootPolicy, isAllowedRootPath };
