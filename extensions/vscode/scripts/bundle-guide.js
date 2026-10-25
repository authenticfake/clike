'use strict';
// Packaging step (vscode:prepublish): CLike's documentation goes inside the extension as guide/,
// indexed by the Memory panel when CLike starts (memory-guide.js).
const fs = require('fs');
const path = require('path');
const { listGuideFiles } = require('../memory-guide');

const ext = path.join(__dirname, '..');
const repo = path.join(ext, '..', '..');
const target = path.join(ext, 'guide');

fs.rmSync(target, { recursive: true, force: true });
const files = listGuideFiles(path.join(repo, 'docs'));
files.push({ path: 'CLIKE_README.md', abs: path.join(repo, 'README.md') });
let copied = 0;
for (const f of files) {
  if (!fs.existsSync(f.abs)) continue;
  const dst = path.join(target, ...f.path.split('/'));
  fs.mkdirSync(path.dirname(dst), { recursive: true });
  fs.copyFileSync(f.abs, dst);
  copied += 1;
}
console.log(`CLike guide: ${copied} file(s) in guide/`);
