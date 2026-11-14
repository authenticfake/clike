'use strict';
// The CLike chat panel as the handlers use it, safe once the panel is closed: a run nobody watches
// any more (an /autopilot, an --fix loop) goes on and its messages are dropped. VS Code throws
// "Webview is disposed" on `panel.webview` after the panel is closed (cdl-pipeline: the autopilot
// stopped right after REQ-009's KIT when the chat was closed).

const DISPOSED_WEBVIEW = Object.freeze({
  postMessage: () => Promise.resolve(false),
  asWebviewUri: (uri) => uri,
  cspSource: '',
  html: '',
  options: {},
  onDidReceiveMessage: () => ({ dispose() {} }),
});

function safePanel(panel) {
  return new Proxy(panel, {
    get(target, prop) {
      if (prop === 'webview') {
        try { return target.webview; } catch { return DISPOSED_WEBVIEW; }
      }
      const value = Reflect.get(target, prop, target);
      return typeof value === 'function' ? value.bind(target) : value;
    },
  });
}

// A postMessage that never throws: false when the webview is gone.
function safePost(post) {
  return (...args) => {
    try {
      return Promise.resolve(post(...args)).catch(() => false);
    } catch {
      return Promise.resolve(false);
    }
  };
}

module.exports = { safePanel, safePost, DISPOSED_WEBVIEW };
