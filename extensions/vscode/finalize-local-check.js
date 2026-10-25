'use strict';
// The local check of /finalize: scripts/check_solution_local on the developer's machine, after the
// solution eval passed in the CLike sandbox. The sandbox runs the solution natively on loopback; the
// developer's default start uses containers (services bound to every interface, reached through
// published ports), which neither the sandbox nor a sandboxed agent can run (test project: the
// console bridge refused every request in containers while the sandbox smoke passed).
const fs = require('fs');
const path = require('path');
const { spawn } = require('child_process');

const REPORT_PATH = 'runs/finalize/LOCAL_CHECK.md';
const CHECK_ID = 'local::check_solution_local';
const TAIL = 8000;

/** The check script for this platform ({ rel, cmd, args }) or null when /finalize wrote none. */
function localCheckScript(root, platform = process.platform) {
  const win = platform === 'win32';
  const rel = `scripts/check_solution_local.${win ? 'ps1' : 'sh'}`;
  if (!fs.existsSync(path.join(root, ...rel.split('/')))) return null;
  return win
    ? { rel, cmd: 'powershell', args: ['-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', rel] }
    : { rel, cmd: 'sh', args: [rel] };
}

const tail = (text, max = TAIL) => (String(text || '').length > max ? `…\n${String(text).slice(-max)}` : String(text || ''));

/** The failure the repair cycle receives, in the solution eval's failure format. */
function localCheckFailure(result) {
  return {
    name: CHECK_ID,
    code: result.code,
    command: result.rel,
    output: [
      `${result.rel} failed on the developer's machine (exit ${result.code}${result.timedOut ? ', timed out' : ''}). ` +
      'It is the default local start the developer uses (containers when a runtime is installed): fix the cause in the ' +
      'solution or its scripts so it passes there too, not only in the sandbox.',
      tail(result.output),
    ].join('\n\n'),
  };
}

/** The evidence of the last local check (runs/finalize/LOCAL_CHECK.md). */
function localCheckMarkdown(result, when = new Date()) {
  return [
    '# Local check', '',
    `- Command: \`${result.rel}\``,
    `- Result: **${result.ok ? 'PASS' : 'FAIL'}** (exit ${result.code}${result.timedOut ? ', timed out' : ''})`,
    `- Date: ${when.toISOString()}`,
    `- Duration: ${Math.round((result.ms || 0) / 1000)} s`, '',
    '## Output (last part)', '', '```text', tail(result.output).trimEnd(), '```', '',
  ].join('\n');
}

/** Runs the check; resolves { ok, code, output, rel, ms, timedOut }. `onData` receives the output live. */
function runLocalCheck(root, script, { timeoutMs = 30 * 60000, onData = () => {}, env = process.env } = {}) {
  return new Promise((resolve) => {
    const started = Date.now();
    let output = '';
    let timedOut = false;
    const child = spawn(script.cmd, script.args, { cwd: root, env });
    const collect = (chunk) => {
      const text = chunk.toString();
      output = (output + text).slice(-TAIL * 4);
      onData(text);
    };
    child.stdout.on('data', collect);
    child.stderr.on('data', collect);
    const timer = setTimeout(() => { timedOut = true; child.kill('SIGTERM'); }, timeoutMs);
    const done = (code) => {
      clearTimeout(timer);
      resolve({ ok: code === 0 && !timedOut, code: timedOut ? 124 : code, output, rel: script.rel, ms: Date.now() - started, timedOut });
    };
    child.on('error', (err) => { output += `\n${err.message}`; done(127); });
    child.on('close', (code) => done(code ?? 1));
  });
}

function writeLocalCheckReport(root, result) {
  const file = path.join(root, ...REPORT_PATH.split('/'));
  fs.mkdirSync(path.dirname(file), { recursive: true });
  fs.writeFileSync(file, localCheckMarkdown(result));
  return REPORT_PATH;
}

module.exports = { REPORT_PATH, CHECK_ID, localCheckScript, localCheckFailure, localCheckMarkdown, runLocalCheck, writeLocalCheckReport };
