const assert = require('assert');
const test = require('node:test');

const {
  buildLocalAgentSpawn,
  pickWindowsPathCandidate,
  resolveLocalAgentCommandPath,
} = require('../local-agent-executors');

const WIN_CMD = 'C:\\Users\\dev\\AppData\\Roaming\\npm\\claude.cmd';
const WIN_CMD_SPACES = 'C:\\Users\\John Doe\\AppData\\Roaming\\npm\\claude.cmd';

// --- buildLocalAgentSpawn: Windows .cmd/.bat go through cmd.exe ---
test('Windows .cmd is executed through cmd.exe /d /s /c with the script as a single arg', () => {
  const { file, args } = buildLocalAgentSpawn(WIN_CMD, ['--version'], 'win32');
  assert.strictEqual(file, 'cmd.exe');
  assert.deepStrictEqual(args, ['/d', '/s', '/c', WIN_CMD, '--version']);
});

test('Windows .cmd path with spaces is passed as one argument (no manual splitting)', () => {
  const { file, args } = buildLocalAgentSpawn(WIN_CMD_SPACES, ['-p', '--model', 'opus'], 'win32');
  assert.strictEqual(file, 'cmd.exe');
  assert.deepStrictEqual(args, ['/d', '/s', '/c', WIN_CMD_SPACES, '-p', '--model', 'opus']);
});

test('Windows .bat is executed through cmd.exe', () => {
  const { file, args } = buildLocalAgentSpawn('C:\\tools\\codex.bat', ['exec'], 'win32');
  assert.strictEqual(file, 'cmd.exe');
  assert.deepStrictEqual(args, ['/d', '/s', '/c', 'C:\\tools\\codex.bat', 'exec']);
});

test('Windows .exe runs directly (no cmd.exe wrapper)', () => {
  const { file, args } = buildLocalAgentSpawn('C:\\tools\\claude.exe', ['--version'], 'win32');
  assert.strictEqual(file, 'C:\\tools\\claude.exe');
  assert.deepStrictEqual(args, ['--version']);
});

// --- buildLocalAgentSpawn: macOS/Linux run the command directly ---
test('macOS runs the command directly', () => {
  const { file, args } = buildLocalAgentSpawn('claude', ['--version'], 'darwin');
  assert.strictEqual(file, 'claude');
  assert.deepStrictEqual(args, ['--version']);
});

test('Linux runs the command directly', () => {
  const { file, args } = buildLocalAgentSpawn('codex', ['exec'], 'linux');
  assert.strictEqual(file, 'codex');
  assert.deepStrictEqual(args, ['exec']);
});

// --- pickWindowsPathCandidate: prefer .cmd > .exe > .bat, never .ps1 ---
test('PATH resolution prefers claude.cmd over claude.ps1 and claude.exe', () => {
  const whereOutput = [
    'C:\\Users\\dev\\AppData\\Roaming\\npm\\claude.ps1',
    'C:\\Users\\dev\\AppData\\Roaming\\npm\\claude.cmd',
    'C:\\Users\\dev\\AppData\\Roaming\\npm\\claude.exe',
  ].join('\r\n');
  assert.strictEqual(
    pickWindowsPathCandidate(whereOutput),
    'C:\\Users\\dev\\AppData\\Roaming\\npm\\claude.cmd'
  );
});

test('PATH resolution falls back to .exe when no .cmd is present and never picks .ps1', () => {
  const whereOutput = 'C:\\x\\claude.ps1\r\nC:\\x\\claude.exe';
  assert.strictEqual(pickWindowsPathCandidate(whereOutput), 'C:\\x\\claude.exe');
});

test('PATH resolution returns empty when only a .ps1 is available', () => {
  assert.strictEqual(pickWindowsPathCandidate('C:\\x\\claude.ps1'), '');
  assert.strictEqual(pickWindowsPathCandidate(''), '');
});

// --- resolveLocalAgentCommandPath ---
test('Windows explicit .cmd absolute path is accepted as-is', () => {
  assert.strictEqual(
    resolveLocalAgentCommandPath(WIN_CMD, { platform: 'win32', log: () => {} }),
    WIN_CMD
  );
});

test('Windows explicit .ps1 with no sibling executable resolves to empty (refused)', () => {
  // The sibling .cmd/.exe do not exist on this test machine, so .ps1 is refused.
  assert.strictEqual(
    resolveLocalAgentCommandPath('C:\\does\\not\\exist\\claude.ps1', { platform: 'win32', log: () => {} }),
    ''
  );
});

test('POSIX leaves the command unchanged (direct PATH resolution at spawn time)', () => {
  assert.strictEqual(resolveLocalAgentCommandPath('claude', { platform: 'darwin' }), 'claude');
  assert.strictEqual(resolveLocalAgentCommandPath('/usr/local/bin/codex', { platform: 'linux' }), '/usr/local/bin/codex');
});

// --- end-to-end of the resolution + spawn decision for an explicit .cmd ---
test('explicit Windows .cmd path resolves then spawns via cmd.exe wrapper', () => {
  const resolved = resolveLocalAgentCommandPath(WIN_CMD_SPACES, { platform: 'win32', log: () => {} });
  const { file, args } = buildLocalAgentSpawn(resolved, ['--version'], 'win32');
  assert.strictEqual(file, 'cmd.exe');
  assert.deepStrictEqual(args, ['/d', '/s', '/c', WIN_CMD_SPACES, '--version']);
});
