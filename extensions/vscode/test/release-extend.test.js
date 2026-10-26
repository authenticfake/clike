'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('fs');
const os = require('os');
const path = require('path');

const re = require('../release-extend');
const { validateExtendPlan } = require('../extend-guard');
const { parseSlash } = require('../slash-parser');

const IDEA_V1 = '# IDEA\n\n## Vision\nLeads for one operator.\n\n## Out of scope\nOutreach.\n';
const SPEC_V1 = '# SPEC\n\n## Goals\nJourney.\n\n## Acceptance Criteria\n- AC01\n';
const TECH_V1 = 'tech_constraints:\n  backend: python\n';
const PLAN_V1 = {
  snapshot: { total: 2 },
  reqs: [
    { id: 'REQ-001', title: 'Config', status: 'done', acceptance: ['a'], dependsOn: [] },
    { id: 'REQ-002', title: 'Discovery', status: 'done', acceptance: ['b'], dependsOn: ['REQ-001'] },
  ],
};

function project() {
  const root = fs.realpathSync(fs.mkdtempSync(path.join(os.tmpdir(), 'clike-release-')));
  const put = (rel, text) => {
    fs.mkdirSync(path.dirname(path.join(root, rel)), { recursive: true });
    fs.writeFileSync(path.join(root, rel), text);
  };
  put('docs/harper/IDEA.md', IDEA_V1);
  put('docs/harper/SPEC.md', SPEC_V1);
  put('docs/harper/TECH_CONSTRAINTS.yaml', TECH_V1);
  put('docs/harper/PLAN.md', '# PLAN\n\n## REQ-001\n\n## REQ-002\n');
  put('docs/harper/plan.json', JSON.stringify(PLAN_V1, null, 2));
  put('docs/inputs/brief_v1.docx', 'x');
  put('docs/inputs/v2/IDEA_EXTEND_R2.md', '# Release 2\n');
  put('docs/reference/v2/blueprint.md', '# Blueprint\n');
  put('runs/kit/REQ-002/ci/LTC.json', JSON.stringify({ checks: [{ id: 'tests' }, { id: 'e2e' }] }));
  return { root, put };
}

const planV2 = (extra = {}) => JSON.stringify({
  ...PLAN_V1,
  snapshot: { total: 4 },
  reqs: [
    ...PLAN_V1.reqs,
    { id: 'REQ-003', title: 'OIDC sign-in', status: 'open', change: 'ADDED', acceptance: ['login'], dependsOn: ['REQ-001'] },
    { id: 'REQ-004', title: 'Identity gateway', status: 'open', change: 'MODIFIED', amends: ['REQ-002'],
      supersedes: [{ check: 'REQ-002#e2e', reason: 'identity instead of name' }], acceptance: ['identity'], dependsOn: ['REQ-002'], ...extra },
  ],
}, null, 2);

test('/idea --extend is parsed as the release cascade; plain /idea is unchanged', () => {
  const s = parseSlash('/idea --extend --from attachment --release v3 --dry-run add sign-in');
  assert.equal(s.cmd, '/idea');
  assert.equal(s.args.extend, true);
  assert.equal(s.args.fromAttachment, true);
  assert.equal(s.args.dryRun, true);
  assert.equal(s.args.release, 'v3');
  assert.equal(s.args.rawInput, 'add sign-in');
  assert.deepEqual(parseSlash('/idea MyProject').args, { name: 'MyProject' });
  // a command pasted with a terminal border or a quote marker in front is still a command
  for (const pasted of ['│ /idea --extend', '┃/idea --extend', '> /idea --extend', '\u00a0/idea --extend']) {
    assert.equal(parseSlash(pasted)?.args?.extend, true, pasted);
  }
  assert.equal(parseSlash('hello /idea --extend'), null);
  // BMAD on the cascade: the agents of the extend phase (analyst, pm, architect, ux)
  const bmad = parseSlash('/idea --extend --methodology bmad --agent analyst');
  assert.equal(bmad.error, undefined);
  assert.equal(bmad.args.extend, true);
  assert.equal(bmad.args.methodology, 'bmad');
  assert.equal(bmad.args.agent, 'analyst');
  assert.match(parseSlash('/idea --extend --methodology bmad --agent developer').error, /not allowed for phase 'extend'/);
  assert.equal(parseSlash('/extend --methodology bmad --agent architect').error, undefined);
});

