const vscode = require('vscode');
const cp = require('child_process');
const path = require('path');
// --- Helpers: estrazione/salvataggio Technology Constraints ---
function extractTechConstraintsYaml(ideaText) {
  if (!ideaText) return null;
  // 1) cerca blocchi fenced ```yaml ... ``` che contengono "tech_constraints:"
  const fenced = [...ideaText.matchAll(/```yaml([\s\S]*?)```/gi)];
  for (const m of fenced) {
    const body = (m[1] || "").trim();
    if (/^\s*tech_constraints\s*:/m.test(body)) {
      return body;
    }
  }

  // 2) fallback: se non c'è fence, prova a prendere dalla riga "tech_constraints:" in poi
  const idx = ideaText.search(/^\s*tech_constraints\s*:/m);
  if (idx >= 0) {
    // prendi fino alla prossima intestazione "## " o fine file oppure fino a un blocco ``` successivo
    const tail = ideaText.slice(idx);
    const stopFence = tail.search(/```/);
    const stopHeader = tail.search(/^\s*##\s+/m);

    let end = tail.length;
    if (stopFence >= 0) end = Math.min(end, stopFence);
    if (stopHeader >= 0) end = Math.min(end, stopHeader);

    return tail.slice(0, end).trim();
  }

  return null;
}

async function saveTechConstraintsYaml(docRootUri, yamlText) {
  if (!yamlText) return null;
  const uri = vscode.Uri.joinPath(docRootUri, 'TECH_CONSTRAINTS.yaml');
  const enc = new TextEncoder();
  await vscode.workspace.fs.writeFile(uri, enc.encode(yamlText.trim() + '\n'));
  return uri;
}
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

/**
 * Rimuove il blocco YAML "tech_constraints" dal testo dell'idea iniziale.
 * Ritorna il testo modificato senza il blocco.
 */
function removeTechConstraintsYaml(ideaText) {
  if (!ideaText) return ""; // Ritorna stringa vuota se l'input non c'è

  let modifiedText = ideaText;

  // 1) Cerca blocchi fenced ```yaml ... ``` che contengono "tech_constraints:"
  const fencedMatches = [...ideaText.matchAll(/(```yaml[\s\S]*?```)/gi)];
  for (const m of fencedMatches) {
    const fullMatch = m[0]; // L'intero blocco ```yaml ... ```
    const body = (m[1] || "").trim(); // Il contenuto all'interno del fence
    if (/^\s*tech_constraints\s*:/m.test(body)) {
      // Trovato il blocco da rimuovere.
      // Sostituiamo l'intero blocco ```yaml ... ``` con una stringa vuota.
      // Usiamo una regex che matchi solo la prima occorrenza per sicurezza, 
      // ma dato che extractTechConstraintsYaml si ferma al primo match, dovremmo essere coerenti.
      modifiedText = modifiedText.replace(fullMatch, "").trim();
      modifiedText = modifiedText.replace(/^##\s+Technology Constraints\s*/m, "").trim();
      console.log("removeTechConstraintsYaml done");

      return modifiedText; // Usciamo subito come fa extractTechConstraintsYaml
    }
  }

  // 2) Fallback: se non c'è fence, prova a prendere dalla riga "tech_constraints:" in poi
  const searchMatch = ideaText.match(/^(\s*tech_constraints\s*:[\s\S]*?)(?=\s*##\s+|\s*```|$)/m);
  
  if (searchMatch) {
    // searchMatch[1] contiene la parte "tech_constraints:..." fino al prossimo "##" o "```" o fine.
    const fullMatch = searchMatch[1];
    
    // Rimuoviamo la parte trovata. Usiamo il testo originale per la sostituzione.
    // L'uso di una regex `search` non è l'ideale per l'eliminazione perché non cattura sempre 
    // lo spazio circostante in modo pulito, ma l'approccio con matchAll/match semplifica.
    modifiedText = modifiedText.replace(fullMatch, "").trim();
    return modifiedText;
  }
  
  // Se non è stato trovato nulla, ritorna il testo originale non modificato.
  return modifiedText;
}

