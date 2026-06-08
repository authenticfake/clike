const assert = require('assert');
const test = require('node:test');

const {
  localAgentSupportsPhase,
  getExecutorConfig,
} = require('../local-agent-executors');

const DOCUMENT_PHASES = ['idea', 'spec', 'plan'];
const ACTUATOR_PHASES = ['kit', 'eval', 'finalize', 'extend'];

test('local agent supports early document phases for both executors', () => {
  for (const phase of DOCUMENT_PHASES) {
    assert.strictEqual(localAgentSupportsPhase('claude_code', phase), true, `claude ${phase}`);
    assert.strictEqual(localAgentSupportsPhase('gpt_codex', phase), true, `codex ${phase}`);
  }
});

test('local agent still supports existing actuator phases', () => {
  for (const phase of ACTUATOR_PHASES) {
    assert.strictEqual(localAgentSupportsPhase('claude_code', phase), true, `claude ${phase}`);
    assert.strictEqual(localAgentSupportsPhase('gpt_codex', phase), true, `codex ${phase}`);
  }
});

test('local agent does not support unrelated phases like gate', () => {
  assert.strictEqual(localAgentSupportsPhase('claude_code', 'gate'), false);
  assert.strictEqual(localAgentSupportsPhase('gpt_codex', 'gate'), false);
});

test('executor capability maps advertise document phases', () => {
  const settings = {
    localAgentEnabled: true,
    claudeCodeEnabled: true,
    codexEnabled: true,
  };
  for (const executor of ['claude_code', 'gpt_codex']) {
    const cfg = getExecutorConfig(executor, settings);
    for (const phase of DOCUMENT_PHASES) {
      assert.strictEqual(cfg.supports[phase], true, `${executor} supports ${phase}`);
    }
    assert.strictEqual(cfg.supports.kit, true);
  }
});
