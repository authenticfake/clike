'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const { safePanel, safePost, panelPost } = require('../safe-panel');

// a VS Code webview panel: `webview` throws once the panel is disposed, onDidDispose fires then
function fakePanel() {
  let disposed = false;
  const sent = [];
  const listeners = [];
  const webview = { postMessage: (m) => { if (disposed) throw new Error('Webview is disposed'); sent.push(m); return Promise.resolve(true); }, html: '' };
  return {
    sent,
    dispose() { disposed = true; listeners.forEach((fn) => fn()); },
    onDidDispose(fn) { listeners.push(fn); return { dispose() {} }; },
    get webview() { if (disposed) throw new Error('Webview is disposed'); return webview; },
    reveal() { return 'revealed'; },
  };
}

test('a run goes on after the chat is closed: with no chat open its messages are dropped, nothing throws', async () => {
  // cdl-pipeline: the autopilot stopped right after REQ-009's KIT when the chat panel was closed
  const raw = fakePanel();
  const panel = safePanel(raw);
  const post = safePost(panel.webview.postMessage.bind(panel.webview));
  const own = panelPost(panel);
  assert.equal(await panel.webview.postMessage({ type: 'echo' }), true);
  assert.equal(await post({ type: 'echo' }), true);
  assert.equal(await own({ type: 'echo' }), true);
  assert.equal(panel.reveal(), 'revealed');
  assert.equal(panel.disposed, false);
  raw.dispose();
  assert.equal(panel.disposed, true);
  assert.equal(await panel.webview.postMessage({ type: 'busy', on: false }), false);
  assert.equal(await post({ type: 'busy', on: false }), false);
  assert.equal(await own({ type: 'busy', on: false }), false);
  assert.equal(raw.sent.length, 3);
});

test('a panel without onDidDispose finds out it is closed from the webview getter', async () => {
  const raw = fakePanel();
  delete raw.onDidDispose;
  const panel = safePanel(raw);
  raw.dispose();
  assert.equal(await panel.webview.postMessage({ type: 'echo' }), false);
  assert.equal(panel.disposed, true);
});

test('the chat reopened during a run follows it: the closed panel relays to the one open now', async () => {
  let current = null;
  const rawOld = fakePanel();
  const old = safePanel(rawOld, { successor: () => current });
  current = old;
  // the chat adds its wrapper on the webview (busy suppression, run card): the relay goes through it
  const own = panelPost(old);
  old.webview.postMessage = (m) => own(m);
  rawOld.dispose();
  current = null; // the chat's onDidDispose
  assert.equal(await old.webview.postMessage({ type: 'echo', message: 'lost' }), false);

  const rawNew = fakePanel();
  const reopened = safePanel(rawNew, { successor: () => current });
  current = reopened;
  const wrapped = [];
  const ownNew = panelPost(reopened);
  reopened.webview.postMessage = (m) => { wrapped.push(m.type); return ownNew(m); };

  // the run's handlers still hold the old panel: their messages reach the reopened chat
  assert.equal(await old.webview.postMessage({ type: 'echo', message: 'eval REQ-009' }), true);
  assert.equal(await own({ type: 'runProgress' }), true);
  assert.deepEqual(rawNew.sent.map((m) => m.type), ['echo', 'runProgress']);
  assert.deepEqual(wrapped, ['echo', 'runProgress']);
  assert.equal(rawOld.sent.length, 0);

  // the reopened chat closed too: dropped again, never back to itself or to a closed one
  rawNew.dispose();
  assert.equal(await old.webview.postMessage({ type: 'echo' }), false);
  assert.equal(await reopened.webview.postMessage({ type: 'echo' }), false);
});

test('a successor that throws or is the panel itself is no relay target', async () => {
  const raw = fakePanel();
  let self = null;
  const panel = safePanel(raw, { successor: () => self });
  self = panel;
  raw.dispose();
  assert.equal(await panel.webview.postMessage({ type: 'echo' }), false);
  const raw2 = fakePanel();
  const p2 = safePanel(raw2, { successor: () => { throw new Error('boom'); } });
  raw2.dispose();
  assert.equal(await p2.webview.postMessage({ type: 'echo' }), false);
});
