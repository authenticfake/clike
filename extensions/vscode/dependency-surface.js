'use strict';
// The code a REQ builds on, for cloud models (a local agent reads the workspace instead).
// Deterministic, no RAG: for each dependency REQ (plan.json dependsOn, transitive, nearest first)
// the files its promotion delivered (latest runs/kit/<REQ>/promotion/*/report.json), read from the
// canonical tree as they are now, interfaces first, within a budget; plus each dependency's
// ci/HOWTO.md. /finalize gets the same for every delivered REQ, manifests and entry points first.
const fs = require('fs');
const path = require('path');

const DELIVERED = new Set(['added', 'updated', 'merged', 'kept_canonical', 'unchanged']);
const SKIP_RE = /(^|\/)(test|tests|__tests__|node_modules|\.next|dist|build|coverage)\/|\.(lock|png|jpe?g|gif|webp|ico|pdf|zip|gz|woff2?|ttf|map|min\.js)$|(^|\/)(package-lock\.json|yarn\.lock|pnpm-lock\.yaml|uv\.lock|poetry\.lock)$/i;
const INTERFACE_RE = /(contract|port|schema|model|types?|dto|api|route|router|interface|protocol|config|settings|errors?|factory|__init__|index|main|app)\b/i;
const ENTRY_RE = /(^|\/)(pyproject\.toml|package\.json|requirements[^/]*\.txt|compose[^/]*\.ya?ml|docker-compose[^/]*\.ya?ml|Dockerfile[^/]*|alembic\.ini|Makefile|\.env\.example|main\.(py|ts|js)|app\.(py|ts|js)|server\.(py|ts|js)|settings\.py|config\.(py|ts|js))$/i;

const readText = (file) => { try { return fs.readFileSync(file, 'utf8'); } catch { return null; } };

function planReqs(root) {
  try {
    const plan = JSON.parse(readText(path.join(root, 'docs', 'harper', 'plan.json')) || '');
    return (plan.reqs || plan.req || []).filter((r) => r && r.id);
  } catch { return []; }
}

/** dependsOn closure of `reqId`, nearest first (breadth-first). */
function dependencyClosure(reqs, reqId) {
  const byId = new Map(reqs.map((r) => [String(r.id).toUpperCase(), r]));
  const seen = new Set();
  const order = [];
  let frontier = [...((byId.get(String(reqId).toUpperCase()) || {}).dependsOn || [])];
  while (frontier.length) {
    const next = [];
    for (const d of frontier.map((x) => String(x).toUpperCase())) {
      if (seen.has(d) || !byId.has(d)) continue;
      seen.add(d);
      order.push(byId.get(d));
      next.push(...(byId.get(d).dependsOn || []));
    }
    frontier = next;
  }
  return order;
}

/** Repository paths a REQ delivered: its latest promotion report, else its KIT src/ and root/. */
function deliveredFiles(root, reqId) {
  const promoDir = path.join(root, 'runs', 'kit', reqId, 'promotion');
  let stamps = [];
  try { stamps = fs.readdirSync(promoDir).sort().reverse(); } catch { /* none */ }
  for (const ts of stamps) {
    try {
      const report = JSON.parse(readText(path.join(promoDir, ts, 'report.json')) || '');
      const paths = (report.results || []).filter((r) => r && r.path && DELIVERED.has(r.outcome)).map((r) => String(r.path));
      if (paths.length) return { paths, from: 'promotion' };
    } catch { /* next */ }
  }
  const out = [];
  const walk = (dir, rel) => {
    let entries = [];
    try { entries = fs.readdirSync(dir, { withFileTypes: true }); } catch { return; }
    for (const e of entries) {
      const r = rel ? `${rel}/${e.name}` : e.name;
      if (e.isDirectory()) walk(path.join(dir, e.name), r);
      else if (e.isFile()) out.push(r);
    }
  };
  const kit = path.join(root, 'runs', 'kit', reqId);
  walk(path.join(kit, 'src'), 'src');
  walk(path.join(kit, 'root'), '');
  return { paths: out, from: 'kit' };
}

function fileText(root, reqId, rel, from) {
  const canonical = readText(path.join(root, ...rel.split('/')));
  if (canonical != null || from === 'promotion') return canonical;
  const kitRel = rel.startsWith('src/') ? rel : `root/${rel}`;
  return readText(path.join(root, 'runs', 'kit', reqId, ...kitRel.split('/')));
}

function render(root, reqs, { priority, maxTotal, maxEach, heading }) {
  const lines = [heading, ''];
  let used = 0;
  const omitted = [];
  for (const req of reqs) {
    const id = String(req.id).toUpperCase();
    const { paths, from } = deliveredFiles(root, id);
    const files = paths.filter((p) => !SKIP_RE.test(p)).sort((a, b) => priority(b) - priority(a) || a.localeCompare(b));
    lines.push(`### ${id} — ${req.title || ''} [${req.status || 'open'}] (${from === 'promotion' ? 'promoted files, canonical content' : 'KIT files, not promoted yet'})`, '');
    const howto = readText(path.join(root, 'runs', 'kit', id, 'ci', 'HOWTO.md'));
    if (howto && used + 2000 < maxTotal) {
      const shown = howto.slice(0, 4000);
      used += shown.length;
      lines.push(`#### runs/kit/${id}/ci/HOWTO.md`, '```markdown', shown.trimEnd(), '```', '');
    }
    for (const rel of files) {
      const text = fileText(root, id, rel, from);
      if (text == null || text.includes('\u0000')) continue;
      const room = Math.min(maxEach, maxTotal - used);
      if (room < 800) { omitted.push(rel); continue; }
      const shown = text.length > room ? `${text.slice(0, room)}\n…[truncated by CLike]` : text;
      used += shown.length;
      lines.push(`#### ${rel}`, '```', shown.trimEnd(), '```', '');
    }
  }
  if (omitted.length) lines.push(`Not shown (budget): ${omitted.slice(0, 60).join(', ')}${omitted.length > 60 ? ', …' : ''}`, '');
  return used ? lines.join('\n') : '';
}

/** Markdown of the code `reqId` builds on, or '' when it has no dependency with files. */
function buildDependencySurface(root, reqId, { maxTotal = 150_000, maxEach = 12_000 } = {}) {
  const deps = dependencyClosure(planReqs(root), reqId);
  if (!deps.length) return '';
  return render(root, deps, {
    priority: (p) => (INTERFACE_RE.test(path.basename(p)) ? 2 : 0) + (ENTRY_RE.test(p) ? 1 : 0),
    maxTotal, maxEach,
    heading: `Dependencies of ${reqId} (nearest first). Reuse these modules and contracts; never re-implement them.`,
  });
}

/** Markdown of the delivered solution for /finalize: manifests and entry points first. */
function buildSolutionSurface(root, { maxTotal = 150_000, maxEach = 10_000 } = {}) {
  const done = planReqs(root).filter((r) => String(r.status || '').toLowerCase() === 'done');
  if (!done.length) return '';
  return render(root, done, {
    priority: (p) => (ENTRY_RE.test(p) ? 3 : 0) + (INTERFACE_RE.test(path.basename(p)) ? 1 : 0),
    maxTotal, maxEach,
    heading: 'Delivered solution (every promoted REQ): manifests, entry points and interfaces first.',
  });
}

module.exports = { buildDependencySurface, buildSolutionSurface, dependencyClosure, deliveredFiles };
