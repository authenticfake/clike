const vscode = require('vscode');
const path = require('path');
const os = require('os');
const crypto = require('crypto');
const fs = require('fs');


// --- PATCH: git auto-commit/tags/branch ---
const cp = require('child_process');
/** Expand "~" and coerce VSCode Uri / Path-like objects to fsPath string */
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

// Ritorna true se il working tree ha modifiche non committate/non staggate
async function isWorkingTreeDirty(gitCtx) {
  try {
    const out = await gitRunVerbose(['status', '--porcelain'], gitCtx, 'diag');
    return Boolean(out && out.trim().length > 0);
  } catch {
    return false;
  }
}

async function gitRun(args, cwd) {
  const workdir = toFsPath(cwd);
  return new Promise((resolve, reject) => {
    // IMPORTANT: use 'cwd', not '_cwd'
    cp.execFile('git', args, { cwd: workdir }, (err, stdout, stderr) => {
      if (err) return reject(new Error((stderr || err.message || '').trim()));
      resolve((stdout || '').trim());
    });
  });
}

function toFsPath(input) {
  if (!input) return '';
  // vscode.Uri
  if (input && typeof input === 'object' && input.scheme && input.fsPath) return input.fsPath;
  // URL object
  if (input instanceof URL) return input.pathname || String(input);
  // Oggetti generici che espongono .path o .toString()
  if (input && typeof input === 'object') {
    if (typeof input.path === 'string') return input.path;
    if (typeof input.toString === 'function') {
      const s2 = input.toString();
      if (s2 && typeof s2 === 'string') return s2;
    }
  }
  let s = String(input).trim();

  // **FIX**: converti "file://..." (anche se è una semplice stringa) in path locale
  if (s.startsWith('file://')) {
    try {
      // gestisce anche spazi/encoding
      const u = new URL(s);
      // su macOS/Unix: u.pathname è già un path assoluto
      s = decodeURI(u.pathname);
    } catch {
      // fallback grezzo (toglie il prefisso)
      s = s.replace(/^file:\/\//, '');
    }
  }

  if (s.startsWith('~')) s = path.join(os.homedir(), s.slice(1));
  return s;
}


function sha1(s) {
  return crypto.createHash('sha1').update(String(s)).digest('hex');
}

function isDirWritable(dir) {
  try {
    const p = path.join(dir, `.clike-write-test-${Date.now()}`);
    fs.writeFileSync(p, 'ok');
    fs.unlinkSync(p);
    return true;
  } catch {
    return false;
  }
}

// Costruisce un contesto git per un workspace anche se è read-only.
// Se la cartella è scrivibile: usa .git locale (preArgs=[]).
// Se è sola lettura: usa separate-git-dir sotto ~/.clike/git/<hash>.
function resolveGitContext(workspaceRoot, defaultBranch = 'main') {
  const cwd = toFsPath(workspaceRoot);
  const writable = isDirWritable(cwd);

  if (writable) {
    return {
      mode: 'local',
      cwd,
      preArgs: [], // nessun --git-dir/--work-tree
      gitDir: path.join(cwd, '.git'),
      workTree: cwd,
      ensureInitNeeded: true
    };
  }

  const root = path.join(os.homedir(), '.clike', 'git');
  const repoId = sha1(cwd).slice(0, 12);
  const gitDir = path.join(root, repoId, '.git'); // teniamo una struttura familiare
  const workTree = cwd;

  return {
    mode: 'separate',
    cwd,                  // eseguiamo comunque da work-tree
    preArgs: ['--git-dir', gitDir, '--work-tree', workTree],
    gitDir,
    workTree,
    ensureInitNeeded: true
  };
}


// Verbose git wrapper (uses your existing gitRun)
async function gitRunVerbose(args, gitCtx, label = 'git', _out) {
  const log = mkLog(_out);
  const pre = Array.isArray(gitCtx?.preArgs) ? gitCtx.preArgs : [];
  const cwd = toFsPath(gitCtx?.cwd || process.cwd());
  const fullArgs = [...pre, ...args];
  try {
    log(`[${label}] $ git ${fullArgs.join(' ')} @ ${cwd}`);
    const out = await gitRun(fullArgs, cwd); // usa la tua gitRun esistente (execFile/spawn)
    if (out && String(out).trim().length) log(`[${label}] out: ${String(out).trim()}`);
    return out;
  } catch (e) {
    log(`[${label}] ERROR: ${e?.message || e}`);
    if (e?.stderr) log(`[${label}] stderr: ${e.stderr}`);
    throw e;
  }
}

// Ensure the default branch exists locally.
// If the repo has no commits, create an empty commit to materialize the branch.
async function ensureDefaultBranchExists(gitRunVerbose, gitCtx, defaultBranch) {
  let hasCommits = true;
  try { await gitRunVerbose(['rev-parse', 'HEAD'], gitCtx, 'diag'); }
  catch { hasCommits = false; }

  // Create/switch default branch in an idempotent way
  await gitRunVerbose(['checkout', '-B', defaultBranch], gitCtx);

  if (!hasCommits) {
    // Bootstrap an empty commit so the branch actually exists
    try {
      await gitRunVerbose(['commit', '--allow-empty', '-m', `chore: bootstrap ${defaultBranch}`], gitCtx, 'init');
    } catch (e) {
      // If user.name/email are missing, ensureGitRepo should have configured them
    }
  }
}


// Ensure repo exists; if not, initialize it and set default branch
async function ensureGitRepo(gitCtx, defaultBranch = 'main', out) {
  const log = mkLog(out);
  // già repo?
  try {
    await gitRunVerbose(['rev-parse', '--is-inside-work-tree'], gitCtx, 'diag', out);
    log('[git:init] repository already initialized');
    return;
  } catch {
    log('[git:init] repository not initialized → creating...');
  }

  // Assicura directory del gitDir in modalità separate
  if (gitCtx.mode === 'separate') {
    const dir = path.dirname(gitCtx.gitDir);
    fs.mkdirSync(dir, { recursive: true });
  }

  // Init
  let inited = false;
  try {
    // Modern git: init -b <branch>
    await gitRunVerbose(['init', '-b', defaultBranch], gitCtx, 'init', out);
    inited = true;
  } catch {
    await gitRunVerbose(['init'], gitCtx, 'init', out);
    try { await gitRunVerbose(['checkout', '-b', defaultBranch], gitCtx, 'init', out); } catch {}
    inited = true;
  }

  // In modalità separate, dobbiamo puntare la work-tree
  if (gitCtx.mode === 'separate') {
    try {
      await gitRunVerbose(['config', 'core.worktree', gitCtx.workTree], gitCtx, 'init', out);
    } catch {}
  }

  // Identity best-effort
  try { await gitRunVerbose(['config', '--get', 'user.name'], gitCtx, 'diag', out); }
  catch { try { await gitRunVerbose(['config', 'user.name', os.userInfo().username || 'clike'], gitCtx, 'init', out); } catch {} }
  try { await gitRunVerbose(['config', '--get', 'user.email'], gitCtx, 'diag', out); }
  catch { try { await gitRunVerbose(['config', 'user.email', 'dev@local'], gitCtx, 'init', out); } catch {} }

  // Primo commit opzionale solo se ci sono file staged
  try {
    await gitRunVerbose(['add', '-A'], gitCtx, 'init', out);
    await gitRunVerbose(['diff', '--cached', '--quiet'], gitCtx, 'init', out); // 0 = no staged changes
    log('[git:init] no files to commit yet (empty repo)');
  } catch {
    try { await gitRunVerbose(['commit', '-m', 'chore: initial commit (clike init)'], gitCtx, 'init'); } catch {}
  }
    // Ensure default branch is present and checked out (idempotent)
  try {
    await ensureDefaultBranchExists(gitRunVerbose, gitCtx, defaultBranch);
  } catch (e) {
    mkLog(out)('[git:init] ensureDefaultBranchExists warn:', e.message || e);
  }

}


// Ensure remote exists; optionally configure it if URL provided
async function ensureRemote(gitCtx, remoteName, remoteUrlOrEmpty, out) {
  const log = mkLog(out);
  try {
    const url = await gitRunVerbose(['remote', 'get-url', remoteName], gitCtx, 'diag', out);
    log(`[git:remote] ${remoteName}=${String(url || '').trim()}`);
    return true;
  } catch {
    if (!remoteUrlOrEmpty) {
      log(`[git:remote] remote '${remoteName}' missing and no URL provided → will commit locally and skip push`);
      return false;
    }
    log(`[git:remote] adding remote '${remoteName}' → ${remoteUrlOrEmpty}`);
    try {
      await gitRunVerbose(['remote', 'add', remoteName, remoteUrlOrEmpty], gitCtx, 'remote', out);
      return true;
    } catch (e) {
      log(`[git:remote] cannot add remote: ${e.message}`);
      return false;
    }
  }
}

function mapKitSrcToWorkspaceTarget(absPath, reqId) {
  // Esempio input:
  // /.../runs/kit/REQ-001/src/storage/models.py
  // Output atteso:
  // /.../src/storage/models.py
  try {
    if (!absPath) return '';
    const marker = `/runs/kit/${reqId}/src/`;
    const idx = absPath.indexOf(marker);
    if (idx === -1) return absPath; // già target o fuori convenzione
    return absPath.slice(0, idx) + '/src/' + absPath.slice(idx + marker.length);
  } catch {
    return absPath;
  }
}


async function clikeGitSync(phase, runId, reqId, changedFiles, opts, settings, out) {
  const log = mkLog(out);
  const cwdFsPath = toFsPath(opts?.workspaceRoot);
  if (!cwdFsPath || cwdFsPath === '/' || cwdFsPath.trim().length === 0) {
    throw new Error('[clikeGit] No valid workspaceRoot: open a folder in VS Code before running Harper commands.');
  }

  const s = settings;
  const cwd = toFsPath(opts.workspaceRoot);
  const gitCtx = resolveGitContext(cwd, s.gitDefaultBranch);

  log(`[git] phase=${phase} runId=${runId} reqId=${reqId || '∅'} files=${Array.isArray(changedFiles) ? changedFiles.length : '∅'} mode=${gitCtx.mode}`);
  if (!s.gitAutoCommit) { log('[git] autoCommit=false → skip'); return; }

  // 1) Repo pronto
  await ensureGitRepo(gitCtx, s.gitDefaultBranch);

  // 2) Remote (opzionale)
  const hasRemote = await ensureRemote(gitCtx, s.gitRemote, s.gitRemoteUrl || '');

  // 3) Branch target
  let targetBranch = s.gitDefaultBranch;
  if (phase === 'kit' || phase === 'eval' || phase === 'gate') {
    if (!reqId) throw new Error('REQ-ID required for phase=' + phase);
    const slug = String(reqId).toLowerCase();
    targetBranch = `${s.gitBranchPrefix}/${slug}`;
  }
  log(`[git] targetBranch=${targetBranch}`);

  // 4) Allineamento con default branch + checkout target
  if (hasRemote) {
    try { await gitRunVerbose(['fetch', s.gitRemote], gitCtx); } catch (e) { log(`[git] fetch warn: ${e.message}`); }
  }

  // Verifica esistenza branch target
  let exists = false;
  try { await gitRunVerbose(['show-ref', '--verify', `refs/heads/${targetBranch}`], gitCtx); exists = true; } catch {}

  if (!exists) {
    // Base nuova branch su default
    await gitRunVerbose(['checkout', '-B', s.gitDefaultBranch], gitCtx);
    if (hasRemote && s.gitPushRebase) {
      // Rebase "best effort" — se dirty, salta
      try {
        const dirty = await isWorkingTreeDirty(gitCtx);
        if (!dirty) {
          await gitRunVerbose(['pull', '--rebase', s.gitRemote, s.gitDefaultBranch], gitCtx);
        } else {
          log('[git] default branch dirty → skip pull --rebase');
        }
      } catch (e) { log(`[git] pull warn: ${e.message}`); }
    }
    if (targetBranch !== s.gitDefaultBranch) {
      await gitRunVerbose(['checkout', '-B', targetBranch], gitCtx);
    }
  } else {
    await gitRunVerbose(['checkout', '-B', targetBranch], gitCtx);
    // Rebase sul default remoto solo se richiesto e se non c'è sporco
    if (hasRemote && targetBranch !== s.gitDefaultBranch && s.gitPushRebase) {
      try {
        await gitRunVerbose(['fetch', s.gitRemote, s.gitDefaultBranch], gitCtx);
        const dirty = await isWorkingTreeDirty(gitCtx);
        if (!dirty) {
          await gitRunVerbose(['rebase', `${s.gitRemote}/${s.gitDefaultBranch}`], gitCtx);
        } else {
          log('[git] working tree dirty → skip rebase');
        }
      } catch (e) { log(`[git] rebase warn: ${e.message}`); }
    }
  }

  // 5) Stage dei file passati (normalizzazione robusta)
  const toArray = (val) => {
    if (!val) return [];
    if (Array.isArray(val)) return val;
    if (typeof val === 'string') return val.split(',').map(s => s.trim()).filter(Boolean);
    return [String(val)];
  };

  
  // helper: rendi relativi i path alla work-tree (git preferisce)
  const toWorkTreeRelative = (pAbs) => {
    const wt = path.resolve(gitCtx.workTree || gitCtx.cwd || process.cwd());
    const p = path.resolve(pAbs);
    if (p.startsWith(wt)) {
      const rel = path.relative(wt, p);
      return rel.length ? rel : '.';
    }
    // se fuori dal repo, lascia assoluto (git lo accetta se dentro work-tree; se no, verrà filtrato)
    return p;
  };

  let files = toArray(changedFiles)
    .map(f => {
      try { return toFsPath(f); } catch { return String(f || ''); }
    })
    .filter(Boolean)
    .map(p => toWorkTreeRelative(p))
    .filter(p => {
      // evita di passare a git path inesistenti
      const abs = path.isAbsolute(p) ? p : path.join(gitCtx.workTree || gitCtx.cwd || process.cwd(), p);
      return fs.existsSync(abs);
    });

  try {
    if (files.length) {
      await gitRunVerbose(['add', ...files], gitCtx);
    } else {
      // nessun file valido → tenta add -A (può capitare se i file non sono ancora stati scritti)
      await gitRunVerbose(['add', '-A'], gitCtx);
    }
  } catch (e) {
    // fallback: aggiungi 1-per-1, così i validi passano comunque
    for (const f of files) {
      try { await gitRunVerbose(['add', f], gitCtx); }
      catch (e2) { mkLog(out)(`[git] add skip file '${f}': ${e2.message}`); }
    }
  }

  // 6) Commit
  const makeMsg = () => {
    const base = `[harper:${phase}] runId=${runId}`;
    if (!s.gitConventional) return base;
    if (phase === 'spec')     return `spec: update SPEC.md\n\n${base}`;
    if (phase === 'plan')     return `plan: update PLAN.md\n\n${base}`;
    if (phase === 'kit')      return `feat(${String(reqId||'req').toLowerCase()}): implement\n\n${base}`;
    if (phase === 'eval')     return `test(${String(reqId||'req').toLowerCase()}): add eval artifacts\n\n${base}`;
    if (phase === 'gate')     return `chore(${String(reqId||'req').toLowerCase()}): gate report & promotion\n\n${base}`;
    if (phase === 'finalize') return `chore: finalize\n\n${base}`;
    return base;
  };
  try { await gitRunVerbose(['commit', '-m', makeMsg()], gitCtx); }
  catch (e) { log(`[git] commit skipped: ${e.message}`); }

  // 7) Push (se remoto configurato)
  if (hasRemote) {
    try {
      const upstream = await gitRunVerbose(['rev-parse', '--abbrev-ref', '--symbolic-full-name', '@{u}'], gitCtx).catch(() => '');
      if (!upstream) await gitRunVerbose(['push', '--set-upstream', s.gitRemote, targetBranch], gitCtx);
      else await gitRunVerbose(['push'], gitCtx);
    } catch (e) { log(`[git] push warn: ${e.message}`); }
  } else {
    log(`[git] no remote configured → committed locally. Set "clike.git.remoteUrl" to enable pushes.`);
  }

  // 8) Tag (best-effort)
  const tag = `${s.gitTagPrefix}/${phase}/${runId}`;
  try {
    await gitRunVerbose(['tag', '-a', tag, '-m', tag], gitCtx);
    if (hasRemote) await gitRunVerbose(['push', s.gitRemote, tag], gitCtx);
  } catch (e) { log(`[git] tag warn: ${e.message}`); }

  // 9) Merge su default branch quando phase === 'gate'
  if (phase === 'gate' && s.gitMergeOnGate === true) {
    try {
      // Vai sul default, aggiorna, unisci no-ff, push
      await gitRunVerbose(['checkout', s.gitDefaultBranch], gitCtx);
      if (hasRemote && s.gitPushRebase) {
        try {
          const dirtyMain = await isWorkingTreeDirty(gitCtx);
          if (!dirtyMain) {
            await gitRunVerbose(['pull', '--rebase', s.gitRemote, s.gitDefaultBranch], gitCtx);
          } else {
            log('[git] main dirty → skip pull --rebase before merge');
          }
        } catch (e) { log(`[git] pull main warn: ${e.message}`); }
      }

      await gitRunVerbose(['merge', '--no-ff', targetBranch, '-m', `merge: ${reqId} via gate [runId=${runId}]`], gitCtx);

      if (hasRemote) {
        try { await gitRunVerbose(['push', s.gitRemote, s.gitDefaultBranch], gitCtx); } 
        catch (e) { log(`[git] push main warn: ${e.message}`); }
      }

      // Opzionale: delete branch feature dopo merge
      if (s.gitDeleteBranchOnMerge === true) {
        try {
          await gitRunVerbose(['branch', '-d', targetBranch], gitCtx);
          if (hasRemote) { await gitRunVerbose(['push', s.gitRemote, '--delete', targetBranch], gitCtx); }
        } catch (e) { log(`[git] delete branch warn: ${e.message}`); }
      }

      // Torna al branch feature se preferisci (o resta su main)
      if (s.gitReturnToFeatureAfterMerge === true) {
        try { await gitRunVerbose(['checkout', targetBranch], gitCtx); } catch {}
      }

    } catch (e) {
      log(`[git] merge-on-gate warn: ${e.message}`);
    }
  }

  // 10) PR per-REQ (opzionale)
  if (phase === 'kit' && s.prPerReqDraft && hasRemote) {
    const title = `[CLike] ${reqId} — draft`;
    try {
      await gitRunVerbose(['push', '-u', s.gitRemote, targetBranch], gitCtx);
      if (s.prUseGhCli) {
        await gitRunVerbose(['gh', 'pr', 'create', '--title', title, '--draft', '--fill'], gitCtx, 'gh');
      } else {
        await vscode.commands.executeCommand('github.createPullRequest');
      }
    } catch (e) { log(`[git] gh pr create skipped: ${e.message}`); }
  }

  if (phase === 'finalize' && opts?.finalizeOpenPr === true && hasRemote) {
    const title = `[CLike] Finalize`;
    try {
      await gitRunVerbose(['checkout', s.gitDefaultBranch], gitCtx);
      if (hasRemote && s.gitPushRebase) { try { await gitRunVerbose(['pull', '--rebase', s.gitRemote, s.gitDefaultBranch], gitCtx); } catch {} }
      if (s.prUseGhCli) {
        const args = ['gh', 'pr', 'create', '--title', title];
        if (s.prBodyPath) args.push('--body-file', s.prBodyPath); else args.push('--fill');
        await gitRunVerbose(args, gitCtx, 'gh');
      } else {
        await vscode.commands.executeCommand('github.createPullRequest');
      }
    } catch (e) { log(`[git] finalize PR skipped: ${e.message}`); }
  }
}


async function gitDebugSnapshot(gitCtx, out) {
  const log = mkLog(out);
  try { await gitRunVerbose(['rev-parse', '--is-inside-work-tree'], gitCtx, 'diag', out); } catch {}
  try { await gitRunVerbose(['status', '--porcelain'], gitCtx, 'diag', out); } catch {}
  try { await gitRunVerbose(['remote', '-v'], gitCtx, 'diag', out); } catch {}
  try { await gitRunVerbose(['branch', '--show-current'], gitCtx, 'diag', out); } catch {}
  try { await gitRunVerbose(['config', '--get', 'user.name'], gitCtx, 'diag', out); } catch {}
  try { await gitRunVerbose(['config', '--get', 'user.email'], gitCtx, 'diag', out); } catch {}
  try { await gitRunVerbose(['ls-files'], gitCtx, 'diag', out); } catch {}
  try { await gitRunVerbose(['rev-parse', 'HEAD'], gitCtx, 'diag', out); } catch {}
  try { await gitRunVerbose(['ls-remote', 'origin'], gitCtx, 'diag', out); } catch (e) { log(`[diag] ls-remote failed: ${e.message}`); }
  // gh (best-effort)
  try { await gitRunVerbose(['--version'], gitCtx, 'gh', out); } catch {}
  try { await gitRunVerbose(['auth', 'status'], gitCtx, 'gh', out); } catch {}
}

async function mergeOnGate(gitCtx, s, hasRemote, targetBranch, runId, reqId, out) {
  const log = mkLog(out);
  if (s.gitMergeOnGate !== true) {
    log('[git:gate] mergeOnGate skipped (gitMergeOnGate !== true)');
    return;
  }

  const defaultBranch = s.gitDefaultBranch || 'master';

  try {
    // 1) Vai sul default branch
    await gitRunVerbose(['checkout', defaultBranch], gitCtx);

    // 2) Aggiorna il default (best-effort)
    if (hasRemote && s.gitPushRebase) {
      try {
        const dirty = await isWorkingTreeDirty(gitCtx);
        if (!dirty) {
          await gitRunVerbose(['pull', '--rebase', s.gitRemote, defaultBranch], gitCtx);
        } else {
          log('[git:gate] default branch dirty → skip pull --rebase');
        }
      } catch (e) { log(`[git:gate] pull warn: ${e.message}`); }
    }

    // 3) Merge no-ff della feature
    const msg = `merge: ${reqId || 'REQ'} via gate [runId=${runId}]`;
    await gitRunVerbose(['merge', '--no-ff', targetBranch, '-m', msg], gitCtx);

    // 4) Push del default (se c'è remote)
    if (hasRemote) {
      try { await gitRunVerbose(['push', s.gitRemote, defaultBranch], gitCtx); }
      catch (e) { log(`[git:gate] push default warn: ${e.message}`); }
    }

    // 5) (Opz) elimina la branch feature locale/remota
    if (s.gitDeleteBranchOnMerge === true) {
      try {
        await gitRunVerbose(['branch', '-d', targetBranch], gitCtx);
        if (hasRemote) { await gitRunVerbose(['push', s.gitRemote, '--delete', targetBranch], gitCtx); }
      } catch (e) { log(`[git:gate] delete feature warn: ${e.message}`); }
    }

    log(`[git:gate] merge completed: ${targetBranch} -> ${defaultBranch}`);
  } catch (e) {
    log(`[git:gate] mergeOnGate warn: ${e.message}`);
  }
}

module.exports = {
    clikeGitSync,
    toFsPath,
    mapKitSrcToWorkspaceTarget
}