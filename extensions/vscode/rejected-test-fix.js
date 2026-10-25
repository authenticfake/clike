'use strict';
// A repair that changed a locked test without the proof the governance needs (an error raised in
// the test itself) is rejected and the test restored — the lock holds. What the repair proposed is
// not thrown away: CLike saves it as a patch with the reasons and stops the loop, so the developer
// decides (/eval REQ --accept "<why>" applies it, audited; or a hint for the code). Same for every
// executor: a cloud repair's rejected test contents come back from the orchestrator, a local agent's
// are on disk before CLike restores them.
const fs = require('fs');
const path = require('path');
const { execFileSync } = require('child_process');
const { createTwoFilesPatch } = require('diff');

const isTestFile = (rel) => /^test\//.test(String(rel || ''));

/**
 * Save the rejected test changes: entries [{ rel, before, after, issues }] (rel inside the KIT,
 * e.g. test/test_x.py). Returns { patch, files } with the patch path relative to the workspace, or
 * null when no test change was rejected.
 */
function saveRejectedTestFix(workspaceRoot, reqId, cycle, entries, now = Date.now()) {
  const tests = (entries || []).filter((e) => e && isTestFile(e.rel) && typeof e.after === 'string');
  if (!tests.length) return null;
  const kit = `runs/kit/${reqId}`;
  const header = [
    `# Test changes proposed by the repair of ${reqId} (cycle ${cycle}), rejected by the acceptance lock.`,
    '# The locked test was restored. Review: if the test is wrong and this keeps every assertion,',
    `# run /eval ${reqId} --accept "<why>": CLike applies this patch and records your reason (audit).`,
    ...tests.map((e) => `# ${e.rel}: ${(e.issues || []).join('; ') || 'rejected'}`),
    '',
  ].join('\n');
  const body = tests.map((e) => createTwoFilesPatch(
    `a/${kit}/${e.rel}`, `b/${kit}/${e.rel}`, String(e.before || ''), e.after, '', '', { context: 3 },
  ).replace(/^=+\n/, '')).join('\n');
  const rel = `runs/eval/${reqId}/proposed_test_fix_${now}.patch`;
  const abs = path.join(workspaceRoot, ...rel.split('/'));
  fs.mkdirSync(path.dirname(abs), { recursive: true });
  fs.writeFileSync(abs, `${header}${body}`, 'utf8');
  return { patch: rel, files: tests.map((e) => e.rel) };
}

const PROPOSAL_RE = /^proposed_test_fix_(\d+)\.patch$/;

/**
 * /eval REQ --accept: apply the latest saved proposal that still applies to the tests (git apply
 * --check), then mark it `.applied`. Returns { applied } (workspace-relative), { stale } when the
 * latest proposal no longer applies (already applied by hand, or the test changed), or null.
 */
function applyLatestTestFix(workspaceRoot, reqId) {
  const dir = path.join(workspaceRoot, 'runs', 'eval', reqId);
  let names = [];
  try { names = fs.readdirSync(dir).filter((n) => PROPOSAL_RE.test(n)); } catch { return null; }
  if (!names.length) return null;
  const latest = names.sort((a, b) => Number(a.match(PROPOSAL_RE)[1]) - Number(b.match(PROPOSAL_RE)[1])).pop();
  const rel = `runs/eval/${reqId}/${latest}`;
  const git = (args) => execFileSync('git', args, { cwd: workspaceRoot, stdio: ['ignore', 'pipe', 'pipe'] });
  try {
    git(['apply', '--check', rel]);
  } catch {
    return { stale: rel };
  }
  git(['apply', rel]);
  const applied = `${rel.replace(/\.patch$/, '')}.applied.patch`;
  fs.renameSync(path.join(workspaceRoot, ...rel.split('/')), path.join(workspaceRoot, ...applied.split('/')));
  return { applied };
}

/** Undo applyLatestTestFix (the lock refused the change even with the developer's reason). */
function revertAppliedTestFix(workspaceRoot, applied) {
  execFileSync('git', ['apply', '-R', applied], { cwd: workspaceRoot, stdio: ['ignore', 'pipe', 'pipe'] });
  const back = applied.replace(/\.applied\.patch$/, '.patch');
  fs.renameSync(path.join(workspaceRoot, ...applied.split('/')), path.join(workspaceRoot, ...back.split('/')));
  return back;
}

/** The chat line that stops the loop on a rejected test fix. */
function rejectedTestFixMessage(reqId, saved) {
  return `⏸ AUTO-EVAL ${reqId} stopped: the repair says a locked test is wrong (${saved.files.join(', ')}) ` +
    'and changed it, but the eval does not prove it (an error raised in the test itself), so the lock ' +
    `restored it. Its change is saved: ${saved.patch}. Review it: if the test is wrong, ` +
    `/eval ${reqId} --accept "<why>" applies it and records your reason (audited); if the code is ` +
    `wrong, /eval ${reqId} --fix "<hint for the code>".`;
}

module.exports = { saveRejectedTestFix, rejectedTestFixMessage, applyLatestTestFix, revertAppliedTestFix, isTestFile };
