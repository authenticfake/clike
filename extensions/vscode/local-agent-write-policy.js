const WRITE_REQUIRED_PHASES = new Set(['kit', 'eval', 'finalize']);
const CODEX_SANDBOX_MODES = new Set([
  'auto',
  'read-only',
  'workspace-write',
  'danger-full-access',
]);

function makePolicyError(code, message, details = {}) {
  const error = new Error(`${code}: ${message}`);
  error.code = code;
  error.details = details;
  return error;
}

function normalizePhase(value) {
  return String(value || '').trim().toLowerCase();
}

function normalizeReqId(value) {
  return String(value || '').trim().toUpperCase();
}

function isWriteRequiredLocalAgentPhase(phase) {
  return WRITE_REQUIRED_PHASES.has(normalizePhase(phase));
}

function normalizeCodexSandboxMode(value) {
  const raw = String(value || '').trim().toLowerCase();
  return CODEX_SANDBOX_MODES.has(raw) ? raw : 'auto';
}

function isCodexSandboxWriteCapable(mode) {
  const normalized = normalizeCodexSandboxMode(mode);
  return normalized === 'workspace-write' || normalized === 'danger-full-access';
}

function resolveCodexSandboxMode({ phase, configuredSandboxMode } = {}) {
  const configured = normalizeCodexSandboxMode(configuredSandboxMode);
  if (configured !== 'auto') return configured;
  return isWriteRequiredLocalAgentPhase(phase) ? 'workspace-write' : 'read-only';
}

function extractCodexSandboxModeFromArgs(args) {
  const argv = Array.isArray(args) ? args.map((arg) => String(arg || '').trim()) : [];

  for (let i = 0; i < argv.length; i += 1) {
    const arg = argv[i];
    if (arg === '--sandbox' || arg === '-s') {
      return normalizeCodexSandboxMode(argv[i + 1] || '');
    }
    if (arg.startsWith('--sandbox=')) {
      return normalizeCodexSandboxMode(arg.slice('--sandbox='.length));
    }
  }

  return '';
}

function assertLocalAgentWritePreflight({
  phase,
  reqId,
  executorId,
  sandboxMode,
  allowedWriteRoots,
} = {}) {
  const executor = String(executorId || '').trim().toLowerCase();
  if (executor !== 'gpt_codex') return;
  if (!isWriteRequiredLocalAgentPhase(phase)) return;

  if (isCodexSandboxWriteCapable(sandboxMode)) return;

  throw makePolicyError(
    'LOCAL_AGENT_WRITE_MODE_UNAVAILABLE',
    `phase=${normalizePhase(phase)} req_id=${normalizeReqId(reqId)} executor=${executor} ` +
      `selected_sandbox=${normalizeCodexSandboxMode(sandboxMode)} ` +
      `allowed_write_roots=${JSON.stringify(Array.isArray(allowedWriteRoots) ? allowedWriteRoots : [])}`,
    {
      phase: normalizePhase(phase),
      req_id: normalizeReqId(reqId),
      executor,
      selected_sandbox: normalizeCodexSandboxMode(sandboxMode),
      allowed_write_roots: Array.isArray(allowedWriteRoots) ? allowedWriteRoots : [],
    }
  );
}

function buildCodexArgsForLocalAgent({
  argsBeforePrompt,
  phase,
  reqId,
  configuredSandboxMode,
  allowedWriteRoots,
} = {}) {
  const args = (Array.isArray(argsBeforePrompt) ? argsBeforePrompt : [])
    .map((arg) => String(arg || '').trim())
    .filter(Boolean);

  const existingSandboxMode = extractCodexSandboxModeFromArgs(args);
  const sandboxMode = existingSandboxMode ||
    resolveCodexSandboxMode({ phase, configuredSandboxMode });

  if (!existingSandboxMode) {
    args.push('--sandbox', sandboxMode);
  }

  assertLocalAgentWritePreflight({
    phase,
    reqId,
    executorId: 'gpt_codex',
    sandboxMode,
    allowedWriteRoots,
  });

  return {
    args,
    sandboxMode,
    sandboxModeSource: existingSandboxMode ? 'invocation_args' : 'settings',
  };
}

function normalizeArtifactPath(value) {
  return String(value || '').trim().replace(/\\/g, '/').replace(/^\/+/, '');
}

function getArtifactPath(artifact) {
  if (typeof artifact === 'string') return normalizeArtifactPath(artifact);
  if (!artifact || typeof artifact !== 'object') return '';
  return normalizeArtifactPath(artifact.path || artifact.file || artifact.name || '');
}

function isForbiddenCandidatePath(candidatePath) {
  const rel = normalizeArtifactPath(candidatePath);
  return (
    rel === '.git' ||
    rel.startsWith('.git/') ||
    rel.startsWith('src/') ||
    rel.startsWith('test/') ||
    rel.startsWith('tests/') ||
    rel.startsWith('docs/harper/')
  );
}

function hasArtifactUnder(artifacts, root) {
  const normalizedRoot = normalizeArtifactPath(root);
  return (Array.isArray(artifacts) ? artifacts : []).some((artifact) => {
    const rel = getArtifactPath(artifact);
    return rel && rel.startsWith(normalizedRoot);
  });
}

function validateLocalAgentRequiredOutputs({
  phase,
  reqId,
  artifacts,
} = {}) {
  const artifactList = Array.isArray(artifacts) ? artifacts : [];
  const forbidden = artifactList
    .map(getArtifactPath)
    .filter(Boolean)
    .filter(isForbiddenCandidatePath);

  if (forbidden.length) {
    throw makePolicyError(
      'LOCAL_AGENT_FORBIDDEN_OUTPUT_PATH',
      `local-agent produced forbidden candidate paths: ${forbidden.slice(0, 10).join(', ')}`,
      { forbidden_paths: forbidden.slice(0, 25) }
    );
  }

  const normalizedPhase = normalizePhase(phase);
  if (normalizedPhase !== 'kit') {
    return { ok: true, missing_required_roots: [] };
  }

  const req = normalizeReqId(reqId);
  const requiredRoots = [
    `runs/kit/${req}/src/`,
    `runs/kit/${req}/test/`,
    `runs/kit/${req}/ci/`,
  ];
  const missingRoots = requiredRoots.filter((root) => !hasArtifactUnder(artifactList, root));

  if (missingRoots.length) {
    throw makePolicyError(
      'LOCAL_AGENT_REQUIRED_OUTPUTS_MISSING',
      `phase=${normalizedPhase} req_id=${req} missing_required_roots=${missingRoots.join(', ')}`,
      {
        phase: normalizedPhase,
        req_id: req,
        missing_required_roots: missingRoots,
      }
    );
  }

  return { ok: true, missing_required_roots: [] };
}

module.exports = {
  buildCodexArgsForLocalAgent,
  extractCodexSandboxModeFromArgs,
  isCodexSandboxWriteCapable,
  isForbiddenCandidatePath,
  isWriteRequiredLocalAgentPhase,
  normalizeCodexSandboxMode,
  resolveCodexSandboxMode,
  assertLocalAgentWritePreflight,
  validateLocalAgentRequiredOutputs,
};
