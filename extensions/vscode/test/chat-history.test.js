const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('fs');
const os = require('os');
const path = require('path');

const { listConversations, archiveCurrent, openConversation, deleteConversation, currentFile } = require('../chat-history');

const line = (role, content, ts) => JSON.stringify({ ts, mode: 'harper', role, content, model: 'auto' });

function sessions(lines) {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'clike-history-'));
  if (lines) fs.writeFileSync(path.join(dir, 'harper.jsonl'), lines.join('\n') + '\n');
  return dir;
}

test('New chat archives the conversation instead of deleting it', () => {
  const dir = sessions([line('user', '/spec', 1000), line('assistant', '✔ SPEC done', 2000)]);
  assert.deepEqual(listConversations(dir, 'harper').current, { id: 'current', title: '/spec', first_ts: 1000, last_ts: 2000, count: 2 });
  const id = archiveCurrent(dir, 'harper');
  assert.ok(id);
  assert.equal(fs.existsSync(currentFile(dir, 'harper')), false);
  const list = listConversations(dir, 'harper');
  assert.equal(list.current, null);
  assert.deepEqual(list.archived.map((c) => [c.id, c.title, c.count]), [[id, '/spec', 2]]);
  // an empty conversation is not archived
  assert.equal(archiveCurrent(dir, 'harper'), null);
});

test('reopening a conversation archives the current one; nothing is lost', () => {
  const dir = sessions([line('user', 'first question', 1000)]);
  const first = archiveCurrent(dir, 'harper');
  fs.writeFileSync(currentFile(dir, 'harper'), line('user', 'second question', 5000) + '\n');
  openConversation(dir, 'harper', first);
  const list = listConversations(dir, 'harper');
  assert.equal(list.current.title, 'first question');
  assert.deepEqual(list.archived.map((c) => c.title), ['second question']);
  // newest first; same start time gets its own id
  fs.writeFileSync(currentFile(dir, 'harper'), line('user', 'third', 9000) + '\n');
  archiveCurrent(dir, 'harper');
  assert.deepEqual(listConversations(dir, 'harper').archived.map((c) => c.title), ['third', 'second question']);
});

test('ids are checked: no path outside the archive', () => {
  const dir = sessions([line('user', 'x', 1)]);
  assert.throws(() => openConversation(dir, 'harper', '../harper'), /invalid conversation id/);
  assert.throws(() => deleteConversation(dir, 'harper', 'nope'), /no conversation/);
  const id = archiveCurrent(dir, 'harper');
  deleteConversation(dir, 'harper', id);
  assert.deepEqual(listConversations(dir, 'harper').archived, []);
  // modes are separate
  assert.deepEqual(listConversations(dir, 'free'), { current: null, archived: [] });
});
