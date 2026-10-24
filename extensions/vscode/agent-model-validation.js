// Validation of the model a local agent runs with (clike.localAgent.codex.model,
// clike.claudeCode.model). An invalid id used to surface only after the run, as a
// 404 from the provider; now it is rejected before the agent starts, on every run,
// until the setting is fixed.
const fs = require('fs');
const os = require('os');
const path = require('path');

const CLAUDE_ALIASES = ['opus', 'sonnet', 'haiku', 'default', 'opusplan'];
const CLAUDE_MODEL_RE = /^claude-[a-z0-9][a-z0-9.-]*$/;

// Codex caches the models of the logged-in account in <CODEX_HOME>/models_cache.json
// (models[].slug). Returns the slugs, or null when the cache is missing/unreadable:
// then the Codex id cannot be checked and is accepted.
function readCodexModelSlugs({ codexHome = process.env.CODEX_HOME || path.join(os.homedir(), '.codex') } = {}) {
  try {
    const data = JSON.parse(fs.readFileSync(path.join(codexHome, 'models_cache.json'), 'utf8'));
    const slugs = (Array.isArray(data?.models) ? data.models : [])
      .map((m) => String(m?.slug || '').trim())
      .filter(Boolean);
    return slugs.length ? slugs : null;
  } catch {
    return null;
  }
}

function compact(value) {
  return String(value || '').toLowerCase().replace(/[^a-z0-9]/g, '');
}

function editDistance(a, b) {
  const row = Array.from({ length: b.length + 1 }, (_, j) => j);
  for (let i = 1; i <= a.length; i += 1) {
    let prev = row[0];
    row[0] = i;
    for (let j = 1; j <= b.length; j += 1) {
      const cur = row[j];
      row[j] = Math.min(row[j] + 1, row[j - 1] + 1, prev + (a[i - 1] === b[j - 1] ? 0 : 1));
      prev = cur;
    }
  }
  return row[b.length];
}

// Closest known id: same letters/digits ignoring separators ("gpt6-1-sol" -> "gpt-6.1-sol"),
// otherwise the nearest one within 3 edits.
function closestModel(model, known) {
  const target = compact(model);
  const same = known.find((k) => compact(k) === target);
  if (same) return same;
  let best = null;
  let bestDistance = 4;
  for (const k of known) {
    const d = editDistance(target, compact(k));
    if (d < bestDistance) {
      best = k;
      bestDistance = d;
    }
  }
  return best;
}

function validateAgentModel({ executorId, model, codexModels = null } = {}) {
  const value = String(model || '').trim();
  const executor = String(executorId || '').trim().toLowerCase();
  if (!value) return { ok: true };

  if (executor === 'gpt_codex') {
    if (!Array.isArray(codexModels) || !codexModels.length) return { ok: true, unchecked: true };
    if (codexModels.includes(value)) return { ok: true };
    const suggestion = closestModel(value, codexModels);
    return {
      ok: false,
      code: 'LOCAL_AGENT_MODEL_INVALID',
      setting: 'clike.localAgent.codex.model',
      suggestion,
      message:
        `Codex model "${value}" is not available to your Codex login` +
        (suggestion ? ` — did you mean "${suggestion}"?` : '.') +
        ` Available: ${codexModels.join(', ')}. ` +
        'Fix clike.localAgent.codex.model (or /agent-model codex <model>), or leave it empty for the Codex default.',
    };
  }

  if (executor === 'claude_code') {
    const base = value.toLowerCase().replace(/\[1m\]$/, '');
    if (CLAUDE_ALIASES.includes(base) || CLAUDE_MODEL_RE.test(base)) return { ok: true };
    const suggestion = closestModel(base, CLAUDE_ALIASES);
    return {
      ok: false,
      code: 'LOCAL_AGENT_MODEL_INVALID',
      setting: 'clike.claudeCode.model',
      suggestion,
      message:
        `Claude Code model "${value}" is not a valid model` +
        (suggestion ? ` — did you mean "${suggestion}"?` : '.') +
        ` Use ${CLAUDE_ALIASES.slice(0, 3).join(', ')} or a full id like claude-opus-5-5. ` +
        'Fix clike.claudeCode.model (or /agent-model claude <model>), or leave it empty for the Claude CLI default.',
    };
  }

  return { ok: true };
}

/**
 * The `/agent-model list` lines. Codex accepts the models of its login (models_cache.json), not the
 * API ids of CLike's cloud catalog: listing the catalog proposed ids Codex refuses and hid the ones
 * it accepts. Each id says whether the cloud catalog has it too (same model in both executions).
 */
function agentModelListMessage({ codexModels = null, catalog = [] } = {}) {
  const names = (provider) => [...new Set((catalog || [])
    .filter((m) => String(m.provider || '').toLowerCase() === provider)
    .flatMap((m) => [String(m.name || '').trim(), String(m.remote_name || '').trim()])
    .filter(Boolean))];
  const cloudOpenai = new Set(names('openai'));
  const cloudAnthropic = names('anthropic').filter((n) => !/\d{8}$/.test(n));
  const mark = (id, cloud) => (cloud.has(id) ? `${id} (cloud too)` : id);
  const codex = Array.isArray(codexModels) && codexModels.length
    ? `Codex (your login): ${codexModels.map((id) => mark(id, cloudOpenai)).join(', ')}`
    : `Codex: the login's model list is not available (~/.codex/models_cache.json appears after a Codex run); ` +
      `set the id your Codex login supports`;
  const claude = `Claude Code: opus, sonnet, haiku (latest of that tier), or an id: ${[...new Set(cloudAnthropic)].join(', ') || 'see your Claude login'}`;
  return `ℹ Agent models you can set with /agent-model —\n${claude}\n${codex}\n` +
    'Cloud models are chosen in the chat model selector, separately: changing one does not change the other.';
}

module.exports = {
  agentModelListMessage,
  CLAUDE_ALIASES,
  closestModel,
  readCodexModelSlugs,
  validateAgentModel,
};
