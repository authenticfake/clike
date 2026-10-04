// extension.js — Clike Orchestrator+Gateway integration GOOGDDDD
const vscode = require('vscode');
const out = vscode.window.createOutputChannel('Clike.telemetry');

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
  log(`persistTelemetryVSCode(${projectId}, ${runId}, ${phase} len=${Object.keys(telemetryLikeObj).length})`);
  // normalizza per sicurezza
  const t = {
    project_id: projectId,
    run_id: runId,
    phase,
    ts: Date.now(),
    ...telemetryLikeObj
  };

             

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
  log( `persistTelemetryVSCode: appending ${line}`);
  const streamFile = telemetryAppendFileUri(wsroot, projectId);
  await appendLineUri(streamFile, line);
  log(`persistTelemetryVSCode: appended ${streamFile.fsPath}`);
}

module.exports = { persistTelemetryVSCode };