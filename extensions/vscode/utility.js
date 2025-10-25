const vscode = require('vscode');
const cp = require('child_process');
const path = require('path');
//const { activateTestController } = require('./testController');
const { gatherRagChunks } = require('./rag.js');

const out = vscode.window.createOutputChannel('Clike.utility');
const crypto = require('crypto');
// usa Node.js fs per calcolare la size di un file
const fs = require('fs');
const { log } = require('console');

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
    const dst = vscode.Uri.joinPath(destRoot, rel.replace(/^\/+/, ''));

    await ensureDir(vscode.Uri.joinPath(dst, '..'));

    const dstExists = await isExisting(dst);
    if (!dstExists) {
      await copyFile(src, dst);
      actions.push({ op: 'copy', from: src.path, to: dst.path });
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
    } else if (strategy === 'skip') {
      actions.push({ op: 'skip_conflict', to: dst.path });
    } else if (strategy === 'backup') {
      const name = dst.path.split('/').pop();
      const parent = vscode.Uri.joinPath(dst, '..');
      const backup = vscode.Uri.joinPath(parent, `${name}.bak-${ts}`);
      await vscode.workspace.fs.rename(dst, backup, { overwrite: true });
      await vscode.workspace.fs.writeFile(dst, a);
      actions.push({ op: 'backup_then_write', old: dst.path, backup: backup.path });
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
    }
  }

  log(`[promote] actions=${actions.length}, diffs=${diffs.length}`);
  return { actions, diffs };
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

/**
 * Promote KIT sources into the workspace with conflict-safe strategies.
 * - Writes a JSON promotion manifest under runs/kit/<REQ>/promotion_manifest_<ts>.json
 * - Returns { manifestUri, actions, diffs }
 */
async function promoteReqSources(projectRootUri, reqId, strategy = 'folder', out) {
  const log = mkLog(out);

  if (!projectRootUri) {
    vscode.window.showErrorMessage('[promote] Workspace root not provided.');
    return null;
  }

  const srcDir = vscode.Uri.joinPath(projectRootUri, 'runs', 'kit', reqId, 'src');
  try {
    await vscode.workspace.fs.stat(srcDir);
  } catch {
    vscode.window.showWarningMessage(`[promote] No KIT src to promote for ${reqId}`);
    return null;
  }

  // Resolve destination root
  const ts = new Date().toISOString().replace(/[:.]/g, '-');
  let destRoot =  vscode.Uri.joinPath(projectRootUri, 'src');
  
  if (strategy === 'folder') {
    destRoot = vscode.Uri.joinPath(projectRootUri, 'promoted', `${reqId}_${ts}`);
    await vscode.workspace.fs.createDirectory(destRoot);
  }

  const { actions, diffs } = await copyTreeWithConflicts(srcDir, destRoot, { strategy, reqId, ts, log });

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
  try { await vscode.workspace.fs.createDirectory(manifestDir); } catch {}
  const manifestUri = vscode.Uri.joinPath(manifestDir, `promotion_manifest_${ts}.json`);
  await vscode.workspace.fs.writeFile(manifestUri, Buffer.from(JSON.stringify(manifest, null, 2), 'utf8'));

  return { manifestUri, actions, diffs };
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
      const r = await promoteReqSources(projectRootUri, target, strategy, out);
      return r;
    });

    if (!result) return;
    const { manifestUri, actions, diffs } = result;

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
    log('[promote] ERROR:', e?.message || String(e));
    vscode.window.showErrorMessage(`[promote] ${e?.message || e}`);
  }
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
          || name.toLowerCase().endsWith('.yaml') || name.toLowerCase().endsWith('.yml')
          || name.toLowerCase().endsWith('.json')) //for plan.json
     
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

