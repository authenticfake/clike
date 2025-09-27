const vscode = require('vscode');
const path = require('path');

// --- Harper payload helpers (core files / IDEA.md) ---

/** Read a text file from the VS Code workspace as UTF-8 (best-effort). */
async function readTextUtf8(uri) {
  try {
    const data = await vscode.workspace.fs.readFile(uri);
    // Fatal=false: tolerate mixed encodings / dirty bytes
    return new TextDecoder('utf-8', { fatal: false }).decode(data);
  } catch (err) {
    console.error('[harper] readTextUtf8 error:', err);
    return null;
  }
}

/** Try to load IDEA.md from the given project root. */
async function loadMd(projectRootUri, fileName) {
  try {
    const ideaUri = vscode.Uri.joinPath(projectRootUri, fileName);
    return await readTextUtf8(ideaUri);
  } catch (err) {
    console.warn('[harper] IDEA.md not found in project root:', err);
    return null;
  }
}

/**
 * If request.core lists relative paths, read them and attach a map filename->content.
 * Non-blocking errors (missing files) are logged and skipped.
 */
async function attachCoreBlobs(projectRootUri, coreList) {
  const out = {};
  if (!Array.isArray(coreList)) return out;
  console.log("attachCoreBlobs coreList", coreList)
  for (const rel of coreList) {
    try {
      const uri = vscode.Uri.joinPath(projectRootUri, rel);
      const txt = await readTextUtf8(uri);
      if (txt != null) out[rel] = txt;
    } catch (e) {
      console.warn('[harper] skip core file:', rel, e);
    }
  }
  return out;
}

// projectRootUri: URI del progetto "attivo" (quello creato con /init nome)
async function buildHarperBody(phase, {
  mode, model, profileHint, docRoot, core, attachments, flags, runId, historyScope
}, projectRootUri) {
   const _docRoot =  vscode.Uri.joinPath(projectRootUri, 'docs', 'harper');

  // 1) Allegati/file core
  const idea_md = await loadMd(_docRoot, 'IDEA.md');           // null se non presente
  const core_blobs = await attachCoreBlobs(_docRoot, core || []);

  // 2) Body retro-compatibile + nuovi campi opzionali
  return {
    cmd: phase,                 // e.g., "spec", "plan", ...
    mode: mode || 'harper',
    model,
    profileHint: profileHint ?? null,
    docRoot: docRoot || 'docs/harper',
    core: Array.isArray(core) ? core : [],
    attachments: Array.isArray(attachments) ? attachments : [],
    flags: flags || { neverSendSourceToCloud: true, redaction: true },
    runId: runId || crypto.randomUUID(),
    historyScope: historyScope || 'singleModel',

    // --- NEW (optional, safe to ignore server-side if unknown) ---
    idea_md,        // contains IDEA.md text if available
    core_blobs      // { "IDEA.md": "...", "path/other.txt": "..." }
  };
}

module.exports = {

  buildHarperBody
};
