const vscode = require('vscode');
const cp = require('child_process');
const path = require('path');
const { gatherRagChunks } = require('./rag.js');

const out = vscode.window.createOutputChannel('Clike.utility');
const crypto = require('crypto');
// usa Node.js fs per calcolare la size di un file
const fs = require('fs');
const myhttp = require("http");
const myhttps = require("https");
const VALID_STATUSES = ['open', 'in_progress', 'done', 'deferred'];

/** Logger that accepts N args and JSON-serializes objects. */
function mkLog(out) {
  return (...args) => {
    const line = args.map(a => {
      if (typeof a === 'string') return a;
      try { return JSON.stringify(a, null, 2); } catch { return String(a); }
    }).join(' ');
    if (out?.appendLine) out.appendLine(line); else console.log(line);
  };
}

/**
 * Funzione di logging personalizzata che scrive su entrambi i canali.
 * @param {...any} args Messaggi o oggetti da loggare.
 */
function log(...args) {
    // 1. Log nella console standard per il debug.
    console.log(...args); 
    
    // 2. Log nel canale di output di VS Code.
    out.appendLine(args.map(arg => {
        // Converte ogni argomento in stringa per l'output.
        if (typeof arg === 'object' && arg !== null) {
            return JSON.stringify(arg, null, 2);
        }
        return String(arg);
    }).join(' ')); 
}


/** sha256 of a Buffer */
function hashBuf(buf) {
  return crypto.createHash('sha256').update(buf).digest('hex');
}

/** Read entire tree (files only) under a Uri directory (depth-first). */
async function readTree(dirUri) {
  const list = [];
  async function walk(u) {
    const entries = await vscode.workspace.fs.readDirectory(u);
    for (const [name, fileType] of entries) {
      const child = vscode.Uri.joinPath(u, name);
      if (fileType === vscode.FileType.Directory) {
        await walk(child);
      } else if (fileType === vscode.FileType.File) {
        list.push(child);
      }
    }
  }
  await walk(dirUri);
  return list;
}

/** Copy a file (read → write). */
async function copyFile(from, to) {
  const data = await vscode.workspace.fs.readFile(from);
  await vscode.workspace.fs.writeFile(to, data);
}

/**
 * Recursively copy src -> dest with conflict strategies.
 * Returns action records and (optionally) pairs for diff previews.
 *
 * strategy:
 *  - 'folder'   : copy into unique folder promoted/<REQ>_<ts> (no conflicts)
 *  - 'suffix'   : write conflicts as <name>.incoming-<REQ>-<ts>
 *  - 'backup'   : rename existing -> <name>.bak-<ts>, then write new
 *  - 'skip'     : keep existing, skip new
 *  - 'overwrite': replace existing
 */
async function copyTreeWithConflicts(srcRoot, destRoot, { strategy, reqId, ts, log }) {
  const actions = [];
  const filesToCommit = [] //file to be commit after the promotion
  const diffs = []; // [{left: existingUri, right: incomingUri, label}]

  async function ensureDir(u) {
    try { await vscode.workspace.fs.createDirectory(u); } catch {}
  }
  async function isExisting(u) {
    try { await vscode.workspace.fs.stat(u); return true; } catch { return false; }
  }

  const srcFiles = await readTree(srcRoot);
  for (const src of srcFiles) {
    // Dest path mirrors relative structure of src under srcRoot
    const rel = src.path.slice(srcRoot.path.length);
    const normalizedRel = rel.replace(/^\/+/, '');

    // Exclude non-promotable staging families from promotion
    if (shouldExcludePromotionRelativePath(normalizedRel)) {
      actions.push({ op: 'skip_excluded', from: src.path, rel: normalizedRel });
      continue;
    }

    const dst = vscode.Uri.joinPath(destRoot, normalizedRel);

    await ensureDir(vscode.Uri.joinPath(dst, '..'));

    const dstExists = await isExisting(dst);
    if (!dstExists) {
      await copyFile(src, dst);
      actions.push({ op: 'copy', from: src.path, to: dst.path });
      filesToCommit.push(dst.fsPath || dst.path);
      continue;
    }

    // Conflict: compare file content
    const [a, b] = await Promise.all([vscode.workspace.fs.readFile(src), vscode.workspace.fs.readFile(dst)]);
    const same = hashBuf(a) === hashBuf(b);
    if (same) {
      actions.push({ op: 'skip_identical', to: dst.path });
      continue;
    }

    // Conflict resolution
    if (strategy === 'overwrite') {
      await vscode.workspace.fs.writeFile(dst, a);
      actions.push({ op: 'overwrite', to: dst.path });
      filesToCommit.push(dst.fsPath || dst.path);
    } else if (strategy === 'skip') {
      actions.push({ op: 'skip_conflict', to: dst.path });
    } else if (strategy === 'backup') {
      const name = dst.path.split('/').pop();
      const parent = vscode.Uri.joinPath(dst, '..');
      const backup = vscode.Uri.joinPath(parent, `${name}.bak-${ts}`);
      await vscode.workspace.fs.rename(dst, backup, { overwrite: true });
      await vscode.workspace.fs.writeFile(dst, a);
      actions.push({ op: 'backup_then_write', old: dst.path, backup: backup.path });
      filesToCommit.push(dst.fsPath || dst.path);
      // Diff: existing backup vs new dest
      diffs.push({ left: backup, right: dst, label: `${name} (backup vs new)` });
    } else if (strategy === 'suffix') {
      const name = dst.path.split('/').pop();
      const parent = vscode.Uri.joinPath(dst, '..');
      const incoming = vscode.Uri.joinPath(parent, `${name}.incoming-${reqId}-${ts}`);
      await vscode.workspace.fs.writeFile(incoming, a);
      actions.push({ op: 'write_suffix', to: incoming.path });
      // Diff: existing vs incoming
      diffs.push({ left: dst, right: incoming, label: `${name} (existing vs incoming)` });
    } else if (strategy === 'folder') {
      // 'folder' uses a unique destRoot, so we shouldn't hit conflicts—still handle gracefully
      await vscode.workspace.fs.writeFile(dst, a);
      actions.push({ op: 'copy_folder_mode', to: dst.path });
      filesToCommit.push(dst.fsPath || dst.path);
    }
  }

  //log(`[copyTreeWithConflicts] actions=${actions.length}, diffs=${diffs.length} files=${filesToCommit.length}`);
  return { actions, diffs, filesToCommit };
}

/** QuickPick strategy selector with helpful descriptions. */
async function pickPromotionStrategy() {
  const items = [
    { label: 'folder',    detail: 'Copy into promoted/<REQ>_<timestamp> (safest; no conflicts in place).', picked: true },
    { label: 'suffix',    detail: 'Keep existing; write conflicts as *.incoming-<REQ>-<timestamp> and open diffs.' },
    { label: 'backup',    detail: 'Backup existing as *.bak-<timestamp> and write new version; open diffs.' },
    { label: 'skip',      detail: 'Keep existing; skip conflicting incoming files.' },
    { label: 'overwrite', detail: 'Replace existing files (destructive).' }
  ];
  const sel = await vscode.window.showQuickPick(items, {
    title: 'Promotion strategy',
    placeHolder: 'Choose how to handle destination conflicts',
    canPickMany: false,
    ignoreFocusOut: true
  });
  return sel?.label || null;
}

/** Open diff editors for conflicting files (if any). */
async function openDiffs(diffs) {
  for (const d of diffs) {
    const title = d.label || 'Diff';
    try {
      await vscode.commands.executeCommand('vscode.diff', d.left, d.right, title, { preview: true });
    } catch (e) {
      console.warn('[promote] diff open failed:', e?.message || String(e));
    }
  }
}
function shouldExcludePromotionRelativePath(relPath) {
  const normalized = String(relPath || '')
    .replace(/\\/g, '/')
    .replace(/^\/+/, '');

  if (!normalized) return false;

  return (
    normalized === 'docs' ||
    normalized.startsWith('docs/') ||
    normalized === 'ci' ||
    normalized.startsWith('ci/')
  );
}
/**
 * Promote KIT sources into the workspace with conflict-safe strategies.
 * - Writes a JSON promotion manifest under runs/kit/<REQ>/promotion_manifest_<ts>.json
 * - Returns { manifestUri, actions, diffs, filesToCommit }
 */
async function promoteReqSources(projectRootUri, reqId, strategy = 'folder', out) {
  const log = mkLog(out);

  if (!projectRootUri) {
    vscode.window.showErrorMessage('[promote] Workspace root not provided.');
    return null;
  }

  const srcDir = vscode.Uri.joinPath(projectRootUri, 'runs', 'kit', reqId);
  try {
    await vscode.workspace.fs.stat(srcDir);
  } catch {
    vscode.window.showWarningMessage(`[promote] No KIT src to promote for ${reqId}`);
    return null;
  }

  // Resolve destination root
  const ts = new Date().toISOString().replace(/[:.]/g, '-');
  let destRoot = vscode.Uri.joinPath(projectRootUri, '.');

  if (strategy === 'folder') {
    destRoot = vscode.Uri.joinPath(projectRootUri, 'promoted', `${reqId}_${ts}`);
    await vscode.workspace.fs.createDirectory(destRoot);
  }

  // usiamo *diffs* (non diff) e lo propaghiamo con lo stesso nome
  const { actions, diffs, filesToCommit } = await copyTreeWithConflicts(
    srcDir,
    destRoot,
    { strategy, reqId, ts, log }
  );
  // --- PULIZIA FISICA DEL FILE SYSTEM ---
  // Definiamo una funzione ricorsiva interna per eliminare __pycache__ e .pyc
  const cleanDirRecursively = async (uri) => {
    const entries = await vscode.workspace.fs.readDirectory(uri);
    
    for (const [name, type] of entries) {
      const childUri = vscode.Uri.joinPath(uri, name);
      
      if (type === vscode.FileType.Directory) {
        if (name === '__pycache__') {
          // Elimina l'intera cartella pycache
          await vscode.workspace.fs.delete(childUri, { recursive: true, useTrash: false });
        } else {
          // Continua la ricerca nelle sottocartelle
          await cleanDirRecursively(childUri);
        }
      } else if (type === vscode.FileType.File) {
        if (name.endsWith('.pyc')) {
          await vscode.workspace.fs.delete(childUri, { useTrash: false });
        }
        if (name.startsWith('.DS_Store')) {
          await vscode.workspace.fs.delete(childUri, { useTrash: false });
        }
      }
    }
  };
  // --- ESCLUDI cartella ci/ e i suoi file (LTC.json, HOWTO.md) dal risultato ---
  // --- NUOVO: Rimuovi __pycache__ e file .pyc dalla destinazione ---
  // NOTA: Questa operazione pulisce solo la destinazione, se sono stati copiati
  
  // Rimuovi tutte le cartelle __pycache__ che potresti trovare
  // (Potrebbe essere complesso se ce ne sono molte, questo è un esempio semplificato)
  // Se la strategia di copia ha un'azione specifica per directory, potresti iterare su actions.
  
  // Per semplicità, ci concentriamo sull'esclusione da filesToCommit e manifest

  // ------------------------------------------------------------------------
  const ciDir = vscode.Uri.joinPath(destRoot, 'ci');
  try {
    await vscode.workspace.fs.delete(ciDir, { recursive: true, useTrash: false });
  } catch {
    // se non esiste, ignora
  }
  await cleanDirRecursively(destRoot);
  const filteredFilesToCommit = (filesToCommit || []).filter((uri) => {
    const p = (uri.fsPath ?? uri.path ?? '').toLowerCase();
    
    // Esclusione esistente per la cartella 'ci'
    const isCI = p.includes('/ci/') || p.includes('\\ci\\');
    
    // NUOVE Esclusioni per Python
    const isPyc = p.endsWith('.pyc');
    const isPycache = p.includes('/__pycache__/') || p.includes('\\__pycache__\\');
    
    return !isCI && !isPyc && !isPycache;
  });

  // Build/write manifest
  const manifest = {
    req_id: reqId,
    strategy,
    timestamp: ts,
    src_root: srcDir.fsPath ?? srcDir.path,
    dest_root: destRoot.fsPath ?? destRoot.path,
    total_actions: actions.length,
    actions
  };

  const manifestDir = vscode.Uri.joinPath(projectRootUri, 'runs', 'kit', reqId);
  try {
    await vscode.workspace.fs.createDirectory(manifestDir);
  } catch {}

  const manifestUri = vscode.Uri.joinPath(
    manifestDir,
    `promotion_manifest_${ts}.json`
  );
  await vscode.workspace.fs.writeFile(
    manifestUri,
    Buffer.from(JSON.stringify(manifest, null, 2), 'utf8')
  );
  const uniqFilesToCommit = [...new Set(
  (filteredFilesToCommit || [])
    .map(p => String(p || '').trim())
    .filter(Boolean)
  )];

  return { manifestUri, actions, diffs, filesToCommit: uniqFilesToCommit };
}


