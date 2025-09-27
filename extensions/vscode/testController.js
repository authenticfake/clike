const vscode = require('vscode');
const api = require('./api');

function activateTestController(ctx) {
  const ctrl = vscode.tests.createTestController('clike-tests', 'CLike Evals');
  ctx.subscriptions.push(ctrl);

  const profiles = ['spec', 'plan', 'kit', 'finalize'];
  profiles.forEach(p => {
    const suite = ctrl.createTestItem(`suite:${p}`, `Eval: ${p}`);
    ctrl.items.add(suite);
  });

  ctrl.createRunProfile('Run Evals', vscode.TestRunProfileKind.Run, async (request) => {
    const run = ctrl.createTestRun(request);
    try {
      const root = vscode.workspace.workspaceFolders?.[0]?.uri?.fsPath || '.';
      for (const p of profiles) {
        const suite = ctrl.items.get(`suite:${p}`);
        run.enqueued(suite);
        const rep = await api.evalRun(p, root);
        rep.cases.forEach((c, idx) => {
          const tc = ctrl.createTestItem(`${p}:${idx}`, c.name);
          suite.children.add(tc);
          run.started(tc);
          c.passed ? run.passed(tc) : run.failed(tc, new vscode.TestMessage('FAIL'));
        });
      }
    } catch (e) {
      vscode.window.showErrorMessage(`[CLike] Eval failed: ${e.message}`);
    } finally {
      run.end();
    }
  }, true);

  return ctrl;
}

module.exports = { activateTestController };
