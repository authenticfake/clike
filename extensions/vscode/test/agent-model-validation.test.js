const assert = require('assert');
const fs = require('fs');
const os = require('os');
const path = require('path');
const test = require('node:test');

const { closestModel, readCodexModelSlugs, validateAgentModel } = require('../agent-model-validation');

const CODEX = ['gpt-6.1-sol', 'gpt-6-astra', 'gpt-6-sol', 'gpt-6-luna', 'gpt-5.6-sol', 'gpt-5.5'];

test('Codex: a model of the account is accepted, empty means the CLI default', () => {
  assert.deepStrictEqual(validateAgentModel({ executorId: 'gpt_codex', model: 'gpt-6.1-sol', codexModels: CODEX }), { ok: true });
  assert.deepStrictEqual(validateAgentModel({ executorId: 'gpt_codex', model: '', codexModels: CODEX }), { ok: true });
});

test('Codex: the misspellings seen in the manual test are rejected with the right suggestion', () => {
  for (const wrong of ['gpt6-1-sol', 'gpt-6-1-sol', 'GPT-6.1-SOL ']) {
    const check = validateAgentModel({ executorId: 'gpt_codex', model: wrong, codexModels: CODEX });
    assert.strictEqual(check.ok, false, wrong);
    assert.strictEqual(check.code, 'LOCAL_AGENT_MODEL_INVALID');
    assert.strictEqual(check.suggestion, 'gpt-6.1-sol', wrong);
    assert.match(check.message, /did you mean "gpt-6\.1-sol"\?/);
    assert.match(check.message, /clike\.localAgent\.codex\.model/);
  }
});

test('Codex: an unknown id far from every model gets no suggestion but the list', () => {
  const check = validateAgentModel({ executorId: 'gpt_codex', model: 'llama-3', codexModels: CODEX });
  assert.strictEqual(check.ok, false);
  assert.strictEqual(check.suggestion, null);
  assert.match(check.message, /Available: gpt-6\.1-sol, /);
});

test('Codex: without the models cache the id cannot be checked and is accepted', () => {
  assert.deepStrictEqual(
    validateAgentModel({ executorId: 'gpt_codex', model: 'anything', codexModels: null }),
    { ok: true, unchecked: true }
  );
});

test('Claude: aliases and full ids are accepted, typos are rejected', () => {
  for (const ok of ['opus', 'sonnet', 'haiku', 'opus[1m]', 'claude-opus-5-5', 'claude-sonnet-5-5']) {
    assert.strictEqual(validateAgentModel({ executorId: 'claude_code', model: ok }).ok, true, ok);
  }
  const check = validateAgentModel({ executorId: 'claude_code', model: 'opsu' });
  assert.strictEqual(check.ok, false);
  assert.strictEqual(check.suggestion, 'opus');
  assert.match(check.message, /clike\.claudeCode\.model/);
});

test('readCodexModelSlugs reads <CODEX_HOME>/models_cache.json and tolerates a missing file', () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'clike-codex-'));
  assert.strictEqual(readCodexModelSlugs({ codexHome: dir }), null);
  fs.writeFileSync(path.join(dir, 'models_cache.json'), JSON.stringify({ models: [{ slug: 'gpt-6.1-sol' }, { slug: 'gpt-5.5' }] }));
  assert.deepStrictEqual(readCodexModelSlugs({ codexHome: dir }), ['gpt-6.1-sol', 'gpt-5.5']);
});

test('closestModel ignores separators first', () => {
  assert.strictEqual(closestModel('gpt-6-astra', CODEX), 'gpt-6-astra');
  assert.strictEqual(closestModel('gpt55', CODEX), 'gpt-5.5');
});

test('/agent-model list shows the Codex models of the login, marking those the cloud has too', () => {
  const { agentModelListMessage } = require('../agent-model-validation');
  const catalog = [
    { provider: 'openai', name: 'gpt-6.1-sol', remote_name: 'gpt-6.1-sol' },
    { provider: 'openai', name: 'gpt-5.4-mini', remote_name: 'gpt-5.4-mini-2026-03-17' },
    { provider: 'anthropic', name: 'claude-haiku-4-5', remote_name: 'claude-haiku-4-5-20251001' },
    { provider: 'anthropic', name: 'claude-fable-5-1', remote_name: 'claude-fable-5-1' },
  ];
  const message = agentModelListMessage({ codexModels: ['gpt-6.1-sol', 'gpt-6-astra'], catalog });
  assert.match(message, /Codex \(your login\): gpt-6\.1-sol \(cloud too\), gpt-6-astra\n/);
  assert.doesNotMatch(message, /gpt-5\.4-mini-2026-03-17/); // a cloud API id Codex refuses
  assert.match(message, /Claude Code: opus, sonnet, haiku .*claude-haiku-4-5, claude-fable-5-1/);
  assert.doesNotMatch(message, /20251001/);
  assert.match(agentModelListMessage({ codexModels: null, catalog }), /login's model list is not available/);
});