/**
 * End-to-end flow with UI:
 * - Ask REQ id (if not provided)
 * - Ask promotion strategy
 * - Show progress & run copy
 * - Show result notification
 * - Offer to open manifest and diffs
 */
async function runPromotionFlow(projectRootUri, reqId, out) {
  const log = mkLog(out);
  const filesToCommit = [];

  try {
    // Step 1: REQ id
    let target = (reqId || '').trim();
    if (!target) {
      target = await vscode.window.showInputBox({
        title: 'REQ to promote',
        placeHolder: 'e.g. REQ-009',
        validateInput: (v) => (!v?.trim() ? 'Required' : undefined)
      });
      if (!target) return;
    }

    // Step 2: Strategy
    const strategy = await pickPromotionStrategy();
    if (!strategy) return;

    // Step 3: Progress UI
    const result = await vscode.window.withProgress({
      location: vscode.ProgressLocation.Notification,
      title: `Promoting ${target} (${strategy})`,
      cancellable: false
    }, async (progress) => {
      progress.report({ message: 'Scanning and copying files...' });
      return await promoteReqSources(projectRootUri, target, strategy, out);
    });

    if (!result) return;

    const { manifestUri, actions, diffs, filesToCommit: _filesToCommit } = result;

    if (_filesToCommit && _filesToCommit.length) {
      filesToCommit.push(..._filesToCommit);
      log(`[runPromotionFlow] filesToCommit=${filesToCommit.length}`);
    }

    // Step 4: Notify & post-actions
    const choice = await vscode.window.showInformationMessage(
      `[promote] ${target}: ${actions.length} action(s) — strategy=${strategy}`,
      'Open manifest',
      diffs?.length ? `Open ${diffs.length} diffs` : undefined
    );

    if (choice === 'Open manifest') {
      await vscode.window.showTextDocument(manifestUri);
    } else if (choice && choice.startsWith('Open') && diffs?.length) {
      await openDiffs(diffs);
    }
  } catch (e) {
    log('[runPromotionFlow] ERROR:', e?.message || String(e));
    vscode.window.showErrorMessage(`[promote] ${e?.message || e}`);
  }

  return filesToCommit;
}




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
  const entries = await vscode.workspace.fs.readDirectory(rootUri);

  const wanted = (coreList || []).map((name) => {
    const parsed = path.parse(String(name || '').trim());
    return {
      original: String(name || '').trim(),
      stem: parsed.name,
      ext: (parsed.ext || '').toLowerCase(),
    };
  });

  for (const item of wanted) {
    const stemLower = item.stem.toLowerCase();
    const declaredExt = item.ext;

    // 1) Read the explicitly requested file only.
    const declaredEntry = entries.find(([name, type]) => {
      if (type !== vscode.FileType.File) return false;
      return name.toLowerCase() === `${stemLower}${declaredExt}`;
    });

    if (declaredEntry) {
      const fileName = declaredEntry[0];
      const fullUri = vscode.Uri.joinPath(rootUri, fileName);
      const content = await vscode.workspace.fs.readFile(fullUri);
      blobs[fileName] = Buffer.from(content).toString('utf8');
    }

    // 2) Prefix autodiscovery for sibling variants of the same stem,
    //    but never re-add the exact declared file under a fake alias.
    const prefixed = entries.filter(([name, type]) => {
      if (type !== vscode.FileType.File) return false;

      const nameLower = name.toLowerCase();
      const sameDeclaredFile = nameLower === `${stemLower}${declaredExt}`;
      if (sameDeclaredFile) return false;

      return (
        nameLower.startsWith(stemLower) &&
        (
          nameLower.endsWith(".md") ||
          nameLower.endsWith(".markdown") ||
          nameLower.endsWith(".txt") ||
          nameLower.endsWith(".1st") ||
          nameLower.endsWith(".yaml") ||
          nameLower.endsWith(".yml") ||
          nameLower.endsWith(".json")
        )
      );
    });

    for (const [name] of prefixed) {
      const fullUri = vscode.Uri.joinPath(rootUri, name);
      try {
        const content = await vscode.workspace.fs.readFile(fullUri);
        blobs[name] = Buffer.from(content).toString('utf8');
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
      mkLog(`repo ${repo}`);
      const remote = repo?.state?.remotes?.[0]?.fetchUrl || repo?.state?.remotes?.[0]?.pushUrl;
      mkLog(`remote ${remote}`);
      const n = normalizeRepoUrl(remote);
      mkLog(`n ${n}`);
      if (n) return n;
    }
  } catch (e) {
    mkLog(`Error while fetching repo URL: ${e}`);  // and ignore    
  }
  // 2) fallback: git config
  const cwd = projectRootUri.fsPath;
  const raw = execSyncSafe('git config --get remote.origin.url', cwd);
  const n = normalizeRepoUrl(raw);
  if (n) return n;

  return null;
}

async function detectRepositoryContext(projectRootUri) {
  const workspaceFolder = projectRootUri?.fsPath || null;
  const fallback = {
    git_detected: false,
    repo_root: workspaceFolder,
    branch: null,
    workspace_folder: workspaceFolder,
    repo_url: null,
  };

  if (!projectRootUri?.fsPath) {
    return fallback;
  }

  // 1) Prefer VS Code Git API because it already knows the active repositories.
  try {
    const gitExt = vscode.extensions.getExtension('vscode.git');
    if (gitExt) {
      const git = gitExt.isActive ? gitExt.exports : await gitExt.activate();
      const api = git.getAPI(1);
      const repo = api.repositories.find(r =>
        projectRootUri.fsPath === r.rootUri.fsPath ||
        projectRootUri.fsPath.startsWith(r.rootUri.fsPath)
      );

      if (repo?.rootUri?.fsPath) {
        const remote =
          repo?.state?.remotes?.[0]?.fetchUrl ||
          repo?.state?.remotes?.[0]?.pushUrl ||
          null;

        const branch =
          repo?.state?.HEAD?.name ||
          execSyncSafe('git rev-parse --abbrev-ref HEAD', repo.rootUri.fsPath) ||
          null;

        return {
          git_detected: true,
          repo_root: repo.rootUri.fsPath,
          branch,
          workspace_folder: workspaceFolder,
          repo_url: normalizeRepoUrl(remote),
        };
      }
    }
  } catch (e) {
    log('[CLike] detectRepositoryContext Git API failed:', e?.message || String(e));
  }

  // 2) Fallback to git CLI from the current workspace folder.
  try {
    const repoRoot = execSyncSafe('git rev-parse --show-toplevel', projectRootUri.fsPath);
    if (!repoRoot) {
      return fallback;
    }

    const branch = execSyncSafe('git rev-parse --abbrev-ref HEAD', repoRoot) || null;
    const rawRemote = execSyncSafe('git config --get remote.origin.url', repoRoot);
    const repoUrl = normalizeRepoUrl(rawRemote);

    return {
      git_detected: true,
      repo_root: repoRoot,
      branch,
      workspace_folder: workspaceFolder,
      repo_url: repoUrl,
    };
  } catch (e) {
    log('[CLike] detectRepositoryContext CLI fallback failed:', e?.message || String(e));
    return fallback;
  }
}
// --- PLAN.md helpers: update only the "### REQ-IDs Table" section (markdown table) ---

/**
 * Estrae la sottosezione testuale tra un'intestazione H3 specifica e la successiva H3 (o EOF).
 */
function _sliceSection(text, h3Title) {
  const startRe = new RegExp(`^###\\s+${h3Title}\\s*$`, 'mi');
  const nextH3 = /^###\s+/mi;
  const m = text.match(startRe);
  if (!m) return { found: false, full: text, head: text, section: '', tail: '' };

  const startIdx = m.index;
  // dal punto dopo la riga H3
  const afterH3Idx = text.indexOf('\n', startIdx) + 1;
  const rest = text.slice(afterH3Idx);
  const next = rest.search(nextH3);
  const sectionEnd = (next >= 0) ? (afterH3Idx + next) : text.length;

  const head = text.slice(0, afterH3Idx);
  const section = text.slice(afterH3Idx, sectionEnd);
  const tail = text.slice(sectionEnd);
  return { found: true, full: text, head, section, tail };
}

/**
 * Parse di una tabella markdown "pipe" (header allineato con ---) e ritorno di array di oggetti.
 * Richiede almeno una colonna "REQ-ID" (case-insensitive). Accetta colonne extra.
 */
function _parseMarkdownTable(sectionText) {
  const lines = sectionText.split(/\r?\n/).map(s => s.trim());
  // trova inizio tabella (riga header con | ... |) e riga separatori
  let start = -1, sep = -1;
  for (let i = 0; i < lines.length; i++) {
    if (/^\|.+\|$/.test(lines[i])) {
      // la riga successiva deve essere separatore --- | --- | ...
      if (i + 1 < lines.length && /^\|\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)+\|?$/.test(lines[i + 1])) {
        start = i; sep = i + 1; break;
      }
    }
  }
  if (start < 0) return { header: [], rows: [], start: -1, sep: -1, end: -1 };

  const headerCells = lines[start].slice(1, -1).split('|').map(s => s.trim());
  const rows = [];
  let end = lines.length;
  for (let i = sep + 1; i < lines.length; i++) {
    if (!/^\|.+\|$/.test(lines[i])) { end = i; break; }
    const cols = lines[i].slice(1, -1).split('|').map(s => s.trim());
    rows.push(cols);
  }
  return { header: headerCells, rows, start, sep, end, lines };
}

/**
 * Dato un testo di sezione tabellare e una mappa { REQ-ID -> status }, ritorna la sezione aggiornata.
 * Se la tabella non esiste, ne crea una minima.
 */
function _updateReqTableSection(sectionText, statusMap) {
  const parsed = _parseMarkdownTable(sectionText);
  // normalizza il nome colonna REQ-ID e Status
  const header = parsed.header.map(h => h.toLowerCase());
  let reqIdx = header.findIndex(h => /^req-?id$/.test(h));
  if (reqIdx < 0) reqIdx = header.findIndex(h => /req/.test(h)); // fallback
  let statusIdx = header.findIndex(h => /^status$/.test(h));
  if (parsed.start < 0 || reqIdx < 0) {
    // tabella assente → creiamone una base con 3 colonne
    const hdr = ['REQ-ID', 'Title', 'Status'];
    const sep = ['---', '---', '---'];
    const rows = Object.entries(statusMap).map(([id, st]) => `| ${id} |  | ${st} |`);
    return [
      `| ${hdr.join(' | ')} |`,
      `| ${sep.join(' | ')} |`,
      ...rows
    ].join('\n') + '\n';
  }

  // Costruiamo una mappa per sostituzioni (case-insensitive su REQ)
  const lowerKeys = Object.keys(statusMap).reduce((acc, k) => {
    acc[k.toLowerCase()] = statusMap[k]; return acc;
  }, {});
  // Se manca "Status", aggiungiamo la colonna in coda
  const addStatusCol = (statusIdx < 0);
  const newHeader = parsed.header.slice();
  if (addStatusCol) newHeader.push('Status');

  const outRows = [];
  for (const cols of parsed.rows) {
    const c = cols.slice();
    const reqVal = (c[reqIdx] || '').toString().trim();
    const key = reqVal.toLowerCase();
    if (lowerKeys[key]) {
      if (statusIdx < 0) {
        c.push(lowerKeys[key]);
      } else {
        c[statusIdx] = lowerKeys[key];
      }
    } else if (addStatusCol) {
      c.push(c[statusIdx] || 'open'); // default per righe esistenti
    }
    outRows.push('| ' + c.join(' | ') + ' |');
  }

  // Aggiungi eventuali nuove righe per REQ non presenti
  const existingReqs = new Set(parsed.rows.map(r => (r[reqIdx] || '').toString().trim().toLowerCase()));
  for (const [id, st] of Object.entries(statusMap)) {
    if (!existingReqs.has(id.toLowerCase())) {
      // cerchiamo anche la colonna "Title" se esiste
      const titleIdx = parsed.header.map(h => h.toLowerCase()).findIndex(h => /^title$/.test(h));
      const newCols = [];
      for (let i = 0; i < newHeader.length; i++) {
        if (i === reqIdx) newCols[i] = id;
        else if (i === statusIdx || (addStatusCol && i === newHeader.length - 1)) newCols[i] = st;
        else if (i === titleIdx) newCols[i] = '';
        else newCols[i] = '';
      }
      outRows.push('| ' + newCols.join(' | ') + ' |');
    }
  }

  const sepLine = '| ' + newHeader.map(() => '---').join(' | ') + ' |';
  const headerLine = '| ' + newHeader.join(' | ') + ' |';

  const rebuilt = [headerLine, sepLine, ...outRows].join('\n') + '\n';
  // Rimonta: rimpiazziamo l'area tabellare evitando di toccare altro testo della sezione
  const before = parsed.lines.slice(0, parsed.start).join('\n');
  const after  = parsed.lines.slice(parsed.end).join('\n');
  const glueA = before ? (before + '\n') : '';
  const glueB = after  ? ('\n' + after)  : '';
  return glueA + rebuilt + glueB;
}

