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

test('local-agent idea allows only docs/harper/IDEA.md', () => {
  assert.deepStrictEqual(
    validateLocalAgentRequiredOutputs({
      phase: 'idea',
      artifacts: [{ path: 'docs/harper/IDEA.md', content: '# IDEA — X' }],
    }),
    { ok: true, missing_required_roots: [] }
  );
});

test('local-agent spec allows only docs/harper/SPEC.md', () => {
  assert.deepStrictEqual(
    validateLocalAgentRequiredOutputs({
      phase: 'spec',
      artifacts: [{ path: 'docs/harper/SPEC.md', content: '# SPEC — X' }],
    }),
    { ok: true, missing_required_roots: [] }
  );
});

test('local-agent plan allows PLAN.md, plan.json, and lane guides', () => {
  assert.deepStrictEqual(
    validateLocalAgentRequiredOutputs({
      phase: 'plan',
      artifacts: [
        { path: 'docs/harper/PLAN.md', content: '# PLAN — X' },
        { path: 'docs/harper/plan.json', content: '{}' },
        { path: 'docs/harper/lane-guides/python.md', content: '# Lane' },
      ],
    }),
    { ok: true, missing_required_roots: [] }
  );
});

test('local-agent idea rejects unrelated docs/harper writes', () => {
  assert.throws(
    () => validateLocalAgentRequiredOutputs({
      phase: 'idea',
      artifacts: [
        { path: 'docs/harper/IDEA.md', content: '# IDEA — X' },
        { path: 'docs/harper/SPEC.md', content: '# SPEC — X' },
      ],
    }),
    (error) => error.code === 'LOCAL_AGENT_FORBIDDEN_OUTPUT_PATH'
  );
});

test('local-agent plan rejects an unrelated docs/harper file', () => {
  assert.throws(
    () => validateLocalAgentRequiredOutputs({
      phase: 'plan',
      artifacts: [
        { path: 'docs/harper/PLAN.md', content: '# PLAN — X' },
        { path: 'docs/harper/plan.json', content: '{}' },
        { path: 'docs/harper/NOTES.md', content: 'notes' },
      ],
    }),
    (error) => error.code === 'LOCAL_AGENT_FORBIDDEN_OUTPUT_PATH'
  );
});

test('lane-guides are allowed only for /plan, rejected for /idea and /spec', () => {
  // /plan accepts a lane guide alongside its canonical outputs.
  assert.deepStrictEqual(
    validateLocalAgentRequiredOutputs({
      phase: 'plan',
      artifacts: [
        { path: 'docs/harper/PLAN.md', content: '# PLAN — X' },
        { path: 'docs/harper/plan.json', content: '{}' },
        { path: 'docs/harper/lane-guides/sql.md', content: '# Lane' },
      ],
    }),
    { ok: true, missing_required_roots: [] }
  );

  // /idea and /spec must reject lane-guides as a forbidden docs/harper write.
  for (const [phase, canonical] of [
    ['idea', 'docs/harper/IDEA.md'],
    ['spec', 'docs/harper/SPEC.md'],
  ]) {
    assert.throws(
      () => validateLocalAgentRequiredOutputs({
        phase,
        artifacts: [
          { path: canonical, content: '# X' },
          { path: 'docs/harper/lane-guides/python.md', content: '# Lane' },
        ],
      }),
      (error) => error.code === 'LOCAL_AGENT_FORBIDDEN_OUTPUT_PATH'
    );
  }
});

test('/extend allows IDEA/SPEC/PLAN/plan.json/lane-guides/EXTEND audit', () => {
  assert.deepStrictEqual(
    validateLocalAgentRequiredOutputs({
      phase: 'extend',
      artifacts: [
        { path: 'docs/harper/IDEA.md', content: '# IDEA' },
        { path: 'docs/harper/SPEC.md', content: '# SPEC' },
        { path: 'docs/harper/PLAN.md', content: '# PLAN' },
        { path: 'docs/harper/plan.json', content: '{}' },
        { path: 'docs/harper/lane-guides/python.md', content: '# Lane' },
        { path: 'docs/harper/EXTEND_2026-06-08_REQ-2_REQ-3.md', content: '# audit' },
      ],
    }),
    { ok: true, missing_required_roots: [] }
  );
});

test('/extend rejects AGENT_EXTEND_* and arbitrary docs/harper files', () => {
  for (const bad of ['docs/harper/AGENT_EXTEND_CONTEXT.json', 'docs/harper/NOTES.md']) {
    assert.throws(
      () => validateLocalAgentRequiredOutputs({
        phase: 'extend',
        artifacts: [
          { path: 'docs/harper/PLAN.md', content: '# PLAN' },
          { path: 'docs/harper/plan.json', content: '{}' },
          { path: 'docs/harper/EXTEND_2026-06-08_REQ-2_REQ-2.md', content: '# audit' },
          { path: bad, content: 'x' },
        ],
      }),
      (error) => error.code === 'LOCAL_AGENT_FORBIDDEN_OUTPUT_PATH'
    );
  }
});

test('/extend requires PLAN.md, plan.json, and EXTEND audit report', () => {
  assert.throws(
    () => validateLocalAgentRequiredOutputs({
      phase: 'extend',
      artifacts: [
        { path: 'docs/harper/PLAN.md', content: '# PLAN' },
        { path: 'docs/harper/plan.json', content: '{}' },
        // missing EXTEND_*.md audit report
      ],
    }),
    (error) =>
      error.code === 'LOCAL_AGENT_REQUIRED_OUTPUTS_MISSING' &&
      error.details.missing_required_outputs.some((p) => p.startsWith('docs/harper/EXTEND_'))
  );
});

test('/extend blocks src/test writes', () => {
  for (const bad of ['src/app.py', 'test/x.py', 'tests/y.py']) {
    assert.throws(
      () => validateLocalAgentRequiredOutputs({
        phase: 'extend',
        artifacts: [
          { path: 'docs/harper/PLAN.md', content: '# PLAN' },
          { path: 'docs/harper/plan.json', content: '{}' },
          { path: 'docs/harper/EXTEND_2026-06-08_REQ-2_REQ-2.md', content: '# audit' },
          { path: bad, content: 'x' },
        ],
      }),
      (error) => error.code === 'LOCAL_AGENT_FORBIDDEN_OUTPUT_PATH'
    );
  }
});

test('local-agent document phases still block src/test/.git writes', () => {
  for (const phase of ['idea', 'spec', 'plan']) {
    assert.throws(
      () => validateLocalAgentRequiredOutputs({
        phase,
        artifacts: [{ path: 'src/app.py', content: '' }],
      }),
      (error) => error.code === 'LOCAL_AGENT_FORBIDDEN_OUTPUT_PATH'
    );
  }
});

test('local-agent document phases require their canonical output', () => {
  assert.throws(
    () => validateLocalAgentRequiredOutputs({
      phase: 'plan',
      artifacts: [{ path: 'docs/harper/PLAN.md', content: '# PLAN — X' }],
    }),
    (error) => error.code === 'LOCAL_AGENT_REQUIRED_OUTPUTS_MISSING'
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
