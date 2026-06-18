const cp = require('child_process');
const fs = require('fs');

function normalizeExecutionPreference(value) {
  const raw = String(value || '').trim().toLowerCase();

  // Backward compatibility. Canonical modes are cloud_only, prefer_local_agent
  // and local_agent_only. Legacy values are mapped deterministically so old
  // persisted settings keep working without exposing ambiguous modes.
  if (raw === 'prefer_claude_code') return 'prefer_local_agent';
  if (raw === 'claude_code_only') return 'local_agent_only';
  if (raw === 'auto') return 'cloud_only';
  if (raw === 'hybrid') return 'prefer_local_agent';

  const allowed = new Set([
    'cloud_only',
    'prefer_local_agent',
    'local_agent_only',
  ]);

  return allowed.has(raw) ? raw : 'cloud_only';
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

  if (p === 'free' || p === 'chat' || p === 'coding') {
    // Standalone chat (Q&A) and coding generation are not part of the Harper
    // REQ pipeline: any installed local agent can serve them.
    return normalized === 'claude_code' || normalized === 'gpt_codex';
  }

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
      model: String(settings.claudeCodeModel || '').trim(),
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
      model: String(settings.codexModel || '').trim(),
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

// ---------------------------------------------------------------------------
// Cross-platform local-agent command resolution & execution.
//
// On Windows, npm-installed CLIs expose `<name>.cmd` / `<name>.ps1` (and
// sometimes `<name>.exe`). `<name>.cmd` cannot be launched with `spawn(..., {
// shell:false })` directly, and `<name>.ps1` is frequently blocked by the
// PowerShell ExecutionPolicy. We therefore resolve a concrete executable
// (preferring `.cmd` > `.exe` > `.bat`, never `.ps1`) and run `.cmd`/`.bat`
// through `cmd.exe /d /s /c`. On macOS/Linux the command runs directly.
// ---------------------------------------------------------------------------

const WINDOWS_EXECUTABLE_PREFERENCE = ['.cmd', '.exe', '.bat'];
const VERSION_CHECK_TTL_MS = 15000;
const _versionCheckCache = new Map();

function isWindowsPlatform(platform) {
  return String(platform || process.platform) === 'win32';
}

function _defaultLocalAgentLog(line) {
  try { console.log(`[CLike][local-agent] ${line}`); } catch { /* noop */ }
}

function getCommandExtension(command) {
  const m = String(command || '').toLowerCase().match(/\.(cmd|bat|exe|ps1)$/);
  return m ? `.${m[1]}` : '';
}

// Pure: pick the safest candidate from raw `where <cmd>` output, preferring
// .cmd > .exe > .bat and never .ps1. Returns '' when no acceptable match.
function pickWindowsPathCandidate(whereOutput) {
  const lines = String(whereOutput || '')
    .split(/\r?\n/)
    .map((l) => l.trim())
    .filter(Boolean);

  for (const ext of WINDOWS_EXECUTABLE_PREFERENCE) {
    const hit = lines.find((l) => l.toLowerCase().endsWith(ext));
    if (hit) return hit;
  }
  return '';
}

// Pure: decide how to spawn an already-resolved command on a given platform.
// Windows .cmd/.bat are executed through cmd.exe; .exe and POSIX commands run
// directly. Returns { file, args } to pass to child_process.spawn.
function buildLocalAgentSpawn(command, args, platform) {
  const cmd = String(command || '');
  const extraArgs = Array.isArray(args) ? args.slice() : [];

  if (isWindowsPlatform(platform)) {
    const ext = getCommandExtension(cmd);
    if (ext === '.cmd' || ext === '.bat') {
      return { file: 'cmd.exe', args: ['/d', '/s', '/c', cmd, ...extraArgs] };
    }
    return { file: cmd, args: extraArgs };
  }

  return { file: cmd, args: extraArgs };
}

// Resolve the concrete command to spawn. On POSIX the command is used as-is
// (PATH resolution happens at spawn time). On Windows we resolve to a concrete
// executable, never returning a `.ps1` (returns '' when only `.ps1` exists).
function resolveLocalAgentCommandPath(command, options = {}) {
  const platform = options.platform || process.platform;
  const log = typeof options.log === 'function' ? options.log : _defaultLocalAgentLog;
  const raw = String(command || '').trim();
  if (!raw || !isWindowsPlatform(platform)) return raw;

  const ext = getCommandExtension(raw);
  const looksAbsolute = /[\\/]/.test(raw) || /^[a-zA-Z]:/.test(raw);

  // Explicit .ps1 → never run it; redirect to a sibling .cmd/.exe/.bat.
  if (ext === '.ps1') {
    const base = raw.slice(0, -'.ps1'.length);
    for (const e of WINDOWS_EXECUTABLE_PREFERENCE) {
      const candidate = base + e;
      try { if (fs.existsSync(candidate)) { log(`resolved ${raw} -> ${candidate}`); return candidate; } } catch { /* ignore */ }
    }
    log(`refusing .ps1 (ExecutionPolicy risk) and no sibling .cmd/.exe/.bat for ${raw}`);
    return '';
  }

  // Explicit executable extension → validate (for absolute) and use as-is.
  if (ext) {
    if (looksAbsolute) {
      try { if (!fs.existsSync(raw)) log(`configured path does not exist: ${raw}`); } catch { /* ignore */ }
    }
    return raw;
  }

  // Absolute path without extension → try known executable extensions.
  if (looksAbsolute) {
    for (const e of WINDOWS_EXECUTABLE_PREFERENCE) {
      const candidate = raw + e;
      try { if (fs.existsSync(candidate)) { log(`resolved ${raw} -> ${candidate}`); return candidate; } } catch { /* ignore */ }
    }
    log(`no executable extension found for absolute path ${raw}`);
    return raw;
  }

  // Bare command name → resolve from PATH preferring .cmd.
  try {
    const out = cp.execSync(`where ${raw}`, { stdio: ['ignore', 'pipe', 'ignore'] }).toString();
    const picked = pickWindowsPathCandidate(out);
    if (picked) {
      log(`PATH candidates for "${raw}": [${out.trim().split(/\r?\n/).map((s) => s.trim()).filter(Boolean).join(', ')}] -> ${picked}`);
      return picked;
    }
    log(`no acceptable PATH candidate for "${raw}" (output: ${out.trim() || 'empty'})`);
  } catch {
    log(`'where ${raw}' found no candidates`);
  }
  return raw;
}

// Verify availability by actually running `<command> --version` through the
// same resolution/wrapper that real execution will use. Results are cached
// briefly to avoid repeated process spawns within a single request.
function runLocalAgentVersionCheck(command, options = {}) {
  const platform = options.platform || process.platform;
  const log = typeof options.log === 'function' ? options.log : _defaultLocalAgentLog;
  const timeout = Number(options.timeoutMs || 7000);
  const raw = String(command || '').trim();

  const cacheKey = `${platform}::${raw}`;
  const cached = _versionCheckCache.get(cacheKey);
  if (cached && (Date.now() - cached.ts) < VERSION_CHECK_TTL_MS) {
    return cached.result;
  }

  const resolved = resolveLocalAgentCommandPath(raw, { platform, log });
  if (!resolved) {
    const result = { ok: false, resolved: '', exitCode: null, stderr: '', file: '', args: [] };
    _versionCheckCache.set(cacheKey, { ts: Date.now(), result });
    return result;
  }

  const { file, args } = buildLocalAgentSpawn(resolved, ['--version'], platform);

  let result;
  try {
    const res = cp.spawnSync(file, args, { timeout, encoding: 'utf8', windowsHide: true });
    const exitCode = res.status;
    const stderrHead = String(res.stderr || '')
      .split(/\r?\n/).filter(Boolean).slice(0, 3).join(' | ');
    const ok = !res.error && exitCode === 0;
    log(
      `version-check platform=${platform} invoked="${file} ${args.join(' ')}" ` +
      `exit=${exitCode == null ? 'null' : exitCode} ok=${ok}` +
      `${stderrHead ? ` stderr="${stderrHead}"` : ''}` +
      `${res.error ? ` error=${res.error.code || res.error.message}` : ''}`
    );
    result = { ok, resolved, exitCode, stderr: stderrHead, file, args };
  } catch (e) {
    log(`version-check failed for "${raw}": ${e && e.message}`);
    result = { ok: false, resolved, exitCode: null, stderr: '', file, args };
  }

  _versionCheckCache.set(cacheKey, { ts: Date.now(), result });
  return result;
}

function commandExists(command, options = {}) {
  const cmd = String(command || '').trim();
  if (!cmd) return false;
  const platform = options.platform || process.platform;

  // Windows: existence (`where`) is not enough — a `.cmd` cannot be spawned
  // directly and `.ps1` is often blocked. Verify by actually running --version
  // through the resolution/wrapper used for real execution.
  if (isWindowsPlatform(platform)) {
    return runLocalAgentVersionCheck(cmd, options).ok;
  }

  // POSIX: PATH resolution via `command -v` (fast, preserves prior behavior).
  try {
    cp.execSync(`command -v ${cmd}`, { stdio: 'ignore' });
    return true;
  } catch {
    return false;
  }
}

function detectLocalAgentAvailability(settings, log) {
  const claude = getExecutorConfig('claude_code', settings);
  const codex = getExecutorConfig('gpt_codex', settings);
  const platform = process.platform;
  const logFn = typeof log === 'function' ? log : _defaultLocalAgentLog;

  function probe(cfg) {
    if (!cfg.enabled) return { resolved: '', ok: false };
    if (isWindowsPlatform(platform)) {
      const r = runLocalAgentVersionCheck(cfg.command, { platform, log: logFn });
      return { resolved: r.resolved, ok: r.ok };
    }
    return { resolved: cfg.command, ok: commandExists(cfg.command, { platform }) };
  }

  const claudeProbe = probe(claude);
  const codexProbe = probe(codex);

  logFn(
    `availability platform=${platform} ` +
    `claude(enabled=${claude.enabled} cmd="${claude.command}" resolved="${claudeProbe.resolved}" available=${claudeProbe.ok}) ` +
    `codex(enabled=${codex.enabled} cmd="${codex.command}" resolved="${codexProbe.resolved}" available=${codexProbe.ok})`
  );

  return {
    claude_code: {
      enabled: claude.enabled,
      configured_command: claude.command,
      resolved_command: claudeProbe.resolved,
      command_found: claudeProbe.ok,
      available: claudeProbe.ok,
    },
    gpt_codex: {
      enabled: codex.enabled,
      configured_command: codex.command,
      resolved_command: codexProbe.resolved,
      command_found: codexProbe.ok,
      available: codexProbe.ok,
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

// Build the CLI args that pin the model for a local-agent invocation. Returns
// an empty array when no model is configured (the CLI then uses its own default).
// Claude and Codex both accept `--model <id>` (Codex also `-m`). For Claude an
// alias like 'opus'/'sonnet' resolves to the latest model of that tier.
function buildLocalAgentModelArgs(executorId, executorConfig) {
  const model = String((executorConfig && executorConfig.model) || '').trim();
  if (!model) return [];

  const normalized = normalizeLocalAgentExecutor(executorId);
  if (normalized === 'claude_code' || normalized === 'gpt_codex') {
    return ['--model', model];
  }
  return [];
}

// Parse the single-result JSON envelope emitted by `claude -p --output-format json`.
// Returns the parsed object (which exposes `result`, `model`, `usage`, ...) or
// null when stdout is not a JSON object, so callers can fall back to raw stdout.
function parseClaudeResultEnvelope(stdout) {
  const text = String(stdout || '').trim();
  if (!text.startsWith('{')) return null;
  try {
    const parsed = JSON.parse(text);
    return parsed && typeof parsed === 'object' && !Array.isArray(parsed) ? parsed : null;
  } catch {
    return null;
  }
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
  buildLocalAgentModelArgs,
  parseClaudeResultEnvelope,
  buildLocalAgentDisplayLabel,
  buildLocalAgentEnv,
  localAgentSupportsPhase,
  detectLocalAgentAvailability,
  commandExists,
  buildLocalAgentSpawn,
  pickWindowsPathCandidate,
  resolveLocalAgentCommandPath,
  runLocalAgentVersionCheck,
  CLOUD_PROVIDER_ENV_KEYS,
};