/**
 * Check whether a given REQ-ID exists in docs/harper/plan.json.
 *
 * - reqId: string like "REQ-001"
 * - workspaceRoot: vscode.WorkspaceFolder or undefined
 *
 * Returns:
 *   - true  if the REQ-ID exists in plan.json
 *   - false if not found or plan.json missing/invalid
 *
 * Shows a VS Code error message if the REQ is missing.
 */
async function ensureReqIdInPlan(reqId, plan) {
  const trimmed = (reqId || '').trim();
 
  out.appendLine(`ensureReqIdInPlan(${trimmed})`);
  if (!trimmed) {
    vscode.window.showErrorMessage('Missing REQ-ID for this command.');
    return false;
  }

  if (!plan || !Array.isArray(plan.reqs)) {
    vscode.window.showErrorMessage(
      `Unable to read "${PLAN_JSON_REL_PATH}". Make sure PLAN has been run and plan.json is present.`
    );
    return false;
  }
  
  const upper = trimmed.toUpperCase();
  const exists = plan.reqs.some((r) => {
    const rid = (r && r.id) ? String(r.id).trim().toUpperCase() : '';
    return rid === upper;
  });

  if (!exists) {

    vscode.window.showErrorMessage(
      `REQ-ID "${trimmed}" not found.`
    );
    return false;
  }


  return true;
}

async function runKitCommand(plan, cmdArgs) {
  out.appendLine(`[runKitCommand] raw cmdArgs=${JSON.stringify(cmdArgs)}`);

  let targetReqId = null;

  if (Array.isArray(cmdArgs) && cmdArgs.length > 0) {
    targetReqId = String(cmdArgs[0] || '').trim().toUpperCase() || null;
  } else if (typeof cmdArgs === 'string') {
    targetReqId = cmdArgs.trim().toUpperCase() || null;
  } else {
    targetReqId = null;
  }

  out.appendLine(`[runKitCommand] normalized targetReqId=${targetReqId}`);

  if (!targetReqId) {
    targetReqId = findNextOpenReq(plan);
    if (!targetReqId) {
      vscode.window.showWarningMessage('No open REQ found in plan.json.');
      return;
    }
    out.appendLine(`[runKitCommand] fallback next open req=${targetReqId}`);
  } else {
    out.appendLine(`[runKitCommand] explicit targetReqId=${targetReqId}`);
    const result = await ensureReqIdInPlan(targetReqId, plan);
    if (!result) return;
  }

  out.appendLine(`[runKitCommand] targetReqId validated=${targetReqId}`);

  const candidate = (plan.reqs || []).find(r => r.id === targetReqId);
  const deps = Array.isArray(candidate?.dependsOn) ? candidate.dependsOn : [];
  const byId = Object.fromEntries((plan.reqs || []).map(r => [r.id, r]));
  const depsOk = deps.every(d => byId[d] && byId[d].status === 'done');

  if (!depsOk) {
    const pick = await vscode.window.showWarningMessage(
      `Dependencies for ${targetReqId} are not all 'done'. Proceed anyway?`,
      'Proceed', 'Cancel'
    );
    if (pick !== 'Proceed') return;
  }

  return targetReqId;
}



async function runEvalGateCommand( plan, cmdArgs) {
  out.appendLine(`[runEvalGateCommand] ${cmdArgs}`);
  // cmdArgs: string dopo "/kit", es. "", "REQ-001"
  let targetReqId = (cmdArgs || '').trim() || null;
  if (!targetReqId) {
    targetReqId = findNextReq(plan, "in_progress");
    if (!targetReqId) {
      vscode.window.showWarningMessage('No pending REQ found in plan.json with status in_progress');
      return;
    }
  } else {
    const result = await ensureReqIdInPlan(targetReqId, plan); 
    if (!result) return;
  }
  // (opzionale) avvisa se deps non done
  const candidate = (plan.reqs || []).find(r => r.id === targetReqId);
  const deps = Array.isArray(candidate?.dependsOn) ? candidate.dependsOn : [];
  const byId = Object.fromEntries((plan.reqs||[]).map(r=>[r.id,r]));
  const depsOk = deps.every(d => byId[d] && byId[d].status === 'done');
  if (!depsOk) {
    const pick = await vscode.window.showWarningMessage(
      `Dependencies for ${targetReqId} are not all 'done'. Proceed anyway?`,
      'Proceed', 'Cancel'
    );
    if (pick !== 'Proceed') return;
  }
  return targetReqId;
}


/**
 * Aggiorna stato REQ (done) e sincronizza plan.json + PLAN.md.
 * - Se `plan` non è passato o non valido, rilegge la versione attuale dal disco.
 * - `targetReqId` è la REQ chiusa dal /kit corrente.
 * - `out` è un OutputChannel (opzionale), altrimenti usa console.log.
 */
async function saveKitCommand(projectRootUri, plan, targetReqId, out) {
  const log = (msg) => {
    if (out && typeof out.appendLine === 'function') out.appendLine(msg);
    else console.log(msg);
  };

  log(`[saveKitCommand] target=${targetReqId}`);

  // 1) Carica plan se mancante
  let effectivePlan = plan;
  if (!effectivePlan || !Array.isArray(effectivePlan.reqs)) {
    effectivePlan = await readPlanJson(projectRootUri);
    if (!effectivePlan || !Array.isArray(effectivePlan.reqs)) {
      vscode.window.showErrorMessage(`[saveKitCommand] plan.json not found or invalid; aborting update. for ${targetReqId}.`);
      log('[saveKitCommand] plan.json not found or invalid; aborting update.');
      //return;
    }
  }

  // 2) Aggiorna stato REQ → done
  const ok = setReqStatus(effectivePlan, targetReqId, 'in_progress');
  if (!ok) {
    log(`[saveKitCommand] REQ ${targetReqId} not found in plan.json; no update performed.`);
    // Continuiamo comunque a scrivere il plan attuale, ma senza cambiare snapshot/table
  }
  //updatePlanSnapshot(effectivePlan);

  // 3) Scrivi plan.json
  await writePlanJson(projectRootUri, effectivePlan);
  log(`[plan.json updated] ${targetReqId}`);

  // 4) Aggiorna PLAN.md in place (Snapshot + Tabella)
  await updatePlanMdInPlace(projectRootUri, effectivePlan);
  log(`[PLAN.md updated] ${targetReqId}`);

  // 5) Notifica
  try {
    vscode.window.showInformationMessage(`KIT completed for ${targetReqId}.`);
  } catch {
    // no-op headless
  }
}

function setManyReqStatus(plan, updates /* [{id, status}, ...] */) {
  if (!plan || !Array.isArray(plan.reqs) || !Array.isArray(updates)) return 0;
  let changed = 0;
  const index = new Map(plan.reqs.map((r, i) => [String(r?.id || '').trim().toUpperCase(), i]));
  for (const u of updates) {
    const key = String(u?.id || '').trim().toUpperCase();
    const i = index.get(key);
    if (i == null) continue;
    const newStatus = normalizeStatus(u?.status);
    if (plan.reqs[i].status !== newStatus) {
      plan.reqs[i].status = newStatus;
      changed++;
    }
  }
  if (changed > 0) updatePlanSnapshot(plan);
  return changed;
}
/**
 * /eval → non cambia stato (ma potresti marcare 'in_progress' se non lo è)
 */
async function saveEvalCommand(projectRootUri, plan, targetReqId, report, out) {
  const log = (m) => (out?.appendLine ? out.appendLine(m) : console.log(m));
  log(`[saveEvalCommand] target=${targetReqId}`);
  let effectivePlan = plan || await readPlanJson(projectRootUri);
  if (!effectivePlan || !Array.isArray(effectivePlan.reqs)) return;
  

  const report_file = await persistReports(projectRootUri, "eval", report, out, targetReqId)
  log(`[saveEvalCommand] persistReports done`);
  // opzionale: se non è ancora in_progress → mettilo
  const req = effectivePlan.reqs.find(r => (r.id || '').toUpperCase() === targetReqId.toUpperCase());
  if (req && (req.status || '').toLowerCase() === 'open') {
    setReqStatus(effectivePlan, targetReqId, 'in_progress');
    await writePlanJson(projectRootUri, effectivePlan);
    await updatePlanMdInPlace(projectRootUri, effectivePlan);
    log(`[PLAN synced to in_progress] ${targetReqId}`);
  }
  return report_file
}
// In utility.js (o dove hai definito persistReports)
async function persistReports(projectRootUri, phase, rep, out, fallbackReqId = '') {
  const vscode = require('vscode');
  const path = require('path');

  // Logger che accetta N argomenti e serializza oggetti
  const log = (...args) => {
    const line = args.map(a => (typeof a === 'string' ? a : (() => { try { return JSON.stringify(a, null, 2); } catch { return String(a); } })())).join(' ');
    if (out?.appendLine) out.appendLine(line); else console.log(line);
  };

  // Normalizza root in Uri
  const rootUri = (projectRootUri && projectRootUri.scheme)
    ? projectRootUri
    : vscode.Uri.file(String(projectRootUri || '.'));

  // Sanity
  if (!rep) {
    log('[persistReports] ERROR: rep is missing');
    vscode.window.showErrorMessage('[persistReports] rep is missing');
    return;
  }
  // Normalizza naming dai possibili alias
  const req_id = String(
    rep.req_id || rep.reqId || rep.request_id || fallbackReqId || 'REQ-UNKNOWN'
  ).trim().toUpperCase();
  const profile = rep.profile || rep.profile_path || null;
  const mode = rep.mode || 'auto';
  const passed = rep.passed ;//Number.isInteger(rep.passed) ? rep.passed : 0;
  const failed = rep.failed ;//Number.isInteger(rep.failed) ? rep.failed : 0;
  const cases = Array.isArray(rep.cases) ? rep.cases : [];

  // runs/<phase>/<req_id>
  const outDirUri = vscode.Uri.joinPath(rootUri, 'runs', phase, req_id);
  //log('[persistReports] outDirUri=', outDirUri);

  try { 
    await vscode.workspace.fs.createDirectory(outDirUri);
  } 
  catch (e) {
    //log('[persistReports] createDirectory warning:', e?.message || String(e));
  }

  const ts = Date.now(); // ms per uniqueness
  const fileBase = `report_${req_id}_${ts}`;

  // Costruisci JSON “persistito” (coerente con orchestrator snake_case)
    const persisted = {
      profile,
      req_id,
      mode,
      status: rep.status || rep.gate || undefined,
      gate: rep.gate || undefined,
      reason_code: rep.reason_code || undefined,
      passed,
      failed,
      passed_count: rep.passed_count,
      blocked_count: rep.blocked_count,
      warning_count: rep.warning_count,
      summary: rep.summary || undefined,
      cases: cases.map(c => ({
      name: c.name,
      passed: !!c.passed,
      code: typeof c.code === 'number' ? c.code : (typeof c.rc === 'number' ? c.rc : undefined),
      cmd: c.cmd || c.run || undefined,
      cwd: c.cwd || undefined,
      expect: typeof c.expect === 'number' ? c.expect : undefined,
      stdout: c.stdout || undefined,
      stderr: c.stderr || undefined
    }))
  };

  // Path dei file di output (URI, non stringhe)
  const jsonUri  = vscode.Uri.joinPath(outDirUri, `${fileBase}.json`);
  // Se vuoi anche il JUnit, scommenta questi due (e genera xml):
  // const junitUri = vscode.Uri.joinPath(outDirUri, `${fileBase}.junit.xml`);

  // Scrivi JSON
  try {
    const buf = Buffer.from(JSON.stringify(persisted, null, 2), 'utf8');
    await vscode.workspace.fs.writeFile(jsonUri, buf);
    log('[persistReports] wrote JSON ->', jsonUri.fsPath || jsonUri.path);
  } catch (e) {
    log('[persistReports] ERROR writing JSON:', e?.message || String(e));
    vscode.window.showErrorMessage(`[persistReports] cannot write JSON: ${e?.message || e}`);
  }
  return jsonUri
  // Se l’orchestrator ha già scritto dei file (rep.json_path, rep.junit_path), puoi opzionalmente copiarli qui.
  // Esempio (facoltativo):
  // if (rep.json_path) {
  //   try {
  //     const src = vscode.Uri.file(rep.json_path);
  //     const dst = vscode.Uri.joinPath(outDirUri, path.basename(rep.json_path));
  //     const data = await vscode.workspace.fs.readFile(src);
  //     await vscode.workspace.fs.writeFile(dst, data);
  //     log('[persistReports] copied orchestrator JSON ->', dst.fsPath);
  //   } catch (e) { log('[persistReports] copy orchestrator JSON warning:', e?.message || String(e)); }
  // }
}

