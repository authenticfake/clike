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

  // Bootstrap with an empty commit: existing workspace files are never committed
  // implicitly (they may include secrets such as .env).
  try {
    await gitRunVerbose(['commit', '--allow-empty', '-m', `chore: bootstrap ${defaultBranch} (clike init)`], gitCtx, 'init', out);
  } catch (e) {
    log(`[git:init] bootstrap commit warn: ${e.message || e}`);
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
  try {
    if (!absPath) return '';

    const normalized = String(absPath).replace(/\\/g, '/');
    const baseMarker = `/runs/kit/${reqId}/`;

    const idx = normalized.indexOf(baseMarker);
    if (idx === -1) return absPath;

    const rest = normalized.slice(idx + baseMarker.length);

    if (rest.startsWith('src/')) {
      return normalized.slice(0, idx) + '/src/' + rest.slice('src/'.length);
    }
    if (rest.startsWith('test/')) {
      return normalized.slice(0, idx) + '/test/' + rest.slice('test/'.length);
    }
    if (rest.startsWith('docs/')) {
      return normalized.slice(0, idx) + '/docs/' + rest.slice('docs/'.length);
    }

    return absPath;
  } catch {
    return absPath;
  }
}


// Harper phase → git (WP5). Non-destructive by design:
//  - never `checkout -B` (it resets an existing branch to HEAD and can drop commits);
//  - the default branch is never moved except by an explicit merge-on-gate;
//  - only the files declared by the phase are staged and committed
//    (`git commit -- <paths>`), unrelated user changes stay untouched;
//  - push happens only with clike.git.autoPush (or an explicitly enabled PR flow).
async function clikeGitSync(phase, runId, reqId, changedFiles, opts, settings, out) {
  const log = mkLog(out);
  const cwdFsPath = toFsPath(opts?.workspaceRoot);
  if (!cwdFsPath || cwdFsPath === '/' || cwdFsPath.trim().length === 0) {
    throw new Error('[clikeGit] No valid workspaceRoot: open a folder in VS Code before running Harper commands.');
  }

  const s = settings;
  const gitCtx = resolveGitContext(cwdFsPath, s.gitDefaultBranch);
  const defaultBranch = s.gitDefaultBranch || 'main';
  const autoPush = s.gitAutoPush === true;
  const conventional = s.gitConventionalCommits ?? s.gitConventional;
  const prPerReqDraft = s.gitPrPerReqDraftEnabled ?? s.prPerReqDraft;
  const prUseGhCli = s.gitPrPerReqDraftUseGhCli ?? s.prUseGhCli;
  const prBodyPath = s.gitPrBodyPath ?? s.prBodyPath;

  log(`[harperGit] phase=${phase} runId=${runId} reqId=${reqId || '∅'} files=${Array.isArray(changedFiles) ? changedFiles.length : '∅'} mode=${gitCtx.mode}`);
  if (!s.gitAutoCommit) { log('[harperGit] autoCommit=false → skip'); return; }

  // 1) Repo pronto
  await ensureGitRepo(gitCtx, defaultBranch, out);

  // 2) Remote (opzionale)
  const hasRemote = await ensureRemote(gitCtx, s.gitRemote, s.gitRemoteUrl || '', out);

  // 3) Branch target
  let targetBranch = defaultBranch;
  if (phase === 'kit' || phase === 'eval' || phase === 'gate') {
    if (!reqId) throw new Error('REQ-ID required for phase=' + phase);
    targetBranch = `${s.gitBranchPrefix}/${String(reqId).toLowerCase()}`;
  }
  log(`[harperGit] targetBranch=${targetBranch}`);

  // 4) Switch to the target branch without rewriting any branch.
  const branchExists = async (b) => {
    try { await gitRunVerbose(['show-ref', '--verify', '--quiet', `refs/heads/${b}`], gitCtx, 'diag', out); return true; }
    catch { return false; }
  };
  const current = await gitRunVerbose(['rev-parse', '--abbrev-ref', 'HEAD'], gitCtx, 'diag', out).catch(() => '');
  if (current !== targetBranch) {
    try {
      if (await branchExists(targetBranch)) {
        await gitRunVerbose(['switch', targetBranch], gitCtx, 'git', out);
      } else {
        const base = (await branchExists(defaultBranch)) ? defaultBranch : 'HEAD';
        await gitRunVerbose(['switch', '-c', targetBranch, base], gitCtx, 'git', out);
      }
    } catch (e) {
      // Uncommitted changes that conflict with the target branch: keep everything as is.
      log(`[harperGit] cannot switch to ${targetBranch}: ${e.message}. Phase files are left uncommitted in the working tree.`);
      return;
    }
  }

  if (hasRemote && s.gitPushRebase && targetBranch !== defaultBranch) {
    try {
      if (!(await isWorkingTreeDirty(gitCtx))) {
        await gitRunVerbose(['fetch', s.gitRemote, defaultBranch], gitCtx, 'git', out);
        await gitRunVerbose(['rebase', `${s.gitRemote}/${defaultBranch}`], gitCtx, 'git', out);
      } else {
        log('[harperGit] working tree dirty → skip rebase');
      }
    } catch (e) {
      try { await gitRunVerbose(['rebase', '--abort'], gitCtx, 'git', out); } catch {}
      log(`[harperGit] rebase warn: ${e.message}`);
    }
  }

  // 5) Only the phase files, relative to the work tree, existing, inside the repo.
  const workTree = path.resolve(gitCtx.workTree || gitCtx.cwd);
  const toArray = (val) => {
    if (!val) return [];
    if (Array.isArray(val)) return val;
    if (typeof val === 'string') return val.split(',').map(x => x.trim()).filter(Boolean);
    return [String(val)];
  };
  const files = [...new Set(toArray(changedFiles)
    .map(f => { try { return toFsPath(f); } catch { return String(f || ''); } })
    .filter(Boolean)
    .map(p => path.resolve(workTree, p))
    .filter(abs => {
      const rel = path.relative(workTree, abs);
      const inside = rel && !rel.startsWith('..') && !path.isAbsolute(rel);
      if (!inside) log(`[harperGit] skip path outside the work tree: ${abs}`);
      return inside && fs.existsSync(abs);
    })
    .map(abs => path.relative(workTree, abs)))];

  if (!files.length) {
    log('[harperGit] no phase files to commit → skip (unrelated changes are never committed)');
    return;
  }

  const dirtyBefore = (await gitRunVerbose(['status', '--porcelain'], gitCtx, 'diag', out).catch(() => ''))
    .split('\n').map(l => l.slice(3).trim()).filter(Boolean);
  const unrelated = dirtyBefore.filter(p => !files.includes(p));
  if (unrelated.length) {
    log(`[harperGit] leaving ${unrelated.length} unrelated change(s) uncommitted: ${unrelated.slice(0, 10).join(', ')}`);
  }

  // 6) Commit only those paths (other staged content is not included)
  const slug = String(reqId || 'req').toLowerCase();
  const base = `[harper:${phase}] runId=${runId}`;
  const messages = {
    spec: `spec: update SPEC.md\n\n${base}`,
    plan: `plan: update PLAN.md\n\n${base}`,
    kit: `feat(${slug}): implement\n\n${base}`,
    eval: `test(${slug}): add eval artifacts\n\n${base}`,
    gate: `chore(${slug}): gate report & promotion\n\n${base}`,
    finalize: `chore: finalize\n\n${base}`,
  };
  const message = conventional === false ? base : (messages[phase] || base);
  try {
    await gitRunVerbose(['add', '--', ...files], gitCtx, 'git', out);
    await gitRunVerbose(['commit', '-m', message, '--', ...files], gitCtx, 'git', out);
  } catch (e) {
    log(`[harperGit] commit skipped: ${e.message}`);
    return;
  }

  // 7) Tag (local, best-effort)
  const tag = `${s.gitTagPrefix}/${phase}/${runId}`;
  try { await gitRunVerbose(['tag', '-a', tag, '-m', tag], gitCtx, 'git', out); }
  catch (e) { log(`[harperGit] tag warn: ${e.message}`); }

  // 8) Push only when explicitly enabled
  if (hasRemote && autoPush) {
    try {
      const upstream = await gitRunVerbose(['rev-parse', '--abbrev-ref', '--symbolic-full-name', '@{u}'], gitCtx, 'diag', out).catch(() => '');
      if (!upstream) await gitRunVerbose(['push', '--set-upstream', s.gitRemote, targetBranch], gitCtx, 'git', out);
      else await gitRunVerbose(['push'], gitCtx, 'git', out);
      await gitRunVerbose(['push', s.gitRemote, tag], gitCtx, 'git', out);
    } catch (e) { log(`[harperGit] push warn: ${e.message}`); }
  } else if (hasRemote) {
    log('[harperGit] committed locally (clike.git.autoPush is off).');
  } else {
    log('[harperGit] no remote configured → committed locally.');
  }

  // 9) Merge into the default branch after a PASS gate (opt-in)
  if (phase === 'gate' && s.gitMergeOnGate === true) {
    let sessionNoiseStashed = false;
    try {
      sessionNoiseStashed = await stashLocalSessionNoise(gitCtx, log);
      await gitRunVerbose(['switch', defaultBranch], gitCtx, 'git', out);
      await gitRunVerbose(['merge', '--no-ff', targetBranch, '-m', `merge: ${reqId} via gate [runId=${runId}]`], gitCtx, 'git', out);
      if (hasRemote && autoPush) {
        try { await gitRunVerbose(['push', s.gitRemote, defaultBranch], gitCtx, 'git', out); }
        catch (e) { log(`[harperGit] push ${defaultBranch} warn: ${e.message}`); }
      }
      if (s.gitDeleteBranchOnMerge === true) {
        try { await gitRunVerbose(['branch', '-d', targetBranch], gitCtx, 'git', out); }
        catch (e) { log(`[harperGit] delete branch warn: ${e.message}`); }
      }
      if (s.gitReturnToFeatureAfterMerge === true) {
        try { await gitRunVerbose(['switch', targetBranch], gitCtx, 'git', out); } catch {}
      }
    } catch (e) {
      try { await gitRunVerbose(['merge', '--abort'], gitCtx, 'git', out); } catch {}
      log(`[harperGit] merge-on-gate warn: ${e.message}`);
    } finally {
      if (sessionNoiseStashed) await popLocalSessionNoise(gitCtx, log);
    }
  }

  // 10) PR flows (explicit opt-in; they need the branch on the remote)
  const runGh = (args) => new Promise((resolve, reject) => {
    cp.execFile('gh', args, { cwd: workTree }, (err, stdout, stderr) => {
      if (err) return reject(new Error((stderr || err.message || '').trim()));
      resolve((stdout || '').trim());
    });
  });
  if (phase === 'kit' && prPerReqDraft && hasRemote) {
    try {
      await gitRunVerbose(['push', '-u', s.gitRemote, targetBranch], gitCtx, 'git', out);
      if (prUseGhCli) await runGh(['pr', 'create', '--title', `[CLike] ${reqId} — draft`, '--draft', '--fill', '--head', targetBranch]);
      else await vscode.commands.executeCommand('github.createPullRequest');
    } catch (e) { log(`[harperGit] draft PR skipped: ${e.message}`); }
  }
  if (phase === 'finalize' && opts?.finalizeOpenPr === true && s.gitOpenPR === true && hasRemote) {
    try {
      const args = ['pr', 'create', '--title', '[CLike] Finalize'];
      if (prBodyPath && fs.existsSync(path.resolve(workTree, prBodyPath))) args.push('--body-file', prBodyPath);
      else args.push('--fill');
      if (prUseGhCli) await runGh(args);
      else await vscode.commands.executeCommand('github.createPullRequest');
    } catch (e) { log(`[harperGit] finalize PR skipped: ${e.message}`); }
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


async function stashLocalSessionNoise(gitCtx, log) {
  try {
    await gitRunVerbose(
      ['stash', 'push', '-m', 'clike-session-noise', '--', '.clike/sessions/harper.jsonl'],
      gitCtx
    );
    log('[harperGit] stashed local session noise');
    return true;
  } catch (e) {
    log(`[harperGit] stash session noise warn: ${e.message}`);
    return false;
  }
}

async function popLocalSessionNoise(gitCtx, log) {
  try {
    await gitRunVerbose(['stash', 'pop'], gitCtx);
    log('[harperGit] restored local session noise');
  } catch (e) {
    log(`[harperGit] stash pop warn: ${e.message}`);
  }
}

module.exports = {
    clikeGitSync,
    toFsPath,
    mapKitSrcToWorkspaceTarget
}