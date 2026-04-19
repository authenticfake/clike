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

  if (p === 'kit') {
    return normalized === 'claude_code' || normalized === 'gpt_codex';
  }

  if (p === 'eval') {
    // /eval uses the local agent only as a pre-pass hardener/diagnostic runner.
    // The canonical CLike EvalRunner remains the final evidence-based judge.
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
        kit: true,
        eval: true,
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
        kit: true,
        eval: true,
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
  localAgentSupportsPhase,
  detectLocalAgentAvailability,
  commandExists,
};