const cp = require('child_process');

function normalizeExecutionPreference(value) {
  const raw = String(value || '').trim().toLowerCase();

  // Backward compatibility.
  if (raw === 'prefer_claude_code') return 'prefer_local_agent';
  if (raw === 'claude_code_only') return 'local_agent_only';

  const allowed = new Set([
    'auto',
    'cloud_only',
    'prefer_local_agent',
    'local_agent_only',
    'hybrid',
  ]);

  return allowed.has(raw) ? raw : 'auto';
}

function normalizeLocalAgentExecutor(value) {
  const raw = String(value || '').trim().toLowerCase();

  if (raw === 'claude') return 'claude_code';
  if (raw === 'codex') return 'gpt_codex';

  const allowed = new Set([
    'auto',
    'claude_code',
    'gpt_codex',
  ]);

  return allowed.has(raw) ? raw : 'auto';
}

function executionPreferenceRequestsLocalAgent(pref) {
  return new Set([
    'prefer_local_agent',
    'local_agent_only',
    'hybrid',
  ]).has(normalizeExecutionPreference(pref));
}

function localAgentSupportsPhase(executorId, phase, settings) {
  const normalized = normalizeLocalAgentExecutor(executorId);
  const p = String(phase || '').trim().toLowerCase();

  if (p === 'idea' || p === 'spec' || p === 'plan') {
    // Early Harper document phases use the local agent as a bounded document
    // actuator. CLike owns canonical validation; the agent only writes the
    // phase-owned Harper artifacts.
    return normalized === 'claude_code' || normalized === 'gpt_codex';
  }

  if (p === 'kit') {
    return normalized === 'claude_code' || normalized === 'gpt_codex';
  }

  if (p === 'eval') {
    // /eval uses the local agent only as a pre-pass hardener/diagnostic runner.
    // The canonical CLike EvalRunner remains the final evidence-based judge.
    return normalized === 'claude_code' || normalized === 'gpt_codex';
  }

  if (p === 'finalize') {
    // /finalize uses the local agent as the solution integration actuator.
    // The orchestrator owns the contract; the agent may patch the real workspace
    // only inside explicit solution write roots.
    return normalized === 'claude_code' || normalized === 'gpt_codex';
  }

  if (p === 'extend') {
    // /extend uses the local agent as a Harper documentation actuator.
    // It may patch only docs/harper planning artifacts, preserving existing REQs.
    return normalized === 'claude_code' || normalized === 'gpt_codex';
  }

  return false;
}

function getExecutorConfig(executorId, settings) {
  const normalized = normalizeLocalAgentExecutor(executorId);

  if (normalized === 'claude_code') {
    return {
      executorId: 'claude_code',
      enabled: !!settings.localAgentEnabled && !!settings.claudeCodeEnabled,
      label: 'Claude Code',
      command: settings.claudeCodeCommand,
      argsBeforePrompt: [],
      printModeFlag: settings.claudeCodePrintModeFlag || '-p',
      permissionMode: settings.claudeCodePermissionMode || 'acceptEdits',
      timeoutMinutes: settings.localAgentTimeoutMinutes || settings.claudeCodeTimeoutMinutes || 20,
      supports: {
        idea: true,
        spec: true,
        plan: true,
        kit: true,
        eval: true,
        finalize: true,
        extend: true,
        followUpKitPhases: false,
        nonInteractive: true,
        permissionMode: true,
        structuredSummary: false,
      },
    };
  }

  if (normalized === 'gpt_codex') {
    return {
      executorId: 'gpt_codex',
      enabled: !!settings.localAgentEnabled && !!settings.codexEnabled,
      label: 'GPT Codex',
      command: settings.codexCommand || 'codex',
      // Codex CLI non-interactive mode.
      argsBeforePrompt: ['exec'],
      printModeFlag: '',
      permissionMode: '',
      timeoutMinutes: settings.localAgentTimeoutMinutes || settings.codexTimeoutMinutes || 20,
      supports: {
        idea: true,
        spec: true,
        plan: true,
        kit: true,
        eval: true,
        finalize: true,
        extend: true,
        followUpKitPhases: false,
        nonInteractive: true,
        permissionMode: false,
        structuredSummary: false,
      },
    };
  }

  return {
    executorId: 'auto',
    enabled: false,
    label: 'auto',
    command: '',
    argsBeforePrompt: [],
    printModeFlag: '',
    permissionMode: '',
    timeoutMinutes: 20,
    supports: {
      kit: false,
      eval: false,
      followUpKitPhases: false,
      nonInteractive: false,
      permissionMode: false,
      structuredSummary: false,
    },
  };
}

