'use strict';
// A repair that changed a locked test without the proof the governance needs (an error raised in
// the test itself) is rejected and the test restored — the lock holds. What the repair proposed is
// not thrown away: CLike saves it as a patch with the reasons and stops the loop, so the developer
// decides (apply it and /eval REQ --accept "<why>", audited; or a hint for the code). Same for every
// executor: a cloud repair's rejected test contents come back from the orchestrator, a local agent's
// are on disk before CLike restores them.
const fs = require('fs');
const path = require('path');
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
    `# apply it (git apply <this file>) and run /eval ${reqId} --accept "<why>" (audited).`,
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

/** The chat line that stops the loop on a rejected test fix. */
function rejectedTestFixMessage(reqId, saved) {
  return `⏸ AUTO-EVAL ${reqId} stopped: the repair says a locked test is wrong (${saved.files.join(', ')}) ` +
    'and changed it, but the eval does not prove it (an error raised in the test itself), so the lock ' +
    `restored it. Its change is saved: ${saved.patch}. Review it: if the test is wrong, apply it ` +
    `(git apply ${saved.patch}) and run /eval ${reqId} --accept "<why>" (audited); if the code is ` +
    `wrong, /eval ${reqId} --fix "<hint for the code>".`;
}

module.exports = { saveRejectedTestFix, rejectedTestFixMessage, isTestFile };
