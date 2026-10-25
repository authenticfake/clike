'use strict';
// Unchanged repository sources sent with a finalize result. Finalize reuses the promoted code:
// a database or auth boundary that already exists is not returned by the agent, so the
// orchestrator checks it in these files (read-only evidence, never written back).

const fs = require('fs');
const path = require('path');

const SOURCE_ROOT = 'src';
const MAX_FILE_BYTES = 150 * 1024;
const MAX_TOTAL_BYTES = 1024 * 1024;
const MAX_FILES = 400;
// Dependency, build and cache folders are not the project's code.
const SKIP_DIRS = new Set([
  'node_modules', '__pycache__', 'dist', 'build', 'target', 'bin', 'obj', 'out', 'coverage',
  'venv', 'vendor',
]);

function isSkippedDir(name) {
  return name.startsWith('.') || SKIP_DIRS.has(name);
}

function isSkippedFile(name) {
  // Env files can hold real values; they are never sent.
  return name.startsWith('.env') || name.startsWith('.');
}

function collectExistingSourceEvidence(workspaceRoot, returnedPaths = [], opts = {}) {
  const maxFileBytes = opts.maxFileBytes || MAX_FILE_BYTES;
  const maxTotalBytes = opts.maxTotalBytes || MAX_TOTAL_BYTES;
  const maxFiles = opts.maxFiles || MAX_FILES;
  const returned = new Set((returnedPaths || []).map((p) => String(p || '').replace(/\\/g, '/').replace(/^\/+/, '')));
  const out = [];
  let total = 0;
  const root = path.join(workspaceRoot, SOURCE_ROOT);
  if (!workspaceRoot || !fs.existsSync(root)) return out;

  const walk = (dir) => {
    let entries;
    try {
      entries = fs.readdirSync(dir, { withFileTypes: true }).sort((a, b) => a.name.localeCompare(b.name));
    } catch {
      return;
    }
    for (const entry of entries) {
      if (out.length >= maxFiles || total >= maxTotalBytes) return;
      const abs = path.join(dir, entry.name);
      if (entry.isDirectory()) {
        if (!isSkippedDir(entry.name)) walk(abs);
        continue;
      }
      if (!entry.isFile() || isSkippedFile(entry.name)) continue;
      const rel = path.relative(workspaceRoot, abs).split(path.sep).join('/');
      if (returned.has(rel)) continue;
      let buf;
      try {
        if (fs.statSync(abs).size > maxFileBytes) continue;
        buf = fs.readFileSync(abs);
      } catch {
        continue;
      }
      if (buf.includes(0) || total + buf.length > maxTotalBytes) continue;
      out.push({ path: rel, content: buf.toString('utf8') });
      total += buf.length;
    }
  };
  walk(root);
  return out;
}

module.exports = { collectExistingSourceEvidence };
