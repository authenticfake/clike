const vscode = require('vscode');
const fs = require('fs');
const path = require('path');

function _readIfExists(root, relPath) {
  try {
    const p = path.join(root, relPath);
    return fs.existsSync(p) ? fs.readFileSync(p, 'utf8') : '';
  } catch { return ''; }
}

// semplice chunking per headings e lunghezza; niente dipendenze esterne
function chunkText(text, maxLen = 1200) {
  if (!text || typeof text !== 'string') return [];
  const lines = text.split(/\r?\n/);
  const chunks = [];
  let buf = [];
  let size = 0;
  for (const ln of lines) {
    if (/^#{1,6}\s/.test(ln) && size > 0) {
      chunks.push(buf.join('\n')); buf = []; size = 0;
    }
    buf.push(ln);
    size += ln.length + 1;
    if (size >= maxLen) { chunks.push(buf.join('\n')); buf = []; size = 0; }
  }
  if (buf.length) chunks.push(buf.join('\n'));
  return chunks;
}

async function gatherRagChunks(projectRootUri, relPaths = ["IDEA.md","SPEC.md"]) {
  const docsRoot = vscode.Uri.joinPath(projectRootUri, 'docs', 'harper');
  const rootFs = docsRoot.fsPath;
  const out = [];
  for (const name of relPaths) {
    const content = _readIfExists(rootFs, name);
    if (content) {
      const chunks = chunkText(content, 1400).slice(0, 16); // cap a 16 chunks per doc
      chunks.forEach((c, i) => out.push({ name, idx: i, text: c }));
    }
  }
  return out;
}

module.exports.gatherRagChunks = module.exports.gatherRagChunks || gatherRagChunks;
