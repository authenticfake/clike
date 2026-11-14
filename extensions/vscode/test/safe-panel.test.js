'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const { safePanel, safePost } = require('../safe-panel');

// a VS Code webview panel: `webview` throws once the panel is disposed
function fakePanel() {
  let disposed = false;
  const sent = [];
  const webview = { postMessage: (m) => { if (disposed) throw new Error('Webview is disposed'); sent.push(m); return Promise.resolve(true); }, html: '' };
  return {
    sent,
    dispose() { disposed = true; },
    get webview() { if (disposed) throw new Error('Webview is disposed'); return webview; },
    reveal() { return 'revealed'; },
  };
}

test('a run goes on after the chat is closed: its messages are dropped, nothing throws', async () => {
  // cdl-pipeline: the autopilot stopped right after REQ-009's KIT when the chat panel was closed
  const raw = fakePanel();
  const panel = safePanel(raw);
  const post = safePost(panel.webview.postMessage.bind(panel.webview));
  assert.equal(await panel.webview.postMessage({ type: 'echo' }), true);
  assert.equal(await post({ type: 'echo' }), true);
  assert.equal(panel.reveal(), 'revealed');
  raw.dispose();
  assert.equal(await panel.webview.postMessage({ type: 'busy', on: false }), false);
  assert.equal(await post({ type: 'busy', on: false }), false);
  assert.equal(raw.sent.length, 2);
});
