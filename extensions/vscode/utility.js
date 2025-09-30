const vscode = require('vscode');
const path = require('path');


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
async function attachCoreBlobs(docUri, coreList) {
  const blobs = {};
  const rootUri = docUri || vscode.Uri.file(path.join('docs', 'harper'));
  
  // Utilizza l'API di VS Code per leggere la directory
  const entries = await vscode.workspace.fs.readDirectory(rootUri);

  // Normalizza lista di 'prefix' a partire dai core (IDEA.md -> 'IDEA')
  const wanted = (coreList || []).map(n => path.parse(n).name); // ['IDEA','SPEC',...]

  for (const base of wanted) {
    // 1) il file dichiarato (es. IDEA.md), se esiste, ha precedenza
    const declaredEntry = entries.find(([name, type]) => 
        type === vscode.FileType.File && name.toLowerCase() === `${base.toLowerCase()}.md`);

    if (declaredEntry) {
      const name = declaredEntry[0];
      const fullUri = vscode.Uri.joinPath(rootUri, name);
      const content = await vscode.workspace.fs.readFile(fullUri);
      blobs[`${base}.md`] = Buffer.from(content).toString('utf8');
    }

    // 2) autodiscovery: tutti i file che iniziano con 'base' (stesso prefisso), esclusi già presi
    const prefixed = entries.filter(([name, type]) => 
      type === vscode.FileType.File
      && name.toLowerCase().startsWith(base.toLowerCase())
      && (name.toLowerCase().endsWith('.md') || name.toLowerCase().endsWith('.markdown') || name.toLowerCase().endsWith('.txt') || name.toLowerCase().endsWith('.1st'))
      && name.toLowerCase() !== `${base.toLowerCase()}.md`
    );

    for (const [name, type] of prefixed) {
      const fullUri = vscode.Uri.joinPath(rootUri, name);
      const key = name; // manteniamo nome completo (es. IDEA_verAndrea.md)
      try {
        const content = await vscode.workspace.fs.readFile(fullUri);
        blobs[key] = Buffer.from(content).toString('utf8');
      } catch (err) {
        console.warn('attachCoreBlobs read error:', fullUri.fsPath, err);
      }
    }
  }

  return blobs;
}

// projectRootUri: URI del progetto "attivo" (quello creato con /init nome)
async function buildHarperBody(phase, payload, projectRootUri) {
  const _docRoot =  vscode.Uri.joinPath(projectRootUri, 'docs', 'harper');

    // 1) Allegati/file core
  const idea_md = await loadMd(_docRoot, 'IDEA.md');           // null se non presente
  const core_blobs = await attachCoreBlobs(_docRoot, payload["core"] || []);
  payload["idea_md"] = idea_md;
  payload["core_blobs"] = core_blobs;
  // 2) Body retro-compatibile + nuovi campi opzionali
  return payload;
}


function extractUserMessages(sessionData) {
    // 1. Filtra l'array per mantenere solo gli elementi con role 'user'.
    const userMessages = sessionData.filter(log => log.role === 'user');

    // 2. Mappa l'array filtrato in un nuovo array con solo i campi 'role' e 'content'.
    const formattedMessages = userMessages.map(log => ({
        role: log.role,
        content: log.content
    }));

    return formattedMessages;
}

function defaultCoreForPhase(phase) {
  switch (phase) {
    case "spec":
      return ["IDEA.md"];
    case "plan":
      return ["IDEA.md", "SPEC.md"];
    case "kit":
      return ["IDEA.md", "SPEC.md", "PLAN.md", "KIT.md"];
    case "build":
      return ["IDEA.md", "SPEC.md", "PLAN.md", "KIT.md", "BUILD_REPORT.md"];
    case "finalize":
      return ["IDEA.md", "SPEC.md", "PLAN.md", "KIT.md", "BUILD_REPORT.md", "RELEASE_NOTES.md"];
    default:
      return ["IDEA.md"];
  }
}

module.exports = {

  buildHarperBody,
  extractUserMessages,
  defaultCoreForPhase
};
