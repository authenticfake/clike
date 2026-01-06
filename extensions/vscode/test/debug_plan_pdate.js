// tools/debug-plan/debug_plan_update.js
// Harness Node per testare la logica di PLAN.md usando le stesse funzioni di utility.js

const fs = require('fs');
const path = require('path');

// ---------- FUNZIONI COPIATE DALL'IMPLEMENTAZIONE ATTUALE ----------

// snapshotCounts: come in utility.js
function snapshotCounts(plan) {
  const total = (plan?.reqs || []).length;
  const done = (plan?.reqs || []).filter(
    r => (r.status || '').toLowerCase() === 'done'
  ).length;
  const open = (plan?.reqs || []).filter(
    r => (r.status || '').toLowerCase() === 'open'
  ).length;
  const inprog = (plan?.reqs || []).filter(
    r => (r.status || '').toLowerCase() === 'in_progress'
  ).length;
  const deferred = (plan?.reqs || []).filter(
    r => (r.status || '').toLowerCase() === 'deferred'
  ).length;
  const progress = total > 0 ? Math.round((done / total) * 100) : 0;
  return { total, done, open, in_progress: inprog, deferred, progress };
}

// renderSnapshotMd: come in utility.js
function renderSnapshotMd(ss) {
  // Ritorna sezione COMPLETA inclusa l’intestazione
  return [
    '## Plan Snapshot',
    '',
    `- **Counts:** total=${ss.total} / open=${ss.open} / in_progress=${ss.in_progress} / done=${ss.done} / deferred=${ss.deferred}`,
    `- **Progress:** ${ss.progress}% complete`,
    '- **Checklist:**',
    '  - [x] SPEC aligned',
    '  - [x] Prior REQ reconciled',
    '  - [x] Dependencies mapped',
    '  - [x] KIT-readiness per REQ confirmed',
    ''
  ].join('\n');
}

// renderReqTableMd: versione attuale attiva in utility.js
function renderReqTableMd(plan) {
  const rows = (plan?.reqs || []).map(r => {
    const id = r.id || '';
    const title = r.title || '';
    const acc = Array.isArray(r.acceptance)
      ? r.acceptance.map(a => a.trim()).join('<br/>')
      : (r.acceptance || '');
    const deps = Array.isArray(r.dependsOn)
      ? r.dependsOn.join(', ')
      : (r.dependsOn || '');
    const track = (r.track || '').toString();
    const status = (r.status || '').toString();
    return `| ${id} | ${title} | ${acc} | ${deps} | ${track} | ${status} |`;
  });

  return [
    '## REQ-IDs Table',
    '',
    '| ID | Title | Acceptance | DependsOn | Track | Status |',
    '|---|---|---|---|---|---|',
    ...rows,
    ''
  ].join('\n');
}

// sectionRegex: come in utility.js
function sectionRegex(titleVariants) {
  const escaped = titleVariants.map(t =>
    t.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
  );
  const union = escaped.join('|');
  return new RegExp(
    `^(##\\s*(?:${union})\\b[^\\n]*\\n)([\\s\\S]*?)(?=^##\\s|\\Z)`,
    'mi'
  );
}

// Versione "solo stringa" di updatePlanMdInPlace:
// prende il contenuto di PLAN.md come stringa + l'oggetto plan, e ritorna la nuova stringa
function updatePlanMdString(md, plan) {
  const ss = snapshotCounts(plan);
  console.log("test ss", ss);
  const newSnapshot = renderSnapshotMd(ss);
 // console.log("test newSnapshot", newSnapshot);
  const newTable = renderReqTableMd(plan);
 //   console.log("test newTable", newTable);


  const rxSnapshot = sectionRegex(['Plan Snapshot']);

  const rxTable = sectionRegex(['REQ-IDs Table', 'REQ IDs Table', 'REQ-IDs table']);
 //   console.log("test rxSnapshot", rxSnapshot);
 //    console.log("test rxSnapshot", rxSnapshot);
  // --- Snapshot (logica identica alla tua updatePlanMdInPlace) ---
  if (rxSnapshot.test(md)) {
    md = md.replace(rxSnapshot, (_, heading /*, body*/) => {
      const contentLines = newSnapshot.split('\n');
      contentLines.shift(); // rimuovi "## Plan Snapshot"
      const content = contentLines.join('\n');
      return `${heading}${content}\n`;
    });
  } else {
    md = `${newSnapshot}\n${md}`;
  }
 // console.log("test rxTable", md);
  console.log("rxTable", rxTable)
 console.log("screenshot md [", md, "]")

  // --- Tabella (logica identica alla tua updatePlanMdInPlace) ---
  const tableHeading = '## REQ-IDs Table';
  const headingIdx = md.indexOf(tableHeading);

  if (headingIdx !== -1) {
    // md = [prima della tabella] + [tabella e resto]
    const before = md.slice(0, headingIdx);
    const after = md.slice(headingIdx);

    // Nel blocco "after", troviamo dove finisce la tabella
    // e dove iniziano le Acceptance già presenti.
    const idxAcceptance = after.indexOf('\n### Acceptance');
    const idxNextSection = after.indexOf('\n## ', tableHeading.length);

    // Se c'è una sezione "### Acceptance — REQ-001", usiamo quella come fine della tabella.
    // Altrimenti, come fallback, usiamo il prossimo "## " oppure la fine del file.
    let cut;
    if (idxAcceptance !== -1) {
      cut = idxAcceptance;
    } else if (idxNextSection !== -1) {
      cut = idxNextSection;
    } else {
      cut = after.length;
    }

    // Inseriamo la tabella nuova (newTable include già "## REQ-IDs Table")
    // e manteniamo tutto ciò che viene dopo (Acceptance, Dependency Graph, ecc.).
    const afterTail = after.slice(cut);
    md = `${before}${newTable}${afterTail}`;
  } else {
    // Se non esiste ancora la sezione, la appendiamo in fondo
    md = `${md}\n\n${newTable}`;
  }
  console.log("req md [", md, "]")



  return md;
}

// ---------- HARNESS PER TEST LOCALE ----------

function main() {
  const base = __dirname;

  const planPath = path.join(base, 'plan_debug.json');
  const mdInPath = path.join(base, 'PLAN_debug.md');
  const mdOutPath = path.join(base, 'PLAN_debug_out.md');

  const plan = JSON.parse(fs.readFileSync(planPath, 'utf8'));
  const mdIn = fs.readFileSync(mdInPath, 'utf8');

  const mdOut = updatePlanMdString(mdIn, plan);

  fs.writeFileSync(mdOutPath, mdOut, 'utf8');

  console.log('PLAN_debug_out.md written.');
  console.log('→ Ora confronta PLAN_debug.md vs PLAN_debug_out.md in VS Code (diff).');
}

if (require.main === module) {
  main();
}
