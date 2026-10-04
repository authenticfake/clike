const assert = require('assert');
const test = require('node:test');
const cp = require('child_process');

const {
  normalizeExecutionPreference,
  reconcileExecutionPreference,
  resolveSelectedLocalAgentExecutor,
} = require('../local-agent-executors');

// --- reconcileExecutionPreference: seed saved state against the canonical set ---
test('reconcile keeps canonical values and maps legacy backward-compat values', () => {
  assert.strictEqual(reconcileExecutionPreference('cloud_only', 'local_agent_only'), 'cloud_only');
  assert.strictEqual(reconcileExecutionPreference('prefer_local_agent', 'local_agent_only'), 'prefer_local_agent');
  assert.strictEqual(reconcileExecutionPreference('local_agent_only', 'cloud_only'), 'local_agent_only');
  assert.strictEqual(reconcileExecutionPreference('claude_code_only', 'cloud_only'), 'local_agent_only');
  assert.strictEqual(reconcileExecutionPreference('prefer_claude_code', 'cloud_only'), 'prefer_local_agent');
});

test('reconcile falls back to the default for removed/empty/unknown values', () => {
  // Removed modes and empty/unknown persisted values must NOT silently route to
  // cloud; they fall back to the configured default.
  assert.strictEqual(reconcileExecutionPreference('auto', 'local_agent_only'), 'local_agent_only');
  assert.strictEqual(reconcileExecutionPreference('hybrid', 'local_agent_only'), 'local_agent_only');
  assert.strictEqual(reconcileExecutionPreference('', 'local_agent_only'), 'local_agent_only');
  assert.strictEqual(reconcileExecutionPreference(undefined, 'local_agent_only'), 'local_agent_only');
  assert.strictEqual(reconcileExecutionPreference('garbage', 'local_agent_only'), 'local_agent_only');
});

// --- DEFECT 4: execution-mode normalization at the boundary ---
test('execution preference normalization maps legacy values to canonical modes', () => {
  assert.strictEqual(normalizeExecutionPreference('auto'), 'cloud_only');
  assert.strictEqual(normalizeExecutionPreference('hybrid'), 'prefer_local_agent');
  assert.strictEqual(normalizeExecutionPreference('prefer_claude_code'), 'prefer_local_agent');
  assert.strictEqual(normalizeExecutionPreference('claude_code_only'), 'local_agent_only');
});

test('execution preference normalization passes through canonical modes and defaults to cloud_only', () => {
  for (const mode of ['cloud_only', 'prefer_local_agent', 'local_agent_only']) {
    assert.strictEqual(normalizeExecutionPreference(mode), mode);
  }
  assert.strictEqual(normalizeExecutionPreference('garbage'), 'cloud_only');
  assert.strictEqual(normalizeExecutionPreference(''), 'cloud_only');
});

// --- DEFECT 1: an installed Claude CLI is a first-class local executor ---
// resolveSelectedLocalAgentExecutor probes the system via child_process at
// call time, so we stub child_process to simulate which CLIs are installed.
// Both probe paths are covered: POSIX (`sh -c 'command -v "$1"'`) and Windows
// (`where <cmd>` + `<cmd> --version`), so the tests are platform independent.
function withInstalledCommands(installed, fn) {
  const { resetLocalAgentProbeCache } = require('../local-agent-executors');
  const original = { execFileSync: cp.execFileSync, spawnSync: cp.spawnSync };
  const isInstalled = (value) => installed.some((name) => {
    const v = String(value || '').toLowerCase();
    return v === name || v.endsWith(`/${name}`) || v.endsWith(`\\${name}.cmd`) || v.endsWith(`\\${name}`);
  });
  cp.execFileSync = (file, args = []) => {
    const probed = String(args.length ? args[args.length - 1] : file);
    if (!isInstalled(probed)) throw new Error(`command not found: ${probed}`);
    // `where` output on Windows, ignored by the POSIX probe
    return Buffer.from(String(file) === 'where' ? `C:\\tools\\${probed}.cmd\r\n` : '');
  };
  cp.spawnSync = (file, args = []) => {
    const ok = [file, ...args].some(isInstalled);
    return ok ? { status: 0, stdout: '1.0.0', stderr: '' } : { status: null, error: Object.assign(new Error('ENOENT'), { code: 'ENOENT' }) };
  };
  resetLocalAgentProbeCache();
  try {
    return fn();
  } finally {
    cp.execFileSync = original.execFileSync;
    cp.spawnSync = original.spawnSync;
    resetLocalAgentProbeCache();
  }
}

const claudeAndCodexEnabled = {
  localAgentEnabled: true,
  claudeCodeEnabled: true,
  claudeCodeCommand: 'claude',
  codexEnabled: true,
  codexCommand: 'codex',
  localAgentPreferredExecutor: 'auto',
};

test('agent only resolves claude_code when only the claude CLI is installed', () => {
  withInstalledCommands(['claude'], () => {
    assert.strictEqual(
      resolveSelectedLocalAgentExecutor(claudeAndCodexEnabled, 'auto', 'free'),
      'claude_code'
    );
  });
});

test('prefer agent resolves claude_code for harper phases when only claude is installed', () => {
  withInstalledCommands(['claude'], () => {
    assert.strictEqual(
      resolveSelectedLocalAgentExecutor(claudeAndCodexEnabled, 'auto', 'spec'),
      'claude_code'
    );
  });
});

test('resolver returns null when no local agent CLI is installed', () => {
  withInstalledCommands([], () => {
    assert.strictEqual(
      resolveSelectedLocalAgentExecutor(claudeAndCodexEnabled, 'auto', 'free'),
      null
    );
  });
});

test('explicitly disabled claude is not selected even when its CLI is installed', () => {
  const claudeDisabled = { ...claudeAndCodexEnabled, claudeCodeEnabled: false };
  withInstalledCommands(['claude'], () => {
    // Codex is enabled but not installed, claude is installed but disabled.
    assert.strictEqual(
      resolveSelectedLocalAgentExecutor(claudeDisabled, 'auto', 'free'),
      null
    );
  });
});
