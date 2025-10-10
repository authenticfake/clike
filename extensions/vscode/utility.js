const vscode = require('vscode');
const cp = require('child_process');
const path = require('path');
//const { activateTestController } = require('./testController');
const { gatherRagChunks } = require('./rag.js');

const out = vscode.window.createOutputChannel('Clike.utility');

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

// PATCH 3 — selezione target e payload /kit (dentro handler del comando Harper)
async function runKitCommand(context, plan, cmdArgs) {
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
      return;
    }
  }

  // 2) Aggiorna stato REQ → done
  const ok = setReqStatus(effectivePlan, targetReqId, 'in_progress');
  if (!ok) {
    log(`[saveKitCommand] REQ ${targetReqId} not found in plan.json; no update performed.`);
    // Continuiamo comunque a scrivere il plan attuale, ma senza cambiare snapshot/table
  }

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
/**
 * /eval → non cambia stato (ma potresti marcare 'in_progress' se non lo è)
 */
async function saveEvalCommand(projectRootUri, plan, targetReqId, out) {
  const log = (m) => (out?.appendLine ? out.appendLine(m) : console.log(m));
  log(`[saveEvalCommand] target=${targetReqId}`);

  let effectivePlan = plan || await readPlanJson(projectRootUri);
  if (!effectivePlan || !Array.isArray(effectivePlan.reqs)) return;

  // opzionale: se non è ancora in_progress → mettilo
  const req = effectivePlan.reqs.find(r => (r.id || '').toUpperCase() === targetReqId.toUpperCase());
  if (req && (req.status || '').toLowerCase() === 'open') {
    setReqStatus(effectivePlan, targetReqId, 'in_progress');
    await writePlanJson(projectRootUri, effectivePlan);
    await updatePlanMdInPlace(projectRootUri, effectivePlan);
    log(`[PLAN synced to in_progress] ${targetReqId}`);
  }
}

/**
 * /gate → porta REQ a done e sincronizza artefatti
 */
async function saveGateCommand(projectRootUri, plan, targetReqId, out) {
  const log = (m) => (out?.appendLine ? out.appendLine(m) : console.log(m));
  log(`[saveGateCommand] target=${targetReqId}`);

  let effectivePlan = plan || await readPlanJson(projectRootUri);
  if (!effectivePlan || !Array.isArray(effectivePlan.reqs)) return;

  if (!setReqStatus(effectivePlan, targetReqId, 'done')) {
    log(`[saveGateCommand] REQ ${targetReqId} not found in plan.json`);
  }

  await writePlanJson(projectRootUri, effectivePlan);
  await updatePlanMdInPlace(projectRootUri, effectivePlan);
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
  log('[buildHarperBody] gen', payload['gen']);
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

function setReqStatus(plan, reqId, status) {
  if (!plan || !Array.isArray(plan.reqs)) return false;
  const r = plan.reqs.find(x => (x.id || '').trim().toUpperCase() === (reqId || '').trim().toUpperCase());
  if (!r) return false;
  r.status = status;
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


async function updatePlanMdInPlace(projectRootUri, plan) {
  const uri = vscode.Uri.joinPath(projectRootUri, 'docs', 'harper', 'PLAN.md');
  const md = await readTextFile(uri);
  if (!md) return;

  const ss = snapshotCounts(plan);
  const newSnapshot = renderSnapshotMd(ss);
  const newTable = renderReqTableMd(plan);

  const snapRx = /(##\s*Plan Snapshot)([\s\S]*?)(?=^##\s|\Z)/m;
  const tableRx = /(##\s*REQ-IDs Table)([\s\S]*?)(?=^##\s|\Z)/m;

  let out = md;
  out = snapRx.test(out) ? out.replace(snapRx, newSnapshot) : (newSnapshot + '\n' + out);
  out = tableRx.test(out) ? out.replace(tableRx, newTable) : (out + '\n\n' + newTable);

  await writeTextFile(uri, out);
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
      return ["SPEC.md", "PLAN.md", "KIT.md", "TECH_CONSTRAINTS.yaml"];
    case "build":
      return ["SPEC.md", "PLAN.md", "KIT.md", "BUILD_REPORT.md", "TECH_CONSTRAINTS.yaml"];
    case "finalize":
      return ["SPEC.md", "PLAN.md", "KIT.md", "BUILD_REPORT.md", "RELEASE_NOTES.md", "TECH_CONSTRAINTS.yaml"];
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
    return 
  } else {
    return 'default';
    
  }
} catch (e) {
  console.warn('[CLike] project_id derivation failed:', e);
  body.project_id = 'default';
}
}

module.exports = {

  buildHarperBody,
  extractUserMessages,
  defaultCoreForPhase,
  readPlanJson,
  runKitCommand,
  saveKitCommand,
  saveGateCommand,
  saveEvalCommand,
  getProjectId,
  resolveLatestReq

};
