const assert = require('assert');
const test = require('node:test');

const {
  buildLocalAgentEnv,
  CLOUD_PROVIDER_ENV_KEYS,
} = require('../local-agent-executors');

const {
  classifyBlockedLocalAgentOutput,
} = require('../local-agent-write-policy');

// --- buildLocalAgentEnv: local agents must not depend on cloud provider keys ---

test('local-agent env strips cloud provider keys by default', () => {
  const base = {
    PATH: '/usr/bin:/bin',
    HOME: '/home/dev',
    OPENAI_API_KEY: 'sk-openai',
    ANTHROPIC_API_KEY: 'sk-anthropic',
    OPENAI_PROJECT_ID: 'proj_123',
    OPENAI_ORG_ID: 'org_123',
  };
  const env = buildLocalAgentEnv(base);
  for (const key of CLOUD_PROVIDER_ENV_KEYS) {
    assert.ok(!(key in env), `${key} must be stripped by default`);
  }
});

test('local-agent env preserves PATH and HOME (CLI auth/session)', () => {
  const env = buildLocalAgentEnv({ PATH: '/usr/bin:/bin', HOME: '/home/dev', USER: 'dev', SHELL: '/bin/zsh' });
  assert.strictEqual(env.PATH, '/usr/bin:/bin');
  assert.strictEqual(env.HOME, '/home/dev');
  assert.strictEqual(env.USER, 'dev');
  assert.strictEqual(env.SHELL, '/bin/zsh');
  // Non-interactive friendly output flags are set.
  assert.strictEqual(env.CLICOLOR, '0');
  assert.strictEqual(env.NO_COLOR, '1');
});

test('local-agent env does not require cloud keys to be present', () => {
  // No provider keys at all -> still produces a usable env (no throw).
  const env = buildLocalAgentEnv({ PATH: '/usr/bin', HOME: '/home/dev' });
  assert.strictEqual(env.PATH, '/usr/bin');
  assert.ok(!('OPENAI_API_KEY' in env));
  assert.ok(!('ANTHROPIC_API_KEY' in env));
});

test('local-agent env keeps provider keys only when explicitly opted in', () => {
  const base = {
    PATH: '/usr/bin',
    ANTHROPIC_API_KEY: 'sk-anthropic',
    CLIKE_LOCAL_AGENT_INHERIT_PROVIDER_ENV: 'true',
  };
  const env = buildLocalAgentEnv(base);
  assert.strictEqual(env.ANTHROPIC_API_KEY, 'sk-anthropic');
});

// --- classifyBlockedLocalAgentOutput: blocked/auth detection ---

test('login/auth output maps to LOCAL_AGENT_AUTH_REQUIRED', () => {
  const cases = [
    'Error: not logged in. Please run claude login.',
    'Authentication required to use this command.',
    'unauthorized: invalid api key',
  ];
  for (const stderr of cases) {
    const result = classifyBlockedLocalAgentOutput({ stdout: '', stderr });
    assert.ok(result, `expected classification for: ${stderr}`);
    assert.strictEqual(result.code, 'LOCAL_AGENT_AUTH_REQUIRED');
    assert.match(result.message, /authentication is required/i);
  }
});

test('read-permission output maps to LOCAL_AGENT_BLOCKED_READ', () => {
  const stdout =
    "I'm blocked from reading the required source attachment. The Read tool needs your " +
    "approval for the path; it's outside the working directory.";
  const result = classifyBlockedLocalAgentOutput({ stdout, stderr: '' });
  assert.ok(result);
  assert.strictEqual(result.code, 'LOCAL_AGENT_BLOCKED_READ');
});

test('benign output is not misclassified as blocked', () => {
  const result = classifyBlockedLocalAgentOutput({
    stdout: 'Wrote docs/harper/IDEA.md successfully.',
    stderr: '',
  });
  assert.strictEqual(result, null);
});
