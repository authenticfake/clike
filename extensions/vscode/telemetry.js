// extension.js — Clike Orchestrator+Gateway integration GOOGDDDD
const vscode = require('vscode');
const out = vscode.window.createOutputChannel('Clike.telemetry');
const fs = require('fs');

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


// --- Telemetry helpers (VS Code side) ---------------------------------------
function telemetryProjectDirUri(wsroot, projectId) {
  // cartella client-side per esplorazione e UI locali
  return vscode.Uri.joinPath(wsroot, '.clike', 'telemetry', String(projectId || 'default'));
}
function telemetryRunFileUri(wsroot, runId, phase) {
  // mirror dello schema Harper ufficiale (per compat): runs/<runId>/telemetry.json
  return vscode.Uri.joinPath(wsroot, 'runs', String(runId || 'unknown'), 'telemetry.json');
}
function telemetryAppendFileUri(wsroot, projectId) {
  // append-only, utile per grafici/aggregazioni veloci lato UI
  const d = new Date();
  const y = String(d.getUTCFullYear());
  const m = String(d.getUTCMonth()+1).padStart(2,'0');
  return vscode.Uri.joinPath(telemetryProjectDirUri(wsroot, projectId), `${y}-${m}.jsonl`);
}

async function ensureDirUri(dir) {
  try { await vscode.workspace.fs.createDirectory(dir); } catch {}
}

async function writeJsonUri(uri, obj) {
  const enc = Buffer.from(JSON.stringify(obj, null, 2), 'utf8');
  await ensureDirUri(vscode.Uri.joinPath(uri, '..'));
  try { await vscode.workspace.fs.writeFile(uri, enc); }
  catch (e) { vscode.window.showWarningMessage(`Telemetry write failed: ${e?.message||e}`); }
}

async function appendLineUri(uri, line) {
  const enc = Buffer.from(line + '\n', 'utf8');
  await ensureDirUri(vscode.Uri.joinPath(uri, '..'));
  try {
    // append robusto (read+concat) per compatibilità
    const exists = await vscode.workspace.fs.stat(uri).then(()=>true).catch(()=>false);
    if (exists) {
      const old = await vscode.workspace.fs.readFile(uri);
      await vscode.workspace.fs.writeFile(uri, Buffer.concat([old, enc]));
    } else {
      await vscode.workspace.fs.writeFile(uri, enc);
    }
  } catch (e) {
    vscode.window.showWarningMessage(`Telemetry append failed: ${e?.message||e}`);
  }
}

/**
 * Persisti due forme:
 *  1) runs/<runId>/telemetry.json (overwrite idempotente per singolo run/phase)
 *  2) .clike/telemetry/<projectId>/<YYYY-MM>.jsonl (append-only per grafici)
 */
async function persistTelemetryVSCode(wsroot, projectId, runId, phase, telemetryLikeObj) {

  if (!wsroot || !telemetryLikeObj) return;
  log(`persistTelemetryVSCode(${projectId}, ${runId}, ${phase}, ${JSON.stringify(telemetryLikeObj, null, 2)})`);
  // normalizza per sicurezza
  const t = {
    project_id: projectId,
    run_id: runId,
    phase,
    ts: Date.now(),
    ...telemetryLikeObj
  };

             
  // // (1) file deterministico per evitare duplicati
  // const runFile = telemetryRunFileUri(wsroot, runId, phase);
  // log(`persistTelemetryVSCode: writing ${runFile.fsPath}`);
  // await writeJsonUri(runFile, t);

  // (2) stream append-only per dashboard
  const line = JSON.stringify({
    project_id: projectId,
    run_id: runId,
    phase,
    timestamp: new Date().toISOString(),
    provider: t.provider || t.pricing?.provider || t.model?.provider || null,
    model: t.model || null,
    usage: t.usage || t.snapshot || {},
    pricing: t.pricing || null,
    files_len: Array.isArray(t.files) ? t.files.length : (t.files_len ?? null),
    meta: { client: 'vscode', source: 'extension' }
  });
  const streamFile = telemetryAppendFileUri(wsroot, projectId);
  await appendLineUri(streamFile, line);
  log(`persistTelemetryVSCode: appended ${streamFile.fsPath}`);
}

module.exports = { persistTelemetryVSCode };