const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('fs');
const os = require('os');
const path = require('path');
const { execFileSync } = require('child_process');

const rp = require('../release-publish');
const re = require('../release-extend');

const plan = {
  project: 'Lead Console',
  reqs: [
    { id: 'REQ-001', title: 'Schema', status: 'done' },
    { id: 'REQ-002', title: 'API', status: 'done' },
    { id: 'REQ-003', title: 'AWS network | logs', status: 'done', release: 'v2', change: 'ADDED' },
    { id: 'REQ-004', title: 'Export v2', status: 'done', release: 'v2', change: 'MODIFIED' },
  ],
};
const RELEASE_NOTES = '# Release Notes\n\n## Release scope\n\nThe console on AWS.\n\n## Finalize changes\n\nAdded deploy/aws.\n';
const FINALIZE_REPORT = [
  '# Finalize Report', '', '## Current run — 2026-10-25', '', 'run', '',
  '## 2. Start and see the solution', '', 'scripts/start_solution_local.sh', '',
  '## 4. MISSING INFORMATION', '', 'AWS account id.', '',
  '## 7. Remaining limitations', '', 'No live providers.', '',
  '## Earlier finalize runs — retained evidence (2026-10-17)', '',
  '## 2. Start and see the solution', '', 'OLD v1 start', '',
].join('\n');
const SOLUTION_EVAL = '# Solution eval\n\n- Result: **PASS**\n';

function repo() {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'clike-release-'));
  const git = (...args) => execFileSync('git', args, { cwd: root, encoding: 'utf8', stdio: ['ignore', 'pipe', 'pipe'] }).trim();
  const put = (rel, text) => {
    const file = path.join(root, ...rel.split('/'));
    fs.mkdirSync(path.dirname(file), { recursive: true });
    fs.writeFileSync(file, text);
  };
  const commit = (msg) => { git('add', '-A'); git('-c', 'user.email=t@t', '-c', 'user.name=t', 'commit', '-q', '--allow-empty', '-m', msg); return git('rev-parse', 'HEAD'); };
  git('init', '-q', '-b', 'main');
  git('config', 'user.email', 't@t');
  git('config', 'user.name', 't');
  put('docs/harper/plan.json', JSON.stringify(plan));
  commit('v1');
  git('tag', 'harper/v1');
  const merges = { 'REQ-003': commit('merge: REQ-003 via gate [runId=a]'), 'REQ-004': commit('merge: REQ-004 via gate [runId=b]') };
  put('docs/harper/RELEASE_NOTES.md', RELEASE_NOTES);
  put('docs/harper/FINALIZE_REPORT.md', FINALIZE_REPORT);
  put('docs/harper/SOLUTION_EVAL.md', SOLUTION_EVAL);
  commit('chore(release): finalize v2');
  git('remote', 'add', 'origin', 'https://github.com/acme/lead-console.git');
  return { root, git, put, commit, merges };
}

test('the GitHub owner/repo of a remote URL', () => {
  assert.equal(rp.githubRepo('https://github.com/acme/lead-console.git'), 'acme/lead-console');
  assert.equal(rp.githubRepo('git@github.com:acme/lead-console.git'), 'acme/lead-console');
  assert.equal(rp.githubRepo('https://gitlab.com/acme/x.git'), '');
});

