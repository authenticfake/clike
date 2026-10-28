'use strict';
// /init into a folder that already has files (--force): the CLike template only adds what is
// missing. Existing files are never overwritten and .gitignore is merged, so an existing
// project keeps its README, docs, CI and ignore rules.
const fs = require('fs');
const path = require('path');

const BINARY_EXTENSIONS = new Set([
  '.png', '.jpg', '.jpeg', '.gif', '.pdf', '.zip', '.exe', '.dll',
  '.so', '.dylib', '.woff', '.woff2', '.ttf', '.eot',
]);

/**
 * Copy the template tree into dest, file by file, without overwriting. Text files get the
 * template variables replaced. Returns { created, kept } (dest-relative, '/' separated).
 */
function copyTemplateTree(src, dest, { vars = {}, isText = () => true, redirect = () => null } = {}) {
  const created = [];
  const kept = [];
  const proposed = [];
  const walk = (from, to, rel) => {
    if (fs.statSync(from).isDirectory()) {
      for (const entry of fs.readdirSync(from).sort()) walk(path.join(from, entry), path.join(to, entry), rel ? `${rel}/${entry}` : entry);
      return;
    }
    // a file the project should decide on goes to another place (the proposals), not to its own path
    const elsewhere = redirect(rel);
    if (elsewhere) {
      to = path.join(dest, ...elsewhere.split('/'));
      proposed.push(rel);
    }
    fs.mkdirSync(path.dirname(to), { recursive: true });
    if (fs.existsSync(to)) { if (!elsewhere) kept.push(rel); return; }
    if (BINARY_EXTENSIONS.has(path.extname(from).toLowerCase()) || !isText(from)) {
      fs.copyFileSync(from, to);
    } else {
      let content = fs.readFileSync(from, 'utf-8');
      for (const [token, value] of Object.entries(vars)) content = content.split(token).join(String(value));
      fs.writeFileSync(to, content);
    }
    if (!elsewhere) created.push(rel);
  };
  walk(src, dest, '');
  return { created, kept, proposed };
}

// The team process files of the template: who reviews (CODEOWNERS), how a PR is described, which CI
// runs. A repository that already has a process of its own gets them as proposals only, under
// .clike/proposals/ (B2B/foundation: 6 workflows of its own; a new CODEOWNERS changes who must
// approve, a new workflow runs jobs in the team's CI). A new folder gets them as before.
const TEAM_PROCESS_FILES = ['.github/CODEOWNERS', '.github/pull_request_template.md', '.github/workflows/clike-ci.yaml'];
const PROPOSALS_DIR = '.clike/proposals';

/** The folder already has a review / PR / CI process of its own. */
function hasTeamProcess(dir) {
  const exists = (...parts) => fs.existsSync(path.join(dir, ...parts));
  let workflows = [];
  try { workflows = fs.readdirSync(path.join(dir, '.github', 'workflows')).filter((n) => /\.ya?ml$/i.test(n)); } catch { /* none */ }
  return workflows.length > 0 ||
    ['.github', '', 'docs'].some((d) => exists(...(d ? [d] : []), 'CODEOWNERS')) ||
    ['.github', '', 'docs'].some((d) => exists(...(d ? [d] : []), 'pull_request_template.md') || exists(...(d ? [d] : []), 'PULL_REQUEST_TEMPLATE.md')) ||
    exists('.github', 'PULL_REQUEST_TEMPLATE');
}

/** redirect() for copyTemplateTree: the team process files to the proposals when the folder has its own. */
function teamProcessRedirect(dir) {
  if (!hasTeamProcess(dir)) return () => null;
  return (rel) => (TEAM_PROCESS_FILES.includes(rel) ? `${PROPOSALS_DIR}/${rel}` : null);
}

/**
 * .gitignore with CLike's rules: a new file gets them as is; an existing one keeps every line
 * and gets only the rules it lacks, under a "# CLike" header. Returns { text, added }.
 */
function mergeGitignore(existingText, clikeLines) {
  const rules = clikeLines.filter((l) => l.trim() !== '');
  if (existingText == null) return { text: `${rules.join('\n')}\n`, added: rules };
  const present = new Set(existingText.split(/\r?\n/).map((l) => l.trim()).filter(Boolean));
  const added = rules.filter((r) => !present.has(r.trim()));
  if (!added.length) return { text: existingText, added };
  const base = existingText.endsWith('\n') || existingText === '' ? existingText : `${existingText}\n`;
  return { text: `${base}${base ? '\n' : ''}# CLike\n${added.join('\n')}\n`, added };
}

module.exports = { copyTemplateTree, mergeGitignore, hasTeamProcess, teamProcessRedirect, TEAM_PROCESS_FILES, PROPOSALS_DIR };
