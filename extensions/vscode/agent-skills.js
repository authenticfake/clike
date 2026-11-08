'use strict';
// Agent skills: the project's CLike skills (.clike/skills, one source) installed as native skills
// for the local agents — .claude/skills for Claude Code, .agents/skills for Codex — in the open
// Agent Skills format (frontmatter `name`, `description`, string `metadata`; CLike's own fields go
// under metadata), plus a CLike block in CLAUDE.md / AGENTS.md with the rules that must always hold,
// and a Claude Code hook that refuses writes to the locked acceptance surface during /eval.
// The cloud path gets the same skills in its prompt (orchestrator capability context).
//
// Never overwrites what CLike does not manage: a skill folder is replaced only when it is listed in
// the target's .clike-skills.json (or absent), instruction files change only between the CLike
// markers, settings.json only gains the guard hook entry.
const fs = require('fs');
const path = require('path');
const crypto = require('crypto');

const TARGETS = ['.claude/skills', '.agents/skills'];
const MANIFEST = '.clike-skills.json';
const BLOCK_BEGIN = '<!-- CLIKE:BEGIN (managed by CLike: edits inside this block are replaced) -->';
const BLOCK_END = '<!-- CLIKE:END -->';
const GUARD_REL = '.claude/hooks/clike-guard.cjs';
const NAME_RE = /^[a-z0-9]+(-[a-z0-9]+)*$/;

