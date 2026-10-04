'use strict';
// Workspace path confinement for paths that come from the orchestrator,
// an LLM or a local agent (WP4). vscode.Uri.joinPath normalizes '..', so a
// server-provided "../../x" would otherwise escape the workspace.

const path = require('path');

class UnsafeWorkspacePathError extends Error {}

// Validate a workspace-relative path and return it in normalized POSIX form.
function safeRelativePath(rel) {
  const raw = String(rel == null ? '' : rel);
  if (!raw.trim()) throw new UnsafeWorkspacePathError('empty path');
  if (raw.includes('\0')) throw new UnsafeWorkspacePathError('NUL byte in path');
  const posix = raw.replace(/\\/g, '/');
  if (posix.startsWith('/') || /^[A-Za-z]:/.test(posix) || posix.startsWith('//')) {
    throw new UnsafeWorkspacePathError(`absolute path not allowed: ${raw}`);
  }
  const normalized = path.posix.normalize(posix.replace(/^(\.\/)+/, ''));
  if (normalized === '..' || normalized.startsWith('../') || normalized === '.' || normalized === '') {
    throw new UnsafeWorkspacePathError(`path escapes the workspace: ${raw}`);
  }
  return normalized;
}

// True if fsPath is the workspace root or inside it (platform-aware).
function isInsideRoot(rootFsPath, fsPath) {
  const rel = path.relative(path.resolve(rootFsPath), path.resolve(fsPath));
  return rel === '' || (!rel.startsWith('..') && !path.isAbsolute(rel));
}

// Uri for a relative path inside the workspace root Uri.
function safeWorkspaceUri(rootUri, rel, Uri = require('vscode').Uri) {
  const segments = safeRelativePath(rel).split('/');
  return Uri.joinPath(rootUri, ...segments);
}

// Accepts a relative path, or an absolute/file:// path that already lies inside the workspace.
function resolveInsideWorkspace(rootUri, p, Uri = require('vscode').Uri) {
  const raw = String(p || '');
  if (raw.startsWith('file://') || raw.startsWith('/') || /^[A-Za-z]:[\\/]/.test(raw)) {
    const uri = raw.startsWith('file://') ? Uri.parse(raw) : Uri.file(raw);
    if (!isInsideRoot(rootUri.fsPath, uri.fsPath)) {
      throw new UnsafeWorkspacePathError(`path outside the workspace: ${raw}`);
    }
    return uri;
  }
  return safeWorkspaceUri(rootUri, raw, Uri);
}

module.exports = {
  UnsafeWorkspacePathError,
  safeRelativePath,
  isInsideRoot,
  safeWorkspaceUri,
  resolveInsideWorkspace,
};
