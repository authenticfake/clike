'use strict';
// Eval checks for a local agent while it repairs a REQ: `node .clike/bin/eval-check.mjs <check>...`
// re-runs those checks of the canonical eval in the real CLike sandbox (composed workspace,
// provisioned variables, services of other REQs) and prints their errors, so the agent iterates
// until they pass inside one session instead of one attempt per auto-eval cycle.
// The helper writes a request under .clike/eval-check/; the extension, which holds the
// orchestrator token, runs the checks and writes the result back. The agent gets neither the
// token nor network access. A partial run is never the REQ's verdict (the full eval is).
const fs = require('fs');
const path = require('path');

const CHANNEL_DIR = path.join('.clike', 'eval-check');
const HELPER_PATH = path.join('.clike', 'bin', 'eval-check.mjs');
const HEARTBEAT = '.bridge';
const CHECK_NAME = /^[\w:.\-/ ]{1,120}$/;
const ERRORS_PER_CHECK = 6000;

const HELPER_SOURCE = `#!/usr/bin/env node
// CLike eval check — re-runs checks of this REQ's canonical eval in the CLike eval sandbox.
// Usage: node .clike/bin/eval-check.mjs <check> [<check>...]   (exit 0: all passed)
// Served by the CLike extension only while it runs a repair; written and removed by CLike.
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const dir = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..', 'eval-check');
const checks = process.argv.slice(2);
const beat = path.join(dir, '${HEARTBEAT}');
const alive = () => { try { return Date.now() - fs.statSync(beat).mtimeMs < 15000; } catch { return false; } };
if (!alive()) {
  console.error('CLike is not serving eval checks now (it does during a CLike repair run).');
  process.exit(2);
}
// A run stopped by the agent's command timeout is resumed: the same checks wait for the same run.
const pending = path.join(dir, \`\${(checks.join('_') || 'all').replace(/[^\\w.-]+/g, '_').slice(0, 80)}.pending\`);
let id = '';
try { id = fs.readFileSync(pending, 'utf8').trim(); } catch { id = ''; }
if (!/^[\\w-]{1,64}$/.test(id)) {
  id = \`\${Date.now()}-\${process.pid}\`;
  const tmp = path.join(dir, \`\${id}.tmp\`);
  fs.writeFileSync(tmp, JSON.stringify({ checks }));
  fs.renameSync(tmp, path.join(dir, \`\${id}.request.json\`));
  fs.writeFileSync(pending, id);
  console.log(\`CLike eval sandbox: running \${checks.join(' ') || 'all the checks'} (a few minutes)...\`);
} else {
  console.log(\`CLike eval sandbox: still running \${checks.join(' ') || 'all the checks'}, waiting for it...\`);
}
const result = path.join(dir, \`\${id}.result.json\`);
const deadline = Date.now() + 40 * 60 * 1000;
while (Date.now() < deadline) {
  if (fs.existsSync(result)) {
    const r = JSON.parse(fs.readFileSync(result, 'utf8'));
    fs.rmSync(result, { force: true });
    fs.rmSync(pending, { force: true });
    if (r.error) console.log(\`\${r.status}: \${r.error}\`);
    for (const c of r.checks || []) {
      console.log(\`\${c.passed ? 'PASS' : c.blocked ? 'BLOCKED' : 'FAIL'} \${c.name}\${c.passed ? '' : \` (exit \${c.code})\`}\`);
      if (!c.passed && c.errors) console.log(c.errors.replace(/^/gm, '    '));
    }
    console.log(\`Result: \${r.status}\`);
    process.exit(r.status === 'PASS' ? 0 : 1);
  }
  if (!alive()) { console.error('CLike stopped serving eval checks.'); process.exit(2); }
  await new Promise((resolve) => setTimeout(resolve, 1000));
}
console.error('No result from CLike within 40 minutes.');
process.exit(2);
`;