test('the target release comes from the release folders, the plan or the command', () => {
  const { root, put } = project();
  let r = re.detectRelease(root);
  assert.equal(r.release, 'v2');
  assert.equal(r.baseline, 'v1');
  assert.deepEqual(r.inputs, ['docs/inputs/v2/IDEA_EXTEND_R2.md']);
  assert.deepEqual(r.references, ['docs/reference/v2/blueprint.md']);
  assert.equal(re.detectRelease(root, { release: 'v3' }).release, 'v3');
  // once v2 is in the plan, the next cascade without a v3 folder targets v3
  const plan = JSON.parse(planV2());
  plan.reqs.forEach((r2, i) => { if (i > 1) r2.release = 'v2'; });
  put('docs/harper/plan.json', JSON.stringify(plan));
  r = re.detectRelease(root);
  assert.equal(r.release, 'v3');
  assert.equal(r.baseline, 'v2');
  fs.rmSync(root, { recursive: true, force: true });
});

test('an empty release folder made in advance does not become the target release', () => {
  // test project: docs/inputs/v3/ with the requirements, docs/reference/v4/ created empty for later;
  // the cascade targeted v4 with no input and the cockpit asked for docs/inputs/v4/
  const { root, put } = project();
  const plan = JSON.parse(planV2());
  plan.reqs.forEach((r2, i) => { if (i > 1) r2.release = 'v2'; });
  put('docs/harper/plan.json', JSON.stringify(plan));
  put('docs/inputs/v3/IDEA_EXTEND_R3.md', '# v3');
  fs.mkdirSync(path.join(root, 'docs', 'reference', 'v4'), { recursive: true });
  const r = re.detectRelease(root);
  assert.equal(r.release, 'v3');
  assert.deepEqual(r.inputs, ['docs/inputs/v3/IDEA_EXTEND_R3.md']);
  assert.equal(r.folders.includes('v4'), false);
  // once it holds the v4 documents it is the next release
  put('docs/reference/v4/apollo.md', '# api');
  assert.equal(re.detectRelease(root).release, 'v4');
  fs.rmSync(root, { recursive: true, force: true });
});