/**
 * /gate → porta REQ a done e sincronizza artefatti
 */
async function saveGateCommand(projectRootUri, plan, targetReqId, report, out) {
  const log = (m) => (out?.appendLine ? out.appendLine(m) : console.log(m));
  log(`[saveGateCommand] target=${targetReqId}`);

  let effectivePlan = plan || await readPlanJson(projectRootUri);
  if (!effectivePlan || !Array.isArray(effectivePlan.reqs)) return;

  const gateVerdict = String(report?.gate || '').trim().toLowerCase();
  const gateStatus = String(report?.status || '').trim().toUpperCase();
  const isPass = gateVerdict === 'pass' && gateStatus === 'PASS';

  if (isPass) {
    if (!setReqStatus(effectivePlan, targetReqId, 'done')) {
      log(`[saveGateCommand] REQ ${targetReqId} not found in plan.json`);
    }
  } else {
    setReqStatus(effectivePlan, targetReqId, 'in_progress');
    log(`[saveGateCommand] gate not passed for ${targetReqId}; status kept as in_progress`);
  }

  await writePlanJson(projectRootUri, effectivePlan);
  await updatePlanMdInPlace(projectRootUri, effectivePlan);

  const planJsonUri = vscode.Uri.joinPath(projectRootUri, 'docs', 'harper', 'plan.json');
  const planMdUri = vscode.Uri.joinPath(projectRootUri, 'docs', 'harper', 'PLAN.md');

  const report_file = await persistReports(projectRootUri, "gate", report, out, targetReqId);

  let filesToCommit = [
    planJsonUri.fsPath,
    planMdUri.fsPath,
  ];

  if (isPass) {
    log(`[saveGateCommand] Gate passed for ${targetReqId}`);

    const choice = await vscode.window.showInformationMessage(
      `Gate passed for ${targetReqId}. Choose how to promote sources now.`,
      'Promote',
      'Skip promote'
    );

    if (choice === 'Promote') {
      const strategy = await pickPromotionStrategy();
      if (strategy) {
        const result = await promoteReqSources(projectRootUri, targetReqId, strategy, out);
        const promotedFiles = Array.isArray(result?.filesToCommit) ? result.filesToCommit : [];
        filesToCommit.push(...promotedFiles);
        log(`[saveGateCommand] promote strategy=${strategy} files=${promotedFiles.length}`);
      } else {
        log('[saveGateCommand] promotion strategy selection cancelled');
      }
    } else {
      log('[saveGateCommand] promote skipped by user');
    }

    try {
      vscode.window.showInformationMessage(`REQ ${targetReqId} marked as done.`);
    } catch {}
  } else {
    try {
      vscode.window.showWarningMessage(`Gate failed for ${targetReqId}. REQ not promoted.`);
    } catch {}
  }

  filesToCommit = [...new Set(
    filesToCommit
      .map(p => String(p || '').trim())
      .filter(Boolean)
  )];

  return {
    report_file,
    filesToCommit,
    planFiles: [planJsonUri.fsPath, planMdUri.fsPath],
  };
}


/**
 * Trova l'ultimo REQ (per mtime) sotto runs/kit, pattern "REQ-*".
 * Ritorna es. "REQ-001" o null se non presente.
 */
function resolveLatestReq(rootDir) {
  try {
    const base = path.join(rootDir, 'runs', 'kit');
    const entries = fs.readdirSync(base)
      .filter(n => /^REQ-/i.test(n))
      .map(n => ({ n, m: fs.statSync(path.join(base, n)).mtimeMs }))
      .sort((a, b) => b.m - a.m);
    return entries.length ? entries[0].n : null;
  } catch {
    return null;
  }
}

// projectRootUri: URI del progetto "attivo" (quello creato con /init nome)
async function buildHarperBody(phase, payload, projectRootUri, out) {
  const _docRoot =  vscode.Uri.joinPath(projectRootUri, 'docs', 'harper');
  // 1) Allegati/file core
  var idea_md = (phase === 'spec') ? await loadMd(_docRoot, 'IDEA.md') : null;
  try {
    // 2: estrai e salva TECH_CONSTRAINTS.yaml a partire da IDEA.md (sovrascrive)
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
      idea_md = removeTechConstraintsYaml(idea_md);
    } 
   // 3) Always attach repository metadata so the orchestrator can become repo-aware.
    const repositoryContext = await detectRepositoryContext(projectRootUri);
    repositoryContext.local_snapshot_verified = true;
    repositoryContext.github_verified = false;
    payload["repository_context"] = repositoryContext;
    
    // Keep backward compatibility with the existing repoUrl field.
    if (repositoryContext?.repo_url) {
      payload["repoUrl"] = repositoryContext.repo_url;
    }
  } catch (err) {
    log('[CLike] saveTechConstraintsYaml failed:', err);
  }
  //4) core blobs
  const core_blobs = await attachCoreBlobs(_docRoot, payload["core"] || []);
  payload["idea_md"] = idea_md;
  payload["core_blobs"] = core_blobs;

  if (phase === 'kit') {
    const requestedKit = payload["kit"] || {};
    const requestedTargets = Array.isArray(requestedKit.targets) ? requestedKit.targets : [];
    const requestedPhases = Array.isArray(requestedKit.phases) ? requestedKit.phases : ['kit'];
    const targetReqId = String(requestedTargets[0] || '').trim().toUpperCase();

    const postKitPhases = ['integrity_eval', 'promotion_hardener', 'promotion_eval'];
    const needsCandidateArtifacts = requestedPhases.some(p =>
      postKitPhases.includes(String(p || '').trim().toLowerCase())
    );

    if (targetReqId && needsCandidateArtifacts) {
      const reqDocsRoot = vscode.Uri.joinPath(projectRootUri, 'runs', 'kit', targetReqId, 'docs');
      const candidateDocs = [
        'TARGET_CONTRACT.json',
        'FILE_REQUIREMENTS.json',
        'REQ_PROMOTION_MANIFEST.md',
        'REPO_ACCESS_MANIFEST.md',
        'REPO_STRUCTURE_EVIDENCE.md',
        'REPO_COMPOSITION_MANIFEST.md',
        'INTEGRITY_EVAL.json',
      ];

      for (const fileName of candidateDocs) {
        try {
          const raw = await vscode.workspace.fs.readFile(vscode.Uri.joinPath(reqDocsRoot, fileName));
          payload["core_blobs"][fileName] = Buffer.from(raw).toString('utf8');
        } catch {
          // best effort: preflight and backend validation will handle missing required files
        }
      }
    }
  }
  //RAG SUGGENSTIONDS
  payload["rag_strategy"] = "auto";
  payload["rag_top_k"] = 12;
  payload["context_hard_limit"] = 12500; // per budgeting lato gateway  

  if (phase === 'kit') {
      payload["rag_strategy"] = "deps_only";//“auto”, “force”, “off”, “deps_only”
      payload["context_hard_limit"] = 22500; // per budgeting lato gateway  
      payload["rag_top_k"] = 150;
  }
   if (phase === 'finalize') {
      payload["rag_top_k"] = 40;
      payload["context_hard_limit"] = 18000;
   }
  return payload;
}
// PATCH 1 — utilities per PLAN/REQ (in alto vicino ad altre utility)
async function readTextFile(uri) {
  try {
    const data = await vscode.workspace.fs.readFile(uri);
    return Buffer.from(data).toString('utf8');
  } catch {
    return null;
  }
}
async function writeTextFile(uri, text) {
  await vscode.workspace.fs.writeFile(uri, Buffer.from(text, 'utf8'));
}

async function readPlanJson(projectRootUri) {
  const uri = vscode.Uri.joinPath(projectRootUri, 'docs', 'harper', 'plan.json');
  try {
    const raw = await readTextFile(uri);
    const parsed = raw ? JSON.parse(raw) : null;
    if (!parsed || typeof parsed !== 'object') return null;

    if (Array.isArray(parsed.reqs)) {
      return parsed;
    }

    if (Array.isArray(parsed.req)) {
      return {
        ...parsed,
        reqs: parsed.req
      };
    }

    return parsed;

  } catch {
    return null;
  }
}

function normalizeStatus(s) {
  const v = String(s || '').trim().toLowerCase();
  return VALID_STATUSES.includes(v) ? v : 'open';
}

function updatePlanSnapshot(plan) {
  if (!plan || !Array.isArray(plan.reqs)) {
    if (plan) plan.snapshot = { total: 0, open: 0, in_progress: 0, done: 0, deferred: 0, progressPct: 0 };
    return plan?.snapshot;
  }

  const total = plan.reqs.length;
  const counts = { open: 0, in_progress: 0, done: 0, deferred: 0 };

  for (const r of plan.reqs) {
    const st = normalizeStatus(r?.status);
    counts[st] += 1;
  }

  const progressPct = total > 0 ? Math.round((counts.done / total) * 100) : 0;

  plan.snapshot = {
    total,
    open: counts.open,
    in_progress: counts.in_progress,
    done: counts.done,
    deferred: counts.deferred,
    progressPct
  };
  return plan.snapshot;
}



async function writePlanJson(projectRootUri, obj) {
  const uri = vscode.Uri.joinPath(projectRootUri, 'docs', 'harper', 'plan.json');
  await writeTextFile(uri, JSON.stringify(obj, null, 2));
}

function findNextOpenReq(plan) {
  if (!plan || !Array.isArray(plan.reqs)) return null;
  // dipendenze tutte done
  const isDepsSatisfied = (req, byId) => {
    const deps = Array.isArray(req.dependsOn) ? req.dependsOn : [];
    return deps.every(d => (byId[d] && byId[d].status === 'done'));
  };
  const byId = Object.fromEntries(plan.reqs.map(r => [r.id, r]));
  for (const req of plan.reqs) {
    if (req.status === 'open' && isDepsSatisfied(req, byId)) return req.id;
  }
  // fallback: primo open anche se deps non soddisfatte
  const anyOpen = plan.reqs.find(r => r.status === 'open');
  return anyOpen ? anyOpen.id : null;
}