/** Flat frontmatter of a CLike SKILL.md: { meta: {key: string|string[]}, body }. */
function parseSkill(text) {
  const raw = String(text || '');
  const m = /^---\s*\n([\s\S]*?)\n---\s*\n?/.exec(raw);
  if (!m) return { meta: {}, body: raw };
  const meta = {};
  let listKey = null;
  for (const line of m[1].split('\n')) {
    const t = line.trim();
    if (listKey && t.startsWith('- ')) { meta[listKey].push(t.slice(2).trim().replace(/^['"]|['"]$/g, '')); continue; }
    const kv = /^([A-Za-z0-9_-]+):\s*(.*)$/.exec(t);
    if (!kv) { listKey = null; continue; }
    const [, key, valueRaw] = kv;
    const value = valueRaw.trim();
    if (!value) { meta[key] = []; listKey = key; continue; }
    listKey = null;
    if (value.startsWith('[') && value.endsWith(']')) {
      meta[key] = value.slice(1, -1).split(',').map((v) => v.trim().replace(/^['"]|['"]$/g, '')).filter(Boolean);
    } else {
      meta[key] = value.replace(/^['"]|['"]$/g, '');
    }
  }
  return { meta, body: raw.slice(m[0].length) };
}

const yamlString = (value) => JSON.stringify(String(value)); // a JSON string is a valid YAML scalar

/** The SKILL.md of a native skill: standard frontmatter, CLike fields as string metadata. */
function toNativeSkill(name, text, source, license = '') {
  const { meta, body } = parseSkill(text);
  const description = String(meta.description || `CLike skill ${name}`).replace(/\s+/g, ' ').trim().slice(0, 1024);
  const metadata = { 'clike-source': source };
  for (const [key, value] of Object.entries(meta)) {
    if (['name', 'description', 'scenarios', 'license'].includes(key)) continue;
    metadata[`clike-${key}`] = Array.isArray(value) ? value.join(', ') : String(value);
  }
  if (Array.isArray(meta.scenarios) && meta.scenarios.length) {
    metadata['clike-scenarios'] = meta.scenarios.map((s) => String(s).split('|')[0].trim()).join(', ');
  }
  const lines = ['---', `name: ${name}`, `description: ${yamlString(description)}`];
  if (license || meta.license) lines.push(`license: ${yamlString(license || meta.license)}`);
  lines.push('metadata:');
  for (const [key, value] of Object.entries(metadata)) lines.push(`  ${key}: ${yamlString(value)}`);
  lines.push('---', '');
  // scenario statements stay readable for the agent: the body lists them when the frontmatter had them
  const scenarioList = Array.isArray(meta.scenarios) && meta.scenarios.length
    ? '\n## Scenario catalog\n\n' + meta.scenarios.map((s) => {
      const [id, level, title, ears] = String(s).split('|').map((p) => p.trim());
      return `- **${id}** (${level}) ${title} — ${ears}`;
    }).join('\n') + '\n'
    : '';
  return lines.join('\n') + body.replace(/^\s+/, '') + scenarioList;
}

/** [{ name, dir, source }] — .clike/skills/<name> and the vendored ones as <vendor>-<name>. */
function sourceSkills(root) {
  const base = path.join(root, '.clike', 'skills');
  const out = [];
  const add = (dir, name) => {
    if (NAME_RE.test(name) && name.length <= 64 && fs.existsSync(path.join(dir, 'SKILL.md'))) {
      out.push({ name, dir, source: path.relative(root, dir).split(path.sep).join('/') });
    }
  };
  let entries = [];
  try { entries = fs.readdirSync(base, { withFileTypes: true }); } catch { return out; }
  for (const e of entries) {
    if (!e.isDirectory()) continue;
    if (e.name === 'vendor') {
      for (const vendor of fs.readdirSync(path.join(base, 'vendor'), { withFileTypes: true }).filter((v) => v.isDirectory())) {
        for (const skill of fs.readdirSync(path.join(base, 'vendor', vendor.name), { withFileTypes: true }).filter((v) => v.isDirectory())) {
          add(path.join(base, 'vendor', vendor.name, skill.name), `${vendor.name}-${skill.name}`);
        }
      }
      continue;
    }
    add(path.join(base, e.name), e.name);
  }
  return out.sort((a, b) => a.name.localeCompare(b.name));
}

function listFiles(dir, rel = '') {
  const out = [];
  for (const e of fs.readdirSync(path.join(dir, rel), { withFileTypes: true })) {
    const r = rel ? `${rel}/${e.name}` : e.name;
    if (e.isDirectory()) out.push(...listFiles(dir, r));
    else if (e.isFile()) out.push(r);
  }
  return out.sort();
}

/** { path: content } of one native skill folder. */
function nativeSkillFiles(skill) {
  const files = {};
  // a vendored skill carries its vendor's license (vendor/<vendor>/LICENSE, VENDORED.json)
  const vendorDir = path.dirname(skill.dir);
  const vendored = path.basename(path.dirname(vendorDir)) === 'vendor';
  const license = vendored ? vendorLicense(vendorDir) : '';
  for (const rel of listFiles(skill.dir)) {
    const content = fs.readFileSync(path.join(skill.dir, rel), 'utf8');
    files[rel] = rel === 'SKILL.md' ? toNativeSkill(skill.name, content, skill.source, license) : content;
  }
  if (vendored && fs.existsSync(path.join(vendorDir, 'LICENSE')) && !files.LICENSE) {
    files.LICENSE = fs.readFileSync(path.join(vendorDir, 'LICENSE'), 'utf8');
  }
  return files;
}

function vendorLicense(vendorDir) {
  const manifest = readJson(path.join(path.dirname(vendorDir), 'VENDORED.json'), {});
  const entry = (manifest.vendors || []).find((v) => v && v.id === path.basename(vendorDir));
  return entry && entry.license ? `${entry.license} (see LICENSE)` : '';
}

const digest = (files) => crypto.createHash('sha256').update(JSON.stringify(files)).digest('hex').slice(0, 16);

function readJson(file, fallback) {
  try { return JSON.parse(fs.readFileSync(file, 'utf8')); } catch { return fallback; }
}

function writeIfChanged(file, content) {
  try { if (fs.readFileSync(file, 'utf8') === content) return false; } catch { /* new */ }
  fs.mkdirSync(path.dirname(file), { recursive: true });
  fs.writeFileSync(file, content);
  return true;
}

/** The rules every agent run must follow, also when no skill is loaded. */
function instructionsBlock(skills) {
  const journeys = skills.filter((s) => s.name.startsWith('journey-')).map((s) => s.name);
  return [
    BLOCK_BEGIN,
    '## CLike rules for this project',
    '',
    'This project is built with the CLike Harper pipeline (IDEA → SPEC → PLAN → KIT → EVAL → GATE → FINALIZE).',
    '',
    '- Work inside the paths the phase allows; canonical `src/` and `test/` change only through promotion.',
    '- During /eval the acceptance surface is locked: never edit `runs/kit/<REQ>/test/` or `runs/kit/<REQ>/ci/` (only `ci/HOWTO.md` may be corrected); repair the source.',
    '- Never stop at the happy path: every journey scenario the plan gives a REQ (`reqs[].scenarios`) is implemented and proved by a blocking check listed in `docs/ACCEPTANCE.json`, and the test that proves it carries the scenario id (e.g. `test_iam_03_…`).',
    '- Assert what the user or the caller sees: the error message shown in the UI, the API error body, the safe state of the device — not only a status code.',
    '- Done means checked: run the checks you touched and report the commands and their results before saying a REQ, a feature or a fix is done.',
    '- Keep shared composition files (entrypoint, router wiring, migration heads) stable: add files and register them through the project seams.',
    journeys.length ? `- Journey catalogs (skills): ${journeys.join(', ')}.` : '',
    `- CLike skills are installed in .claude/skills and .agents/skills (from .clike/skills; run "CLike: Sync agent skills" after changing them).`,
    BLOCK_END,
  ].filter((l) => l !== '').join('\n');
}

/** Insert or replace the CLike block of an instruction file; the rest of the file is kept. */
function upsertBlock(file, block) {
  let text = '';
  try { text = fs.readFileSync(file, 'utf8'); } catch { /* new file */ }
  const start = text.indexOf(BLOCK_BEGIN);
  const end = text.indexOf(BLOCK_END);
  let next;
  if (start >= 0 && end > start) next = text.slice(0, start) + block + text.slice(end + BLOCK_END.length);
  else next = (text.trim() ? text.replace(/\s*$/, '\n\n') : '') + block + '\n';
  return writeIfChanged(file, next);
}

const GUARD_SCRIPT = `#!/usr/bin/env node
// CLike guard (installed by CLike): during /eval the acceptance surface is locked. CLike starts the
// agent with CLIKE_LOCKED_ROOTS (paths separated by ':'); a write under them is refused, so the agent
// repairs the source instead of the tests (ci/HOWTO.md stays editable). No env: nothing is refused.
let input = '';
process.stdin.on('data', (c) => { input += c; });
process.stdin.on('end', () => {
  const roots = String(process.env.CLIKE_LOCKED_ROOTS || '').split(':').map((r) => r.trim().replace(/\\/+$/, '')).filter(Boolean);
  if (!roots.length) process.exit(0);
  let file = '';
  try {
    const data = JSON.parse(input || '{}');
    const ti = data.tool_input || {};
    file = String(ti.file_path || ti.notebook_path || ti.path || '');
  } catch { process.exit(0); }
  if (!file) process.exit(0);
  const base = String(process.env.CLAUDE_PROJECT_DIR || process.cwd()).replace(/\\\\/g, '/').replace(/\\/+$/, '');
  let rel = file.replace(/\\\\/g, '/');
  if (rel.startsWith(base + '/')) rel = rel.slice(base.length + 1);
  rel = rel.replace(/^\\.\\//, '');
  if (/\\/ci\\/HOWTO\\.md$/i.test(rel)) process.exit(0);
  const hit = roots.find((r) => rel === r || rel.startsWith(r + '/'));
  if (!hit) process.exit(0);
  process.stderr.write(\`CLike: \${rel} is part of the locked acceptance surface (\${hit}) during /eval. Repair the source under the allowed roots; tests and CI stay as written.\\n\`);
  process.exit(2);
});
`;

/** Add the guard hook to .claude/settings.json (kept otherwise as it is). */
function ensureGuardHook(root) {
  const settingsFile = path.join(root, '.claude', 'settings.json');
  const settings = readJson(settingsFile, {});
  if (!settings || typeof settings !== 'object' || Array.isArray(settings)) return false;
  const command = `node "$CLAUDE_PROJECT_DIR/${GUARD_REL}"`;
  settings.hooks = settings.hooks && typeof settings.hooks === 'object' ? settings.hooks : {};
  const pre = Array.isArray(settings.hooks.PreToolUse) ? settings.hooks.PreToolUse : [];
  const present = pre.some((e) => Array.isArray(e?.hooks) && e.hooks.some((h) => String(h?.command || '').includes(GUARD_REL)));
  let changed = writeIfChanged(path.join(root, GUARD_REL), GUARD_SCRIPT);
  if (!present) {
    pre.push({ matcher: 'Write|Edit|MultiEdit|NotebookEdit', hooks: [{ type: 'command', command }] });
    settings.hooks.PreToolUse = pre;
    changed = writeIfChanged(settingsFile, JSON.stringify(settings, null, 2) + '\n') || changed;
  }
  return changed;
}

/**
 * Install the project's CLike skills for the local agents. Returns
 * { skills, written: [paths], skipped: [{ target, name, reason }], removed: [paths] }.
 */
function syncAgentSkills(root, { instructions = true, hook = true } = {}) {
  const skills = sourceSkills(root);
  const result = { skills: skills.map((s) => s.name), written: [], skipped: [], removed: [] };
  if (!skills.length) return result;
  for (const target of TARGETS) {
    const targetDir = path.join(root, ...target.split('/'));
    const manifestFile = path.join(targetDir, MANIFEST);
    const manifest = readJson(manifestFile, { managed: {} });
    const managed = manifest && typeof manifest.managed === 'object' ? manifest.managed : {};
    const next = {};
    for (const skill of skills) {
      const dir = path.join(targetDir, skill.name);
      if (fs.existsSync(dir) && !managed[skill.name]) {
        result.skipped.push({ target, name: skill.name, reason: 'a skill with this name exists and CLike does not manage it' });
        continue;
      }
      const files = nativeSkillFiles(skill);
      const hash = digest(files);
      next[skill.name] = { source: skill.source, digest: hash };
      if (managed[skill.name]?.digest === hash && fs.existsSync(path.join(dir, 'SKILL.md'))) continue;
      fs.rmSync(dir, { recursive: true, force: true });
      for (const [rel, content] of Object.entries(files)) {
        fs.mkdirSync(path.dirname(path.join(dir, rel)), { recursive: true });
        fs.writeFileSync(path.join(dir, rel), content);
      }
      result.written.push(`${target}/${skill.name}`);
    }
    for (const name of Object.keys(managed)) {
      if (!next[name]) {
        fs.rmSync(path.join(targetDir, name), { recursive: true, force: true });
        result.removed.push(`${target}/${name}`);
      }
    }
    writeIfChanged(manifestFile, JSON.stringify({ note: 'Skills installed by CLike from .clike/skills; do not edit them here.', managed: next }, null, 2) + '\n');
  }
  if (instructions) {
    const block = instructionsBlock(skills);
    for (const file of ['CLAUDE.md', 'AGENTS.md']) {
      if (upsertBlock(path.join(root, file), block)) result.written.push(file);
    }
  }
  if (hook && ensureGuardHook(root)) result.written.push('.claude/settings.json (guard hook)');
  return result;
}

/** CLIKE_LOCKED_ROOTS for an agent run: the acceptance surface of the REQ during /eval. */
function lockedRootsEnv(phase, reqId) {
  const req = String(reqId || '').trim();
  if (String(phase || '').toLowerCase() !== 'eval' || !/^[A-Za-z0-9_.-]+$/.test(req)) return {};
  return { CLIKE_LOCKED_ROOTS: [`runs/kit/${req}/test`, `runs/kit/${req}/ci`].join(':') };
}

module.exports = {
  parseSkill, toNativeSkill, sourceSkills, syncAgentSkills, instructionsBlock, upsertBlock,
  ensureGuardHook, lockedRootsEnv, GUARD_SCRIPT, BLOCK_BEGIN, BLOCK_END, TARGETS,
};
