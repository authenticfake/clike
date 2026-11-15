'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('fs');
const path = require('path');

// The extension README is shown by VS Code, the Marketplace and Open VSX from inside the .vsix: vsce rewrites
// relative links from the repository root, so a link leaving the package (../../docs/…) or an image under
// extensions/vscode/ ends up dead. Links and images are absolute.
test('the extension README has only absolute links and images', () => {
  const text = fs.readFileSync(path.join(__dirname, '..', 'README.md'), 'utf8');
  const targets = [...text.matchAll(/\]\(([^)\s]+)\)/g), ...text.matchAll(/<img[^>]+src="([^"]+)"/g)].map((m) => m[1]);
  const relative = targets.filter((t) => !/^(https?:|mailto:|#)/.test(t));
  assert.deepEqual(relative, []);
});
