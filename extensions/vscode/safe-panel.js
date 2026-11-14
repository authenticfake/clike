'use strict';
// The CLike chat panel as the handlers use it, safe once the panel is closed: a run nobody watches
// any more (an /autopilot, an --fix loop) goes on. VS Code throws "Webview is disposed" on
// `panel.webview` after the panel is closed (cdl-pipeline: the autopilot stopped right after
// REQ-009's KIT when the chat was closed). Once closed, the panel relays its messages to the chat
// opened after it (`successor`), so a reopened chat follows the run live; with no chat open they
// are dropped.

const DISPOSED_WEBVIEW = Object.freeze({
  postMessage: () => Promise.resolve(false),
  asWebviewUri: (uri) => uri,
  cspSource: '',
  html: '',
  options: {},
  onDidReceiveMessage: () => ({ dispose() {} }),
});

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

/**
 * @param panel the VS Code webview panel
 * @param {{ successor?: () => any }} options `successor`: the chat panel open now (the relay target
 *   once this one is closed; itself or a closed one is never a target)
 */
function safePanel(panel, { successor } = {}) {
  let disposed = false;
  let proxy = null;
  try { panel.onDidDispose(() => { disposed = true; }); } catch { /* the getter below finds out */ }
  const next = () => {
    try {
      const p = successor && successor();
      return p && p !== proxy && !p.disposed ? p : null;
    } catch {
      return null;
    }
  };
  const relay = Object.freeze({
    ...DISPOSED_WEBVIEW,
    postMessage: (...args) => {
      const p = next();
      return p ? safePost((...a) => p.webview.postMessage(...a))(...args) : Promise.resolve(false);
    },
  });
  proxy = new Proxy(panel, {
    get(target, prop) {
      if (prop === 'disposed') return disposed;
      if (prop === 'webview') {
        if (disposed) return relay;
        try { return target.webview; } catch { disposed = true; return relay; }
      }
      const value = Reflect.get(target, prop, target);
      return typeof value === 'function' ? value.bind(target) : value;
    },
  });
  return proxy;
}

/**
 * The panel's own postMessage (before any wrapper the chat adds), safe: while the panel is open
 * it posts to its webview, once closed it goes through the relay to the chat open now.
 */
function panelPost(panel) {
  const own = safePost(panel.webview.postMessage.bind(panel.webview));
  return (...args) => (panel.disposed ? panel.webview.postMessage(...args) : own(...args));
}

module.exports = { safePanel, safePost, panelPost, DISPOSED_WEBVIEW };