function commandExists(command) {
  const cmd = String(command || '').trim();
  if (!cmd) return false;

  const probe = process.platform === 'win32'
    ? `where ${cmd}`
    : `command -v ${cmd}`;

  try {
    cp.execSync(probe, { stdio: 'ignore' });
    return true;
  } catch {
    return false;
  }
}

function detectLocalAgentAvailability(settings) {
  const claude = getExecutorConfig('claude_code', settings);
  const codex = getExecutorConfig('gpt_codex', settings);

  const claudeFound = claude.enabled ? commandExists(claude.command) : false;
  const codexFound = codex.enabled ? commandExists(codex.command) : false;

  return {
    claude_code: {
      enabled: claude.enabled,
      configured_command: claude.command,
      command_found: claudeFound,
      available: claudeFound,
    },
    gpt_codex: {
      enabled: codex.enabled,
      configured_command: codex.command,
      command_found: codexFound,
      available: codexFound,
    },
  };
}

function resolveSelectedLocalAgentExecutor(settings, requestedExecutor, phase) {
  const explicit = normalizeLocalAgentExecutor(requestedExecutor);
  const preferred = normalizeLocalAgentExecutor(settings.localAgentPreferredExecutor);
  const availability = detectLocalAgentAvailability(settings);

  const order = [];

  if (explicit !== 'auto') order.push(explicit);
  if (preferred !== 'auto' && !order.includes(preferred)) order.push(preferred);

  // Preserve old Claude path as the first auto fallback.
  if (!order.includes('claude_code')) order.push('claude_code');
  if (!order.includes('gpt_codex')) order.push('gpt_codex');

  for (const candidate of order) {
    const cfg = getExecutorConfig(candidate, settings);
    const available = !!availability?.[candidate]?.available;
    if (!cfg.enabled) continue;
    if (!available) continue;
    if (!localAgentSupportsPhase(candidate, phase, settings)) continue;
    return candidate;
  }

  return null;
}

// Cloud/gateway provider keys. Local agents authenticate via their own CLI
// login/session, so by default we do NOT forward these into the agent process.
const CLOUD_PROVIDER_ENV_KEYS = [
  'OPENAI_API_KEY',
  'ANTHROPIC_API_KEY',
  'OPENAI_PROJECT_ID',
  'OPENAI_ORG_ID',
];

function isTruthyEnvFlag(value) {
  const s = String(value == null ? '' : value).trim().toLowerCase();
  return s === '1' || s === 'true' || s === 'yes' || s === 'on';
}

// Build the environment for a spawned local agent. Inherits the standard shell
// environment (PATH, HOME, USER, SHELL, TMPDIR, TERM, XDG_*, etc.) so the CLI
// can find its own auth/session, but strips cloud provider API keys by default
// so local-agent execution never depends on (nor leaks) gateway cloud keys.
// Set CLIKE_LOCAL_AGENT_INHERIT_PROVIDER_ENV=true to opt back in.
function buildLocalAgentEnv(baseEnv, overrides = {}) {
  const source = baseEnv && typeof baseEnv === 'object' ? baseEnv : {};
  const env = { ...source };

  const inheritProviderEnv = isTruthyEnvFlag(
    source.CLIKE_LOCAL_AGENT_INHERIT_PROVIDER_ENV
  );
  if (!inheritProviderEnv) {
    for (const key of CLOUD_PROVIDER_ENV_KEYS) {
      delete env[key];
    }
  }

  // Keep CLI output machine-readable / non-interactive friendly.
  env.CLICOLOR = '0';
  env.NO_COLOR = '1';

  return { ...env, ...overrides };
}

function buildLocalAgentDisplayLabel(executorId) {
  const normalized = normalizeLocalAgentExecutor(executorId);
  if (normalized === 'claude_code') return 'Claude Code';
  if (normalized === 'gpt_codex') return 'GPT Codex';
  return 'Local Agent';
}

module.exports = {
  normalizeExecutionPreference,
  normalizeLocalAgentExecutor,
  executionPreferenceRequestsLocalAgent,
  resolveSelectedLocalAgentExecutor,
  getExecutorConfig,
  buildLocalAgentDisplayLabel,
  buildLocalAgentEnv,
  localAgentSupportsPhase,
  detectLocalAgentAvailability,
  commandExists,
  CLOUD_PROVIDER_ENV_KEYS,
};