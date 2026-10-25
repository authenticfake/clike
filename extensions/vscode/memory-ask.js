'use strict';
// Ask, in the Memory panel: an answer written only from the memory's sources, numbered, with the
// steps and exact commands when the question asks what to do, how sure it is and why, and the next
// questions. The same contract for the chat's cloud model and for a local agent (read-only run).
// The "NOW" questions come from the project's state: a failed eval, a test patch to review, the
// next action of the cockpit.

const fs = require('fs');
const path = require('path');

const PASSING = new Set(['PASS', 'PASS_WITH_WARNINGS', 'PASSED', 'OK']);
const MAX_SOURCE_CHARS = 1800;
const CONFIDENCE = new Set(['high', 'medium', 'low']);

/** Sources for the answer: the best chunks of each memory, numbered from 1. */
function pickSources(byCollection, limits = { project: 5, guide: 4 }) {
  const out = [];
  for (const [collection, hits] of Object.entries(byCollection || {})) {
    const seen = new Set();
    const best = [...(hits || [])].sort((a, b) => Number(b.score) - Number(a.score));
    for (const h of best) {
      if (out.filter((s) => s.collection === collection).length >= (limits[collection] ?? 4)) break;
      const key = `${h.path}#${h.chunk}`;
      if (!h.path || seen.has(key)) continue;
      seen.add(key);
      out.push({ collection, path: String(h.path), score: Number(h.score) || 0, text: String(h.text || '').slice(0, MAX_SOURCE_CHARS) });
    }
  }
  return out.sort((a, b) => b.score - a.score).map((s, i) => ({ ...s, n: i + 1 }));
}

/** The prompt of an answer: rules, the numbered sources, the question. */
function buildAskPrompt(question, sources, context = '') {
  const blocks = sources.map((s) =>
    `[${s.n}] ${s.collection === 'guide' ? 'CLike guide' : 'Project'} · ${s.path}${s.modified ? ` (modified ${s.modified})` : ''}\n${s.text.trim()}`).join('\n\n');
  return [
    'You answer questions about a software project and about CLike, the tool that builds it, using ONLY the numbered sources below.',
    'Rules:',
    '- Answer in the language of the question. Be short: at most 120 words in "answer".',
    '- Cite the sources you use as [n] in the answer. Never use knowledge that is not in the sources.',
    '- The project state below is the truth about now: when a source disagrees with it, or an older source with a newer one, follow the state and the newest source, and say that the older one is outdated.',
    '- If the sources do not answer the question, set "not_in_memory": true and say what is missing.',
    '- When the question asks what to do or how to do something, give "steps": each one sentence, with the exact command or path from the sources in "command" when there is one (a CLike chat command such as /eval REQ-001 --fix, or a file path to open). Never invent a command; never give tools an agent uses internally (anything under .clike/).',
    '- "confidence": "high" when several sources agree and answer directly, "medium" when one source answers, "low" otherwise; "confidence_reason" says why in a few words.',
    '- "followups": up to 3 short next questions the developer would likely ask.',
    'Reply with JSON only, no other text:',
    '{"answer": "...", "steps": [{"text": "...", "command": "..."}], "confidence": "high|medium|low", "confidence_reason": "...", "sources_used": [1], "followups": ["..."], "not_in_memory": false}',
    context ? `\nProject state now:\n${context}` : '',
    `\nSources:\n${blocks || '(none)'}`,
    `\nQuestion: ${question}`,
  ].filter(Boolean).join('\n');
}

/** The model's reply → a validated answer (a reply that is not JSON becomes a low-confidence answer). */
function parseAskAnswer(text, sources = []) {
  const raw = String(text || '').trim();
  let obj = null;
  const start = raw.indexOf('{');
  const end = raw.lastIndexOf('}');
  if (start >= 0 && end > start) {
    try { obj = JSON.parse(raw.slice(start, end + 1)); } catch { obj = null; }
  }
  const valid = new Set(sources.map((s) => s.n));
  if (!obj || typeof obj.answer !== 'string') {
    return { answer: raw || 'No answer.', steps: [], confidence: 'low', confidence_reason: 'the reply was not in the expected form', sources_used: [], followups: [], not_in_memory: false };
  }
  const steps = (Array.isArray(obj.steps) ? obj.steps : [])
    .map((s) => (typeof s === 'string' ? { text: s } : s))
    .filter((s) => s && typeof s.text === 'string' && s.text.trim())
    .slice(0, 6)
    .map((s) => ({ text: s.text.trim(), command: typeof s.command === 'string' && s.command.trim() ? s.command.trim() : '' }));
  return {
    answer: obj.answer.trim(),
    steps,
    confidence: CONFIDENCE.has(obj.confidence) ? obj.confidence : 'low',
    confidence_reason: typeof obj.confidence_reason === 'string' ? obj.confidence_reason.trim() : '',
    sources_used: (Array.isArray(obj.sources_used) ? obj.sources_used : []).map(Number).filter((n) => valid.has(n)),
    followups: (Array.isArray(obj.followups) ? obj.followups : []).filter((f) => typeof f === 'string' && f.trim()).slice(0, 3).map((f) => f.trim()),
    not_in_memory: obj.not_in_memory === true,
  };
}

