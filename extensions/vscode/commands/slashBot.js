const api = require('../api');

function parseSlash(line) {
  const m = line.trim().match(/^\/([a-zA-Z][\w:-]*)(?:\s+(.+))?$/);
  if (!m) return null;
  const cmd = m[1];
  const args = m[2] ? m[2].split(/\s+/).filter(Boolean) : [];
  return { cmd, args };
}

async function handleEval(args, root) {
  const profile = args[0];
  if (!['spec','plan','kit','finalize'].includes(profile || '')) throw new Error('Usage: /eval <spec|plan|kit|finalize>');
  const rep = await api.evalRun(profile, root);
  const msg = rep.failed === 0 ? 'PASS' : 'FAIL';
  return `Eval ${profile}: ${msg}\nCases: ${rep.cases.length}\nReport: ${rep.json}`;
}
async function handleGate(args, root) {
  const profile = args[0];
  if (!['spec','plan','kit','finalize'].includes(profile || '')) throw new Error('Usage: /gate <spec|plan|kit|finalize>');
  const g = await api.gateCheck(profile, root);
  return `Gate ${profile}: ${g.gate}`;
}
async function handleSync(args) {
  const mdPath = args[0] || 'docs/harper/SPEC.md';
  const res = await api.syncConstraints(mdPath);
  return `Constraints sync: ${res.updated ? 'updated' : 'no changes'} → ${res.path}`;
}
async function handlePlanUpdate(args) {
  if (args.length < 1) throw new Error('Usage: /planUpdate <REQ-ID> [runs/.../eval/kit.report.json]');
  const itemId = args[0];
  const runJson = args[1] || '';
  const res = await api.updatePlan('PLAN.md', runJson, itemId);
  return `PLAN updated (${itemId}): ${res.updated ? 'yes' : 'no'}`;
}


module.exports = { handlePlanUpdate,handleSync,handleGate,handleEval };
