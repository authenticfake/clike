const assert = require('assert');
const test = require('node:test');

const {
  buildCodexArgsForLocalAgent,
  extractCodexSandboxModeFromArgs,
  isForbiddenCandidatePath,
  resolveCodexSandboxMode,
  validateLocalAgentRequiredOutputs,
} = require('../local-agent-write-policy');

test('Codex kit launch adds a write-capable sandbox by default', () => {
  const result = buildCodexArgsForLocalAgent({
    argsBeforePrompt: ['exec'],
    phase: 'kit',
    reqId: 'REQ-002',
    configuredSandboxMode: 'auto',
    allowedWriteRoots: ['runs/kit/REQ-002/'],
  });

  assert.deepStrictEqual(result.args, ['exec', '--sandbox', 'workspace-write']);
  assert.strictEqual(result.sandboxMode, 'workspace-write');
  assert.strictEqual(extractCodexSandboxModeFromArgs(result.args), 'workspace-write');
});

test('Codex inspect-only launch may remain read-only', () => {
  const result = buildCodexArgsForLocalAgent({
    argsBeforePrompt: ['exec'],
    phase: 'extend',
    reqId: 'REQ-002',
    configuredSandboxMode: 'auto',
  });

  assert.deepStrictEqual(result.args, ['exec', '--sandbox', 'read-only']);
  assert.strictEqual(result.sandboxMode, 'read-only');
});

test('Codex read-only sandbox is rejected for write-required phases', () => {
  assert.throws(
    () => buildCodexArgsForLocalAgent({
      argsBeforePrompt: ['exec'],
      phase: 'kit',
      reqId: 'REQ-002',
      configuredSandboxMode: 'read-only',
      allowedWriteRoots: ['runs/kit/REQ-002/'],
    }),
    (error) => error.code === 'LOCAL_AGENT_WRITE_MODE_UNAVAILABLE'
  );
});

test('Codex invocation-provided read-only sandbox is rejected for kit', () => {
  assert.throws(
    () => buildCodexArgsForLocalAgent({
      argsBeforePrompt: ['exec', '--sandbox', 'read-only'],
      phase: 'kit',
      reqId: 'REQ-002',
      configuredSandboxMode: 'workspace-write',
      allowedWriteRoots: ['runs/kit/REQ-002/'],
    }),
    (error) => error.code === 'LOCAL_AGENT_WRITE_MODE_UNAVAILABLE'
  );
});

test('local-agent kit package-only artifacts are rejected', () => {
  const artifacts = [
    { path: 'runs/kit/REQ-002/docs/AGENT_EXECUTION_CONTEXT.json', content: '{}' },
    { path: 'runs/kit/REQ-002/docs/AGENT_PROMPT.md', content: 'prompt' },
    { path: 'runs/kit/REQ-002/docs/TARGET_CONTRACT.json', content: '{}' },
    { path: 'runs/kit/REQ-002/docs/FILE_REQUIREMENTS.json', content: '{}' },
  ];

  assert.throws(
    () => validateLocalAgentRequiredOutputs({
      phase: 'kit',
      reqId: 'REQ-002',
      artifacts,
    }),
    (error) =>
      error.code === 'LOCAL_AGENT_REQUIRED_OUTPUTS_MISSING' &&
      error.details.missing_required_roots.includes('runs/kit/REQ-002/src/') &&
      error.details.missing_required_roots.includes('runs/kit/REQ-002/test/') &&
      error.details.missing_required_roots.includes('runs/kit/REQ-002/ci/')
  );
});

test('local-agent kit artifacts missing one required root are rejected', () => {
  const artifacts = [
    { path: 'runs/kit/REQ-002/src/coffeebuddy/runtime/__init__.py', content: '' },
    { path: 'runs/kit/REQ-002/test/coffeebuddy/runtime/test_req.py', content: '' },
  ];

  assert.throws(
    () => validateLocalAgentRequiredOutputs({
      phase: 'kit',
      reqId: 'REQ-002',
      artifacts,
    }),
    (error) =>
      error.code === 'LOCAL_AGENT_REQUIRED_OUTPUTS_MISSING' &&
      error.details.missing_required_roots.includes('runs/kit/REQ-002/ci/')
  );
});

test('local-agent kit artifacts with src test and ci outputs are accepted', () => {
  const artifacts = [
    { path: 'runs/kit/REQ-002/src/coffeebuddy/runtime/__init__.py', content: '' },
    { path: 'runs/kit/REQ-002/test/coffeebuddy/runtime/test_req.py', content: '' },
    { path: 'runs/kit/REQ-002/ci/HOWTO.md', content: '' },
    { path: 'runs/kit/REQ-002/docs/RUNBOOK.md', content: '' },
  ];

  assert.deepStrictEqual(
    validateLocalAgentRequiredOutputs({
      phase: 'kit',
      reqId: 'REQ-002',
      artifacts,
    }),
    { ok: true, missing_required_roots: [] }
  );
});

test('canonical workspace roots remain forbidden candidate outputs', () => {
  assert.strictEqual(isForbiddenCandidatePath('src/app.py'), true);
  assert.strictEqual(isForbiddenCandidatePath('test/test_app.py'), true);
  assert.strictEqual(isForbiddenCandidatePath('tests/test_app.py'), true);
  assert.strictEqual(isForbiddenCandidatePath('docs/harper/PLAN.md'), true);
  assert.strictEqual(isForbiddenCandidatePath('.git/config'), true);
  assert.strictEqual(isForbiddenCandidatePath('runs/kit/REQ-002/src/app.py'), false);

  assert.throws(
    () => validateLocalAgentRequiredOutputs({
      phase: 'kit',
      reqId: 'REQ-002',
      artifacts: [{ path: 'src/app.py', content: '' }],
    }),
    (error) => error.code === 'LOCAL_AGENT_FORBIDDEN_OUTPUT_PATH'
  );
});

test('Codex sandbox auto resolves by phase', () => {
  assert.strictEqual(
    resolveCodexSandboxMode({ phase: 'kit', configuredSandboxMode: 'auto' }),
    'workspace-write'
  );
  assert.strictEqual(
    resolveCodexSandboxMode({ phase: 'extend', configuredSandboxMode: 'auto' }),
    'read-only'
  );
});