function findNextReq(plan, status) {
  if (!plan || !Array.isArray(plan.reqs)) return null;
  // dipendenze tutte done
  const isDepsSatisfied = (req, byId) => {
    const deps = Array.isArray(req.dependsOn) ? req.dependsOn : [];
    return deps.every(d => (byId[d] && byId[d].status === 'done'));
  };
  const byId = Object.fromEntries(plan.reqs.map(r => [r.id, r]));
  for (const req of plan.reqs) {
    if (req.status === status && isDepsSatisfied(req, byId)) return req.id;
  }
  // fallback: primo open anche se deps non soddisfatte
  const anyOpen = plan.reqs.find(r => r.status === status);
  return anyOpen ? anyOpen.id : null;
}

function setReqStatus(plan, reqId, status) {
  if (!plan || !Array.isArray(plan.reqs)) return false;
  const r = plan.reqs.find(x => (x.id || '').trim().toUpperCase() === (reqId || '').trim().toUpperCase());
  if (!r) return false;
  r.status = status;
  updatePlanSnapshot(plan);
  return true;
}


// -- renderer di snapshot/table (usa i tuoi se già esistono) --
function snapshotCounts(plan) {
  const total = (plan?.reqs || []).length;
  const done = (plan?.reqs || []).filter(r => (r.status || '').toLowerCase() === 'done').length;
  const open = (plan?.reqs || []).filter(r => (r.status || '').toLowerCase() === 'open').length;
  const inprog = (plan?.reqs || []).filter(r => (r.status || '').toLowerCase() === 'in_progress').length;
  const deferred = (plan?.reqs || []).filter(r => (r.status || '').toLowerCase() === 'deferred').length;
  const progress = total > 0 ? Math.round((done / total) * 100) : 0;
  return { total, done, open, in_progress: inprog, deferred, progress };
}

function renderSnapshotMd(ss) {
  // Ritorna sezione COMPLETA inclusa l’intestazione
  return [
    '## Plan Snapshot',
    '',
    `- **Counts:** total=${ss.total} / open=${ss.open} / in_progress=${ss.in_progress} / done=${ss.done} / deferred=${ss.deferred}`,
    `- **Progress:** ${ss.progress}% complete`,
    '- **Checklist:**',
    '  - [x] SPEC aligned',
    '  - [x] Prior REQ reconciled',
    '  - [x] Dependencies mapped',
    '  - [x] KIT-readiness per REQ confirmed',
    ''
  ].join('\n');
}

function renderReqTableMd(plan) {
  // Tabella Markdown semplice, robusta
  const rows = (plan?.reqs || []).map(r => {
    const id = r.id || '';
    const title = r.title || '';
    const acc = Array.isArray(r.acceptance) ? r.acceptance.map(a => a.trim()).join('<br/>') : (r.acceptance || '');
    const deps = Array.isArray(r.dependsOn) ? r.dependsOn.join(', ') : (r.dependsOn || '');
    const track = (r.track || '').toString();
    const status = (r.status || '').toString();
    return `| ${id} | ${title} | ${acc} | ${deps} | ${track} | ${status} |`;
  });

  return [
    '## REQ-IDs Table',
    '',
    '| ID | Title | Acceptance | DependsOn | Track | Status |',
    '|---|---|---|---|---|---|',
    ...rows,
    ''
  ].join('\n');
}


