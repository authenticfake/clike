const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('fs');
const os = require('os');
const path = require('path');

const lc = require('../finalize-local-check');

function project(script) {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'clike-localcheck-'));
  if (script !== undefined) {
    fs.mkdirSync(path.join(root, 'scripts'), { recursive: true });
    fs.writeFileSync(path.join(root, 'scripts', 'check_solution_local.sh'), script);
  }
  return root;
}

test('the check script of the platform, none when /finalize wrote none', () => {
  const root = project('exit 0\n');
  assert.deepEqual(lc.localCheckScript(root, 'darwin'), { rel: 'scripts/check_solution_local.sh', cmd: 'sh', args: ['scripts/check_solution_local.sh'] });
  assert.equal(lc.localCheckScript(root, 'win32'), null);
  fs.writeFileSync(path.join(root, 'scripts', 'check_solution_local.ps1'), 'exit 0\n');
  assert.equal(lc.localCheckScript(root, 'win32').cmd, 'powershell');
  assert.equal(lc.localCheckScript(project(), 'linux'), null);
});

test('a passing check, its output live and its evidence', async () => {
  const root = project('echo building\necho smoke ok\n');
  let live = '';
  const result = await lc.runLocalCheck(root, lc.localCheckScript(root, 'linux'), { onData: (t) => { live += t; } });
  assert.equal(result.ok, true);
  assert.equal(result.code, 0);
  assert.match(live, /smoke ok/);
  const rel = lc.writeLocalCheckReport(root, result);
  assert.equal(rel, 'runs/finalize/LOCAL_CHECK.md');
  const md = fs.readFileSync(path.join(root, rel), 'utf8');
  assert.match(md, /Result: \*\*PASS\*\* \(exit 0\)/);
  assert.match(md, /smoke ok/);
});

test('a failing check becomes a repair failure in the solution eval format', async () => {
  // test project: the console bridge refused every request in containers
  const root = project('echo "UI page did not show its content: /clients" >&2\nexit 3\n');
  const result = await lc.runLocalCheck(root, lc.localCheckScript(root, 'linux'));
  assert.equal(result.ok, false);
  assert.equal(result.code, 3);
  const failure = lc.localCheckFailure(result);
  assert.equal(failure.name, 'local::check_solution_local');
  assert.equal(failure.command, 'scripts/check_solution_local.sh');
  assert.equal(failure.code, 3);
  assert.match(failure.output, /failed on the developer's machine \(exit 3\)/);
  assert.match(failure.output, /UI page did not show its content: \/clients/);
});

test('a check that runs too long is stopped and fails', async () => {
  const root = project('sleep 5\n');
  const result = await lc.runLocalCheck(root, lc.localCheckScript(root, 'linux'), { timeoutMs: 200 });
  assert.equal(result.ok, false);
  assert.equal(result.timedOut, true);
  assert.equal(result.code, 124);
  assert.match(lc.localCheckFailure(result).output, /timed out/);
});

test('local check: files the run leaves visible to git fail it, so the repair ignores them', () => {
  const { withLeftovers } = require('../finalize-local-check');
  const ok = { ok: true, code: 0, output: 'smoke passed', rel: 'scripts/check_solution_local.sh' };
  const before = new Set(['notes.md']);
  // B2B: setup --oidc wrote the private realm import with the local passwords under .runtime/
  const after = new Set(['notes.md', '.runtime/oidc/leadintel-realm.json', '.env.oidc']);
  const r = withLeftovers(ok, before, after);
  assert.equal(r.ok, false);
  assert.equal(r.code, 3);
  assert.deepEqual(r.leftovers, ['.env.oidc', '.runtime/oidc/leadintel-realm.json']);
  assert.match(r.output, /git does not ignore[\s\S]*\.runtime\/oidc\/leadintel-realm\.json/);
  assert.equal(withLeftovers(ok, before, new Set(['notes.md'])), ok);
  assert.equal(withLeftovers(ok, null, after), ok);  // no git: nothing to compare
});

test('finalize: the Harper documents left uncommitted go with the release, nothing else of the developer', () => {
  const { uncommittedHarperDocs } = require('../finalize-verify');
  const { execFileSync } = require('child_process');
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'clike-fin-'));
  const put = (rel, text) => { fs.mkdirSync(path.dirname(path.join(root, rel)), { recursive: true }); fs.writeFileSync(path.join(root, rel), text); };
  execFileSync('git', ['init', '-q'], { cwd: root });
  put('docs/harper/lane-guides/python.md', '# v2\n');
  execFileSync('git', ['add', '.'], { cwd: root });
  execFileSync('git', ['-c', 'user.email=a@b', '-c', 'user.name=t', 'commit', '-qm', 'init'], { cwd: root });
  put('docs/harper/lane-guides/python.md', '# v3\n');
  put('docs/inputs/v3/IDEA_EXTEND_R3.md', '# R3\n');
  put('docs/inputs/v3/.DS_Store', 'x');
  put('.mcp.json', '{}');
  put('HOWTO_CONSOLE.md', '# mine\n');
  assert.deepEqual(uncommittedHarperDocs(root).sort(), ['docs/harper/lane-guides/python.md', 'docs/inputs/v3/IDEA_EXTEND_R3.md']);
  fs.rmSync(root, { recursive: true, force: true });
});
