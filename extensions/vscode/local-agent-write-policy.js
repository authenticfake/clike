// Every local-agent phase writes its outputs to the workspace, which the
// extension then reads back: Codex needs a write-capable sandbox for all of
// them. The path policy below limits what is accepted.
const WRITE_REQUIRED_PHASES = new Set([
  'idea', 'spec', 'plan', 'kit', 'eval', 'finalize', 'extend',
]);

// Early Harper document phases may write only their exact canonical Harper
// outputs. Everything else under docs/harper/ stays forbidden.
const DOCUMENT_PHASE_REQUIRED_OUTPUTS = {
  idea: ['docs/harper/IDEA.md'],
  spec: ['docs/harper/SPEC.md'],
  plan: ['docs/harper/PLAN.md', 'docs/harper/plan.json'],
};

// Additional path prefixes a document phase is allowed to write.
const DOCUMENT_PHASE_ALLOWED_PREFIXES = {
  idea: [],
  spec: [],
  plan: ['docs/harper/lane-guides/'],
};
// BMAD companion documents (docs/harper/bmad/**, docs/harper/ux/**) are
// declared per phase/agent by the orchestrator in active_output_contract.
// Only these roots can ever be opened up by a contract.
const BMAD_COMPANION_SAFE_ROOTS = ['docs/harper/bmad/', 'docs/harper/ux/'];

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
  // A new Harper project is often not a git repository yet: without this flag Codex
  // exits 1 ("Not inside a trusted directory"). The agent chat passes it too.
  if (!args.includes('--skip-git-repo-check')) {
    args.push('--skip-git-repo-check');
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

function isDocumentPhase(phase) {
  return Object.prototype.hasOwnProperty.call(
    DOCUMENT_PHASE_REQUIRED_OUTPUTS,
    normalizePhase(phase)
  );
}

function isDocumentPhaseAllowedOutput(phase, candidatePath) {
  const p = normalizePhase(phase);
  const rel = normalizeArtifactPath(candidatePath);
  const exact = DOCUMENT_PHASE_REQUIRED_OUTPUTS[p] || [];
  if (exact.includes(rel)) return true;
  const prefixes = DOCUMENT_PHASE_ALLOWED_PREFIXES[p] || [];
  return prefixes.some((prefix) => rel.startsWith(prefix)) && isLaneGuideFile(rel);
}

// Lane guides are Markdown, as the orchestrator accepts them (B12).
function isLaneGuideFile(rel) {
  return !rel.startsWith('docs/harper/lane-guides/') || /\.md$/i.test(rel);
}

// /extend is a mutation/append phase: it may rewrite the canonical Harper docs
// (IDEA/SPEC/PLAN/plan.json), lane-guides, and must emit a dated EXTEND audit
// report. Everything else under docs/harper/ (including AGENT_* internals) and
// all src/test/runs roots remain forbidden.
const EXTEND_ALLOWED_EXACT = [
  'docs/harper/IDEA.md',
  'docs/harper/SPEC.md',
  'docs/harper/PLAN.md',
  'docs/harper/plan.json',
];
const EXTEND_ALLOWED_PREFIXES = ['docs/harper/lane-guides/'];

function isExtendPhase(phase) {
  return normalizePhase(phase) === 'extend';
}

function isExtendAuditPath(candidatePath) {
  return /^docs\/harper\/EXTEND_.+\.md$/.test(normalizeArtifactPath(candidatePath));
}

function isExtendAllowedOutput(candidatePath) {
  const rel = normalizeArtifactPath(candidatePath);
  if (EXTEND_ALLOWED_EXACT.includes(rel)) return true;
  if (EXTEND_ALLOWED_PREFIXES.some((prefix) => rel.startsWith(prefix))) return isLaneGuideFile(rel);
  return isExtendAuditPath(rel);
}

function isBmadContract(outputContract) {
  return !!outputContract && typeof outputContract === 'object' &&
    String(outputContract.methodology || '').trim().toLowerCase() === 'bmad';
}

function isSafeCompanionPath(rel) {
  return (
    !rel.split('/').includes('..') &&
    /\.md$/i.test(rel) &&
    BMAD_COMPANION_SAFE_ROOTS.some((root) => rel.startsWith(root))
  );
}

// Glob -> RegExp with the orchestrator's fnmatch semantics ("*" crosses "/").
function globToRegExp(glob) {
  const escaped = normalizeArtifactPath(glob)
    .replace(/[.+^${}()|[\]\\]/g, '\\$&')
    .replace(/\*+/g, '.*')
    .replace(/\?/g, '.');
  return new RegExp(`^${escaped}$`);
}

function matchesAnyGlob(rel, globs) {
  return (Array.isArray(globs) ? globs : []).some((glob) => globToRegExp(glob).test(rel));
}

// Companion outputs a BMAD contract declares for a document phase: the exact
// mandatory paths and the directories of the optional root globs, both
// restricted to the BMAD companion roots.
function documentPhaseCompanionTargets(outputContract) {
  if (!isBmadContract(outputContract)) return { files: [], dirs: [] };
  const files = (outputContract.required_outputs || [])
    .map(normalizeArtifactPath)
    .filter((rel) => !rel.includes('*') && isSafeCompanionPath(rel));
  const dirs = (outputContract.allowed_optional_output_globs || [])
    .map(normalizeArtifactPath)
    .map((glob) => glob.replace(/\/?\*+$/, ''))
    .filter((dir) => dir && !dir.includes('*') && isSafeCompanionPath(`${dir}/x.md`));
  return { files: [...new Set(files)], dirs: [...new Set(dirs)] };
}

function isDocumentPhaseCompanionOutput(outputContract, candidatePath) {
  if (!isBmadContract(outputContract)) return false;
  const rel = normalizeArtifactPath(candidatePath);
  if (!isSafeCompanionPath(rel)) return false;
  if (matchesAnyGlob(rel, outputContract.forbidden_output_globs)) return false;
  const targets = documentPhaseCompanionTargets(outputContract);
  return targets.files.includes(rel) || targets.dirs.some((dir) => rel.startsWith(`${dir}/`));
}

function isDocumentPhaseContractOutput(phase, outputContract, rel) {
  if (isDocumentPhaseCompanionOutput(outputContract, rel)) return true;
  if (!isDocumentPhaseAllowedOutput(phase, rel)) return false;
  return !(isBmadContract(outputContract) && matchesAnyGlob(rel, outputContract.forbidden_output_globs));
}

// Canonical outputs of a document phase, minus those the BMAD agent is
// forbidden to write (the companion-only spec/ux agent never writes SPEC.md).
function documentPhaseRequiredOutputs(phase, outputContract) {
  const required = DOCUMENT_PHASE_REQUIRED_OUTPUTS[normalizePhase(phase)] || [];
  if (!isBmadContract(outputContract)) return required;
  return required.filter((rel) => !matchesAnyGlob(rel, outputContract.forbidden_output_globs));
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
  kitStage = null,
  outputContract = null,
} = {}) {
  const artifactList = Array.isArray(artifacts) ? artifacts : [];
  const normalizedPhase = normalizePhase(phase);
  const documentPhase = isDocumentPhase(normalizedPhase);
  const extendPhase = isExtendPhase(normalizedPhase);

  const forbidden = artifactList
    .map(getArtifactPath)
    .filter(Boolean)
    .filter(
      (rel) =>
        isForbiddenCandidatePath(rel) &&
        !(documentPhase && isDocumentPhaseContractOutput(normalizedPhase, outputContract, rel)) &&
        !(extendPhase && isExtendAllowedOutput(rel))
    );

  if (forbidden.length) {
    throw makePolicyError(
      'LOCAL_AGENT_FORBIDDEN_OUTPUT_PATH',
      `local-agent produced forbidden candidate paths: ${forbidden.slice(0, 10).join(', ')}`,
      { forbidden_paths: forbidden.slice(0, 25) }
    );
  }

  if (documentPhase) {
    const required = documentPhaseRequiredOutputs(normalizedPhase, outputContract);
    const present = new Set(artifactList.map(getArtifactPath).filter(Boolean));
    const missingOutputs = required.filter((output) => !present.has(output));

    if (missingOutputs.length) {
      throw makePolicyError(
        'LOCAL_AGENT_REQUIRED_OUTPUTS_MISSING',
        `phase=${normalizedPhase} missing_required_outputs=${missingOutputs.join(', ')}`,
        {
          phase: normalizedPhase,
          missing_required_outputs: missingOutputs,
        }
      );
    }

    return { ok: true, missing_required_roots: [] };
  }

  if (extendPhase) {
    const presentPaths = artifactList.map(getArtifactPath).filter(Boolean);
    const present = new Set(presentPaths);
    const missingOutputs = [];
    if (!present.has('docs/harper/PLAN.md')) missingOutputs.push('docs/harper/PLAN.md');
    if (!present.has('docs/harper/plan.json')) missingOutputs.push('docs/harper/plan.json');
    if (!presentPaths.some(isExtendAuditPath)) {
      missingOutputs.push('docs/harper/EXTEND_<date>_<first_req>_<last_req>.md');
    }

    if (missingOutputs.length) {
      throw makePolicyError(
        'LOCAL_AGENT_REQUIRED_OUTPUTS_MISSING',
        `phase=extend missing_required_outputs=${missingOutputs.join(', ')}`,
        { phase: 'extend', missing_required_outputs: missingOutputs }
      );
    }

    return { ok: true, missing_required_roots: [] };
  }

  if (normalizedPhase !== 'kit') {
    return { ok: true, missing_required_roots: [] };
  }

  const req = normalizeReqId(reqId);
  // Acceptance-first stage 1 writes the tests and the eval profile only.
  const requiredRoots = kitStage === 'acceptance'
    ? [`runs/kit/${req}/test/`, `runs/kit/${req}/ci/`]
    : [`runs/kit/${req}/src/`, `runs/kit/${req}/test/`, `runs/kit/${req}/ci/`];
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

// Early Harper document phases have phase-specific input source-of-truth rules.
// This pure guard is evaluated in the extension BEFORE any orchestrator call so
// invalid runs never reach the network or trigger the local agent / cloud
// fallback. The extension supplies the observable inputs (current-run
// attachment count, and whether the canonical upstream doc exists on disk).
function evaluateDocumentPhaseInputPreflight({
  phase,
  attachmentCount,
  ideaPresent,
  specPresent,
} = {}) {
  const p = normalizePhase(phase);

  if (p === 'idea') {
    if (!(Number(attachmentCount) > 0)) {
      return {
        ok: false,
        code: 'IDEA_REQUIRES_CURRENT_ATTACHMENT',
        message:
          'Cannot run /idea without at least one attached source file. ' +
          'Attach an IDEA/source document and retry.',
      };
    }
    return { ok: true };
  }

  if (p === 'spec') {
    if (!ideaPresent) {
      return {
        ok: false,
        code: 'SPEC_REQUIRES_IDEA',
        message:
          'Cannot run /spec because docs/harper/IDEA.md is missing. ' +
          'Run /idea with an attachment first.',
      };
    }
    return { ok: true };
  }

  if (p === 'plan') {
    if (!specPresent) {
      return {
        ok: false,
        code: 'PLAN_REQUIRES_SPEC',
        message:
          'Cannot run /plan because docs/harper/SPEC.md is missing. Run /spec first.',
      };
    }
    return { ok: true };
  }

  return { ok: true };
}

// /extend --from attachment requires at least one current-run attachment.
function evaluateExtendInputPreflight({ fromAttachment, attachmentCount } = {}) {
  if (fromAttachment && !(Number(attachmentCount) > 0)) {
    return {
      ok: false,
      code: 'EXTEND_REQUIRES_CURRENT_ATTACHMENT',
      message:
        'Cannot run /extend --from attachment without at least one attached source file. ' +
        'Attach a source document and retry.',
    };
  }
  return { ok: true };
}

// When a local agent exits but produces no candidate files, its stdout/stderr
// often explains why: it was blocked reading an attachment, or it is not
// authenticated. We classify that text so completion reports a precise,
// actionable error instead of a misleading "empty artifact" / cloud failure.
const LOCAL_AGENT_AUTH_PATTERNS = [
  /\bnot logged in\b/i,
  /\bplease log ?in\b/i,
  /\blog ?in (required|first)\b/i,
  /\blogin required\b/i,
  /\bauthenticat(e|ion) (is )?(required|needed|failed)\b/i,
  /\bunauthorized\b/i,
  /\binvalid api key\b/i,
  /\bsession (has )?expired\b/i,
  /\brun .*(login|auth)\b/i,
];

const LOCAL_AGENT_READ_BLOCK_PATTERNS = [
  /needs your approval/i,
  /permission to (use|read|access)/i,
  /outside (the |your )?(working|current) directory/i,
  /blocked from reading/i,
  /requires (your )?approval/i,
  /read tool .*(approval|permission)/i,
];

// Document/extend phases read their outputs back from disk, where the template or an
// earlier run already left IDEA.md, SPEC.md, ...: only files the agent wrote during this
// run count (2 s tolerance for filesystem timestamp rounding).
const FRESH_ARTIFACT_TOLERANCE_MS = 2000;

function isFreshLocalAgentArtifact(mtimeMs, runStartedAtMs) {
  if (!Number.isFinite(Number(runStartedAtMs))) return true;
  return Number(mtimeMs) >= Number(runStartedAtMs) - FRESH_ARTIFACT_TOLERANCE_MS;
}

// A local agent that exits non-zero without writing anything: report its own error
// (last stderr lines) instead of a misleading output-validation failure.
// With machine-readable output the agent's own error is a JSON event on stdout
// (Codex: turn.failed / error; Claude: a result with is_error), not on stderr.
function localAgentErrorFromJsonOutput(stdout) {
  let found = '';
  for (const line of String(stdout || '').split(/\r?\n/)) {
    const text = line.trim();
    if (!text.startsWith('{')) continue;
    let event;
    try {
      event = JSON.parse(text);
    } catch {
      continue;
    }
    if (event?.type === 'turn.failed' && event.error?.message) found = String(event.error.message);
    else if (event?.type === 'error' && event.message && !found) found = String(event.message);
    else if (event?.is_error && (event.result || event.error)) found = String(event.result || event.error);
  }
  return found.replace(/,\s*(url|cf-ray|request id):.*$/i, '').trim();
}

function describeFailedLocalAgentRun({ exitCode, stderr = '', stdout = '', executorLabel = 'Local agent' } = {}) {
  if (exitCode === 0 || exitCode === '0' || exitCode === null || exitCode === undefined) return null;
  const tail = [
    localAgentErrorFromJsonOutput(stdout),
    ...String(stderr || '')
      .split(/\r?\n/)
      .map((line) => line.trim())
      .filter((line) => line && !/^Reading prompt from stdin/i.test(line))
      .slice(-6),
  ]
    .filter(Boolean)
    .join(' | ');
  return {
    code: 'LOCAL_AGENT_EXITED_WITH_ERROR',
    message: `${executorLabel} exited with code ${exitCode} without writing any output` +
      (tail ? `: ${tail}` : '.'),
  };
}

function classifyBlockedLocalAgentOutput({ stdout = '', stderr = '' } = {}) {
  const text = `${String(stdout || '')}\n${String(stderr || '')}`;

  for (const pattern of LOCAL_AGENT_AUTH_PATTERNS) {
    const match = pattern.exec(text);
    if (match) {
      return {
        code: 'LOCAL_AGENT_AUTH_REQUIRED',
        message:
          'Local agent authentication is required. Run the Claude/Codex CLI login flow ' +
          'or configure the explicit local-agent auth environment.',
        evidence: match[0],
      };
    }
  }

  for (const pattern of LOCAL_AGENT_READ_BLOCK_PATTERNS) {
    const match = pattern.exec(text);
    if (match) {
      return {
        code: 'LOCAL_AGENT_BLOCKED_READ',
        message:
          'Local agent was blocked from reading a required source file (path outside its ' +
          'working directory or pending approval). The attachment must be materialized into ' +
          'the workspace before the agent runs.',
        evidence: match[0],
      };
    }
  }

  return null;
}

module.exports = {
  describeFailedLocalAgentRun,
  isFreshLocalAgentArtifact,
  buildCodexArgsForLocalAgent,
  classifyBlockedLocalAgentOutput,
  evaluateDocumentPhaseInputPreflight,
  evaluateExtendInputPreflight,
  isExtendAllowedOutput,
  isExtendAuditPath,
  extractCodexSandboxModeFromArgs,
  isCodexSandboxWriteCapable,
  isForbiddenCandidatePath,
  isDocumentPhase,
  isDocumentPhaseAllowedOutput,
  isDocumentPhaseCompanionOutput,
  documentPhaseCompanionTargets,
  documentPhaseRequiredOutputs,
  isWriteRequiredLocalAgentPhase,
  normalizeCodexSandboxMode,
  resolveCodexSandboxMode,
  assertLocalAgentWritePreflight,
  validateLocalAgentRequiredOutputs,
};
