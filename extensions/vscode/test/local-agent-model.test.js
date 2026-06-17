const assert = require('assert');
const test = require('node:test');

const {
  getExecutorConfig,
  buildLocalAgentModelArgs,
  parseClaudeResultEnvelope,
} = require('../local-agent-executors');

const SETTINGS = {
  localAgentEnabled: true,
  claudeCodeEnabled: true,
  claudeCodeCommand: 'claude',
  claudeCodeModel: 'opus',
  codexEnabled: true,
  codexCommand: 'codex',
  codexModel: 'gpt-5.5-codex',
};

// --- model is surfaced on the executor config ---
test('executor config exposes the configured model per executor', () => {
  assert.strictEqual(getExecutorConfig('claude_code', SETTINGS).model, 'opus');
  assert.strictEqual(getExecutorConfig('gpt_codex', SETTINGS).model, 'gpt-5.5-codex');
});

// --- model injection args ---
test('builds --model args for claude and codex when a model is configured', () => {
  assert.deepStrictEqual(
    buildLocalAgentModelArgs('claude_code', getExecutorConfig('claude_code', SETTINGS)),
    ['--model', 'opus']
  );
  assert.deepStrictEqual(
    buildLocalAgentModelArgs('gpt_codex', getExecutorConfig('gpt_codex', SETTINGS)),
    ['--model', 'gpt-5.5-codex']
  );
});

test('builds no model args when no model is configured (CLI default is used)', () => {
  const noModel = { ...SETTINGS, claudeCodeModel: '', codexModel: '' };
  assert.deepStrictEqual(buildLocalAgentModelArgs('claude_code', getExecutorConfig('claude_code', noModel)), []);
  assert.deepStrictEqual(buildLocalAgentModelArgs('gpt_codex', getExecutorConfig('gpt_codex', noModel)), []);
});

// --- claude JSON envelope parsing (capture the model actually used) ---
test('parses the claude json envelope to expose the model used and result text', () => {
  const stdout = JSON.stringify({
    type: 'result',
    subtype: 'success',
    result: 'Hello from the agent.',
    model: 'claude-opus-4-8',
    session_id: 'abc',
  });
  const env = parseClaudeResultEnvelope(stdout);
  assert.ok(env);
  assert.strictEqual(env.model, 'claude-opus-4-8');
  assert.strictEqual(env.result, 'Hello from the agent.');
});

test('returns null for non-json stdout so callers fall back to raw text', () => {
  assert.strictEqual(parseClaudeResultEnvelope('plain text answer'), null);
  assert.strictEqual(parseClaudeResultEnvelope(''), null);
  assert.strictEqual(parseClaudeResultEnvelope('[1,2,3]'), null);
  assert.strictEqual(parseClaudeResultEnvelope('{not valid json'), null);
});
