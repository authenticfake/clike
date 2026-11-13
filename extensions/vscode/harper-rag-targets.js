'use strict';
// The project artifacts each Harper phase writes or reads, indexed in the project RAG when the phase
// ends (cloud and local agents alike), so /rag, the Memory panel and later phases find them. The RAG
// store re-embeds only changed files and replaces every chunk of a changed file.

const INPUTS = ['docs/inputs', 'docs/reference'];
const LANE_GUIDES = ['docs/harper/lane-guides'];

const TARGETS = {
  idea: {
    files: ['docs/harper/IDEA.md', 'docs/harper/TECH_CONSTRAINTS.yaml'],
    dirs: [...INPUTS, 'docs/harper/bmad/idea'],
  },
  spec: {
    files: ['docs/harper/SPEC.md', 'docs/harper/TECH_CONSTRAINTS.yaml'],
    dirs: [...INPUTS, 'docs/harper/ux', 'docs/harper/bmad/spec'],
  },
  plan: {
    // plan.json is not indexed: PLAN.md carries the same REQs as prose
    files: ['docs/harper/PLAN.md'],
    dirs: [...LANE_GUIDES, 'docs/harper/bmad/architecture', 'docs/harper/bmad/plan'],
  },
  finalize: {
    files: [
      'README.md',
      'docs/harper/HOWTO_RUN.md',
      'docs/harper/SANITY_CHECKS.md',
      'docs/harper/RELEASE_NOTES.md',
      'docs/harper/TODO_NEXT.md',
      'docs/harper/FINALIZE_REPORT.md',
      'docs/harper/INFRA_READINESS.md',
    ],
    dirs: ['docs/harper/bmad/finalize'],
  },
};
// /extend and /idea --extend rewrite idea, spec and plan together
TARGETS.extend = {
  files: [...new Set([...TARGETS.idea.files, ...TARGETS.spec.files, ...TARGETS.plan.files])],
  dirs: [...new Set([...TARGETS.idea.dirs, ...TARGETS.spec.dirs, ...TARGETS.plan.dirs])],
};

// Text the store reads as it is, and documents it converts (docx, pdf, xlsx, pptx).
const INDEXABLE_EXTENSIONS = new Set(['md', 'markdown', 'txt', 'yaml', 'yml', 'json', 'csv', 'docx', 'pdf', 'xlsx', 'xls', 'xlsb', 'pptx']);

function harperRagTargets(phase) {
  const t = TARGETS[String(phase || '').toLowerCase()];
  return t ? { files: [...t.files], dirs: [...t.dirs] } : { files: [], dirs: [] };
}

function isRagIndexable(name) {
  const base = String(name || '');
  if (!base || base.startsWith('.')) return false;
  const ext = (base.split('.').pop() || '').toLowerCase();
  return base.includes('.') && INDEXABLE_EXTENSIONS.has(ext);
}

module.exports = { harperRagTargets, isRagIndexable };
