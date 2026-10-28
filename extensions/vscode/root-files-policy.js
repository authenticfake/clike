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
// Also deliverable (B2B REQ-037/038 had no legal place for them and staged them under ci/shared/,
// which is never promoted): the example of each private env file (.env.oidc.example), the ignore
// files, the solution eval profile, and project documentation outside the Harper/input folders.
const ENV_EXAMPLE_RE = /^\.env(\.[\w-]+)?\.example$/;
const EXTRA_ROOT_FILES = ['.gitignore', '.dockerignore'];
const SOLUTION_FILES = ['ci/SOLUTION_LTC.json'];
const DOCS_DENIED = new Set(['harper', 'inputs', 'reference']);

function rootPolicy(workspaceRoot) {
  let meta = {};
  try { meta = JSON.parse(fs.readFileSync(path.join(workspaceRoot, '.clike', 'project.json'), 'utf8')) || {}; } catch { /* defaults */ }
  const list = (v) => (Array.isArray(v) ? v.map((x) => String(x || '').trim().replace(/^\.?\/+|\/+$/g, '')).filter(Boolean) : []);
  const areas = projectAreas(meta);
  // the areas of a project (a monorepo of services): their roots are repository folders a KIT delivers
  // through root/<area root>/…, as scripts/ or deploy/ (promotion, eval overlay, regression unchanged)
  const areaFolders = areas.map((a) => a.root.split('/')[0]);
  const folders = [...new Set([...DEFAULT_ROOT_FOLDERS, ...list(meta.root_folders), ...areaFolders])].filter((f) => !f.includes('/') && !DENIED_FIRST_SEGMENTS.has(f));
  const files = [...new Set([...DEFAULT_ROOT_FILES, ...list(meta.root_files)])].filter((f) => !f.includes('/'));
  return { folders, files, areas };
}

/** The areas `.clike/project.json` declares: [{ name, root, source, tests, commands }] (mirror of root_files.py). */
function projectAreas(meta) {
  const clean = (v) => String(v || '').trim().replace(/^\.?\/+|\/+$/g, '');
  const out = [];
  for (const raw of Array.isArray(meta?.areas) ? meta.areas : []) {
    if (!raw || typeof raw !== 'object') continue;
    const root = clean(raw.root);
    if (!root || root.startsWith('/') || root.split('/').includes('..') || DENIED_FIRST_SEGMENTS.has(root.split('/')[0])) continue;
    const paths = (key) => (Array.isArray(raw[key]) ? raw[key] : (raw[key] ? [raw[key]] : [])).map(clean).filter(Boolean);
    out.push({
      name: String(raw.name || root.split('/').pop()),
      root,
      source: paths('source').length ? paths('source') : [root],
      tests: paths('tests'),
      commands: raw.commands && typeof raw.commands === 'object' ? raw.commands : {},
    });
  }
  return out;
}

/** Repository-relative test roots of the areas (their files are acceptance, locked like test/). */
function areaTestRoots(workspaceRoot) {
  return rootPolicy(workspaceRoot).areas.flatMap((a) => a.tests);
}

/** True when `rel` (repository-relative) may be delivered by a KIT root/ directory. */
function isAllowedRootPath(rel, policy) {
  const p = String(rel || '').replace(/\\/g, '/').replace(/^\.\//, '');
  if (!p || p.startsWith('/') || /^[A-Za-z]:/.test(p)) return false;
  const parts = p.split('/');
  if (parts.some((s) => !s || s === '.' || s === '..')) return false;
  const name = parts[parts.length - 1];
  if (DENIED_NAME_RE.test(name) && !ENV_EXAMPLE_RE.test(name)) return false;
  if (SOLUTION_FILES.includes(p)) return true;
  if (parts[0] === 'docs') return parts.length > 2 ? !DOCS_DENIED.has(parts[1]) : parts.length === 2;
  if (DENIED_FIRST_SEGMENTS.has(parts[0])) return false;
  if (parts.length === 1) return policy.files.includes(name) || ENV_EXAMPLE_RE.test(name) || EXTRA_ROOT_FILES.includes(name);
  return policy.folders.includes(parts[0]);
}

module.exports = { KIT_ROOT_DIR, DEFAULT_ROOT_FOLDERS, DEFAULT_ROOT_FILES, rootPolicy, isAllowedRootPath, projectAreas, areaTestRoots };
