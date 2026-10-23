const assert = require('assert');
const test = require('node:test');

const {
  describeInterruptedLocalAgentRun,
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

  assert.deepStrictEqual(result.args, ['exec', '--sandbox', 'workspace-write', '--skip-git-repo-check']);
  assert.strictEqual(result.sandboxMode, 'workspace-write');
  assert.strictEqual(extractCodexSandboxModeFromArgs(result.args), 'workspace-write');
});

test('Codex auto stays read-only for a launch outside the Harper phases', () => {
  const result = buildCodexArgsForLocalAgent({
    argsBeforePrompt: ['exec'],
    phase: 'chat',
    reqId: 'REQ-002',
    configuredSandboxMode: 'auto',
  });

  assert.deepStrictEqual(result.args, ['exec', '--sandbox', 'read-only', '--skip-git-repo-check']);
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
    { path: 'runs/kit/REQ-002/ci/LTC.json', content: '{}' },
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

test('Codex sandbox auto resolves by phase: every Harper phase writes', () => {
  for (const phase of ['idea', 'spec', 'plan', 'kit', 'eval', 'finalize', 'extend']) {
    assert.strictEqual(
      resolveCodexSandboxMode({ phase, configuredSandboxMode: 'auto' }),
      'workspace-write',
      phase
    );
  }
  assert.strictEqual(
    resolveCodexSandboxMode({ phase: 'chat', configuredSandboxMode: 'auto' }),
    'read-only'
  );
});

test('Codex read-only sandbox is rejected for document phases too', () => {
  for (const phase of ['idea', 'spec', 'plan', 'extend']) {
    assert.throws(
      () => buildCodexArgsForLocalAgent({
        argsBeforePrompt: ['exec'],
        phase,
        reqId: 'SOLUTION',
        configuredSandboxMode: 'read-only',
      }),
      (error) => error.code === 'LOCAL_AGENT_WRITE_MODE_UNAVAILABLE',
      phase
    );
  }
});

test('lane guides must be Markdown, as the orchestrator accepts them (B12)', () => {
  const policy = require('../local-agent-write-policy');
  const check = policy.isDocumentPhaseAllowedOutput || null;
  if (!check) return;
  assert.equal(check('plan', 'docs/harper/lane-guides/python.md'), true);
  assert.equal(check('plan', 'docs/harper/lane-guides/run.sh'), false);
});

// BMAD companion documents of the local document phases. The contracts mirror
// orchestrator/methodologies/bmad/manifest.json (sample project on PostgreSQL).
const bmadPolicy = require('../local-agent-write-policy');

const SPEC_PM_CONTRACT = {
  methodology: 'bmad',
  agent: 'pm',
  required_outputs: [
    'docs/harper/SPEC.md',
    'docs/harper/bmad/spec/PRD.md',
    'docs/harper/bmad/spec/EPICS.md',
  ],
  allowed_optional_output_globs: ['docs/harper/bmad/spec/**'],
  forbidden_output_globs: ['docs/harper/PLAN.md', 'docs/harper/plan.json', 'src/**', 'test/**', 'tests/**'],
};

const SPEC_UX_CONTRACT = {
  methodology: 'bmad',
  agent: 'ux',
  required_outputs: ['docs/harper/ux/DESIGN.md', 'docs/harper/ux/USER_JOURNEYS.md'],
  allowed_optional_output_globs: ['docs/harper/ux/**'],
  forbidden_output_globs: ['docs/harper/SPEC.md', 'docs/harper/PLAN.md', 'docs/harper/plan.json', 'src/**'],
};

const PLAN_ARCHITECT_CONTRACT = {
  methodology: 'bmad',
  agent: 'architect',
  required_outputs: [
    'docs/harper/PLAN.md',
    'docs/harper/plan.json',
    'docs/harper/lane-guides/**',
    'docs/harper/bmad/architecture/ARCHITECTURE.md',
  ],
  allowed_optional_output_globs: ['docs/harper/bmad/architecture/**'],
  forbidden_output_globs: ['docs/harper/IDEA.md', 'docs/harper/SPEC.md', 'src/**'],
};

const PG = '# PRD\n\nOrders are stored in PostgreSQL 16 (schema `orders`).\n';

test('BMAD spec/pm: SPEC.md plus companions are accepted', () => {
  const result = bmadPolicy.validateLocalAgentRequiredOutputs({
    phase: 'spec',
    outputContract: SPEC_PM_CONTRACT,
    artifacts: [
      { path: 'docs/harper/SPEC.md', content: '# SPEC' },
      { path: 'docs/harper/bmad/spec/PRD.md', content: PG },
      { path: 'docs/harper/bmad/spec/SCOPE_DECISIONS.md', content: '# Scope' },
    ],
  });
  assert.strictEqual(result.ok, true);
});

test('BMAD spec/pm: SPEC.md stays required', () => {
  assert.throws(
    () => bmadPolicy.validateLocalAgentRequiredOutputs({
      phase: 'spec',
      outputContract: SPEC_PM_CONTRACT,
      artifacts: [{ path: 'docs/harper/bmad/spec/PRD.md', content: PG }],
    }),
    (error) => error.code === 'LOCAL_AGENT_REQUIRED_OUTPUTS_MISSING'
  );
});

test('BMAD spec/ux is companion-only: no SPEC.md required, SPEC.md forbidden', () => {
  const ok = bmadPolicy.validateLocalAgentRequiredOutputs({
    phase: 'spec',
    outputContract: SPEC_UX_CONTRACT,
    artifacts: [{ path: 'docs/harper/ux/DESIGN.md', content: '# Design' }],
  });
  assert.strictEqual(ok.ok, true);
  assert.throws(
    () => bmadPolicy.validateLocalAgentRequiredOutputs({
      phase: 'spec',
      outputContract: SPEC_UX_CONTRACT,
      artifacts: [
        { path: 'docs/harper/ux/DESIGN.md', content: '# Design' },
        { path: 'docs/harper/SPEC.md', content: '# SPEC' },
      ],
    }),
    (error) => error.code === 'LOCAL_AGENT_FORBIDDEN_OUTPUT_PATH'
  );
});

test('BMAD plan/architect: architecture companions are accepted', () => {
  const result = bmadPolicy.validateLocalAgentRequiredOutputs({
    phase: 'plan',
    outputContract: PLAN_ARCHITECT_CONTRACT,
    artifacts: [
      { path: 'docs/harper/PLAN.md', content: '# PLAN' },
      { path: 'docs/harper/plan.json', content: '{}' },
      { path: 'docs/harper/lane-guides/postgres.md', content: '# PostgreSQL lane' },
      { path: 'docs/harper/bmad/architecture/ARCHITECTURE.md', content: PG },
      { path: 'docs/harper/bmad/architecture/DECISIONS.md', content: '# ADR: PostgreSQL' },
    ],
  });
  assert.strictEqual(result.ok, true);
});

test('BMAD companions outside the contract roots stay forbidden', () => {
  for (const bad of [
    'docs/harper/bmad/plan/STORIES.md',          // another agent's root
    'docs/harper/bmad/architecture/schema.sql',  // not Markdown
    'docs/harper/bmad/architecture/../SPEC.md',  // traversal
    'docs/harper/AGENT_PLAN_CONTEXT.json',
  ]) {
    assert.throws(
      () => bmadPolicy.validateLocalAgentRequiredOutputs({
        phase: 'plan',
        outputContract: PLAN_ARCHITECT_CONTRACT,
        artifacts: [
          { path: 'docs/harper/PLAN.md', content: '# PLAN' },
          { path: 'docs/harper/plan.json', content: '{}' },
          { path: bad, content: 'x' },
        ],
      }),
      (error) => error.code === 'LOCAL_AGENT_FORBIDDEN_OUTPUT_PATH',
      bad
    );
  }
});

test('without a BMAD contract companions are not accepted (native CLike unchanged)', () => {
  assert.throws(
    () => bmadPolicy.validateLocalAgentRequiredOutputs({
      phase: 'spec',
      outputContract: { methodology: 'native_clike', required_outputs: ['docs/harper/SPEC.md'] },
      artifacts: [
        { path: 'docs/harper/SPEC.md', content: '# SPEC' },
        { path: 'docs/harper/bmad/spec/PRD.md', content: PG },
      ],
    }),
    (error) => error.code === 'LOCAL_AGENT_FORBIDDEN_OUTPUT_PATH'
  );
});

test('companion targets come only from the BMAD roots of the contract', () => {
  assert.deepStrictEqual(bmadPolicy.documentPhaseCompanionTargets(PLAN_ARCHITECT_CONTRACT), {
    files: ['docs/harper/bmad/architecture/ARCHITECTURE.md'],
    dirs: ['docs/harper/bmad/architecture'],
  });
  assert.deepStrictEqual(
    bmadPolicy.documentPhaseCompanionTargets({
      methodology: 'bmad',
      required_outputs: ['src/app.py', 'docs/harper/SPEC.md'],
      allowed_optional_output_globs: ['src/**', 'docs/harper/**'],
    }),
    { files: [], dirs: [] }
  );
});

test('only files written during the run count as document-phase output', () => {
  const started = Date.parse('2026-10-10T22:29:50Z');
  assert.strictEqual(bmadPolicy.isFreshLocalAgentArtifact(Date.parse('2026-10-10T22:21:46Z'), started), false);
  assert.strictEqual(bmadPolicy.isFreshLocalAgentArtifact(started - 1000, started), true);
  assert.strictEqual(bmadPolicy.isFreshLocalAgentArtifact(started + 60000, started), true);
  assert.strictEqual(bmadPolicy.isFreshLocalAgentArtifact(0, null), true);
});

test('a local agent that exits with an error reports its own stderr', () => {
  const failed = bmadPolicy.describeFailedLocalAgentRun({
    exitCode: 1,
    stderr: 'Reading prompt from stdin...\nNot inside a trusted directory and --skip-git-repo-check was not specified.\n',
    executorLabel: 'Codex',
  });
  assert.strictEqual(failed.code, 'LOCAL_AGENT_EXITED_WITH_ERROR');
  assert.match(failed.message, /^Codex exited with code 1 without writing any output: Not inside a trusted directory/);
  assert.doesNotMatch(failed.message, /Reading prompt/);
  assert.strictEqual(bmadPolicy.describeFailedLocalAgentRun({ exitCode: 0, stderr: 'x' }), null);
});

test('a failed Codex --json run reports the turn.failed message from stdout', () => {
  const stdout = [
    '{"type":"turn.started"}',
    '{"type":"error","message":"Reconnecting... 2/5 (unexpected status 404 Not Found: The model `gpt6-1-sol` does not exist or you do not have access to it.)"}',
    '{"type":"turn.failed","error":{"message":"unexpected status 404 Not Found: The model `gpt6-1-sol` does not exist or you do not have access to it., url: https://api.openai.com/v1/responses, cf-ray: x, request id: req_1"}}',
  ].join('\n');
  const failed = bmadPolicy.describeFailedLocalAgentRun({
    exitCode: 1,
    stdout,
    stderr: 'Reading prompt from stdin...\n',
    executorLabel: 'GPT Codex',
  });
  assert.strictEqual(
    failed.message,
    'GPT Codex exited with code 1 without writing any output: ' +
      'unexpected status 404 Not Found: The model `gpt6-1-sol` does not exist or you do not have access to it.'
  );
});

test('a failed Claude --output-format json run reports its error result', () => {
  const failed = bmadPolicy.describeFailedLocalAgentRun({
    exitCode: 1,
    stdout: '{"type":"result","is_error":true,"result":"Invalid API key · Please run /login"}',
    executorLabel: 'Claude Code',
  });
  assert.match(failed.message, /Claude Code exited with code 1 without writing any output: Invalid API key/);
});

test('finalize writes the canonical solution inside its package write roots, never tests, runs or secrets', () => {
  const roots = ['src', 'scripts', 'docs/harper', 'README.md', '.env.example', 'ci/SOLUTION_LTC.json', 'ci/solution'];
  const forbiddenPaths = ['.git', 'node_modules', '.env', 'secrets'];
  const ok = ['src/leadintel/execution/worker.py', 'src/runtime/compose.yaml', 'docs/harper/FINALIZE_REPORT.md',
    'README.md', '.env.example', 'ci/SOLUTION_LTC.json', 'ci/solution/smoke.py', 'scripts/setup_local.sh'];
  assert.deepEqual(validateLocalAgentRequiredOutputs({
    phase: 'finalize', artifacts: ok.map((path) => ({ path, content: 'x' })), allowedWriteRoots: roots, forbiddenPaths,
  }), { ok: true, missing_required_roots: [] });
  for (const bad of ['test/test_app.py', 'runs/kit/REQ-001/src/a.py', 'src/web/node_modules/x/index.js', '.env', 'ci/other.json', 'README.md.bak']) {
    assert.throws(
      () => validateLocalAgentRequiredOutputs({ phase: 'finalize', artifacts: [{ path: bad, content: 'x' }], allowedWriteRoots: roots, forbiddenPaths }),
      (error) => error.code === 'LOCAL_AGENT_FORBIDDEN_OUTPUT_PATH',
      bad
    );
  }
  // the KIT rule is unchanged: a KIT never writes the canonical src/
  assert.throws(
    () => validateLocalAgentRequiredOutputs({ phase: 'kit', reqId: 'REQ-001', artifacts: [{ path: 'src/a.py', content: 'x' }] }),
    (error) => error.code === 'LOCAL_AGENT_FORBIDDEN_OUTPUT_PATH'
  );
});


test('a KIT without its eval profile is incomplete (B2B REQ-026: ci/ held only check.py and FILE_REQUIREMENTS.json)', () => {
  const artifacts = [
    { path: 'runs/kit/REQ-026/src/leadintel/history/service.py', content: '' },
    { path: 'runs/kit/REQ-026/test/v2/test_req_026_contracts.py', content: '' },
    { path: 'runs/kit/REQ-026/ci/check.py', content: '' },
    { path: 'runs/kit/REQ-026/ci/FILE_REQUIREMENTS.json', content: '{}' },
  ];
  assert.throws(
    () => validateLocalAgentRequiredOutputs({ phase: 'kit', reqId: 'REQ-026', artifacts }),
    (error) => error.code === 'LOCAL_AGENT_REQUIRED_OUTPUTS_MISSING' &&
      error.details.missing_required_roots.includes('runs/kit/REQ-026/ci/LTC.json')
  );
});

test('an agent that exits with an error after writing files is interrupted, Codex and Claude Code alike', () => {
  // Codex: exit 1 and turn.failed (B2B REQ-026: the model at capacity mid-run)
  const codex = describeInterruptedLocalAgentRun({
    exitCode: 1,
    stdout: '{"type":"turn.failed","error":{"message":"Selected model is at capacity. Please try a different model."}}',
    executorLabel: 'GPT Codex',
  });
  assert.equal(codex.code, 'LOCAL_AGENT_INTERRUPTED');
  assert.match(codex.message, /at capacity/);
  assert.match(codex.message, /not used or committed/);
  // Claude Code: its result envelope says is_error, even with exit code 0
  const claude = describeInterruptedLocalAgentRun({
    exitCode: 0,
    stdout: '{"type":"result","is_error":true,"result":"API Error: 529 Overloaded"}',
    executorLabel: 'Claude Code',
    isError: true,
  });
  assert.equal(claude.code, 'LOCAL_AGENT_INTERRUPTED');
  assert.match(claude.message, /529 Overloaded/);
  // a run that finished
  assert.equal(describeInterruptedLocalAgentRun({ exitCode: 0, stdout: '{"type":"turn.completed"}' }), null);
});