test('the release needs files in docs/inputs/<release>/ or an attachment', () => {
  const { root } = project();
  const rel = re.detectRelease(root);
  assert.equal(re.cascadeInputCheck(rel, 0).ok, true);            // docs/inputs/v2/ has the requirements
  const empty = re.detectRelease(root, { release: 'v3' });
  assert.equal(re.cascadeInputCheck(empty, 1).ok, true);          // attached
  const none = re.cascadeInputCheck(empty, 0);
  assert.equal(none.ok, false);
  assert.match(none.message, /docs\/inputs\/v3\//);
  fs.rmSync(root, { recursive: true, force: true });
});

test('the baseline reports REQs not delivered and the last solution verification', () => {
  const { root, put } = project();
  assert.deepEqual(re.baselineStatus(root), { hasPlan: true, total: 2, notDone: [], solution: 'not run' });
  put('docs/harper/SOLUTION_EVAL.md', '# Solution eval\n\nStatus: PASS\n');
  const plan = { reqs: [{ id: 'REQ-001', status: 'done' }, { id: 'REQ-002', status: 'in_progress' }] };
  put('docs/harper/plan.json', JSON.stringify(plan));
  const b = re.baselineStatus(root);
  assert.equal(b.solution, 'PASS');
  assert.deepEqual(b.notDone, ['REQ-002 (in_progress)']);
  fs.rmSync(root, { recursive: true, force: true });
});

test('merged documents keep every section of the earlier release', () => {
  const merged = re.compareMarkdown(IDEA_V1, `${IDEA_V1}\n## Release v2\nSign-in.\n`);
  assert.equal(merged.ok, true);
  assert.deepEqual(merged.added, ['## Release v2']);
  const rewritten = re.compareMarkdown(IDEA_V1, '# IDEA\n\n## Vision\nSomething else.\n');
  assert.equal(rewritten.ok, false);
  assert.deepEqual(rewritten.missing, ['## Out of scope']);
  assert.equal(re.compareAdditive(TECH_V1, `${TECH_V1}  auth: oidc\n`).ok, true);
  assert.equal(re.compareAdditive(TECH_V1, 'tech_constraints:\n  backend: java\n').ok, false);
});

test('delta rules: change type, release filled in, amends and supersedes resolved', () => {
  const { root } = project();
  const ltc = (id) => re.ltcCheckIds(root, id);
  const ok = re.validateDelta({ beforeText: JSON.stringify(PLAN_V1), planText: planV2(), release: 'v2', ltcChecks: ltc });
  assert.equal(ok.ok, true, ok.errors.join('; '));
  assert.deepEqual(ok.delta.map((r) => r.release), ['v2', 'v2']);

  const bad = re.validateDelta({
    beforeText: JSON.stringify(PLAN_V1),
    planText: planV2({ supersedes: [{ check: 'REQ-002#lint' }, { check: 'REQ-001#tests', reason: 'x' }], amends: ['REQ-002'] }),
    release: 'v2', ltcChecks: ltc,
  });
  assert.equal(bad.ok, false);
  assert.ok(bad.errors.some((e) => /LTC has no check "lint"/.test(e)));
  assert.ok(bad.errors.some((e) => /REQ-001, which it does not amend/.test(e)));

  const untyped = JSON.parse(planV2());
  delete untyped.reqs[2].change;
  const r = re.validateDelta({ beforeText: JSON.stringify(PLAN_V1), planText: JSON.stringify(untyped), release: 'v2' });
  assert.ok(r.errors.some((e) => /REQ-003: change must be/.test(e)));
  fs.rmSync(root, { recursive: true, force: true });
});

test('local agent: rewritten documents are restored, the report gets CLike verification', () => {
  const { root, put } = project();
  const before = re.snapshotDocs(root);
  const started = Date.now() - 1000;
  // what a local agent leaves on disk
  put('docs/harper/IDEA.md', '# IDEA\n\n## Vision\nRelease 2 only.\n');            // dropped "Out of scope"
  put('docs/harper/SPEC.md', `${SPEC_V1}\n## Release v2\nOIDC.\n`);                 // merged
  put('docs/harper/TECH_CONSTRAINTS.yaml', `${TECH_V1}  auth: oidc\n`);              // additive
  put('docs/harper/plan.json', planV2());
  put('docs/harper/EXTEND_2026-10-18_REQ-003_REQ-004.md', '# EXTEND\n\nDelta.\n');
  const files = [];
  const out = re.reconcileExtend({
    root, before, files, isAgent: true, mode: 'cascade', validateExtendPlan, startedAt: started,
    cascade: { release: 'v2', baseline: 'v1', inputs: ['docs/inputs/v2/IDEA_EXTEND_R2.md'], baselineInfo: re.baselineStatus(root) },
  });
  assert.equal(out.ok, true, out.errors.join('; '));
  assert.equal(fs.readFileSync(path.join(root, 'docs/harper/IDEA.md'), 'utf8'), IDEA_V1);
  assert.match(fs.readFileSync(path.join(root, 'docs/harper/SPEC.md'), 'utf8'), /## Release v2/);
  assert.match(fs.readFileSync(path.join(root, 'docs/harper/TECH_CONSTRAINTS.yaml'), 'utf8'), /auth: oidc/);
  assert.ok(out.warnings.some((w) => /IDEA\.md dropped sections/.test(w)));
  const plan = JSON.parse(fs.readFileSync(path.join(root, 'docs/harper/plan.json'), 'utf8'));
  assert.equal(plan.reqs[3].release, 'v2');
  const report = fs.readFileSync(path.join(root, out.report), 'utf8');
  assert.match(report, /## CLike verification/);
  assert.match(report, /\| REQ-004 \| MODIFIED \| Identity gateway \| REQ-002 \| REQ-002#e2e \| REQ-002 \|/);
  assert.match(report, /IDEA\.md: \*\*restored\*\*/);
  fs.rmSync(root, { recursive: true, force: true });
});

test('cloud: dry run keeps only the report; a broken delta is rejected and nothing is kept', () => {
  const { root } = project();
  const before = re.snapshotDocs(root);
  const files = [
    { path: 'docs/harper/IDEA.md', content: `${IDEA_V1}\n## Release v2\nx\n` },
    { path: 'docs/harper/plan.json', content: planV2() },
    { path: 'docs/harper/EXTEND_2026-10-18_REQ-003_REQ-004.md', content: '# EXTEND\n' },
  ];
  const dry = re.reconcileExtend({ root, before, files, isAgent: false, mode: 'cascade', validateExtendPlan, cascade: { release: 'v2', baseline: 'v1', dryRun: true } });
  assert.equal(dry.ok, true);
  assert.deepEqual(files.map((f) => f.path), ['docs/harper/EXTEND_2026-10-18_REQ-003_REQ-004.md']);
  assert.match(files[0].content, /Dry run/);

  const broken = JSON.parse(planV2());
  broken.reqs[3].amends = ['REQ-009'];
  const files2 = [{ path: 'docs/harper/plan.json', content: JSON.stringify(broken) }, { path: 'docs/harper/SPEC.md', content: 'x' }];
  const rejected = re.reconcileExtend({ root, before, files: files2, isAgent: false, mode: 'cascade', validateExtendPlan, cascade: { release: 'v2', baseline: 'v1' } });
  assert.equal(rejected.ok, false);
  assert.ok(rejected.errors.some((e) => /amends REQ-009/.test(e)));
  assert.deepEqual(files2, []);
  // the rejected run's documents are kept, nothing is lost
  assert.match(rejected.kept, /^runs\/extend\/rejected\//);
  assert.equal(fs.readFileSync(path.join(root, rejected.kept, 'docs', 'harper', 'SPEC.md'), 'utf8'), 'x');
  fs.rmSync(root, { recursive: true, force: true });
});

test('local agent: a rejected cascade leaves no lane guide or report of its own behind', () => {
  // test project: the rejected run's v3 lane guidance and EXTEND report stayed in the workspace
  const { root, put } = project();
  put('docs/harper/lane-guides/python.md', '# python\n');
  put('docs/harper/EXTEND_2026-10-18_REQ-003_REQ-004.md', '# EXTEND v2\n');
  const before = re.snapshotDocs(root);
  const broken = JSON.parse(planV2());
  broken.reqs[3].amends = ['REQ-009'];
  put('docs/harper/plan.json', JSON.stringify(broken));
  put('docs/harper/lane-guides/python.md', '# python\n\n## Release v3\n');
  put('docs/harper/lane-guides/go.md', '# go\n');
  put('docs/harper/EXTEND_2026-10-25_REQ-005_REQ-006.md', '# EXTEND v3\n');
  const out = re.reconcileExtend({ root, before, files: [], isAgent: true, mode: 'cascade', validateExtendPlan, cascade: { release: 'v3', baseline: 'v2' } });
  assert.equal(out.ok, false);
  const at = (rel) => path.join(root, ...rel.split('/'));
  assert.equal(fs.readFileSync(at('docs/harper/lane-guides/python.md'), 'utf8'), '# python\n');
  assert.equal(fs.existsSync(at('docs/harper/lane-guides/go.md')), false);
  assert.equal(fs.existsSync(at('docs/harper/EXTEND_2026-10-25_REQ-005_REQ-006.md')), false);
  assert.equal(fs.readFileSync(at('docs/harper/EXTEND_2026-10-18_REQ-003_REQ-004.md'), 'utf8'), '# EXTEND v2\n');
  assert.equal(fs.readFileSync(at('docs/harper/plan.json'), 'utf8'), JSON.stringify(PLAN_V1, null, 2));
  // all of it is kept for comparison
  for (const rel of ['docs/harper/lane-guides/python.md', 'docs/harper/lane-guides/go.md', 'docs/harper/EXTEND_2026-10-25_REQ-005_REQ-006.md']) {
    assert.ok(fs.existsSync(path.join(root, out.kept, ...rel.split('/'))), rel);
  }
  fs.rmSync(root, { recursive: true, force: true });
});

test('the commit of a cascade holds the lane guides and the release inputs, and names the release', () => {
  // test project: the v3 lane guides and docs/inputs/v3/ stayed out of the extend commit
  const { root, put } = project();
  put('docs/harper/lane-guides/python.md', '# python\n');
  put('docs/inputs/v3/IDEA_EXTEND_R3.md', '# Release 3\n');
  put('docs/inputs/v3/.DS_Store', 'x');
  put('docs/reference/v3/api/catalog.md', '# catalog\n');
  assert.deepEqual(re.cascadeCommitFiles(root, 'v3').sort(), [
    'docs/harper/lane-guides/python.md', 'docs/inputs/v3/IDEA_EXTEND_R3.md', 'docs/reference/v3/api/catalog.md',
  ]);
  assert.deepEqual(re.cascadeCommitFiles(root, '../x'), ['docs/harper/lane-guides/python.md']);
  assert.equal(
    re.cascadeCommitMessage({ release: 'v3', baseline: 'v2', delta: [{ id: 'REQ-037', change: 'MODIFIED' }, { id: 'REQ-038', change: 'ADDED' }] }, 'abc'),
    'docs(harper): release v3 from v2 — REQ-037 MODIFIED, REQ-038 ADDED\n\n[harper:extend] runId=abc',
  );
  fs.rmSync(root, { recursive: true, force: true });
});

test('supersedes: every check section of an LTC counts, a test id without its REQ is completed', () => {
  // test project: REQ-032 declares commands and external_checks (keycloak was refused as unknown);
  // the agent named tests without REQ-x# and the whole cascade was discarded
  const { root, put } = project();
  put('runs/kit/REQ-001/ci/LTC.json', JSON.stringify({ commands: [{ id: 'tests' }], external_checks: [{ id: 'keycloak' }] }));
  put('runs/kit/REQ-002/test/v2/test_setup.py', 'x');
  assert.deepEqual(re.ltcCheckIds(root, 'REQ-001'), ['tests', 'keycloak']);
  const plan = JSON.parse(planV2());
  const r = plan.reqs[3];
  r.change = 'MODIFIED';
  r.amends = ['REQ-001', 'REQ-002'];
  r.supersedes = [
    { check: 'REQ-001#keycloak', reason: 'container Keycloak' },
    { check: 'test/v2/req-001.states.test.tsx::restores the workspace', reason: 'by number' },
    { check: 'test/v2/test_setup.py::SetupTests::test_cli', reason: 'by KIT tests' },
    { check: 'test/v2/other.spec.ts::unknown owner', reason: 'ambiguous' },
  ];
  const out = re.validateDelta({
    beforeText: JSON.stringify(PLAN_V1), planText: JSON.stringify(plan), release: 'v2',
    ltcChecks: (id) => re.ltcCheckIds(root, id), testOwner: (ref, amends) => re.kitTestOwner(root, ref, amends),
  });
  assert.ok(!out.errors.some((e) => /keycloak/.test(e)), out.errors.join('\n'));
  const fixed = JSON.parse(out.planText).reqs[3].supersedes.map((x) => x.check);
  assert.equal(fixed[1], 'REQ-001#test/v2/req-001.states.test.tsx::restores the workspace');
  assert.equal(fixed[2], 'REQ-002#test/v2/test_setup.py::SetupTests::test_cli');
  assert.ok(out.warnings.some((w) => /completed as REQ-001#/.test(w)));
  assert.deepEqual(out.errors, ['REQ-004: supersedes "test/v2/other.spec.ts::unknown owner" is not REQ-x#<check or test id> and its REQ is not clear among REQ-001, REQ-002']);
  // with a single amended REQ the prefix is that REQ
  r.amends = ['REQ-002'];
  r.supersedes = [{ check: 'test/v2/other.spec.ts::unknown owner', reason: 'single' }];
  const single = re.validateDelta({ beforeText: JSON.stringify(PLAN_V1), planText: JSON.stringify(plan), release: 'v2' });
  assert.deepEqual(single.errors, []);
  assert.equal(JSON.parse(single.planText).reqs[3].supersedes[0].check, 'REQ-002#test/v2/other.spec.ts::unknown owner');
  fs.rmSync(root, { recursive: true, force: true });
});

test('/extend (plan mode) never changes TECH_CONSTRAINTS', () => {
  const { root } = project();
  const before = re.snapshotDocs(root);
  const files = [{ path: 'docs/harper/TECH_CONSTRAINTS.yaml', content: 'other: true\n' }];
  const out = re.reconcileExtend({ root, before, files, isAgent: false, mode: 'plan' });
  assert.equal(out.ok, true);
  assert.equal(files[0].content, TECH_V1);
  assert.ok(out.warnings.some((w) => /not an \/extend output/.test(w)));
  fs.rmSync(root, { recursive: true, force: true });
});

test('the baseline tag is created once on HEAD', () => {
  const { execFileSync } = require('child_process');
  const { root } = project();
  const git = (...args) => execFileSync('git', args, { cwd: root, encoding: 'utf8' });
  git('init', '-q', '-b', 'main');
  git('config', 'user.email', 't@t');
  git('config', 'user.name', 't');
  git('add', '-A');
  git('-c', 'user.email=t@t', '-c', 'user.name=t', 'commit', '-q', '-m', 'v1');
  assert.equal(re.tagBaseline(root, 'v1'), 'harper/v1');
  assert.equal(re.tagBaseline(root, 'v1'), 'harper/v1');
  assert.match(git('tag', '-l'), /harper\/v1/);
  fs.rmSync(root, { recursive: true, force: true });
  const plain = fs.mkdtempSync(path.join(os.tmpdir(), 'clike-nogit-'));
  assert.equal(re.tagBaseline(plain, 'v1'), '');
  fs.rmSync(plain, { recursive: true, force: true });
});

test('PLAN.md index sections list the new REQs (table, dependency graph, per-REQ bullets)', () => {
  const md = [
    '# PLAN', '', '## REQ-IDs Table', '', '| ID | Title | Acceptance | DependsOn | Track | Status |', '|---|---|---|---|---|---|',
    '| REQ-001 | Config | a | | | done |', '| REQ-002 | Discovery | b | REQ-001 | | done |', '',
    '## Dependency Graph', '', '- REQ-001 <- none', '- REQ-002 <- REQ-001', '',
    '## Test Strategy', '', '**REQ-001** — unit.', '', '**REQ-002** — e2e.', '',
    '## Release v2', '', '### Test Strategy — REQ-003', 'OIDC tests.', '',
  ].join('\n');
  const plan = JSON.parse(planV2());
  plan.reqs[2].release = 'v2';
  const out = re.syncPlanMd(md, JSON.stringify(plan));
  assert.match(out.text, /\| REQ-003 \| OIDC sign-in \| login \| REQ-001 \|/);
  assert.match(out.text, /- REQ-004 <- REQ-002\n/);
  assert.match(out.text, /\*\*REQ-003\*\* — see `### Test Strategy — REQ-003` \(Release v2\)\./);
  assert.match(out.text, /\*\*REQ-004\*\* — see the REQ-004 section\./);
  assert.match(out.text, /\| REQ-001 \| Config \| a \|/);     // delivered rows unchanged
  assert.equal(re.syncPlanMd(out.text, JSON.stringify(plan)).added.length, 0); // idempotent
});

test('the chat (webview) copy of the slash parser runs: every constant it uses is included', () => {
  const vm = require('vm');
  const { buildBrowserSlashParserSource } = require('../slash-parser');
  const sandbox = {};
  vm.runInNewContext(`${buildBrowserSlashParserSource()}\nthis.out = [parseSlash('│ /idea --extend --methodology bmad --agent analyst'), parseSlash('/kit REQ-015'), parseSlash('hello')];`, sandbox);
  const [extend, kit, chat] = sandbox.out;
  assert.equal(extend.args.extend, true);
  assert.equal(extend.args.agent, 'analyst');
  assert.equal(kit.cmd, '/kit');
  assert.equal(chat, null);
});

test('/eval REQ --supersede declares a delivered test the open REQ changes, audited', () => {
  // B2B REQ-037: a REQ-015 test pinned the exact session fields; the cascade had not named it
  const { root, put } = project();
  const plan = JSON.parse(planV2());
  plan.reqs[3].status = 'in_progress';
  plan.reqs[3].change = 'ADDED';
  delete plan.reqs[3].amends;
  delete plan.reqs[3].supersedes;
  put('docs/harper/plan.json', JSON.stringify(plan, null, 2));
  put('runs/kit/REQ-001/test/leadintel/test_session.py', 'def test_session_fields():\n    assert fields == {"actor"}\n');
  const ref = 'REQ-001#test/leadintel/test_session.py::test_session_fields';
  const ok = re.declareSupersede(root, 'REQ-004', ref, 'the session view adds subject and groups', { author: 'dev' });
  assert.equal(ok.ok, true, ok.message);
  assert.match(ok.message, /amends REQ-001.*ADDED → MODIFIED/);
  const after = JSON.parse(fs.readFileSync(path.join(root, 'docs/harper/plan.json'), 'utf8')).reqs[3];
  assert.deepEqual(after.supersedes, [{ check: ref, reason: 'the session view adds subject and groups' }]);
  assert.deepEqual(after.amends, ['REQ-001']);
  assert.equal(after.change, 'MODIFIED');
  assert.match(fs.readFileSync(path.join(root, 'runs/extend/declared-supersedes.jsonl'), 'utf8'), /"author":"dev"/);
  assert.equal(re.declareSupersede(root, 'REQ-004', ref, 'the session view adds subject and groups').changed, false);
  // typed over two lines with its quotes (B2B): stored as one clean line
  re.declareSupersede(root, 'REQ-004', 'REQ-002#tests', '"v3:\nthe session view adds subject"');
  const last = JSON.parse(fs.readFileSync(path.join(root, 'docs/harper/plan.json'), 'utf8')).reqs[3].supersedes.pop();
  assert.equal(last.reason, 'v3: the session view adds subject');
  // refused: no reason, unknown test, a delivered REQ declaring, a check not in the LTC
  assert.match(re.declareSupersede(root, 'REQ-004', ref, 'x').message, /at least 10/);
  assert.match(re.declareSupersede(root, 'REQ-004', 'REQ-001#test/leadintel/test_session.py::test_other', 'a good long reason').message, /has no test "test_other"/);
  assert.match(re.declareSupersede(root, 'REQ-002', ref, 'a good long reason').message, /is delivered/);
  assert.match(re.declareSupersede(root, 'REQ-004', 'REQ-002#lint', 'a good long reason').message, /LTC has no check "lint"/);
  assert.equal(re.declareSupersede(root, 'REQ-004', 'REQ-002#e2e', 'a good long reason').ok, true);
  fs.rmSync(root, { recursive: true, force: true });
});

test('/eval --supersede is parsed with its reference and reason; other flags still apply', () => {
  const p = parseSlash('/eval REQ-037 --supersede REQ-015#test/x.py::test_a "the release adds fields" --fix');
  assert.deepEqual(p.args.supersede, { ref: 'REQ-015#test/x.py::test_a', reason: 'the release adds fields' });
  assert.equal(p.args.fix, true);
  assert.deepEqual(p.args.targets, ['REQ-037']);
});

test('extend: the journeys of the release are use cases of the SPEC, as /spec writes them', () => {
  const UC = '## Use Cases\n\n### UC-01 — Search\n- UC-01.1 the operator searches\n';
  const run = (specBefore, specAfter) => {
    const { root, put } = project();
    put('docs/harper/SPEC.md', specBefore);
    const before = re.snapshotDocs(root);
    put('docs/harper/SPEC.md', specAfter);
    put('docs/harper/plan.json', planV2());
    const out = re.reconcileExtend({ root, before, files: [], isAgent: true, mode: 'cascade', validateExtendPlan,
      cascade: { release: 'v2', baseline: 'v1' } });
    const report = out.report ? fs.readFileSync(path.join(root, out.report), 'utf8') : '';
    fs.rmSync(root, { recursive: true, force: true });
    return { out, report };
  };
  // B2B: a SPEC without the section, an extend that did not add it
  const none = run(SPEC_V1, `${SPEC_V1}\n## Release v2\nOIDC.\n`);
  assert.equal(none.out.ok, true, none.out.errors.join('; '));
  assert.ok(none.out.warnings.some((w) => /SPEC\.md has no ## Use Cases/.test(w)));
  assert.match(none.report, /- Use cases: none in SPEC\.md/);
  // the section is there but the release did not touch it
  const same = run(`${SPEC_V1}\n${UC}`, `${SPEC_V1}\n${UC}\n## Release v2\nOIDC.\n`);
  assert.ok(same.out.warnings.some((w) => /## Use Cases unchanged/.test(w)));
  // the release adds its journey: no warning, the report names it
  const added = run(`${SPEC_V1}\n${UC}`, `${SPEC_V1}\n${UC}\n### UC-02 — Sign in (v2)\n- UC-02.1 the operator signs in\n\n## Release v2\nOIDC.\n`);
  assert.ok(!added.out.warnings.some((w) => /Use Cases/.test(w)), added.out.warnings.join('; '));
  assert.match(added.report, /- Use cases: 2 \(new: UC-02\)/);
});

test('/finalize --verify verifies again without a new agent run; plain /finalize is unchanged', () => {
  assert.deepEqual(parseSlash('/finalize --verify').args, { verifyOnly: true });
  assert.equal(parseSlash('/finalize').args.verifyOnly, undefined);
});
