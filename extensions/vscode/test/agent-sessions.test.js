'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');

const { extractSessionId, sessionToResume, rememberSession, resumeArgs, SESSION_TTL_MS } = require('../agent-sessions');
const { withMachineReadableOutput } = require('../local-agent-executors');

test('the session id of a run: Claude events, Codex thread.started', () => {
  const claude = '{"type":"system","subtype":"init","session_id":"c-1"}\nnot json\n{"type":"result","session_id":"c-1","result":"ok"}';
  assert.equal(extractSessionId('claude_code', claude), 'c-1');
  const codex = '{"type":"thread.started","thread_id":"t-9"}\n{"type":"turn.completed"}';
  assert.equal(extractSessionId('gpt_codex', codex), 't-9');
  assert.equal(extractSessionId('gpt_codex', claude), '');
  assert.equal(extractSessionId('claude_code', ''), '');
});

test('a session is resumed for the same REQ and executor within the TTL only', () => {
  const now = 1_000_000_000;
  let store = rememberSession({}, 'req-004', 'claude_code', 'c-1', now);
  assert.equal(sessionToResume(store, 'REQ-004', 'claude_code', now + 1000), 'c-1');
  assert.equal(sessionToResume(store, 'REQ-004', 'gpt_codex', now), '');
  assert.equal(sessionToResume(store, 'REQ-005', 'claude_code', now), '');
  assert.equal(sessionToResume(store, 'REQ-004', 'claude_code', now + SESSION_TTL_MS + 1), '');
  store = rememberSession(store, 'REQ-009', 'gpt_codex', 't-2', now + SESSION_TTL_MS + 1);
  assert.deepEqual(Object.keys(store), ['REQ-009:gpt_codex'], 'expired sessions are dropped');
});

test('Claude resumes forked, keeping its other arguments', () => {
  const args = resumeArgs('claude_code', ['--allowedTools', 'Bash(x)', '-p', '--permission-mode', 'acceptEdits'], 'c-1');
  assert.deepEqual(args, ['--allowedTools', 'Bash(x)', '-p', '--permission-mode', 'acceptEdits', '--resume', 'c-1', '--fork-session']);
  const final = withMachineReadableOutput('claude_code', args);
  assert.ok(final.includes('--output-format'));
  assert.deepEqual(resumeArgs('claude_code', ['-p', '--resume', 'x'], 'c-1'), ['-p', '--resume', 'x']);
});

test('Codex resumes with exec resume, the sandbox as config, JSON events kept', () => {
  const args = resumeArgs('gpt_codex', ['exec', '--sandbox', 'workspace-write', '--skip-git-repo-check', '--model', 'm'], 't-9');
  assert.deepEqual(args, ['exec', 'resume', 't-9', '--json', '-c', 'sandbox_mode="workspace-write"', '--skip-git-repo-check', '--model', 'm']);
  assert.deepEqual(withMachineReadableOutput('gpt_codex', args), args, 'no second --json is inserted');
  assert.deepEqual(resumeArgs('gpt_codex', ['exec', '--sandbox=read-only'], 't-9'), ['exec', 'resume', 't-9', '--json', '-c', 'sandbox_mode="read-only"']);
  assert.deepEqual(resumeArgs('gpt_codex', ['exec', '--sandbox', 'x'], ''), ['exec', '--sandbox', 'x']);
});
