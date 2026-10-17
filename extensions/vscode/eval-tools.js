'use strict';
// Native tools of the eval sandbox (orchestrator eval_tools): before an eval/gate CLike asks what
// the REQ declares or runs that the sandbox lacks, and installs it from its catalog — after the
// developer's confirmation, or at once when the project approved it in .clike/eval-tools.yaml
// (clike.evalTools.install: ask | always | never). A check that still stops on a missing program
// (report.missing_tools) gets the same question, then the eval runs again instead of a repair.
const fs = require('fs');
const path = require('path');

const PROJECT_FILE = path.join('.clike', 'eval-tools.yaml');
const ANSWER_TIMEOUT_MS = 5 * 60 * 1000;

/** The tools a project installs without asking (`tools:` of .clike/eval-tools.yaml). */
function readApproved(text) {
  const src = String(text || '');
  const flow = src.match(/^tools:\s*\[([^\]]*)\]/m);
  if (flow) return flow[1].split(',').map((s) => s.trim().replace(/^["']|["']$/g, '')).filter(Boolean);
  const block = src.match(/^tools:\s*\n((?:[ \t]+-[^\n]*\n?)+)/m);
  if (!block) return [];
  return block[1].split('\n').map((l) => l.replace(/^\s*-\s*/, '').trim().replace(/^["']|["']$/g, '')).filter(Boolean);
}

/** The file with `names` added to `tools:` (other content, e.g. `custom:`, kept as written). */
function addApproved(text, names) {
  const src = String(text || '');
  const current = readApproved(src);
  const added = names.filter((n) => !current.includes(n));
  if (!added.length) return src;
  const all = [...current, ...added];
  const block = `tools:\n${all.map((n) => `  - ${n}`).join('\n')}\n`;
  if (/^tools:\s*\[[^\]]*\]\s*\n?/m.test(src)) return src.replace(/^tools:\s*\[[^\]]*\]\s*\n?/m, block);
  if (/^tools:\s*\n((?:[ \t]+-[^\n]*\n?)+)/m.test(src)) return src.replace(/^tools:\s*\n((?:[ \t]+-[^\n]*\n?)+)/m, block);
  const header = '# Native tools CLike installs in the eval sandbox without asking (see GET /v1/eval/tools).\n';
  return src.trim() ? `${block}${src.endsWith('\n') ? src : `${src}\n`}` : `${header}${block}`;
}

/** The file without `names` in `tools:`. */
function removeApproved(text, names) {
  const src = String(text || '');
  const kept = readApproved(src).filter((n) => !names.includes(n) && !names.includes(n.split('@')[0]));
  const block = kept.length ? `tools:\n${kept.map((n) => `  - ${n}`).join('\n')}\n` : 'tools: []\n';
  if (/^tools:\s*\[[^\]]*\]\s*\n?/m.test(src)) return src.replace(/^tools:\s*\[[^\]]*\]\s*\n?/m, block);
  if (/^tools:\s*\n((?:[ \t]+-[^\n]*\n?)+)/m.test(src)) return src.replace(/^tools:\s*\n((?:[ \t]+-[^\n]*\n?)+)/m, block);
  return src;
}

function withdrawForProject(workspaceRoot, names) {
  const file = path.join(workspaceRoot, PROJECT_FILE);
  let text = '';
  try { text = fs.readFileSync(file, 'utf8'); } catch { return; }
  fs.writeFileSync(file, removeApproved(text, names), 'utf8');
}

/** Catalog tool of a name (`kafkacat`, a program like `kcat`, or `jdk@17`), or null. */
function catalogTool(catalog, name) {
  const base = String(name || '').split('@')[0];
  if (catalog && catalog[base]) return base;
  for (const [tool, entry] of Object.entries(catalog || {})) {
    if ((entry.binaries || []).includes(base)) return tool;
  }
  return null;
}

/** Text of `/tools` (list) and `/tools search <q>`, from GET /v1/eval/tools. */
function toolsListing(data, query = '') {
  const catalog = data?.catalog || {};
  const installed = data?.installed || {};
  const approved = data?.approved || [];
  const q = String(query || '').toLowerCase();
  const lines = [];
  const versionsOf = (rec) => Object.entries(rec?.versions || {}).map(([k, v]) => `${k} ${v}`).join(', ');
  const installedAs = (name) => Object.keys(installed).filter((k) => k === name || k.split('@')[0] === name);
  if (!q) {
    const list = Object.entries(installed).map(([k, rec]) => `${k}${versionsOf(rec) ? ` (${versionsOf(rec)})` : ''}`);
    lines.push(`Installed in the eval sandbox: ${list.join('; ') || 'none (PostgreSQL client tools are in the image)'}`);
    if (data?.update_due) {
      lines.push(`⚠ Tools last updated ${data.updated_days_ago} days ago: /tools update (or ./rebuild.sh --update-tools).`);
    } else if (list.length && data?.updated_days_ago != null) {
      lines.push(`Tools updated ${data.updated_days_ago} day(s) ago.`);
    }
    lines.push(`Approved for this project (.clike/eval-tools.yaml): ${approved.join(', ') || 'none'}`);
    if (data && data.installable === false) lines.push('⚠ The eval-tools service is not configured: tools cannot be installed here.');
    lines.push('', 'Catalog (/tools add <tool>[@version]):');
  }
  const groups = {};
  for (const [name, entry] of Object.entries(catalog)) {
    const text = `${name} ${entry.about || ''} ${(entry.binaries || []).join(' ')} ${entry.group || ''}`.toLowerCase();
    if (q && !text.includes(q)) continue;
    const here = installedAs(name);
    const version = here.map((k) => versionsOf(installed[k])).filter(Boolean).join(' / ');
    (groups[entry.group || 'other'] = groups[entry.group || 'other'] || []).push(
      `  ${here.length ? '✔' : '·'} ${name}${version ? ` ${version}` : ''} — ${entry.about || ''} [${(entry.binaries || []).join(', ')}]`
    );
  }
  for (const [group, items] of Object.entries(groups)) lines.push(`${group}:`, ...items);
  if (q && !Object.keys(groups).length) {
    lines.push(`No catalog tool matches "${query}". A conda-forge package can be added under custom: in .clike/eval-tools.yaml; ` +
      'a library of your language (psycopg, ojdbc, kafka-python…) goes in the project manifest instead.');
  }
  return lines.join('\n');
}

/** Text of `/tools update`: what changed, what stayed, what failed. */
function updateSummary(result) {
  const changes = result?.changes || {};
  const lines = Object.entries(changes).map(([name, diff]) =>
    `  ${name}: ${Object.entries(diff).map(([pkg, [from, to]]) => `${pkg} ${from || '-'} → ${to}`).join(', ')}`);
  if (!(result?.updated || []).length && !Object.keys(result?.failed || {}).length) return 'No tools installed: nothing to update.';
  if (!lines.length && (result?.updated || []).length) lines.push('All tools are already at their latest versions.');
  for (const [name, error] of Object.entries(result?.failed || {})) lines.push(`  ✖ ${name} not updated (the previous version stays): ${String(error).slice(0, 300)}`);
  return `Eval tools updated:\n${lines.join('\n')}`;
}

/** Why `/tools add` does not take a name that is not in the catalog (a library, an unknown package). */
function unknownToolHint(names) {
  return `Not in CLike's tools catalog: ${names.join(', ')}. ` +
    'If it is a library of your language (psycopg, ojdbc11, kafka-python…), add it to the project manifest ' +
    '(requirements.txt / pyproject.toml, package.json, pom.xml / build.gradle): the eval installs it. ' +
    'If it is a native program on conda-forge, declare it under custom: in .clike/eval-tools.yaml ' +
    '(name: {packages: [<conda package>], binaries: [<program>]}) and run /tools add <name>.';
}

function approveForProject(workspaceRoot, names) {
  const file = path.join(workspaceRoot, PROJECT_FILE);
  let text = '';
  try { text = fs.readFileSync(file, 'utf8'); } catch { text = ''; }
  fs.mkdirSync(path.dirname(file), { recursive: true });
  fs.writeFileSync(file, addApproved(text, names), 'utf8');
}

function withTimeout(promise, ms, fallback) {
  let timer;
  return Promise.race([
    promise.finally(() => clearTimeout(timer)),
    new Promise((resolve) => { timer = setTimeout(() => resolve(fallback), ms); }),
  ]);
}

/**
 * Install what an eval needs. Inputs are injected (testable without VS Code):
 *   check()            → { missing: [{tool, about, source, in_catalog, approved}], installable }
 *   install(names)     → { installed, binaries, versions, seconds }
 *   ask(items)         → 'install' | 'always' | 'no'   (a question to the developer)
 *   approve(names)     → records them in .clike/eval-tools.yaml
 *   policy             → 'ask' | 'always' | 'never'
 *   extra              → names to add (e.g. the programs a report says are missing)
 * → { installed: [...], declined: [...], unavailable: [...], error? }
 */
async function ensureEvalTools({ check, install, ask, approve, policy = 'ask', extra = [], say = () => {}, timeoutMs = ANSWER_TIMEOUT_MS }) {
  const out = { installed: [], declined: [], unavailable: [] };
  let result;
  try {
    result = await check();
  } catch (err) {
    return { ...out, error: `tools check failed: ${err?.message || err}` };
  }
  const missing = (result?.missing || []).filter((m) => m && m.tool);
  for (const name of extra) {
    if (!missing.some((m) => m.tool === name || (m.binaries || []).includes(name))) {
      missing.push({ tool: name, about: '', source: 'failed', in_catalog: true, approved: false });
    }
  }
  out.unavailable = missing.filter((m) => !m.in_catalog).map((m) => m.tool);
  const wanted = missing.filter((m) => m.in_catalog);
  if (!wanted.length) return out;
  if (!result?.installable) {
    say(`⚠ The eval sandbox lacks ${wanted.map((m) => m.tool).join(', ')} and CLike cannot install tools here (eval-tools service not configured).`);
    return { ...out, declined: wanted.map((m) => m.tool) };
  }
  const auto = wanted.filter((m) => m.approved || policy === 'always');
  let toAsk = policy === 'never' ? [] : wanted.filter((m) => !auto.includes(m));
  out.declined = policy === 'never' ? wanted.filter((m) => !auto.includes(m)).map((m) => m.tool) : [];
  let names = auto.map((m) => m.tool);
  if (toAsk.length) {
    const answer = await withTimeout(Promise.resolve(ask(toAsk)), timeoutMs, 'timeout');
    if (answer === 'install' || answer === 'always') {
      names = [...names, ...toAsk.map((m) => m.tool)];
      if (answer === 'always') approve(toAsk.map((m) => m.tool));
    } else {
      out.declined.push(...toAsk.map((m) => m.tool));
      if (answer === 'timeout') say(`⚠ No answer about ${toAsk.map((m) => m.tool).join(', ')}: the eval runs without them.`);
    }
    toAsk = [];
  }
  if (!names.length) return out;
  say(`⬇ Installing in the eval sandbox: ${names.join(', ')} (conda-forge; the first time takes a minute or two)…`);
  try {
    const res = await install(names);
    out.installed = names;
    const versions = Object.entries(res?.versions || {}).map(([k, v]) => `${k} ${v}`).join(', ');
    say(`✔ Installed ${names.join(', ')}${versions ? ` (${versions})` : ''}${res?.seconds != null ? ` in ${res.seconds}s` : ''}.`);
  } catch (err) {
    out.error = `install failed: ${err?.message || err}`;
    say(`✖ Installing ${names.join(', ')} failed: ${String(err?.message || err).slice(0, 500)}`);
  }
  return out;
}

/** The question shown in VS Code, one line per tool. */
function questionText(reqId, items) {
  const list = items.map((m) => `${m.tool}${m.about ? ` — ${m.about}` : ''}${m.source === 'used' ? ' (run by the code)' : m.source === 'failed' ? ' (a check needs it)' : ''}`);
  return `${reqId || 'The eval'} needs native tools the eval sandbox lacks: ${list.join('; ')}. Install them (conda-forge)?`;
}

module.exports = {
  PROJECT_FILE, addApproved, approveForProject, catalogTool, ensureEvalTools, questionText, readApproved, removeApproved,
  toolsListing, unknownToolHint, updateSummary, withdrawForProject,
};
