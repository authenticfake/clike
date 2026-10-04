// extension.js — Clike Orchestrator+Gateway integration GOOGDDDD
const vscode = require('vscode');
const out = vscode.window.createOutputChannel('Clike.telemetry');

/**
 * Custom logging function that writes to both channels.
 * @param {...any} args Messages or objects to log.
 */
function log(...args) {
    // 1. Log to the standard console for debugging.
    console.log(...args); 
    
    // 2. Log to the VS Code output channel.
    out.appendLine(args.map(arg => {
        // Convert each argument to a string for output.
        if (typeof arg === 'object' && arg !== null) {
            return JSON.stringify(arg, null, 2);
        }
        return String(arg);
    }).join(' ')); 
}


// --- Telemetry helpers (VS Code side) ---------------------------------------
function telemetryProjectDirUri(wsroot, projectId) {
  // client-side folder for local exploration and UI
  return vscode.Uri.joinPath(wsroot, '.clike', 'telemetry', String(projectId || 'default'));
}

function telemetryAppendFileUri(wsroot, projectId) {
  // append-only, handy for quick charts/aggregations on the UI side
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
    // robust append (read+concat) for compatibility
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
 * Persist two forms:
 *  1) runs/<runId>/telemetry.json (idempotent overwrite per single run/phase)
 *  2) .clike/telemetry/<projectId>/<YYYY-MM>.jsonl (append-only for charts)
 */
async function persistTelemetryVSCode(wsroot, projectId, runId, phase, telemetryLikeObj) {

  if (!wsroot || !telemetryLikeObj) return;
  log(`persistTelemetryVSCode(${projectId}, ${runId}, ${phase} len=${Object.keys(telemetryLikeObj).length})`);
  // normalize for safety
  const t = {
    project_id: projectId,
    run_id: runId,
    phase,
    ts: Date.now(),
    ...telemetryLikeObj
  };

             

  // (2) append-only stream for dashboards
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