test('sections: the newest of each title, no run markers, no code, numbering dropped', () => {
  const titles = rp.sections(FINALIZE_REPORT).map((s) => s.title);
  assert.deepEqual(titles, ['Start and see the solution', 'MISSING INFORMATION', 'Remaining limitations']);
  assert.ok(!rp.sections(FINALIZE_REPORT).some((s) => /OLD v1/.test(s.body)));
  // test project: a short verification run on top, the release's full sections in the run below it
  const layered = ['# Report', '## Current verification run — 2026-10-25 (b)', '### File changes', 'smoke fixed',
    '## Earlier integration run — 2026-10-25 (a)', '## 2. Start and see the solution', '```sh', '## not a heading', '```',
    '## 6. Problems encountered and verification', 'none', '## Earlier finalize runs — retained evidence', '## 2. Start and see the solution', 'OLD'].join('\n');
  const s = rp.sections(layered);
  assert.deepEqual(s.map((x) => x.title), ['Start and see the solution', 'Problems encountered and verification']);
  assert.match(s[0].body, /## not a heading/);
  // a document without sections is one: its text under the title
  assert.deepEqual(rp.sections('# Release notes — v2\n\nWhat changed.\n', 'Release notes'), [{ title: 'Release notes', body: 'What changed.' }]);
  assert.deepEqual(rp.sections('# Only a title\n', 'Release notes'), []);
});

test('the release, its REQs, gate merges and previous tag come from the plan and git', () => {
  const { root, merges } = repo();
  const info = rp.releaseInfo(root);
  assert.equal(info.release, 'v2');
  assert.equal(info.tag, 'v2');
  assert.equal(info.project, 'Lead Console');
  assert.deepEqual(info.reqs.map((r) => r.id), ['REQ-003', 'REQ-004']);
  assert.equal(info.merges['REQ-003'], merges['REQ-003']);
  assert.equal(info.previousTag, 'harper/v1');
  assert.equal(info.repo, 'acme/lead-console');
  assert.equal(info.status, 'PASS');
  assert.equal(info.prerelease, false);
  assert.equal(rp.releaseInfo(root, { status: 'PASS_WITH_WARNINGS' }).prerelease, true);
  assert.deepEqual(info.assets, rp.ASSETS);
  fs.rmSync(root, { recursive: true, force: true });
});

test('the finalize commit and the tag name the release and its REQs', () => {
  const { root } = repo();
  const info = rp.releaseInfo(root);
  const msg = rp.finalizeCommitMessage(info, 'run1');
  assert.match(msg, /^chore\(release\): finalize v2 — Lead Console\n/);
  assert.match(msg, /Release v2: 2 REQ \(ADDED 1, MODIFIED 1\), since harper\/v1\./);
  assert.match(msg, /- REQ-003 AWS network \| logs \(ADDED\)/);
  assert.match(msg, /\[harper:finalize\] runId=run1$/);
  assert.match(rp.evidenceCommitMessage(info, 'PASS', 'r2'), /^chore\(release\): v2 solution evaluation PASS/);
  const tag = rp.tagMessage(info);
  assert.match(tag, /^Lead Console v2\n/);
  assert.match(tag, /REQ-003, REQ-004/);
  assert.match(tag, /Solution evaluation: PASS/);
  fs.rmSync(root, { recursive: true, force: true });
});

test('the release notes cite REQs, gate merges, documents and the full changelog', () => {
  const { root, merges } = repo();
  const info = rp.releaseInfo(root);
  const md = rp.releaseNotesMarkdown(info);
  assert.match(md, /^## Lead Console v2\n/);
  assert.match(md, /The console on AWS\./);
  assert.match(md, /\| REQ-003 \| AWS network \\\| logs \| ADDED \|/);
  assert.ok(md.includes(`https://github.com/acme/lead-console/commit/${merges['REQ-004']}`));
  assert.match(md, /## Finalize changes\n\nAdded deploy\/aws\./);
  assert.match(md, /## How to start and see it\n\nscripts\/start_solution_local\.sh/);
  assert.match(md, /## Missing information\n\nAWS account id\./);
  assert.match(md, /## Remaining limitations\n\nNo live providers\./);
  assert.ok(!md.includes('OLD v1 start'));
  assert.match(md, /\[FINALIZE_REPORT\.md\]\(https:\/\/github\.com\/acme\/lead-console\/blob\/v2\/docs\/harper\/FINALIZE_REPORT\.md\)/);
  assert.match(md, /\*\*Full changelog\*\*: https:\/\/github\.com\/acme\/lead-console\/compare\/harper\/v1\.\.\.v2/);
  const rel = rp.writeReleaseNotes(root, info);
  assert.equal(rel, 'runs/finalize/RELEASE_v2.md');
  assert.equal(fs.readFileSync(path.join(root, rel), 'utf8'), md);
  fs.rmSync(root, { recursive: true, force: true });
});

test('the tag vN marks HEAD once and is never moved', () => {
  const { root, git, commit } = repo();
  let info = rp.releaseInfo(root);
  const first = rp.tagRelease(root, info);
  assert.deepEqual(first, { tag: 'v2', created: true });
  assert.equal(git('cat-file', '-t', 'v2'), 'tag');                           // annotated
  assert.match(git('tag', '-l', '--format=%(contents)', 'v2'), /Lead Console v2/);
  info = rp.releaseInfo(root);
  assert.deepEqual(rp.tagRelease(root, info), { tag: 'v2', created: false });
  commit('later work');
  info = rp.releaseInfo(root);
  const moved = rp.tagRelease(root, info);
  assert.equal(moved.created, false);
  assert.match(moved.error, /already marks .* not HEAD .*git tag -d v2/);
  // the next release cascade takes v2 as its baseline instead of adding harper/v2
  assert.equal(re.tagBaseline(root, 'v2'), 'v2');
  assert.equal(git('tag', '-l', 'harper/v2'), '');
  fs.rmSync(root, { recursive: true, force: true });
  const plain = fs.mkdtempSync(path.join(os.tmpdir(), 'clike-nogit-'));
  assert.equal(rp.tagRelease(plain, { tag: 'v1', tagExists: false }).tag, '');
  fs.rmSync(plain, { recursive: true, force: true });
});

test('gh creates the release with every field, or edits it and replaces its assets', () => {
  const { root } = repo();
  const info = rp.releaseInfo(root);
  const [create] = rp.ghReleaseArgs(info, 'runs/finalize/RELEASE_v2.md');
  assert.deepEqual(create, ['release', 'create', 'v2', '--title', 'Lead Console v2', '--notes-file', 'runs/finalize/RELEASE_v2.md',
    '--latest', '--verify-tag', ...rp.ASSETS]);
  const edit = rp.ghReleaseArgs({ ...info, prerelease: true }, 'n.md', { exists: true });
  assert.deepEqual(edit[0], ['release', 'edit', 'v2', '--title', 'Lead Console v2', '--notes-file', 'n.md', '--latest', '--prerelease', '--draft=false']);
  assert.deepEqual(edit[1], ['release', 'upload', 'v2', ...rp.ASSETS, '--clobber']);
  fs.rmSync(root, { recursive: true, force: true });
});