// Esempio d'uso (ipotetico)
/*
const ideaTextWithYaml = "...\n## Idea\n...\n```yaml\ntech_constraints:\n - cpu: 4 cores\n```\n...\n";
const cleanedText = removeTechConstraintsYaml(ideaTextWithYaml);
console.log(cleanedText); // Il testo senza il blocco YAML
*/

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
      && (name.toLowerCase().endsWith('.md') || name.toLowerCase().endsWith('.markdown') 
          || name.toLowerCase().endsWith('.txt') || name.toLowerCase().endsWith('.1st') 
          || name.toLowerCase().endsWith('.yaml') || name.toLowerCase().endsWith('.yml'))
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

function execSyncSafe(cmd, cwd) {
  try {
    return cp.execSync(cmd, { cwd, stdio: ['ignore', 'pipe', 'ignore'] })
      .toString('utf8')
      .trim() || null;
  } catch {
    return null;
  }
}

function normalizeRepoUrl(raw) {
  if (!raw) return null;
  // git@github.com:org/repo.git -> https://github.com/org/repo
  const ssh = raw.match(/^git@([^:]+):(.+?)(\.git)?$/);
  if (ssh) {
    const host = ssh[1];
    const repo = ssh[2].replace(/\.git$/, '');
    return `https://${host}/${repo}`;
  }
  // https urls: drop .git
  if (/^https?:\/\//i.test(raw)) return raw.replace(/\.git$/, '');
  // file:// o altre -> restituisci com'è
  return raw;
}

async function detectRepoUrl(projectRootUri) {
  // 1) VS Code Git API
  try {
    const gitExt = vscode.extensions.getExtension('vscode.git');
    if (gitExt) {
      const git = gitExt.isActive ? gitExt.exports : await gitExt.activate();
      const api = git.getAPI(1);
      const repo = api.repositories.find(r =>
        r.rootUri.fsPath === projectRootUri.fsPath ||
        projectRootUri.fsPath.startsWith(r.rootUri.fsPath)
      );
      const remote = repo?.state?.remotes?.[0]?.fetchUrl || repo?.state?.remotes?.[0]?.pushUrl;
      const n = normalizeRepoUrl(remote);
      if (n) return n;
    }
  } catch {
    // ignore
  }

  // 2) fallback: git config
  const cwd = projectRootUri.fsPath;
  const raw = execSyncSafe('git config --get remote.origin.url', cwd);
  const n = normalizeRepoUrl(raw);
  if (n) return n;

  return null;
}

// projectRootUri: URI del progetto "attivo" (quello creato con /init nome)
async function buildHarperBody(phase, payload, projectRootUri) {
  const _docRoot =  vscode.Uri.joinPath(projectRootUri, 'docs', 'harper');

    // 1) Allegati/file core
  var idea_md = await loadMd(_docRoot, 'IDEA.md');

  try {
    // NEW: estrai e salva TECH_CONSTRAINTS.yaml a partire da IDEA.md (sovrascrive)
    if (phase === 'spec' && idea_md) {
      const yaml = extractTechConstraintsYaml(idea_md || '');
      if (yaml) {
        await saveTechConstraintsYaml(_docRoot, yaml);
        // assicura che rientri nei core (senza duplicati)
        const core = Array.isArray(payload["core"]) ? payload["core"] : [];
        if (!core.some(n => n.toLowerCase() === 'tech_constraints.yaml')) {
          core.push('TECH_CONSTRAINTS.yaml');
        }
        payload["core"] = core;
     }
     if (idea_md)
      idea_md = removeTechConstraintsYaml(idea_md);

    } 
    else if (phase === 'kit') {
       // 0) repoUrl
      const repoUrl = await detectRepoUrl(projectRootUri);
        if (repoUrl) payload["repoUrl"] = repoUrl;
    }
  } catch (err) {
    console.warn('[CLike] saveTechConstraintsYaml failed:', err);
  }
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
      return [];
    case "plan":
      return ["SPEC.md", "TECH_CONSTRAINTS.yaml"];
    case "kit":
      return ["SPEC.md", "PLAN.md", "KIT.md", "TECH_CONSTRAINTS.yaml"];
    case "build":
      return ["SPEC.md", "PLAN.md", "KIT.md", "BUILD_REPORT.md", "TECH_CONSTRAINTS.yaml"];
    case "finalize":
      return ["SPEC.md", "PLAN.md", "KIT.md", "BUILD_REPORT.md", "RELEASE_NOTES.md", "TECH_CONSTRAINTS.yaml"];
    default:
      return ["IDEA.md"];
  }
}


module.exports = {

  buildHarperBody,
  extractUserMessages,
  defaultCoreForPhase
};
