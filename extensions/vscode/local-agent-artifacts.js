'use strict';
// Artifacts a local agent returns to /local-agent/complete: scratch is never sent, and within the
// size budget the candidate code and tests come first (an agent's 27 MB ci/.tmp once pushed
// src/ and test/ out and the KIT failed as "required outputs missing").

const LOCAL_AGENT_COMPLETE_MAX_FILES = 500;
const LOCAL_AGENT_COMPLETE_MAX_TOTAL_CHARS = 8 * 1024 * 1024;

const LOCAL_AGENT_EXCLUDED_ARTIFACT_SEGMENTS = new Set([
  '.git',
  '.venv',
  'node_modules',
  '.next',
  'dist',
  'build',
  'out',
  'coverage',
  '.turbo',
  '.cache',
  '.pytest_cache',
  '.ruff_cache',
  '.mypy_cache',
  '__pycache__',
  '__MACOSX',
  // scratch an agent leaves while validating (tool installs, staged copies, npm cache)
  '.tmp',
  '.npm-cache',
  '.npm',
  'local-eval-workspaces',
]);

const LOCAL_AGENT_EXCLUDED_ARTIFACT_FILENAMES = new Set([
  '.DS_Store',
  'tsconfig.tsbuildinfo',
]);

function localAgentArtifactPath(artifact) {
  return String(artifact?.path || artifact?.file || artifact?.name || '').replace(/\\/g, '/');
}

function localAgentArtifactSizeChars(artifact) {
  if (!artifact || typeof artifact !== 'object') return 0;

  if (typeof artifact.content === 'string') {
    return artifact.content.length;
  }

  if (typeof artifact.text === 'string') {
    return artifact.text.length;
  }

  if (typeof artifact.bytes_b64 === 'string') {
    return artifact.bytes_b64.length;
  }

  if (typeof artifact.content_base64 === 'string') {
    return artifact.content_base64.length;
  }

  try {
    return JSON.stringify(artifact).length;
  } catch {
    return 0;
  }
}

function shouldSendLocalAgentCompleteArtifact(artifact) {
  const relPath = localAgentArtifactPath(artifact);
  if (!relPath) return false;

  const parts = relPath.split('/').filter(Boolean);
  const filename = parts[parts.length - 1] || '';

  if (LOCAL_AGENT_EXCLUDED_ARTIFACT_FILENAMES.has(filename)) {
    return false;
  }

  if (parts.some((part) => LOCAL_AGENT_EXCLUDED_ARTIFACT_SEGMENTS.has(part))) {
    return false;
  }

  return true;
}

function pruneLocalAgentCompleteArtifacts(artifacts, phaseForAgent, reqForAgent) {
  const phase = String(phaseForAgent || '').trim().toLowerCase();
  const req = String(reqForAgent || '').trim().toUpperCase();

  const filtered = (Array.isArray(artifacts) ? artifacts : []).filter((artifact) => {
    if (!shouldSendLocalAgentCompleteArtifact(artifact)) {
      return false;
    }

    const relPath = localAgentArtifactPath(artifact);

    if (phase === 'eval') {
      const reqPrefix = `runs/kit/${req}/`;
      if (!relPath.startsWith(reqPrefix)) {
        return false;
      }

      return (
        relPath.startsWith(`${reqPrefix}ci/`) ||
        relPath.startsWith(`${reqPrefix}docs/`) ||
        relPath.startsWith(`${reqPrefix}reports/`) ||
        relPath.startsWith(`${reqPrefix}test/`)
      );
    }

    return true;
  });

  // Within the size budget, the candidate code and tests come first, then the CI profile and the
  // docs: the required roots are never dropped to make room for other files.
  const priority = (artifact) => {
    const rel = localAgentArtifactPath(artifact);
    const sub = rel.startsWith(`runs/kit/${req}/`) ? rel.slice(`runs/kit/${req}/`.length) : rel;
    if (/^(src|test|tests|root)\//.test(sub)) return 0;
    if (/^ci\/(LTC\.json|HOWTO\.md|[^/]+\.(json|txt|toml|mjs|cjs|js|py|sh))$/.test(sub)) return 1;
    if (/^docs\//.test(sub)) return 2;
    return 3;
  };
  const ordered = filtered
    .map((artifact, index) => ({ artifact, index, rank: priority(artifact) }))
    .sort((a, b) => a.rank - b.rank || a.index - b.index)
    .map((entry) => entry.artifact);

  const kept = [];
  let totalChars = 0;

  for (const artifact of ordered) {
    if (kept.length >= LOCAL_AGENT_COMPLETE_MAX_FILES) {
      break;
    }

    const sizeChars = localAgentArtifactSizeChars(artifact);
    if (totalChars + sizeChars > LOCAL_AGENT_COMPLETE_MAX_TOTAL_CHARS) {
      break;
    }

    kept.push(artifact);
    totalChars += sizeChars;
  }

  const keptSet = new Set(kept);
  return {
    files: kept,
    dropped: ordered.filter((artifact) => !keptSet.has(artifact)).map(localAgentArtifactPath),
    original_count: Array.isArray(artifacts) ? artifacts.length : 0,
    filtered_count: filtered.length,
    kept_count: kept.length,
    total_chars: totalChars,
    truncated: kept.length < filtered.length,
  };
}

module.exports = {
  LOCAL_AGENT_COMPLETE_MAX_FILES,
  LOCAL_AGENT_COMPLETE_MAX_TOTAL_CHARS,
  localAgentArtifactPath,
  localAgentArtifactSizeChars,
  pruneLocalAgentCompleteArtifacts,
  shouldSendLocalAgentCompleteArtifact,
};