async function runKitCommand( plan, cmdArgs) {
  out.appendLine(`[runKitCommand] ${cmdArgs}`);
  // cmdArgs: string dopo "/kit", es. "", "REQ-001"
  let targetReqId = (cmdArgs || '').trim() || null;
  if (!targetReqId) {
    targetReqId = findNextOpenReq(plan);
    if (!targetReqId) {
      vscode.window.showWarningMessage('No open REQ found in plan.json.');
      return;
    }
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
  

  await persistReports(projectRootUri, "eval", report, out)
  log(`[saveEvalCommand] persistReports done`);
  // opzionale: se non è ancora in_progress → mettilo
  const req = effectivePlan.reqs.find(r => (r.id || '').toUpperCase() === targetReqId.toUpperCase());
  if (req && (req.status || '').toLowerCase() === 'open') {
    setReqStatus(effectivePlan, targetReqId, 'in_progress');
    await writePlanJson(projectRootUri, effectivePlan);
    await updatePlanMdInPlace(projectRootUri, effectivePlan);
    log(`[PLAN synced to in_progress] ${targetReqId}`);
  }
}
// In utility.js (o dove hai definito persistReports)
async function persistReports(projectRootUri, phase, rep, out) {
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
  const req_id = rep.req_id || rep.reqId || rep.request_id || 'REQ-UNKNOWN';
  const profile = rep.profile || rep.profile_path || null;
  const mode = rep.mode || 'auto';
  const passed = rep.passed ;//Number.isInteger(rep.passed) ? rep.passed : 0;
  const failed = rep.failed ;//Number.isInteger(rep.failed) ? rep.failed : 0;
  const cases = Array.isArray(rep.cases) ? rep.cases : [];

  // runs/<phase>/<req_id>
  const outDirUri = vscode.Uri.joinPath(rootUri, 'runs', phase, req_id);
  log('[persistReports] outDirUri=', outDirUri);

  try { await vscode.workspace.fs.createDirectory(outDirUri); } catch (e) {
    log('[persistReports] createDirectory warning:', e?.message || String(e));
  }

  const ts = Date.now(); // ms per uniqueness
  const fileBase = `report_${req_id}_${ts}`;

  // Costruisci JSON “persistito” (coerente con orchestrator snake_case)
  const persisted = {
    profile,
    req_id,
    mode,
    passed,
    failed,
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
async function saveGateCommand(projectRootUri, plan, targetReqId,report, out) {
  const log = (m) => (out?.appendLine ? out.appendLine(m) : console.log(m));
  log(`[saveGateCommand] target=${targetReqId}`);

  let effectivePlan = plan || await readPlanJson(projectRootUri);
  if (!effectivePlan || !Array.isArray(effectivePlan.reqs)) return;

  if (!setReqStatus(effectivePlan, targetReqId, 'done')) {
    log(`[saveGateCommand] REQ ${targetReqId} not found in plan.json`);
  }

  await writePlanJson(projectRootUri, effectivePlan);
  await updatePlanMdInPlace(projectRootUri, effectivePlan);
  await persistReports(projectRootUri, "gate", report, out)
  if (report.gate.toLowerCase()==='pass') {
    log("[saveGateCommand] Gate passed for " + targetReqId);
    const choice = await vscode.window.showInformationMessage(
      `Gate passed for ${targetReqId}. Promote sources now?`,
      'Promote',
      'Cancel'
    );
    if (choice === 'Promote') {
      await runPromotionFlow(projectRootUri, targetReqId, out);
    }
  }
  try { vscode.window.showInformationMessage(`REQ ${targetReqId} marked as done.`); } catch {}
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
async function buildHarperBody(phase, payload, projectRootUri, rag_prefer_for,rag_enabler, out) {
  const log = (msg) => {
    if (out && typeof out.appendLine === 'function') out.appendLine(msg);
    else console.log(msg);
  };
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
    else if (phase === 'kit') {
       // 3) repoUrl
      const repoUrl = await detectRepoUrl(projectRootUri);
        if (repoUrl) payload["repoUrl"] = repoUrl;
    }
  } catch (err) {
    log('[CLike] saveTechConstraintsYaml failed:', err);
  }
  //4) core blobs
  const core_blobs = await attachCoreBlobs(_docRoot, payload["core"] || []);
  payload["idea_md"] = idea_md;
  payload["core_blobs"] = core_blobs;
  payload["rag_prefer_for"]= rag_prefer_for;
  //RAG SUGGENSTIONDS
  payload["rag_strategy"] = "prefer";                  // semantic hint
  // --- RAG ephemeral chunks from workspace (client-first) ---
  let rag_chunks
  if (rag_enabler) {
      try {
        rag_chunks = await gatherRagChunks(projectRootUri, rag_prefer_for);
        payload["rag_chunks"] = rag_chunks;
        log(`[CLike] attached ${rag_chunks.length} RAG chunks`);
        // --- RAG queries from headings (client hint) ---
        try {
          const qs = [];
          for (const ch of (rag_chunks|| [])) {
            const name = (ch.name || '').toLowerCase();
            const nnpref_lc = rag_prefer_for.map(function(txt) {
                return txt.toLowerCase();
            });
            if (nnpref_lc.includes(name) ) {
              const lines = (ch.text || '').split(/\r?\n/);
              const head = lines.find(l => /^#{1,3}\s/.test(l));
              if (head) qs.push(head.replace(/^#+\s*/, '').trim());
            }
          }
          if (qs.length) payload["rag_queries"] = qs.slice(0, 6);
            log(`[CLike] attached ${payload["rag_queries"].length} RAG chunks`);

        } catch (e) {
          log('[CLike] build rag queries failed:', e);
        }


      } catch (e) {
        log('[CLike] gatherRagChunks failed:', e);
      }   
  }

  payload["context_hard_limit"] = 6500;                // per budgeting lato gateway  
  //RAG HARPER END

  // 2) Body retro-compatibile + nuovi campi opzionali
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
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
}
const VALID_STATUSES = ['open', 'in_progress', 'done', 'deferred'];

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

  // Sostituisci o aggiungi Tabella
  if (rxTable.test(md)) {
    md = md.replace(rxTable, (_, heading /*, body*/) => {
      const contentLines = newTable.split('\n');
      contentLines.shift(); // rimuovi "## REQ-IDs Table"
      const content = contentLines.join('\n');
      return `${heading}${content}\n`;
    });
  } else {
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
    case "spec":
      return [];
    case "plan":
      return ["SPEC.md", "TECH_CONSTRAINTS.yaml"];
    case "kit":
      return ["SPEC.md", "PLAN.md", "TECH_CONSTRAINTS.yaml"];
    case "finalize":
      return ["SPEC.md", "PLAN.md", "TECH_CONSTRAINTS.yaml"];
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

    // 1) tenta testo
    const t = await readWorkspaceTextFile(p, out);
    if (t && t.trim()) {
      items.push({ path: p, text: t });
      log(`read ${p} -> text`);
      continue;
    }

    // 2) fallback: bytes -> base64 (PDF/DOCX ecc.)
    const buf = await readWorkspaceFileBytes(p);
    if (buf && buf.length) {
      items.push({ path: p, bytes_b64: buf.toString('base64') });
      log(`read ${p} -> binary (${buf.length}B)`);
    } else {
      log(`read ${p} -> skip (empty/unreadable)`);
    }
  }
  log(`items -> ${items.length}`);
  return items;
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

async function postJson(url, body, { signal } = {}) {
  const f = (typeof fetch === 'function')
    ? fetch
    : ((...args) => import('node-fetch').then(({ default: ff }) => ff(...args)));
  const res = await f(url, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify(body),
    signal
  });
  if (!res.ok) {
    const txt = await res.text().catch(() => '');
    throw new Error(`POST ${url} -> ${res.status} ${txt}`);
  }
  return await res.json();
}

// Pre-index RAG items before chat/generate. Non-blocking on failure.
async function preIndexRag(projectId, rag_files,url ,out) {
  const log = mkLog(out);
  //log('preIndexRag:', projectId, rag_files, url);
  const items = await buildRagItemsForIndex(rag_files, out);
  //log('preIndexRag items:', items);
  if (!items.length) return { ok: true, upserts: 0 };
  
  try {
    return await postJson(url, { project_id: projectId, items });
  } catch (e) {
    console.warn('[RAG] preIndex failed', e);
    return { ok: false, upserts: 0, error: String(e) };
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
  try { console.log(prefix, JSON.stringify(obj, null, 2)); }
  catch { console.log(prefix, obj); }
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

module.exports = {

  buildHarperBody,
  extractUserMessages,
  defaultCoreForPhase,
  readPlanJson,
  runKitCommand,
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
  getFileSizeBytes

};
