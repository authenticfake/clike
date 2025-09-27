const vscode = require('vscode');
const api = require('../api');

// all'inizio file


function registerCommands(ctx) {

        ctx.subscriptions.push(
            vscode.commands.registerCommand('clike.eval.runAll', async () => {
                const root = vscode.workspace.workspaceFolders?.[0]?.uri?.fsPath || '.';
                const profiles = ['spec','plan','kit','finalize'];
                for (const p of profiles) {
                    const rep = await api.evalRun(p, root);
                    const msg = rep.failed === 0 ? 'PASS' : 'FAIL';
                    vscode.window.showInformationMessage(`[CLike] Eval ${p}: ${msg}`);
                }
            }),

            vscode.commands.registerCommand('clike.gate.checkPhase', async () => {
                const profile = await vscode.window.showQuickPick(['spec','plan','kit','finalize'], { placeHolder: 'Select phase to gate-check' });
                if (!profile) return;
                const root = vscode.workspace.workspaceFolders?.[0]?.uri?.fsPath || '.';
                const g = await api.gateCheck(profile, root);
                vscode.window.showInformationMessage(`[CLike] Gate ${profile}: ${g.gate}`);
            }),

            vscode.commands.registerCommand('clike.constraints.sync', async () => {
                const file = await vscode.window.showInputBox({ prompt: 'Path to IDEA.md or SPEC.md', value: 'docs/harper/SPEC.md' });
                if (!file) return;
                const res = await api.syncConstraints(file);
                vscode.window.showInformationMessage(`[CLike] Constraints sync: ${res.updated ? 'updated' : 'no changes'} (${res.path})`);
            }),

            vscode.commands.registerCommand('clike.plan.updateChecklist', async () => {
                const runJson = await vscode.window.showInputBox({ prompt: 'Path to eval report JSON', value: 'runs/.../eval/kit.report.json' });
                const itemId = await vscode.window.showInputBox({ prompt: 'PLAN item or REQ id', value: '' });
                const res = await api.updatePlan('PLAN.md', runJson || '', itemId || '');
                vscode.window.showInformationMessage(`[CLike] PLAN updated: ${res.updated ? 'yes' : 'no'}`);
            })
  );
}
module.exports = { registerCommands };
