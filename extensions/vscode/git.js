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

// Return true if the working tree has uncommitted/unstaged changes
/** Git automation problems are shown, not only logged (silent failures left phases uncommitted). */
/**
 * Paths of `git status --porcelain`. The output may arrive trimmed, so the first line can miss
 * its leading status column (" M docs/x" → "M docs/x"): the status is the first token, not the
 * first three characters. Renames give their new path.
 */
function porcelainPaths(raw) {
  return String(raw || '').split('\n').map(l => l.trimEnd()).filter(Boolean)
    .map(l => l.replace(/^\s*\S{1,2}\s+/, ''))
    .map(p => (p.includes(' -> ') ? p.split(' -> ').pop() : p).replace(/^"(.*)"$/, '$1'));
}

function notifyGitProblem(message) {
  try {
    require('vscode').window.showWarningMessage(message);
  } catch {
    // outside VS Code (tests): the log line is enough
  }
}

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
  // Generic objects exposing .path or .toString()
  if (input && typeof input === 'object') {
    if (typeof input.path === 'string') return input.path;
    if (typeof input.toString === 'function') {
      const s2 = input.toString();
      if (s2 && typeof s2 === 'string') return s2;
    }
  }
  let s = String(input).trim();

  // **FIX**: convert "file://..." (even a plain string) to a local path
  if (s.startsWith('file://')) {
    try {
      // also handles spaces/encoding
      const u = new URL(s);
      // on macOS/Unix: u.pathname is already an absolute path
      s = decodeURI(u.pathname);
    } catch {
      // raw fallback (strips the prefix)
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

// Build a git context for a workspace even if it is read-only.
// If the folder is writable: use the local .git (preArgs=[]).
// If it is read-only: use separate-git-dir under ~/.clike/git/<hash>.
function resolveGitContext(workspaceRoot, defaultBranch = 'main') {
  const cwd = toFsPath(workspaceRoot);
  const writable = isDirWritable(cwd);

  if (writable) {
    return {
      mode: 'local',
      cwd,
      preArgs: [], // no --git-dir/--work-tree
      gitDir: path.join(cwd, '.git'),
      workTree: cwd,
      ensureInitNeeded: true
    };
  }

  const root = path.join(os.homedir(), '.clike', 'git');
  const repoId = sha1(cwd).slice(0, 12);
  const gitDir = path.join(root, repoId, '.git'); // keep a familiar structure
  const workTree = cwd;

  return {
    mode: 'separate',
    cwd,                  // run from the work-tree anyway
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
    const out = await gitRun(fullArgs, cwd); // use your existing gitRun (execFile/spawn)
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
  // already a repo?
  try {
    await gitRunVerbose(['rev-parse', '--is-inside-work-tree'], gitCtx, 'diag', out);
    log('[git:init] repository already initialized');
    return;
  } catch {
    log('[git:init] repository not initialized → creating...');
  }

  // Ensure the gitDir directory exists in separate mode
  if (gitCtx.mode === 'separate') {
    const dir = path.dirname(gitCtx.gitDir);
    fs.mkdirSync(dir, { recursive: true });
  }

  // Init
  try {
    // Modern git: init -b <branch>
    await gitRunVerbose(['init', '-b', defaultBranch], gitCtx, 'init', out);
  } catch {
    await gitRunVerbose(['init'], gitCtx, 'init', out);
    try { await gitRunVerbose(['checkout', '-b', defaultBranch], gitCtx, 'init', out); } catch {}
  }

  // In separate mode, we must point to the work-tree
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


// A phase run while another branch is checked out writes files that its target branch tracks:
// /kit REQ-021 after the gate of REQ-020 left the developer on main (runs/kit/REQ-021/ is on
// feature/req-021), a /finalize or /spec run from a REQ branch (its handoff documents are on main
// from an earlier run). Untracked here, they block the switch and the phase stayed uncommitted.
// They are the phase's newer output, so they are carried onto the branch: copied aside (under the
// git dir), switched, written back over the branch's versions (still in its history) and
// committed by the phase. Only when every blocking path is untracked and is a file of this phase
// or inside the REQ's runs/kit/<REQ>/; on any failure the files are put back where they were.
async function switchCarryingPhaseFiles(targetBranch, reqId, changedFiles, switchError, gitCtx, out) {
  const log = mkLog(out);
  const text = String(switchError?.message || switchError || '');
  if (!/untracked working tree files would be overwritten/.test(text) || /local changes to the following files/.test(text)) return false;
  const workTree = path.resolve(gitCtx.workTree || gitCtx.cwd);
  const kitDir = reqId ? `runs/kit/${String(reqId).toUpperCase()}/` : null;
  const phaseFiles = new Set((Array.isArray(changedFiles) ? changedFiles : [])
    .map((f) => { try { return toFsPath(f); } catch { return String(f || ''); } })
    .filter(Boolean)
    .map((p) => path.relative(workTree, path.resolve(workTree, p)).split(path.sep).join('/')));
  const paths = [...new Set(text.split(/\r?\n/).filter((l) => /^\t\S/.test(l)).map((l) => l.trim()))];
  const carryable = (p) => !p.includes('..') && (phaseFiles.has(p) || (kitDir && p.startsWith(kitDir)));
  if (!paths.length || !paths.every(carryable)) return false;
  const gitDir = (await gitRunVerbose(['rev-parse', '--absolute-git-dir'], gitCtx, 'diag', out).catch(() => '')).trim();
  if (!gitDir) return false;
  const carry = path.join(gitDir, 'clike-carry', `${Date.now()}`);
  const copyAll = (fromRoot, toRoot) => {
    for (const rel of paths) {
      const dst = path.join(toRoot, rel);
      fs.mkdirSync(path.dirname(dst), { recursive: true });
      fs.copyFileSync(path.join(fromRoot, rel), dst);
    }
  };
  try {
    copyAll(workTree, carry);
  } catch (e) {
    log(`[harperGit] cannot copy the phase files aside: ${e.message}`);
    return false;
  }
  for (const rel of paths) fs.rmSync(path.join(workTree, rel), { force: true });
  try {
    await gitRunVerbose(['switch', targetBranch], gitCtx, 'git', out);
  } catch (e) {
    copyAll(carry, workTree);
    log(`[harperGit] switch to ${targetBranch} failed again: the phase files are back in place (${e.message})`);
    return false;
  }
  copyAll(carry, workTree);
  fs.rmSync(carry, { recursive: true, force: true });
  log(`[harperGit] carried ${paths.length} file(s) of this phase onto ${targetBranch}`);
  return true;
}

// Harper phase → git (WP5). Non-destructive by design:
//  - never `checkout -B` (it resets an existing branch to HEAD and can drop commits);
//  - the default branch is never moved except by an explicit merge-on-gate;
//  - only the files declared by the phase are staged and committed
//    (`git commit -- <paths>`), unrelated user changes stay untouched;
//  - push happens only with clike.git.autoPush (or an explicitly enabled PR flow).
/** The configured default branch when it exists; else the repository's own (origin/HEAD, then the current branch). */
async function repositoryDefaultBranch(gitCtx, configured, out) {
  const ok = (args) => gitRunVerbose(args, gitCtx, 'diag', out).then(() => true, () => false);
  if (await ok(['show-ref', '--verify', '--quiet', `refs/heads/${configured}`])) return configured;
  if (!(await ok(['rev-parse', '--verify', '--quiet', 'HEAD']))) return configured;   // no commit yet: CLike's bootstrap
  const remoteHead = await gitRunVerbose(['symbolic-ref', '--quiet', '--short', 'refs/remotes/origin/HEAD'], gitCtx, 'diag', out).catch(() => '');
  const fromRemote = String(remoteHead || '').trim().replace(/^origin\//, '');
  if (fromRemote && await ok(['show-ref', '--verify', '--quiet', `refs/heads/${fromRemote}`])) return fromRemote;
  const current = String(await gitRunVerbose(['rev-parse', '--abbrev-ref', 'HEAD'], gitCtx, 'diag', out).catch(() => '')).trim();
  return current && current !== 'HEAD' ? current : configured;
}

async function clikeGitSync(phase, runId, reqId, changedFiles, opts, settings, out) {
  const log = mkLog(out);
  const cwdFsPath = toFsPath(opts?.workspaceRoot);
  if (!cwdFsPath || cwdFsPath === '/' || cwdFsPath.trim().length === 0) {
    throw new Error('[clikeGit] No valid workspaceRoot: open a folder in VS Code before running Harper commands.');
  }

  const s = settings;
  const gitCtx = resolveGitContext(cwdFsPath, s.gitDefaultBranch);
  let defaultBranch = s.gitDefaultBranch || 'main';
  const autoPush = s.gitAutoPush === true;
  const conventional = s.gitConventionalCommits ?? s.gitConventional;
  const prPerReqDraft = s.gitPrPerReqDraftEnabled ?? s.prPerReqDraft;
  const prUseGhCli = s.gitPrPerReqDraftUseGhCli ?? s.prUseGhCli;
  const prBodyPath = s.gitPrBodyPath ?? s.prBodyPath;

  log(`[harperGit] phase=${phase} runId=${runId} reqId=${reqId || '∅'} files=${Array.isArray(changedFiles) ? changedFiles.length : '∅'} mode=${gitCtx.mode}`);
  if (!s.gitAutoCommit) { log('[harperGit] autoCommit=false → skip'); return; }

  // 1) Repo ready
  await ensureGitRepo(gitCtx, defaultBranch, out);
  // a repository that already has history and no branch by the configured name (a project not built
  // with CLike: develop, master, trunk) keeps its own default branch — CLike never creates another one
  defaultBranch = await repositoryDefaultBranch(gitCtx, defaultBranch, out);

  // 2) Remote (optional)
  const hasRemote = await ensureRemote(gitCtx, s.gitRemote, s.gitRemoteUrl || '', out);

  // 3) Target branch
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
        try {
          await gitRunVerbose(['switch', targetBranch], gitCtx, 'git', out);
        } catch (e) {
          if (!(await switchCarryingPhaseFiles(targetBranch, reqId, changedFiles, e, gitCtx, out))) throw e;
        }
      } else {
        // A new REQ branch starts from the default branch only when the current work is already
        // in it. Otherwise (earlier REQs promoted on their branches, merge-on-gate off) it is
        // stacked on the current branch, so it carries the code it depends on; creating a branch
        // at HEAD never conflicts with local changes.
        let base = 'HEAD';
        if (await branchExists(defaultBranch)) {
          const merged = await gitRunVerbose(['merge-base', '--is-ancestor', 'HEAD', defaultBranch], gitCtx, 'diag', out)
            .then(() => true, () => false);
          base = merged ? defaultBranch : 'HEAD';
          if (!merged) log(`[harperGit] ${current} is not merged into ${defaultBranch}: ${targetBranch} is stacked on it`);
        }
        await gitRunVerbose(['switch', '-c', targetBranch, base], gitCtx, 'git', out);
      }
    } catch (e) {
      // Uncommitted changes that conflict with the target branch: keep everything as is.
      const message = `[harperGit] cannot switch to ${targetBranch}: ${e.message}. Phase files are left uncommitted in the working tree.`;
      log(message);
      notifyGitProblem(`CLike Git: ${phase} of ${reqId || 'the project'} not committed — cannot switch to ${targetBranch} (local changes would be overwritten). Commit or stash them, or switch branch, then re-run the phase.`);
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
  let files = [...new Set(toArray(changedFiles)
    .map(f => { try { return toFsPath(f); } catch { return String(f || ''); } })
    .filter(Boolean)
    .map(p => path.resolve(workTree, p))
    .filter(abs => {
      const rel = path.relative(workTree, abs);
      const inside = rel && !rel.startsWith('..') && !path.isAbsolute(rel);
      if (!inside) log(`[harperGit] skip path outside the work tree: ${abs}`);
      return inside && fs.existsSync(abs);
    })
    // git paths use '/', also on Windows: check-ignore and status answer with them.
    .map(abs => path.relative(workTree, abs).split(path.sep).join('/')))];

  // Paths the project ignores (eval reports, KIT report dirs, caches) are never committed: one
  // of them in `git add` fails the whole add, and the phase was left staged but not committed.
  const ignored = new Set((await gitRunVerbose(['check-ignore', '--', ...files], gitCtx, 'diag', out).catch(() => ''))
    .split('\n').map(l => l.trim()).filter(Boolean));
  if (ignored.size) {
    log(`[harperGit] not committing ${ignored.size} ignored path(s): ${[...ignored].slice(0, 10).join(', ')}`);
    files = files.filter(f => !ignored.has(f));
  }

  if (!files.length) {
    log('[harperGit] no phase files to commit → skip (unrelated changes are never committed)');
    return;
  }

  const dirtyBefore = porcelainPaths(await gitRunVerbose(['status', '--porcelain'], gitCtx, 'diag', out).catch(() => ''));
  // Tracked files of the REQ's own KIT (runs/kit/<REQ>/) changed outside the phase's file list —
  // CLike's agent package rewritten at every eval, a ci/HOWTO.md a pre-pass or repair updated:
  // committed with the phase, otherwise a modified one blocks the switch to the default branch and
  // merge-on-gate fails. Untracked files there (agent scratch, reports) are left alone.
  if (reqId && (phase === 'kit' || phase === 'eval' || phase === 'gate')) {
    const kitDir = `runs/kit/${String(reqId).toUpperCase()}/`;
    const tracked = (await gitRunVerbose(['diff', '--name-only', 'HEAD', '--', kitDir], gitCtx, 'diag', out).catch(() => ''))
      .split('\n').map(l => l.trim()).filter(Boolean);
    for (const p of tracked) {
      if (p.startsWith(kitDir) && !files.includes(p)) files.push(p);
    }
  }
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
  // spec/ux (BMAD) writes only companion documents: the message names what changed
  if (phase === 'spec' && !files.includes('docs/harper/SPEC.md')) {
    messages.spec = `docs(spec): update ${files.map((f) => path.basename(f)).slice(0, 4).join(', ')}${files.length > 4 ? ', …' : ''}\n\n${base}`;
  }
  // the caller names the commit (the finalize names its release and REQs: release-publish.js)
  const message = opts?.commitMessage || (conventional === false ? base : (messages[phase] || base));
  try {
    await gitRunVerbose(['add', '--', ...files], gitCtx, 'git', out);
    await gitRunVerbose(['commit', '-m', message, '--', ...files], gitCtx, 'git', out);
  } catch (e) {
    log(`[harperGit] commit skipped: ${e.message}`);
    notifyGitProblem(`CLike Git: ${phase} of ${reqId || 'the project'} not committed — ${String(e.message || e).split('\n')[0]}`);
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

  // 8b) A document phase run from another branch (a REQ branch with its KIT in progress) is
  // committed on the default branch, then the developer is put back on that branch, which gets
  // the documents: switching to the default branch alone hid the KIT from the working tree.
  const documentPhase = !['kit', 'eval', 'gate'].includes(phase);
  if (documentPhase && current && current !== 'HEAD' && current !== targetBranch) {
    try {
      await gitRunVerbose(['switch', current], gitCtx, 'git', out);
      try {
        await gitRunVerbose(['merge', '--no-edit', targetBranch, '-m', `merge: ${phase} documents from ${targetBranch}`], gitCtx, 'git', out);
        log(`[harperGit] back on ${current}, with the ${phase} documents of ${targetBranch}`);
      } catch (e) {
        try { await gitRunVerbose(['merge', '--abort'], gitCtx, 'git', out); } catch {}
        notifyGitProblem(`CLike Git: ${phase} committed on ${targetBranch}; you are back on ${current}, which does not have it yet ` +
          `(merge conflict: ${String(e.message || e).split('\n')[0]}). Run: git merge ${targetBranch}`);
      }
    } catch (e) {
      notifyGitProblem(`CLike Git: ${phase} committed on ${targetBranch}, but switching back to ${current} failed: ` +
        `${String(e.message || e).split('\n')[0]}. Run: git switch ${current}`);
    }
  }

  // 9) Merge into the default branch after a PASS gate (opt-in), only for a promoted REQ: a REQ
  // whose promotion left conflicts is still in progress (src/ incomplete) and stays on its branch.
  if (phase === 'gate' && s.gitMergeOnGate === true && opts?.skipMergeOnGate) {
    log(`[harperGit] ${reqId} not merged into ${defaultBranch}: promotion left conflicts (resolve them and run /gate again).`);
    notifyGitProblem(
      `CLike Git: ${reqId} passed the gate but is NOT merged into ${defaultBranch}: its promotion left conflicts. ` +
      `Resolve them (runs/kit/${reqId}/promotion/<latest>/conflicts.md) and run /gate ${reqId} again.`
    );
  } else if (phase === 'gate' && s.gitMergeOnGate === true) {
    let sessionNoiseStashed = false;
    try {
      sessionNoiseStashed = await stashLocalSessionNoise(gitCtx, log);
      await gitRunVerbose(['switch', defaultBranch], gitCtx, 'git', out);
      // The remote default branch may have moved (a PR merged on the host): bring it in first,
      // otherwise the push below is rejected as non-fast-forward and main stays local only.
      let remoteInSync = true;
      if (hasRemote && autoPush) {
        try {
          await gitRunVerbose(['fetch', s.gitRemote, defaultBranch], gitCtx, 'git', out);
          await gitRunVerbose(
            ['merge', '--no-edit', `${s.gitRemote}/${defaultBranch}`, '-m', `merge: ${s.gitRemote}/${defaultBranch} into ${defaultBranch} before ${reqId}`],
            gitCtx, 'git', out
          );
        } catch (e) {
          remoteInSync = false;
          try { await gitRunVerbose(['merge', '--abort'], gitCtx, 'git', out); } catch {}
          log(`[harperGit] sync ${defaultBranch} with ${s.gitRemote} warn: ${e.message}`);
          notifyGitProblem(
            `CLike Git: ${s.gitRemote}/${defaultBranch} has commits that do not merge cleanly into ${defaultBranch}: ` +
            `${reqId} is merged locally but ${defaultBranch} is not pushed. Merge ${s.gitRemote}/${defaultBranch}, then git push ${s.gitRemote} ${defaultBranch}.`
          );
        }
      }
      await gitRunVerbose(['merge', '--no-ff', targetBranch, '-m', `merge: ${reqId} via gate [runId=${runId}]`], gitCtx, 'git', out);
      if (hasRemote && autoPush && remoteInSync) {
        try { await gitRunVerbose(['push', s.gitRemote, defaultBranch], gitCtx, 'git', out); }
        catch (e) {
          log(`[harperGit] push ${defaultBranch} warn: ${e.message}`);
          notifyGitProblem(
            `CLike Git: ${reqId} is merged into ${defaultBranch} locally, but pushing ${defaultBranch} failed — ` +
            `${String(e.message || e).split('\n')[0]}. Run git push ${s.gitRemote} ${defaultBranch}.`
          );
        }
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
      const cause = String(e?.stderr || e?.message || e).split('\n').filter(Boolean).slice(0, 3).join(' ');
      notifyGitProblem(
        `CLike Git: ${reqId} passed the gate and was promoted, but it is NOT merged into ${defaultBranch}: ${cause}. ` +
        `Commit or restore those files, then: git switch ${defaultBranch} && git merge --no-ff ${targetBranch}`
      );
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
  return { committed: true };
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
    porcelainPaths,
    repositoryDefaultBranch,
    clikeGitSync,
    toFsPath,
    mapKitSrcToWorkspaceTarget
}