/** Test patches proposed by a repair and not applied yet: [{ req, file }]. */
function pendingTestPatches(root) {
  const out = [];
  const evalDir = path.join(root || '', 'runs', 'eval');
  let reqs = [];
  try { reqs = fs.readdirSync(evalDir); } catch { return out; }
  for (const req of reqs.sort()) {
    let names = [];
    try { names = fs.readdirSync(path.join(evalDir, req)); } catch { continue; }
    const patch = names.filter((n) => /^proposed_test_fix_\d+\.patch$/.test(n)).sort().pop();
    if (patch) out.push({ req, file: `runs/eval/${req}/${patch}` });
  }
  return out;
}

/**
 * The questions worth asking now, from the cockpit state (buildCockpitState) and the pending test
 * patches: [{ label, query, why }], at most 4, the most urgent first.
 */
function nowSuggestions(state, patches = []) {
  const out = [];
  const add = (label, query, why) => { if (out.length < 4 && !out.some((x) => x.query === query)) out.push({ label, query, why }); };
  for (const p of patches) {
    add(`Review the test patch proposed for ${p.req}`, `What does the test patch proposed for ${p.req} (${p.file}) change, and should I accept it?`, 'a repair proposed a test fix');
    add('What does --accept do?', `What does /eval ${p.req} --accept do, and what will the gate check afterwards?`, 'a test fix waits for you');
  }
  const last = state && state.last_run;
  if (last && last.req_id && !PASSING.has(String(last.status || '').toUpperCase())) {
    add(`Why did the last ${last.phase} of ${last.req_id} fail?`, `Why did the last ${last.phase} of ${last.req_id} fail, and what do I do now?`, `${last.phase} ${last.status}`);
  }
  const blocked = (state?.reqs || []).find((r) => (r.blockers || []).length || (r.open_decisions || []).length);
  if (blocked) add(`What decisions block ${blocked.id}?`, `Which open decisions block ${blocked.id}, and what does the SPEC say about them?`, 'open decisions');
  const cmd = state?.next?.command;
  if (cmd) add(`What does ${cmd} do here?`, `What does ${cmd} do, and what should I check before running it?`, 'the next action');
  add('How does the autopilot work?', 'How does /autopilot work, and how do I stop or resume it?', 'CLike guide');
  return out;
}

/** The blocking failures of the latest report of a run (phase eval or gate): [{ name, error }], at most 6. */
function lastRunFailures(root, run) {
  if (!root || !run || !run.req_id || !/^(eval|gate)$/.test(run.phase || '')) return [];
  const dir = path.join(root, 'runs', run.phase, run.req_id);
  let file = '';
  try {
    file = fs.readdirSync(dir).filter((n) => /^report_.*\.json$/.test(n)).sort().pop() || '';
  } catch { return []; }
  let rep = null;
  try { rep = JSON.parse(fs.readFileSync(path.join(dir, file), 'utf8')); } catch { return []; }
  return (Array.isArray(rep?.cases) ? rep.cases : [])
    .filter((c) => c && c.passed === false && c.blocking !== false && !c.warning)
    .slice(0, 6)
    .map((c) => ({
      name: String(c.name || ''),
      error: String(c.excerpt || c.stderr || c.stdout || '').split('\n').map((l) => l.trim()).filter(Boolean).slice(-2).join(' | ').slice(0, 300),
    }));
}

/** A few lines of project state for the prompt (what "now" means): next action, last run and its failures. */
function stateContext(state, patches = [], failures = []) {
  if (!state) return '';
  const lines = [];
  if (state.next?.command) lines.push(`Next action: ${state.next.command} — ${state.next.message || ''}`.trim());
  const last = state.last_run;
  if (last) lines.push(`Last run: ${last.phase} ${last.req_id} ${last.status}${last.failed ? ` (${last.failed} failed)` : ''}`);
  for (const f of failures) lines.push(`  blocking failure ${f.name}${f.error ? `: ${f.error}` : ''}`);
  for (const p of patches) lines.push(`Test patch waiting for review: ${p.file}`);
  if (state.counts) lines.push(`REQs: ${state.counts.done}/${state.counts.total} done`);
  return lines.join('\n');
}

module.exports = { pickSources, buildAskPrompt, parseAskAnswer, pendingTestPatches, nowSuggestions, stateContext, lastRunFailures };