// Regex di sezione robuste: case-insensitive, tolleranti su spazi/varianti
function sectionRegex(titleVariants) {
  // Esempio: ['Plan Snapshot'] o ['REQ-IDs Table']
  const escaped = titleVariants.map(t => t.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'));
  const union = escaped.join('|');
  // Cattura l'intestazione (## <title...>) e il contenuto fino al prossimo ## o fine file
  return new RegExp(
    `^(##\\s*(?:${union})\\b[^\n]*\\n)([\\s\\S]*?)(?=^##\\s|\\Z)`,
    'mi'
  );
}

async function updatePlanMdInPlace(projectRootUri, plan) {
  const uri = vscode.Uri.joinPath(projectRootUri, 'docs', 'harper', 'PLAN.md');
  let md = await readTextFile(uri);
  if (!md) return;

  const ss = snapshotCounts(plan);
  const newSnapshot = renderSnapshotMd(ss);
  const newTable = renderReqTableMd(plan);

  // Cerca le sezioni con regex robuste (accetta anche eventuali varianti di scrittura)
  const rxSnapshot = sectionRegex(['Plan Snapshot']);
  const rxTable = sectionRegex(['REQ-IDs Table', 'REQ IDs Table', 'REQ-IDs table']);

  // Sostituisci o aggiungi Snapshot
  if (rxSnapshot.test(md)) {
    md = md.replace(rxSnapshot, (_, heading /*, body*/) => {
      // Manteniamo la riga heading originale (per non cambiare maiuscole/spazi),
      // sostituiamo solo il contenuto con quello nuovo (senza ripetere l’intestazione)
      const contentLines = newSnapshot.split('\n');
      contentLines.shift(); // rimuovi "## Plan Snapshot"
      const content = contentLines.join('\n');
      return `${heading}${content}\n`;
    });
  } else {
    // Non trovata → appenderla in cima
    md = `${newSnapshot}\n${md}`;
  }
  log("test rxTable", rxTable.test(md));
  // --- Tabella (logica identica alla tua updatePlanMdInPlace) ---
  const tableHeading = '## REQ-IDs Table';
  const headingIdx = md.indexOf(tableHeading);

  if (headingIdx !== -1) {
    // md = [prima della tabella] + [tabella e resto]
    const before = md.slice(0, headingIdx);
    const after = md.slice(headingIdx);

    // Nel blocco "after", troviamo dove finisce la tabella
    // e dove iniziano le Acceptance già presenti.
    const idxAcceptance = after.indexOf('\n### Acceptance');
    const idxNextSection = after.indexOf('\n## ', tableHeading.length);

    // Se c'è una sezione "### Acceptance — REQ-001", usiamo quella come fine della tabella.
    // Altrimenti, come fallback, usiamo il prossimo "## " oppure la fine del file.
    let cut;
    if (idxAcceptance !== -1) {
      cut = idxAcceptance;
    } else if (idxNextSection !== -1) {
      cut = idxNextSection;
    } else {
      cut = after.length;
    }

    // Inseriamo la tabella nuova (newTable include già "## REQ-IDs Table")
    // e manteniamo tutto ciò che viene dopo (Acceptance, Dependency Graph, ecc.).
    const afterTail = after.slice(cut);
    md = `${before}${newTable}${afterTail}`;
  } else {
    // Se non esiste ancora la sezione, la appendiamo in fondo
    md = `${md}\n\n${newTable}`;
  }
  
  await writeTextFile(uri, md);
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
  switch ((phase||'').toLowerCase()) {
     case "idea":
      return [];
    case "spec":
      return [];
    case "plan":
      return ["SPEC.md", "TECH_CONSTRAINTS.yaml"];
    case "kit":
      return ["SPEC.md", "PLAN.md", "plan.json", "TECH_CONSTRAINTS.yaml"];
    case "eval":
      return ["SPEC.md", "PLAN.md", "plan.json", "TECH_CONSTRAINTS.yaml"];
    case "finalize":
      return ["SPEC.md", "PLAN.md",  "plan.json", "TECH_CONSTRAINTS.yaml"];
    default:
      return ["IDEA.md"];
  }
}



function getProjectId() {
   // --- project_id: derive from workspace folder name ---
  try {
    const ws = vscode.workspace.workspaceFolders?.[0];
    if (ws && ws.name) {
      return ws.name.toLowerCase().replace(/\s+/g, '-'); 
    } else {
      return 'default';
    }
  } catch (e) {
    console.warn('[CLike] project_id derivation failed:', e);
    body.project_id = 'default';
  }
}

// Converte l'argomento utente in un path LTC.json
async function resolveProfilePath(arg, workspaceRoot) {
  const rootPath = (workspaceRoot && (workspaceRoot.fsPath || workspaceRoot.path)) || ".";
  const wsUri = workspaceRoot || vscode.workspace.workspaceFolders?.[0]?.uri;

  // Se l'utente passa direttamente un .json, usalo
  if (typeof arg === "string" && arg.trim().toLowerCase().endsWith(".json")) {
    return arg.trim();
  }

  // Se è un REQ-ID tipo REQ-123 → runs/kit/REQ-123/LTC.json (o .../ci/LTC.json se è lì)
  if (typeof arg === "string" && /^REQ-\d+$/i.test(arg.trim())) {
    const p1 = `runs/kit/${arg.trim()}/LTC.json`;
    const p2 = `runs/kit/${arg.trim()}/ci/LTC.json`;
    // Verifica esistenza p1 o p2 (best effort)
    try {
      const uri1 = vscode.Uri.joinPath(wsUri, p1);
      await vscode.workspace.fs.stat(uri1);
      return p1;
    } catch (_) {
      // p1 non esiste, prova p2
      try {
        const uri2 = vscode.Uri.joinPath(wsUri, p2);
        await vscode.workspace.fs.stat(uri2);
        return p2;
      } catch (_) {
        // nessuno dei due, restituisci p1 di default (orchestrator potrà fallire con errore chiaro)
        return p1;
      }
    }
  }
  // Fallback: LTC.json in root
  return "LTC.json";
}
function getWorkspaceRootUri() {
  const folders = vscode.workspace.workspaceFolders || [];
  if (folders.length === 1) return folders[0].uri;
  const active = vscode.window.activeTextEditor?.document?.uri;
  if (active) {
    const ws = vscode.workspace.getWorkspaceFolder(active);
    if (ws?.uri) return ws.uri;
  }
  return folders[0]?.uri;
}
function getProjectNameFromWorkspace() {
  const uri = getWorkspaceRootUri();
  if (!uri || uri.scheme !== 'file') return null;
  const fsPath = uri.fsPath;
  return path.basename(fsPath); // solo nome cartella
}

async function readWorkspaceFileBytes(pathInWs) {
  try {
    const ws = vscode.workspace.workspaceFolders?.[0];
    if (!ws) return null;

    const input = String(pathInWs || '');
    const rel = input.replace(/^\.?[\\/]/, '');
    const absPath = path.isAbsolute(input) ? input : path.join(ws.uri.fsPath, rel);
    const fileUri = vscode.Uri.file(absPath);

    const data = await vscode.workspace.fs.readFile(fileUri); // Uint8Array
    return Buffer.from(data);
  } catch {
    return null;
  }
}


// Decode base64 to UTF-8 (text-ish), returns null for binary/invalid.
function decodeTextBase64Safe(b64) {
  try {
    const buf = Buffer.from(b64, 'base64');
    const txt = buf.toString('utf8');
    if (/\x00/.test(txt)) return null;
    return txt;
  } catch { return null; }
}

// Build items for /v1/rag/index from rag_files (path -> text OR bytes_b64)
async function buildRagItemsForIndex(rag_files, out) {
  const log = mkLog(out);
  const items = [];

  for (const f of (rag_files || [])) {
    if (!f) continue;

    const p = f.path || (f.name ? `attachments/${f.name}` : null);
    if (!p) continue;

    // 1) Trust already-normalized content first
    if (typeof f.content === 'string' && f.content.trim()) {
      items.push({ path: p, text: f.content });
      log(`[harperRAG] use provided content for ${p}`);
      continue;
    }

    // 2) Trust provided bytes_b64 before trying to re-read from workspace
    if (typeof f.bytes_b64 === 'string' && f.bytes_b64.length > 0) {
      items.push({ path: p, bytes_b64: f.bytes_b64 });
      //log(`[harperRAG] use provided bytes_b64 for ${p}`);
      continue;
    }

    // 3) Workspace text fallback
    const t = await readWorkspaceTextFile(p, out);
    if (t && t.trim()) {
      items.push({ path: p, text: t });
      log(`[harperRAG] read workspace text for ${p}`);
      continue;
    }

    // 4) Workspace binary fallback
    const buf = await readWorkspaceFileBytes(p);
    if (buf && buf.length) {
      items.push({ path: p, bytes_b64: buf.toString('base64') });
      log(`[harperRAG] read workspace binary for ${p} (${buf.length}B)`);
      continue;
    }

    log(`[harperRAG] skip unreadable item ${p}`);
  }

  log(`[harperRAG] items built -> ${items.length}`);
  return items;
}

// Read a workspace-relative OR absolute text file (UTF-8). Returns null if binary/failed.
async function readWorkspaceTextFile(pathInWs, out) {
  try {
    const dbg = mkLog(out);
    const ws = vscode.workspace.workspaceFolders?.[0];
    if (!ws) return null;

    const input = String(pathInWs || '');
    const rel = input.replace(/^\.?[\\/]/, '');
    const absPath = path.isAbsolute(input) ? input : path.join(ws.uri.fsPath, rel);
    const fileUri = vscode.Uri.file(absPath);

    const data = await vscode.workspace.fs.readFile(fileUri); // Uint8Array
    if (!data || data.length === 0) return '';

    // binary guard (null byte in first 4KB)
    const limit = Math.min(data.length, 4096);
    for (let i = 0; i < limit; i++) {
      if (data[i] === 0) return null;
    }

    return Buffer.from(data).toString('utf8');
  } catch (e) {
    console.warn('[readWorkspaceTextFile] failed', e);
    return null;
  }
}

async function postJson(url, body, { signal, timeoutMs = 30000 } = {}) {
  const f = (typeof fetch === 'function')
    ? fetch
    : ((...args) => import('node-fetch').then(({ default: ff }) => ff(...args)));

  const controller = signal ? null : new AbortController();
  const effectiveSignal = signal || controller.signal;
  const timer = controller
    ? setTimeout(() => controller.abort(), Math.max(1000, Number(timeoutMs) || 30000))
    : null;

  try {
    const res = await f(url, {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify(body),
      signal: effectiveSignal
    });

    if (!res.ok) {
      const txt = await res.text().catch(() => '');
      throw new Error(`POST ${url} -> ${res.status} ${txt}`);
    }

    return await res.json();
  } finally {
    if (timer) clearTimeout(timer);
  }
}

// Pre-index RAG items before chat/generate. Non-blocking on failure.
async function preIndexRag(projectId, rag_files, url, out, options = {}) {
  const log = mkLog(out);
  const timeoutMs = Math.max(1000, Number(options.timeoutMs || 30000));

  const items = await buildRagItemsForIndex(rag_files, out);
  if (!items.length) return { ok: true, upserts: 0 };

  try {
    return await postJson(url, { project_id: projectId, items }, { timeoutMs });
  } catch (e) {
    const msg = e?.name === 'AbortError'
      ? `RAG preIndex timed out after ${timeoutMs}ms`
      : String(e?.message || e);
    log(`[RAG] preIndex skipped: ${msg}`);
    console.warn('[RAG] preIndex failed', e);
    return { ok: false, upserts: 0, error: msg };
  }
}





// Approximate bytes from base64 length (good enough for thresholds)
function bytesFromBase64Len(b64) {
  if (!b64) return 0;
  const len = b64.length;
  let pad = 0;
  if (b64.endsWith("==")) pad = 2; else if (b64.endsWith("=")) pad = 1;
  return Math.max(0, Math.floor((len * 3) / 4) - pad);
}

// Normalization: unify name/path/origin/content/bytes_b64/sizeBytes
function normalizeAttachment(a) {
  const name = (a?.name || a?.filename || a?.fileName || a?.path || "file").toString();
  const path = (a?.path || null);
  const origin = a?.origin || null;
  const content = (typeof a?.content === "string" && a.content.length > 0) ? a.content : null;
  const { b64, header } = base64FromAny(a);
  const bytes_b64 = b64;

  let sizeBytes = 0;
  if (a?.size != null) {
    const n = Number(a.size);
    sizeBytes = Number.isFinite(n) && n >= 0 ? n : 0;
  }
  if (!sizeBytes && content)  sizeBytes = Buffer.byteLength(content, "utf8");
  if (!sizeBytes && bytes_b64) sizeBytes = bytesFromBase64Len(bytes_b64);

  return { name, path, origin, content, bytes_b64, dataUrlHeader: header, sizeBytes };
}
// Pretty JSON logger to avoid [object Object]
function safeLog(prefix, obj) {
  try { log(prefix, JSON.stringify(obj, null, 2)); }
  catch { log(prefix, obj); }
}

// Accept many base64 aliases, strip data URL header if any
function base64FromAny(a) {
  const raw = a?.bytes_b64 || a?.base64 || a?.b64 || a?.dataUrl || a?.data || "";
  if (typeof raw !== "string" || !raw) return { b64: null, header: null };
  const m = raw.match(/^data:[^;]+;base64,(.*)$/i);
  return m ? { b64: m[1], header: raw.slice(0, raw.indexOf(",") + 1) } : { b64: raw, header: null };
}

async function getFileSizeBytes(filePath) {
  try {
    // se è relativo, risolvilo nel workspace
    const ws = vscode.workspace.workspaceFolders && vscode.workspace.workspaceFolders[0];
    const absPath = path.isAbsolute(filePath)
      ? filePath
      : path.join(ws ? ws.uri.fsPath : process.cwd(), filePath);
    const stats = await fs.promises.stat(absPath);
    return stats.isFile() ? stats.size : 0;
  } catch {
    return 0;
  }
}

function normalizeChangedFiles(reportUri, promotedTargets) {
  const list = [];
  if (reportUri) {
    try { list.push(toFsPath(reportUri)); } catch { list.push(String(reportUri)); }
  }
  // promotedTargets può essere array di path o stringa con virgole
  const toArray = (val) => {
    if (!val) return [];
    if (Array.isArray(val)) return val;
    if (typeof val === 'string') return val.split(',').map(s => s.trim()).filter(Boolean);
    return [String(val)];
  };
  for (const p of toArray(promotedTargets)) {
    if (!p) continue;
    try { list.push(toFsPath(p)); } catch { list.push(String(p)); }
  }
  return list.filter(Boolean);
}

const sanitize = (x) => {
  if (!x) return '';
  if (x.fsPath) return x.fsPath;                 // vscode.Uri
  const s = String(x);
  if (s.startsWith('file://')) {
    try { return decodeURI(new URL(s).pathname); }
    catch { return s.replace(/^file:\/\//, ''); }
  }
  return s;
};

function httpPostJsonLong(url, { headers, body }, timeoutMs) {
  return new Promise((resolve, reject) => {
    const u = new URL(url);
    const lib = u.protocol === "https:" ? myhttps : myhttp;

    const req = lib.request(
      {
        hostname: u.hostname,
        port: u.port || (u.protocol === "https:" ? 443 : 80),
        path: u.pathname + u.search,
        method: "POST",
        headers: headers || {},
      },
      (res) => {
        let data = "";
        res.setEncoding("utf8");

        res.on("data", (chunk) => {
          data += chunk;
        });

        res.on("end", () => {
          const response = {
            ok: res.statusCode >= 200 && res.statusCode < 300,
            status: res.statusCode,
            async json() {
              try {
                return JSON.parse(data);
              } catch (e) {
                log(
                  `[harper] invalid JSON from orchestrator: ${e.message}. ` +
                  `Body[0..500]=${data.slice(0, 500)}`
                );
                throw e;
              }
            },
            async text() {
              return data;
            },
          };
          resolve(response);
        });
      }
    );

    req.on("error", (err) => {
      reject(err);
    });

    // timeout socket lato client (disabilitato se timeoutMs <= 0)
    if (timeoutMs && timeoutMs > 0) {
      req.setTimeout(timeoutMs, () => {
        req.destroy(new Error(`Request timeout after ${timeoutMs}ms`));
      });
    }

    if (body) {
      req.write(body);
    }
    req.end();
  });
}


function logCurrentTimeStandard(activity) {
    const now = new Date();

    // Estrae i componenti (ore, minuti, secondi)
    const hours = now.getHours().toString().padStart(2, '0');
    const minutes = now.getMinutes().toString().padStart(2, '0');
    const seconds = now.getSeconds().toString().padStart(2, '0');
    
    // Opzionale: aggiunge i millisecondi
    const milliseconds = now.getMilliseconds().toString().padStart(3, '0');

    // Costruisce il log
    const timeString = `${hours}:${minutes}:${seconds}.${milliseconds}`;
    
    log(`Clike Time:[${timeString}] --> [${activity}]`);
}

function _findReq(plan, reqId) {
  const key = String(reqId || '').trim().toUpperCase();
  const reqs = Array.isArray(plan?.reqs) ? plan.reqs : Array.isArray(plan?.req) ? plan.req : [];
  return reqs.find(r => String(r?.id || '').trim().toUpperCase() === key) || null;
}

function buildAgentExecutionContext({
  phase,
  reqId,
  plan,
  projectMeta = {},
  requestedPhases = null,
  ltc = null,
  howtoPath = null,
}) {
  const req = _findReq(plan, reqId) || {};
  const lane = String(req?.lane || ltc?.lane || 'unknown').trim() || 'unknown';
  const acceptance = Array.isArray(req?.acceptance) ? req.acceptance : [];
  const dependsOn = Array.isArray(req?.dependsOn) ? req.dependsOn : [];
  const dependencyKitRoots = dependsOn
    .map(dep => String(dep || '').trim().toUpperCase())
    .filter(dep => dep.startsWith('REQ-'))
    .map(dep => `runs/kit/${dep}`);

  const base = {
    schema_version: 'v1',
    context_type: 'agent_execution_context',
    phase: String(phase || '').trim().toLowerCase(),
    req: {
      id: String(reqId || '').trim().toUpperCase(),
      title: String(req?.title || '').trim(),
      lane,
      status: String(req?.status || '').trim().toLowerCase(),
      acceptance_criteria: acceptance,
      depends_on: dependsOn,
      functional_scope: String(req?.functional_scope || '').trim(),
      technical_scope: String(req?.technical_scope || '').trim(),
      domain: String(req?.domain || '').trim(),
      runtime_profile: String(req?.runtime_profile || '').trim(),
      packs: Array.isArray(req?.packs) ? req.packs : [],
      skills: Array.isArray(req?.skills) ? req.skills : [],
      design_profiles: Array.isArray(req?.design_profiles) ? req.design_profiles : [],
      gate_expectations: Array.isArray(req?.gate_expectations) ? req.gate_expectations : [],
      main_module_boundary: String(req?.main_module_boundary || '').trim(),
      future_compatibility_notes: Array.isArray(req?.future_compatibility_notes) ? req.future_compatibility_notes : [],
    },
    project: {
      project_id: String(projectMeta.project_id || '').trim(),
      project_name: String(projectMeta.project_name || '').trim(),
      harper_doc_root: String(projectMeta.harper_doc_root || 'docs/harper').trim(),
      rag_namespace: String(projectMeta.rag_namespace || '').trim(),
    },
    repository: {
      working_directory: '.',
      source_folder: String(projectMeta.source_folder || 'src').trim(),
      test_folder: String(projectMeta.test_folder || 'test').trim(),
    },
    workspace_inspection_policy: {
      purpose: 'Inspect promoted source/test roots and dependency KIT roots before writing or repairing candidate files.',
      canonical_promoted_source_roots: ['src'],
      canonical_promoted_test_roots: ['test', 'tests'],
      dependency_req_ids: dependsOn,
      dependency_kit_roots: dependencyKitRoots,
      target_candidate_root: `runs/kit/${String(reqId || '').trim().toUpperCase()}`,
      read_policy: 'Read promoted roots and dependency KIT roots when present.',
      write_policy: 'Write only inside the target candidate root.',
    },
  };

  if (base.phase === 'kit') {
    return {
      ...base,
      requested_phases: Array.isArray(requestedPhases) ? requestedPhases : ['kit'],
      required_reads: [
        '.clike/project.json',
        'docs/harper/plan.json',
        'docs/harper/PLAN.md',
      ],
      allowed_write_roots: [
        `runs/kit/${base.req.id}/src`,
        `runs/kit/${base.req.id}/test`,
        `runs/kit/${base.req.id}/ci`,
        `runs/kit/${base.req.id}/docs`,
      ],
      forbidden_paths: [
        'docs/harper/PLAN.md',
        'docs/harper/plan.json',
        'src',
        'test',
      ],
      expected_outputs: {
        source_root: `runs/kit/${base.req.id}/src`,
        test_root: `runs/kit/${base.req.id}/test`,
        ci_files: [
          `runs/kit/${base.req.id}/ci/LTC.json`,
          `runs/kit/${base.req.id}/ci/HOWTO.md`,
          `runs/kit/${base.req.id}/ci/requirements.txt`,
        ],
        docs_files: [
          `runs/kit/${base.req.id}/docs/README_${base.req.id}.md`,
          `runs/kit/${base.req.id}/docs/KIT_${base.req.id}.md`,
        ],
      },
      generation_rules: [
        'Generate repository-aware code (src/ ), tests (test/) and docs aligned to the REQ acceptance criteria.',
        'Before writing, inspect workspace_inspection_policy, promoted src/test roots, and dependency KIT roots when present.',
        'Treat canonical src/test roots as promoted truth and dependency KIT roots as E2E contract evidence.',        
        'Respect req.functional_scope and req.technical_scope when present.',
        'Respect req.domain, req.runtime_profile, req.packs, req.skills, req.design_profiles, req.gate_expectations, req.main_module_boundary, and req.future_compatibility_notes when present.',
        'Use req.main_module_boundary to keep the implementation focused and avoid scattered files.',
        'Do not write outside allowed_write_roots.',
        'Do not promote candidate files into canonical src/ or test/ roots.',
        'README and KIT docs are required candidate artifacts for local KIT parity.',
      ],
    };
  }

  if (base.phase === 'eval') {
    return {
      ...base,
      required_reads: [
        '.clike/project.json',
        `runs/kit/${base.req.id}/docs/AGENT_EXECUTION_CONTEXT.json`,
        `runs/kit/${base.req.id}/ci/LTC.json`,
        howtoPath || `runs/kit/${base.req.id}/ci/HOWTO.md`,
      ],
      allowed_write_roots: [
        `runs/kit/${base.req.id}/src`,
        `runs/kit/${base.req.id}/test`,
        `runs/kit/${base.req.id}/ci`,
        `runs/kit/${base.req.id}/docs`,
      ],
      forbidden_paths: [
        'docs/harper/PLAN.md',
        'docs/harper/plan.json',
        'src',
        'test',
      ],
      eval_contract: {
        lane,
        tools: ltc?.tools || {},
        commands: ltc?.commands || {},
        reports: ltc?.reports || [],
        normalize: ltc?.normalize || {},
        gate_policy: ltc?.gate_policy || {},
        external_runner: ltc?.external_runner || null,
        constraints_applied: ltc?.constraints_applied || [],
      },
      evaluation_rules: [
        'Run the execution recipe from LTC/HOWTO.',
        'Before repairing, inspect workspace_inspection_policy, promoted src/test roots, and dependency KIT roots when present.',
        'Treat canonical src/test roots as promoted truth and dependency KIT roots as E2E contract evidence.',        
        'If checks fail, fix candidate source/test files only under allowed_write_roots.',
        'Re-run the relevant checks after each remediation.',
        'Do not modify canonical workspace src/ or test/ roots.',
        'Return a concise execution summary with commands run, fixes applied, and remaining failures.',
      ],
    };
  }

  return base;
}

async function writeAgentExecutionContext(workspaceRootUri, reqId, contextPayload, out) {
  const log = mkLog(out);
  const req = String(reqId || '').trim().toUpperCase();
  if (!workspaceRootUri?.fsPath) {
    throw new Error('writeAgentExecutionContext: workspace root is required');
  }
  if (!req) {
    throw new Error('writeAgentExecutionContext: reqId is required');
  }

  const docsDir = path.join(workspaceRootUri.fsPath, 'runs', 'kit', req, 'docs');
  fs.mkdirSync(docsDir, { recursive: true });

  const filePath = path.join(docsDir, 'AGENT_EXECUTION_CONTEXT.json');
  fs.writeFileSync(filePath, JSON.stringify(contextPayload, null, 2), 'utf8');
  log('[agentExecutionContext] wrote', filePath);
  return filePath;
}

function buildAgentEvalPrompt({ reqId }) {
  const targets = Array.isArray(reqId) ? reqId.join(', ') : String(reqId || '').trim();
  return [
    'You are a local software-generation agent working inside the current repository workspace.',
    `Your task is to perform a local pre-pass for /eval on REQ target(s): ${targets}.`,
    '',
    'Read these artifacts before acting:',
    `1. runs/kit/${targets}/ci/LTC.json`,
    `2. runs/kit/${targets}/docs/AGENT_EXECUTION_CONTEXT.json`,
    `3. runs/kit/${targets}/ci/HOWTO.md`,
    `4. runs/kit/${targets}/src/**`,
    `5. runs/kit/${targets}/test/**`,
    '',
    'Rules:',
    '- Read and follow the execution recipe from AGENT_EXECUTION_CONTEXT.json and LTC.json.',
    '- Operate only inside candidate roots for the targeted REQ.',
    '- You may run tests, lint, type checks, and minimal remediation allowed by the execution contract.',
    '- When repairing CI scripts, preserve the CLike eval workspace contract: scripts must consume CLIKE_EVAL_WORKSPACE, CLIKE_EVAL_WORKSPACE_ROOT, CLIKE_EVAL_OVERLAY_WORKSPACE, or CLIKE_OVERLAY_WORKSPACE when present.',
    '- Do not repair eval failures by creating an unconditional second overlay workspace.',
    '- Helpers such as createOverlayWorkspace, prepareWorkspace, buildWorkspace, composeWorkspace, or runtime-specific equivalents must return the CLike-provided eval workspace directly when available.',
    '- Do not mutate canonical workspace roots outside the candidate area.',
    '- Do not perform git operations.',
    '- Return a concise execution summary on stdout.',
  ].join('\n');
}

function buildAgentKitPrompt({ reqId, requestedPhases }) {
  const phases = Array.isArray(requestedPhases) && requestedPhases.length
    ? requestedPhases.join(', ')
    : 'kit';

  return [
    'You are a local software-generation agent working inside the current repository workspace.',
    '',
    'Read local project context before making changes:',
    '1. .clike/project.json',
    `2. runs/kit/${reqId}/docs/AGENT_EXECUTION_CONTEXT.json`,
    '3. docs/harper/plan.json',
    '4. docs/harper/PLAN.md',
    '5. docs/harper/SPEC.md',
    '6. docs/harper/IDEA.md',
    '7. docs/harper/lane-guides/* if present and relevant',
    '',
    `Target REQ: ${reqId}`,
    `Requested phase(s): ${phases}`,
    '',
    'Strict execution rules:',
    '- Follow AGENT_EXECUTION_CONTEXT.json as the primary execution contract.',
    '- Read and respect capability_context when present.',
    '- Use main_module_boundary when present to keep the implementation focused and avoid scattered files.',
    '- Do not modify docs/harper/PLAN.md or docs/harper/plan.json.',
    '- Do not commit, branch, push, open PRs, or modify git metadata.',
    '- Do not promote candidate files into canonical src/ or test/ roots.',
    '- Generate source, tests, and docs required by the contract.',
    '- Return a concise execution summary on stdout.',
    '',
      'Required candidate outputs:',
    `- runs/kit/${reqId}/src/...`,
    `- runs/kit/${reqId}/test/...`,
    `- runs/kit/${reqId}/ci/LTC.json`,
    `- runs/kit/${reqId}/ci/HOWTO.md`,
    `- runs/kit/${reqId}/ci/<runtime-native-eval-manifest> only when required by the selected runtime`,
    `- runs/kit/${reqId}/docs/README_${reqId}.md`,
    `- runs/kit/${reqId}/docs/KIT_${reqId}.md`,
    '',
    'Implementation expectations:',
    '- Produce real repository-aware code and real tests aligned to the acceptance criteria.',
    '- Keep changes minimal, concrete, and promotable.',
    '- If candidate files already exist under runs/kit/<REQ-ID>/..., update them instead of duplicating them.',
    '- Generated CI scripts must consume the official CLike eval workspace when present: CLIKE_EVAL_WORKSPACE, CLIKE_EVAL_WORKSPACE_ROOT, CLIKE_EVAL_OVERLAY_WORKSPACE, or CLIKE_OVERLAY_WORKSPACE.',
    '- Generated helpers such as createOverlayWorkspace, prepareWorkspace, buildWorkspace, composeWorkspace, or runtime-specific equivalents must return the CLike-provided eval workspace directly when available.',
    '- Do not create a second temporary overlay, recopy src/test/tests, or reconstruct dependency KIT composition when CLike EvalRunner has already provided an eval workspace.',
    '- Fallback overlay creation is allowed only for manual execution outside canonical CLike EvalRunner.',
    '',
    'At the end, print a concise summary:',
    '- files created/updated',
    '- main decisions taken',
    '- commands run locally',
    '- unresolved gaps, if any',
  ].join('\n');
}

async function runLocalAgentSync({
  workspaceRootUri,
  prompt,
  executorId = 'claude_code',
  command = 'claude',
  argsBeforePrompt = [],
  promptTransport = '',
  printModeFlag = '',
  permissionMode = '',
  timeoutMinutes = 20,
  out,
}) {
  const normalizedExecutor = String(executorId || '').trim();
  const finalCommand = String(command || '').trim();

  if (!workspaceRootUri?.fsPath) {
    throw new Error('Missing workspace root for local agent execution.');
  }

  if (!finalCommand) {
    throw new Error(`Missing local agent command for executor=${normalizedExecutor}.`);
  }

  const argv = [];

  for (const arg of Array.isArray(argsBeforePrompt) ? argsBeforePrompt : []) {
    const clean = String(arg || '').trim();
    if (clean) argv.push(clean);
  }

  const transport = String(promptTransport || '').trim() ||
    (normalizedExecutor === 'gpt_codex' ? 'stdin' : 'argv_last');

  if (transport === 'argv_last') {
    argv.push(prompt);
  }

  const safeArgvForLog = argv.map((arg) => {
    const s = String(arg || '');
    if (s.length > 200) return `${s.slice(0, 200)}...<${s.length} chars>`;
    return s;
  });

  if (out && typeof out.appendLine === 'function') {
    out.appendLine(
      `[CLike] [local-agent:${normalizedExecutor}] command=${finalCommand} argv=${JSON.stringify(safeArgvForLog)} cwd=${workspaceRootUri.fsPath} promptTransport=${transport}`
    );
  }

  const timeoutMs = Math.max(1, Number(timeoutMinutes || 20)) * 60 * 1000;

  return await new Promise((resolve, reject) => {
    const child = cp.spawn(finalCommand, argv, {
      cwd: workspaceRootUri.fsPath,
      shell: false,
      stdio: ['pipe', 'pipe', 'pipe'],
      env: {
        ...process.env,
        CLICOLOR: '0',
        NO_COLOR: '1',
      },
    });

    let stdout = '';
    let stderr = '';
    let settled = false;

    const timer = setTimeout(() => {
      if (settled) return;
      settled = true;

      try {
        child.kill('SIGTERM');
      } catch {
        // Ignore kill errors.
      }

      reject(
        new Error(
          `${normalizedExecutor} timed out after ${timeoutMinutes} minute(s). ` +
          `stdout=${stdout.slice(-2000)} stderr=${stderr.slice(-2000)}`
        )
      );
    }, timeoutMs);

    child.stdout.on('data', (chunk) => {
      const text = chunk.toString();
      stdout += text;
      if (out && typeof out.appendLine === 'function') {
        for (const line of text.split(/\r?\n/)) {
          if (line.trim()) {
            out.appendLine(`[CLike] [local-agent:${normalizedExecutor}][stdout] ${line}`);
          }
        }
      }
    });

    child.stderr.on("data", (chunk) => {
      const text = chunk.toString();

      for (const line of text.split(/\r?\n/)) {
        const trimmed = line.trim();
        if (!trimmed) {
          continue;
        }

        const isErrorLike =
          /\b(error|failed|failure|fatal|panic|traceback|exception|denied|timeout|cannot|not found|permission)\b/i.test(trimmed);

        const channel = isErrorLike ? "stderr:error" : "stderr:diagnostic";
        out.appendLine(`[CLike] [local-agent:${normalizedExecutor}][${channel}] ${trimmed}`);
      }
    });

    child.on('error', (error) => {
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      reject(error);
    });

    child.on('close', (exitCode) => {
      if (settled) return;
      settled = true;
      clearTimeout(timer);

      if (out && typeof out.appendLine === 'function') {
        out.appendLine(
          `[CLike] [local-agent:${normalizedExecutor}] exitCode=${exitCode} stdoutChars=${stdout.length} stderrChars=${stderr.length}`
        );
      }

      resolve({
        executorId: normalizedExecutor,
        command: finalCommand,
        args: argv,
        exitCode,
        stdout,
        stderr,
      });
    });

    if (transport === 'stdin' && child.stdin) {
      child.stdin.write(prompt);
      child.stdin.end();
    } else if (child.stdin) {
      child.stdin.end();
    }
  });
} 
async function collectReqCandidateFileArtifacts(projectRootUri, reqId) {
  const reqNorm = String(reqId || '').trim().toUpperCase();
  const reqRoot = vscode.Uri.joinPath(projectRootUri, 'runs', 'kit', reqNorm);

  try {
    await vscode.workspace.fs.stat(reqRoot);
  } catch {
    return [];
  }

  const files = await readTree(reqRoot);
  const artifacts = [];

  for (const uri of files) {
    try {
      const raw = await vscode.workspace.fs.readFile(uri);
      const rel = path.relative(projectRootUri.fsPath, uri.fsPath).split(path.sep).join('/');
      if (!rel.startsWith(`runs/kit/${reqNorm}/`)) {
        continue;
      }

      artifacts.push({
        path: rel,
        content: Buffer.from(raw).toString('utf8'),
        encoding: 'utf-8',
      });
    } catch {
      // Skip binary/unreadable files in the actuator result.
    }
  }

  return artifacts;
}
async function collectReqCandidateFiles(projectRootUri, reqId) {
  const reqRoot = vscode.Uri.joinPath(projectRootUri, 'runs', 'kit', reqId);
  try {
    await vscode.workspace.fs.stat(reqRoot);
  } catch {
    return [];
  }

  const files = await readTree(reqRoot);
  return files
    .filter(Boolean)
    .map((u) => u.fsPath || u.path)
    .filter(Boolean);
}

function isFinalizeAllowedPath(relPath) {
  const p = String(relPath || '').replace(/\\/g, '/').replace(/^\/+/, '');

  if (!p) return false;

  const forbiddenParts = new Set([
    '.git',
    'node_modules',
    '.venv',
    '__pycache__',
    '__MACOSX',
    '.next',
    'dist',
    'build',
    '.ruff_cache',
    '.mypy_cache',
  ]);

  if (p === '.DS_Store' || p.endsWith('/.DS_Store') || p.endsWith('.pyc')) {
    return false;
  }

  for (const part of p.split('/')) {
    if (forbiddenParts.has(part)) {
      return false;
    }
  }

  if (p === 'README.md') return true;
  if (p === '.env.example') return true;
  if (p.startsWith('src/')) return true;
  if (p.startsWith('scripts/')) return true;
  if (p.startsWith('docs/harper/')) return true;


  const platformRoots = [
    'infra/',
    'deploy/',
    'ops/',
    'config/',
    'configs/',
    'schemas/',
    'migrations/',
    'db/',
    'database/',
    'connectors/',
    'jobs/',
    'pipelines/',
    'packages/',
    'model/',
    'models/',
  ];

  if (platformRoots.some((root) => p.startsWith(root))) return true;

  const manifestNames = new Set([
    'package.json',
    'package-lock.json',
    'pnpm-lock.yaml',
    'yarn.lock',
    'pyproject.toml',
    'requirements.txt',
    'pom.xml',
    'build.gradle',
    'settings.gradle',
    'go.mod',
    'go.sum',
    'Cargo.toml',
    'Cargo.lock',
    'docker-compose.yml',
    'Dockerfile',
    'Makefile',
  ]);

  if (manifestNames.has(path.basename(p))) return true;
  if (p.endsWith('.csproj') || p.endsWith('.sln')) return true;

  return false;
}

function collectGitChangedFinalizePaths(rootPath) {
  try {
    const raw = cp.execSync('git status --porcelain', {
      cwd: rootPath,
      encoding: 'utf8',
      stdio: ['ignore', 'pipe', 'ignore'],
    });

    return raw
      .split(/\r?\n/)
      .map((line) => line.trimEnd())
      .filter(Boolean)
      .map((line) => {
        const candidate = line.slice(3).trim();
        const renamed = candidate.includes(' -> ')
          ? candidate.split(' -> ').pop().trim()
          : candidate;
        return renamed.replace(/\\/g, '/');
      })
      .filter(isFinalizeAllowedPath);
  } catch {
    return [];
  }
}

function collectFinalizeSupportPaths(rootPath) {
  const results = [];
  const srcRoot = path.join(rootPath, 'src');

  const wantedBasenames = new Set([
    'app.py',
    'main.py',
    'server.py',
    'wsgi.py',
    'asgi.py',
    'db.py',
    'database.py',
    'settings.py',
    'config.py',
    'env.py',
    'auth.py',
    'auth_config.py',
    'identity.py',

    'app.js',
    'app.ts',
    'server.js',
    'server.ts',
    'main.js',
    'main.ts',
    'index.js',
    'index.ts',
    'db.js',
    'db.ts',
    'database.js',
    'database.ts',
    'config.js',
    'config.ts',
    'env.js',
    'env.ts',
    'auth.js',
    'auth.ts',
    'identity.js',
    'identity.ts',

    'Application.java',
    'Main.java',
    'application.yml',
    'application.yaml',
    'application.properties',

    'Program.cs',
    'Startup.cs',
    'appsettings.json',

    'main.go',
    'config.go',
    'database.go',
    'auth.go',

    'Cargo.toml',
    'main.rs',
    'lib.rs',

    'composer.json',
    'artisan',
    'index.php',
    'config.php',
  ]);

  const forbiddenParts = new Set([
    '.git',
    'node_modules',
    '.venv',
    '__pycache__',
    '__MACOSX',
    '.next',
    'dist',
    'build',
    '.ruff_cache',
    '.mypy_cache',
  ]);

  function walk(dirPath, depth) {
    if (depth > 7) return;

    let entries;
    try {
      entries = fs.readdirSync(dirPath, { withFileTypes: true });
    } catch {
      return;
    }

    for (const entry of entries) {
      const abs = path.join(dirPath, entry.name);
      const rel = path.relative(rootPath, abs).replace(/\\/g, '/');

      if (!rel || rel.split('/').some((part) => forbiddenParts.has(part))) {
        continue;
      }

      if (entry.isDirectory()) {
        walk(abs, depth + 1);
        continue;
      }

      if (!entry.isFile()) {
        continue;
      }

      const base = path.basename(rel);
      const isRuntimeOrBoundaryFile =
        rel.startsWith('src/') && wantedBasenames.has(base);

      const isStackManifest =
        rel === 'package.json' ||
        rel.endsWith('/package.json') ||
        rel === 'pyproject.toml' ||
        rel.endsWith('/pyproject.toml') ||
        rel === 'requirements.txt' ||
        rel.endsWith('/requirements.txt') ||
        rel === 'pom.xml' ||
        rel.endsWith('/pom.xml') ||
        rel === 'build.gradle' ||
        rel.endsWith('/build.gradle') ||
        rel === 'build.gradle.kts' ||
        rel.endsWith('/build.gradle.kts') ||
        rel === 'go.mod' ||
        rel.endsWith('/go.mod') ||
        rel === 'Cargo.toml' ||
        rel.endsWith('/Cargo.toml') ||
        rel === 'composer.json' ||
        rel.endsWith('/composer.json') ||
        rel === 'global.json' ||
        rel.endsWith('/global.json') ||
        rel === 'appsettings.json' ||
        rel.endsWith('/appsettings.json');

      if ((isRuntimeOrBoundaryFile || isStackManifest) && isFinalizeAllowedPath(rel)) {
        results.push(rel);
      }
    }
  }

  try {
    if (fs.existsSync(srcRoot)) {
      walk(srcRoot, 0);
    }
  } catch {
    return [];
  }

  return [...new Set(results)];
}


async function collectFinalizeCandidateFileArtifacts(projectRootUri) {
  const rootPath = projectRootUri?.fsPath || projectRootUri?.path || '';
  if (!rootPath) return [];

  const expected = [
    'README.md',
    '.env.example',
    'docs/harper/HOWTO_RUN.md',
    'docs/harper/SANITY_CHECKS.md',
    'docs/harper/INFRA_READINESS.md',
    'docs/harper/RELEASE_NOTES.md',
    'docs/harper/TODO_NEXT.md',
    'docs/harper/PR_BODY.md',
    'scripts/check_solution_local.sh',
    'scripts/check_solution_local.ps1',
    'scripts/run_backend_local.sh',
    'scripts/run_backend_local.ps1',
    'scripts/run_frontend_local.sh',
    'scripts/run_frontend_local.ps1',
    'scripts/run_worker_local.sh',
    'scripts/run_worker_local.ps1',
    'scripts/check_infra_prereqs.sh',
    'scripts/check_infra_prereqs.ps1',
    'scripts/provision_plan.sh',
    'scripts/provision_plan.ps1',
    'scripts/check_deployment.sh',
    'scripts/check_deployment.ps1',
    'scripts/check_runtime_services.sh',
    'scripts/check_runtime_services.ps1',
    'scripts/cloud_inventory.sh',
    'scripts/cloud_inventory.ps1',
    'scripts/provision_cloud_plan.sh',
    'scripts/provision_cloud_plan.ps1',
    'scripts/provision_cloud_apply.sh',
    'scripts/provision_cloud_apply.ps1',
  ];

  const changed = collectGitChangedFinalizePaths(rootPath);
  const support = collectFinalizeSupportPaths(rootPath);
  const paths = [...new Set([...changed, ...expected, ...support].filter(isFinalizeAllowedPath))];

  const artifacts = [];

  for (const relPath of paths) {
    const absPath = path.join(rootPath, relPath);
    try {
      const stat = await vscode.workspace.fs.stat(vscode.Uri.file(absPath));
      if (stat.type !== vscode.FileType.File) continue;
      if (stat.size > 512 * 1024) continue;

      const raw = await vscode.workspace.fs.readFile(vscode.Uri.file(absPath));
      artifacts.push({
        path: relPath.replace(/\\/g, '/'),
        content: Buffer.from(raw).toString('utf8'),
        encoding: 'utf-8',
      });
    } catch {
      // Missing optional finalize artifacts are handled by the orchestrator normalizer.
    }
  }

  return artifacts;
}

async function collectFinalizeCandidateFiles(projectRootUri) {
  const artifacts = await collectFinalizeCandidateFileArtifacts(projectRootUri);
  return artifacts.map((item) => item.path);
}

module.exports = {
  buildHarperBody,
  extractUserMessages,
  defaultCoreForPhase,
  readPlanJson,
  runKitCommand,
  runLocalAgentSync,
  runEvalGateCommand,
  saveKitCommand,
  saveGateCommand,
  saveEvalCommand,
  getProjectId,
  resolveLatestReq,
  resolveProfilePath,
  preIndexRag,
  readTextFile,
  promoteReqSources,
  runPromotionFlow,
  copyTreeWithConflicts,
  getProjectNameFromWorkspace,
  normalizeAttachment,
  safeLog,
  readWorkspaceTextFile,
  getFileSizeBytes,
  normalizeChangedFiles,
  sanitize,
  logCurrentTimeStandard,
  httpPostJsonLong,
  ensureReqIdInPlan,
  buildAgentKitPrompt,
  collectReqCandidateFiles,
  buildAgentExecutionContext,
  writeAgentExecutionContext,
  buildAgentEvalPrompt,
  collectReqCandidateFiles,
  collectReqCandidateFileArtifacts,
  collectFinalizeCandidateFiles,
  collectFinalizeCandidateFileArtifacts,
}