/** The result the helper prints: the requested checks and the failed setup steps, with errors. */
function compactResult(report) {
  const cases = Array.isArray(report?.cases) ? report.cases : [];
  const checks = cases
    .filter((c) => c && (!String(c.name || '').startsWith('env::') || !c.passed))
    .map((c) => ({
      name: c.name,
      passed: !!c.passed,
      blocked: !!c.blocked,
      code: c.code,
      ...(c.passed ? {} : {
        errors: String(c.excerpt || `${String(c.stderr || '').slice(0, 1500)}\n${String(c.stdout || '').slice(-2500)}`)
          .slice(0, ERRORS_PER_CHECK),
      }),
    }));
  const failed = checks.some((c) => !c.passed && !String(c.name).startsWith('structure::'));
  return { status: failed || !checks.length ? 'FAIL' : 'PASS', checks };
}

function writeAtomic(file, text) {
  const tmp = `${file}.tmp`;
  fs.writeFileSync(tmp, text, 'utf8');
  fs.renameSync(tmp, file);
}

/**
 * Serve eval-check requests of a local agent until stop().
 * runChecks(checks: string[]) → eval report (the orchestrator /v1/eval/run payload).
 */
function startEvalCheckBridge({ workspaceRoot, runChecks, maxRuns = 8, pollMs = 1000, log = () => {} }) {
  const dir = path.join(workspaceRoot, CHANNEL_DIR);
  const helper = path.join(workspaceRoot, HELPER_PATH);
  fs.mkdirSync(dir, { recursive: true });
  fs.mkdirSync(path.dirname(helper), { recursive: true });
  fs.writeFileSync(helper, HELPER_SOURCE, 'utf8');
  const beat = path.join(dir, HEARTBEAT);
  let busy = false;
  let stopped = false;
  let runs = 0;

  async function tick() {
    if (stopped) return;
    try { fs.writeFileSync(beat, String(Date.now())); } catch { /* channel removed */ }
    if (busy) return;
    let names = [];
    try { names = fs.readdirSync(dir).filter((n) => n.endsWith('.request.json')).sort(); } catch { return; }
    if (!names.length) return;
    busy = true;
    const name = names[0];
    const id = name.slice(0, -'.request.json'.length);
    const requestPath = path.join(dir, name);
    try {
      let request = null;
      try { request = JSON.parse(fs.readFileSync(requestPath, 'utf8')); } catch { request = null; }
      fs.rmSync(requestPath, { force: true });
      if (!/^[\w-]{1,64}$/.test(id)) return;
      let result;
      const checks = (Array.isArray(request?.checks) ? request.checks : []).map(String).filter((c) => CHECK_NAME.test(c)).slice(0, 20);
      if (!request) {
        result = { status: 'ERROR', error: 'invalid request' };
      } else if (runs >= maxRuns) {
        result = { status: 'LIMIT', error: `eval-check run limit reached (${maxRuns}); finish with what you have, CLike runs the full eval next` };
      } else {
        runs += 1;
        log(`[evalCheck] run ${runs}/${maxRuns}: ${checks.join(' ') || 'all checks'}`);
        try {
          result = compactResult(await runChecks(checks));
        } catch (e) {
          result = { status: 'ERROR', error: String(e?.message || e).slice(0, 2000) };
        }
        log(`[evalCheck] result ${result.status}`);
      }
      if (!stopped) writeAtomic(path.join(dir, `${id}.result.json`), JSON.stringify(result));
    } finally {
      busy = false;
    }
  }

  tick();
  const timer = setInterval(tick, pollMs);
  return {
    get runs() { return runs; },
    stop() {
      stopped = true;
      clearInterval(timer);
      fs.rmSync(dir, { recursive: true, force: true });
      fs.rmSync(helper, { force: true });
      try { fs.rmdirSync(path.dirname(helper)); } catch { /* not empty */ }
    },
  };
}

/**
 * Agent CLI arguments that let it run the helper. Claude Code -p denies shell commands not
 * allowed up front: --allowedTools takes a list of values, so it goes first, where the next
 * argument is always an option (never the prompt). Codex (workspace-write) needs nothing.
 */
function agentArgsForEvalCheck(executorId, args) {
  const list = Array.isArray(args) ? [...args] : [];
  if (executorId !== 'claude_code' || list.includes('--allowedTools')) return list;
  return ['--allowedTools', `Bash(node ${HELPER_PATH.split(path.sep).join('/')}:*)`, ...(list.length ? list : ['-p'])];
}

module.exports = { CHANNEL_DIR, HELPER_PATH, agentArgsForEvalCheck, compactResult, startEvalCheckBridge };
