
const vscode = require('vscode');

async function postJSON(url, body) {
  const res = await fetch(url, { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify(body) });
  if (!res.ok) throw new Error(`HTTP ${res.status}: ${await res.text()}`);
  return res.json();
}
function baseUrl() {
  const cfg = vscode.workspace.getConfiguration('clike');
  return cfg.get('orchestratorUrl') || 'http://localhost:8080';
}
module.exports = {
  async evalRun(profile, projectRoot) {
    return postJSON(`${baseUrl()}/v1/eval/run`, { profile, project_root: projectRoot || '.' });
  },
  async gateCheck(profile, projectRoot) {
    return postJSON(`${baseUrl()}/v1/gate/check`, { profile, project_root: projectRoot || '.' });
  },
};
