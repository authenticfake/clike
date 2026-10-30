'use strict';
// A project opened outside the folders the CLike stack can read (CLIKE_PROJECTS_DIR, and the
// projects mounted by docker/mount-project.sh): eval, gate and the /adopt baseline answer 403.
// On the developer's confirmation, that folder alone is mounted read-only and the containers are
// recreated; never asked twice for the same folder in a session, never in an unattended run.
const fs = require('fs');
const path = require('path');

const SCRIPT = 'mount-project.sh';

function isWithin(p, roots) {
  const norm = (x) => path.resolve(String(x || '')).replace(/[\\/]+$/, '');
  const target = norm(p);
  return (roots || []).filter(Boolean).some((r) => {
    const root = norm(r);
    return target === root || target.startsWith(`${root}${path.sep}`);
  });
}

const hasScript = (dir) => Boolean(dir) && fs.existsSync(path.join(dir, SCRIPT));

/**
 * Inputs are injected (testable without VS Code):
 *   getRoots()            → { roots: [...], stack_dir }
 *   ask(root)             → true to mount
 *   stackDir              → the clike.stackDir setting ('' when unset)
 *   pickStackDir()        → the docker folder of the CLike stack the developer picks (or '')
 *   run(script, args, cwd) → { ok, output }
 * → { mounted: bool, reason }
 */
async function ensureProjectMounted({ root, getRoots, ask, stackDir = '', pickStackDir, run, say = () => {}, unattended = false, declined = new Set() }) {
  let info;
  try { info = await getRoots(); } catch (e) { return { mounted: false, reason: `the stack did not answer (${e?.message || e})` }; }
  const roots = Array.isArray(info?.roots) ? info.roots : [];
  if (!roots.length || isWithin(root, roots)) return { mounted: false, reason: 'readable' };
  if (unattended) return { mounted: false, reason: 'outside the stack folders (unattended run: not asked)' };
  if (declined.has(root)) return { mounted: false, reason: 'declined' };
  if (!(await ask(root))) { declined.add(root); return { mounted: false, reason: 'declined' }; }
  let dir = [stackDir, info?.stack_dir].find(hasScript) || '';
  if (!dir) dir = await pickStackDir();
  if (!hasScript(dir)) return { mounted: false, reason: `no ${SCRIPT} in the folder of the stack` };
  say(`▶ mounting ${root} read-only in the CLike stack (the containers are recreated, about a minute)…`);
  const out = await run(path.join(dir, SCRIPT), ['add', root], dir);
  if (!out.ok) return { mounted: false, reason: `${SCRIPT} failed: ${String(out.output || '').trim().split('\n').slice(-3).join(' ')}`, stackDir: dir };
  let after;
  try { after = await getRoots(); } catch { after = null; }
  const ok = isWithin(root, after?.roots || []);
  return { mounted: ok, reason: ok ? 'mounted' : 'the stack still does not list it', stackDir: dir };
}

module.exports = { ensureProjectMounted, isWithin, SCRIPT };
