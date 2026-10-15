# Brownfield and evolution: `/adopt` and `/idea --extend`

- **Status:** design proposal, not implemented
- **Date:** 2026-10-15
- **Scope:** how CLike (1) takes over a project it did not create, whether hand-written, built with
  another agent or method, or a CLike project that drifted, and (2) evolves a CLike project
  with new or changed requirements, integrations included.

## 1. Summary

Two commands. Everything is a requirement: no new kinds of directive.

```
/adopt [--from attachment] [--dry-run] [--refresh]
   any existing repository → a CLike project: .clike/project.json, IDEA/SPEC/PLAN "as is",
   adopted REQs that carry their own verification (existing tests or characterization tests),
   locked as the regression baseline.

/idea --extend [--from attachment] [--dry-run]
   new needs on a CLike project → IDEA delta → SPEC delta merged → PLAN/plan.json with
   ADDED / MODIFIED / REMOVED REQs → reviewed EXTEND report → /kit /eval /gate as today.
```

What makes the two commands **safe** rather than just document generators is CLike's enforced
oracle: locked acceptance, regression of promoted REQs and the gate. Most comparable tools
(§3) give the model context to read and leave regression protection to the team. This design
extends the oracle instead:

- adopted code gets locked verification on day one;
- changes to delivered behavior are declared, approved and enforced at the gate;
- integrations are verified offline in the sandbox and, separately, live.

## 2. Current state (evidence)

Paths are relative to the repository root.

### 2.1 Evolving a CLike project

- **`/extend` (alias `/add-req`) is append-only, after an anchor REQ.**
  - Spec: `docs/CLike_Harper_Extend_Feature.md`.
  - Phase: `orchestrator/phases/extend/phase.yaml`. It forbids changing existing REQs (`:51`), acceptance and status (`text.yaml:46-53`).
- **Preservation is prompt-only.**
  - The agent returns a full `plan.json` (`phase.yaml:63`), and no code diffs the existing `reqs[]` before and after.
  - Also unchecked: anchor existence, ID uniqueness, dependency resolution, `snapshot` consistency.
  - What `services/local_agent/normalize.py:563-600` does check: required files are present, `plan.json` parses, every REQ has acceptance, and the audit is at least 40 characters.
- **`/extend` sees no code.** It runs with `rag_strategy="off"` (`extensions/vscode/utility.js:1458-1462`), and the cloud core docs are only SPEC, PLAN, plan.json and TECH_CONSTRAINTS (`utility.js:1739-1740`).
- **IDEA, SPEC and PLAN regenerate from scratch.** `/plan` and `/spec` overwrite their outputs (`orchestrator/phases/plan/phase.yaml:29-31`, `spec/phase.yaml:23-25`). SPEC changes from `/extend` are an appended "Extension Scope" section.
- **No way to change delivered behavior.** There is no `amends`, `supersedes` or `retire`.
  - The regression re-runs the LTC of every `done` REQ (`orchestrator/eval_runner.py:2788-2805`), so a new REQ that legitimately changes REQ-A's behavior fails `GATE_BLOCKED_REGRESSION`.
  - Editing REQ-A's tests trips `GATE_BLOCKED_ACCEPTANCE_TAMPERED` (`orchestrator/services/gate_integrity.py:242-292`).
  - Today's workarounds are all bad: re-`/kit` REQ-A (it leaves the regression set, with no record of intent), an audited override on every gate, or `clike.eval.regression=false` for the whole project.
- **Status model:** `open | in_progress | done | deferred` (`utility.js:16`). `deferred` is never set by code, and there is no flow that reopens a `done` REQ.
- **KIT context in the cloud does not include canonical code.**
  - The RAG indexes only `runs/kit/<dep>/src` (`gateway/routes/harper.py:1847-1910`).
  - The local agent does read `src/` (`utility.js:2143`, `local_agent/kit.py:117`).

### 2.2 Onboarding a repository CLike did not create

- **No adopt, import or reverse phase exists.** `docs/integrations/bmad/FUTURE_IMPORTER.md` is design-only; "brownfield reverse-SPEC" is roadmap (`README.md:243`).
- **`src`, `test` and `tests` are hard-coded:**
  - promotion (`extensions/vscode/promote-merge.js:15`);
  - eval composition (`eval_runner.py:857-875`, path map `:1572-1604`, `_resolve_kit_root` needs `ci/` and `src/` side by side `:1342`);
  - KIT context and write roots (`utility.js:2143`, `:2160-2172`);
  - write policy (`local-agent-write-policy.js:162-171`);
  - input fingerprint (`auto-eval.js`);
  - repository manifest (`orchestrator/services/repository_manifest.py:54-61`, `:218-225`);
  - `config.py:31-32` and `utils/namespace_paths.py`.
- **`.clike/project.json` already declares `source_folder` and `test_folder`,** but they are only echoed into the agent context (`utility.js:2138-2139`); promotion and eval ignore them.
- **`/init` creates a new folder.** With `--force` it overwrites files and always rewrites `.gitignore` (`extensions/vscode/extension.js:3617-3749`).
- **Existing tests and CI are never part of the oracle.**
  - A check without `cwd` runs in the real project root, not in the sandbox (`eval_runner.py:1796-1802`).
  - No setting declares project-native test commands.
- **`.clike/context.yaml` skips code files** (`.py`, `.java`, `.go` count as an unsupported format; `orchestrator/services/context_sources.py:44-48`, `:159`).
- **Context budget:** 18–22.5k characters per phase call (`utility.js:1449-1462`). A real repository has to be analyzed piecewise.

### 2.3 Defects found during the analysis (independent of this design)

All four are **fixed** (F0, 2026-10-15); the table records what they were.

| # | Defect | Where | Action |
|---|---|---|---|
| D1 | `/extend` preservation of existing REQs is not verified in code | `normalize.py:563-600` | deterministic validator (§6.6) |
| D2 | Regression of REQ-A composes canonical, then A's dependencies, then **A's original KIT `src`**, then the candidate. A file that a later promoted REQ also changed is shadowed by A's stale KIT copy, so A's tests run on code that will not exist after promotion. | `eval_runner.py:2807-2842` with `:827-868` | reproduce with a test, then compose the regression from the canonical tree (which already holds A, promoted) plus the candidate |
| D3 | `context.yaml` rejects source files | `context_sources.py:44-48` | accept code extensions within the existing caps |
| D4 | `/init --force` overwrites files and `.gitignore` | `extension.js:3695`, `:3720-3749` | merge mode (also used by `/adopt`) |

## 3. Comparable solutions

| Tool | How it captures the "as is" | How it changes existing behavior | Regression guard |
|---|---|---|---|
| GitHub Spec Kit | `specify init --here` on an existing repo. The constitution records the practices that exist ("do not invent standards"). It does not reverse-engineer specs. | One spec per change, including the compatibility requirements to preserve | `/speckit.analyze` consistency only |
| OpenSpec | "Brownfield-first": `openspec/specs/` grows slice by slice as changes land | `changes/<id>/` with delta specs: **ADDED / MODIFIED** (full restatement) **/ REMOVED** requirements. Archive merges the deltas into the living spec. | scenarios per requirement, `/opsx:verify` |
| BMAD v4 / v6 | v4: `document-project` or brownfield PRD first. v6: verified `project-context` (AGENTS.md); the code is the truth. | brownfield PRD, epics and stories; v6 `bmad-spec`/`bmad-build` | v4 QA agent: `*risk`, `*trace`, `*gate` |
| AWS Kiro | Steering docs generated from the repo (`product.md`, `tech.md`, `structure.md`) | Feature specs. **Bugfix specs:** current, expected and **unchanged behavior ("SHALL CONTINUE TO")**. | property-based tests for bugfix specs |
| Tessl | `tessl document --code` reverse-engineers specs (about one spec per file, beta) | edit the spec, regenerate the code | `@test`-linked tests |
| Claude Code, Cursor, Amp, Aider, DeepWiki | `/init` CLAUDE.md, rules, AGENTS.md, repo map, wiki | edit the context files | none ("context, not enforced configuration") |
| Legacy practice | Characterization, approval or golden-master tests (Feathers); strangler fig (Fowler) | replace pieces behind seams | the recorded tests are the oracle |

**What we take:**

- **From OpenSpec:** a thin "as is" spec grown by changes, and delta changes merged into a living spec with an archive.
- **From Kiro:** "unchanged behavior" stated explicitly. In CLike it is the regression, now declared per change.
- **From Claude `/init`, Kiro steering and BMAD v6:** analyze the repo and produce verified context.
- **From Feathers:** characterization tests locked before any agent touches the code.

**What we avoid:**

- reverse-engineering a complete fake history of `done` REQs (nobody does it reliably);
- context files that are advisory only.

**Gap no comparable tool fills:** enforced regression of existing and adopted behavior. CLike already has the machinery for it.

Sources: github.github.com/spec-kit/guides/existing-projects.html, github.com/Fission-AI/OpenSpec
(docs/concepts.md), docs.bmad-method.org/existing-codebases, kiro.dev/docs/specs/bugfix-specs,
kiro.dev/docs/steering, code.claude.com/docs/en/memory,
martinfowler.com/articles/exploring-gen-ai/sdd-3-tools.html,
martinfowler.com/bliki/StranglerFigApplication.html.

## 4. Principles

1. **Everything is a requirement.** Integrations, changes and removals are REQs in `plan.json`. There are no side channels.
2. **No requirement without verification.** A REQ is `done` only with locked checks: KIT tests, existing tests adopted as baseline, or characterization tests. Documents alone never make a REQ `done`.
3. **Observed, inferred, open.** Every statement CLike derives from code or foreign documents is labelled as one of the three. Undecided business behavior stops the flow with questions; it never becomes an implicit default.
4. **Change is declared before it is built.** A change to delivered behavior names the checks it supersedes at planning time, is approved in the EXTEND report and is enforced at the gate. It is never discovered as a regression or a tampered test.
5. **Merge, never overwrite.** Existing files, `.gitignore`, CI, README and foreign tool artifacts are preserved.
6. **One source of truth after adoption.** Harper documents rule. Foreign artifacts stay in place, recorded as imported, and are never deleted.
7. **Deterministic first.** Validation, impact, ownership and fingerprints are code, not prompts.

## 5. Foundation: `.clike/project.json` honored

`project.json` already exists (`extensions/vscode/templates/harper-init/.clike/project.json`)
and is extended. No new file.

```json
{
  "project_id": "portale-ordini",
  "harper_doc_root": "docs/harper",
  "source_folders": [
    { "path": "backend/app", "lane": "python" },
    { "path": "frontend/src", "lane": "node" }
  ],
  "test_folders": ["backend/tests", "frontend/__tests__"],
  "commands": {
    "build": ["npm --prefix frontend run build"],
    "test":  ["pytest backend/tests", "npm --prefix frontend test"],
    "lint":  ["ruff check backend", "npm --prefix frontend run lint"]
  },
  "git": { "default_branch": "develop", "req_branch_prefix": "clike/" },
  "origin": { "adopted_at": "2026-10-15", "from": ["code", "bmad"] }
}
```

- **Backward compatibility.** `source_folder` and `test_folder` (strings) keep working. Absent, the default is `src`, `test` and `tests`: existing CLike projects do not change.
- **One resolver**, in the extension and the orchestrator, replaces every hard-coded root of §2.2: promotion, eval overlay and path map, KIT write roots, write policy, fingerprint, repository manifest, regression.
- **The KIT mirrors repository-relative paths.** For example `runs/kit/REQ-009/backend/app/payments/service.py`. Today `runs/kit/<REQ>/src/...` maps to `src/...`; the same rule now applies to any declared root.
- **Promotion can delete and rename.** `runs/kit/<REQ>/ci/PROMOTION.json` lists `{"delete": [...], "rename": [[from, to]]}`, limited to declared roots. Each entry is reported and reverted by `git apply -R` like the rest.
- **`commands`** are the project's native checks. `/adopt` uses them for the baseline, and the eval runs them **inside the sandbox**, never in the real root (unlike today's cwd-less checks).

## 6. `/idea --extend`

### 6.1 Command

```
/idea --extend [--from attachment] [--dry-run]
```

The attachment carries the new needs: a document, notes, a ticket export. `--dry-run` writes only the report.

`/extend` and `/add-req` remain as the plan-only step: today's behavior, plus the validator of §6.6.

### 6.2 Cascade

Each step runs in **extend mode**: it changes only what the delta needs, keeps everything else
byte-identical, and shows the diff in the report before it is applied.

1. **IDEA delta.** New goals, users and constraints are merged into IDEA.md, with the decisions that came with the attachment. Missing decisions (provider, licensing, privacy basis, budget) become **open questions**, and the cascade **stops** there unless the user answers or explicitly defers them.
2. **SPEC delta.** New or changed capabilities, interfaces, data and integration contracts are **merged** into the relevant SPEC sections, replacing the appended "Extension Scope".
3. **PLAN and plan.json delta.** New REQ IDs continue the sequence. Each REQ in the delta has a `change`:
   - `ADDED`: a new REQ, as today;
   - `MODIFIED`: a new REQ with `amends: ["REQ-006"]` that restates in full each acceptance criterion it changes and lists `supersedes: ["REQ-006#<check-or-test-id>", ...]`;
   - `REMOVED`: a REQ that retires a capability: `retires: ["REQ-00X"]`, with acceptance proving the removal (routes gone, data migrated, UI entry removed).
4. **Report** `docs/harper/EXTEND_<date>_<first>_<last>.md` contains:
   - the IDEA, SPEC and PLAN diffs;
   - the delta table;
   - for every `MODIFIED`/`REMOVED` REQ, the superseded checks with the reason;
   - the impact (§6.7);
   - the open questions.

   The user approves it, by applying the change, before `/kit`.

### 6.3 plan.json fields (additive)

```json
{
  "id": "REQ-015",
  "change": "MODIFIED",
  "amends": ["REQ-006"],
  "supersedes": [
    { "check": "REQ-006#test_unknown_without_financials", "reason": "real financials now decide PASS/FAIL" }
  ],
  "unchanged": ["REQ-006 PASS/FAIL/UNKNOWN semantics for missing years"],
  "origin": "extend:EXTEND_2026-10-20_REQ-015_REQ-017"
}
```

On the amended REQ, after the gate: `"amended_by": ["REQ-015"]`, `"retired_checks": [...]`.

`unchanged` is Kiro's "SHALL CONTINUE TO". It is informative: what enforces it is the regression of the amended REQ with its non-superseded checks.

### 6.4 Gate and lock rules for changes

- **Regression of an amended REQ** excludes exactly the superseded checks of the change being gated. Every exclusion is listed in the gate report and in `state/audit/` with the change ID.
  - The checks are named by LTC check ID or by test ID. A test ID filters with the runner's deselect (`pytest --deselect`, `vitest -t` negation) produced by the eval runner, never by editing the locked files.
- **Acceptance lock of the amended REQ.** When the change REQ is promoted, the superseded checks move from the amended REQ's lock to `retired` (kept, with hash and change ID). The rest of its lock is unchanged, so tampering protection still covers it.
- **Superseded tests are never edited.** Their replacements live in the change REQ's KIT and are locked there.
- **`REMOVED`:** the retired REQ leaves the regression set when its retiring REQ is promoted; its KIT and lock stay as history.
- **Order.** A change REQ may not supersede checks of a REQ that is `in_progress`. That REQ is re-planned in the same delta instead, with a new KIT generation.

### 6.5 Living spec

When a REQ in the delta is promoted, its SPEC delta is already merged (§6.2). The EXTEND report is the archive: the trace from each SPEC section to the EXTEND reports that changed it is kept in `docs/harper/history.json`. SPEC stays one readable document.

### 6.6 Deterministic validator (also for `/extend`)

It runs after the agent and before anything is written. It fails the phase when:

- any existing REQ changes, except the fields CLike itself sets (`amended_by`, `retired_checks`);
- IDs are not unique, or a new ID does not continue the sequence;
- the anchor REQ is missing;
- a `dependsOn`, `amends`, `retires` or `supersedes` target is missing;
- a superseded check is not found in the target's LTC or tests;
- `snapshot` is inconsistent;
- a `MODIFIED` REQ has no full restatement of a changed criterion.

### 6.7 Impact (deterministic)

- **Ownership:** which REQ wrote which file, from every `runs/kit/<REQ>/promotion/<ts>/report.json` (path and outcome), plus adopted REQs' `files` (§7.4).
- **Graph:** `dependsOn`, `amends`, `retires`.
- **Tests:** each REQ's LTC checks and test files.

Given the files or capabilities the delta touches, the impact step lists the affected REQs, files and checks. The agent receives the **code slices** of those files: the local agent reads them; the cloud gets them as attachments within the budget. The agent then proposes the delta grounded in real code, which today it cannot see (§2.1).

### 6.8 Integrations are requirements

An integration (for example the real financial-data provider behind `EvidencePort` in the B2B
project) is an `ADDED` or `MODIFIED` REQ. Completeness rules apply in IDEA and SPEC:

- **Decisions required before PLAN:**
  - provider and contract;
  - licensing for automated use;
  - privacy basis (for personal data);
  - credentials model (names of environment variables, never values);
  - cost model and quotas.

  Missing decisions are open questions (§6.2, step 1).
- **Inputs:** provider documentation and sample responses go in `docs/inputs/integrations/<provider>/`, already read through `.clike/context.yaml`.
- **Acceptance is of two kinds:**
  - **Contract (offline, blocking).** Tests against recorded provider responses run in the sandbox: no network, no credentials. They cover mapping into the project's normalized types, timeouts, quota and error mapping, cost recording, and adapter selection by configuration.
  - **Live (outside the sandbox, evidence).** `runs/kit/<REQ>/ci/LIVE_LTC.json` is run by the developer on demand, with their credentials, from the extension. The result (time, provider, outcome, no secrets) is attached to the gate report. It is non-blocking by default; a project may make it required for `/finalize`. This closes the gap where a gate could pass on an integration that was never called.

## 7. `/adopt`

### 7.1 Command

```
/adopt [--from attachment] [--dry-run] [--refresh]
```

- Runs on the open workspace: an existing repository, in place.
- **`--from attachment`:** the "why" (product brief, deck, contract), used for IDEA.
- **`--dry-run`:** writes only the report.
- **`--refresh`:** re-adopts a project already adopted or built with CLike, reconciling the Harper documents with the code as it is now (drift).

Execution is local-agent first: the agent reads the repository. The cloud path is limited to the deterministic survey plus attached slices.

### 7.2 Steps

1. **Survey (deterministic).** Stacks and package managers, candidate source and test roots, entry points, CI workflows, existing Harper or foreign artifacts (§7.5), git state (default branch, protection hints).
2. **Baseline run (sandbox).** The project's native commands (§5) run in the eval sandbox. Each test is recorded as passing, failing or skipped. Already-failing tests are recorded as **failing at adoption**.
3. **Analysis (agent, map-reduce).** One module at a time, within the context budget. For each module: capabilities, interfaces, data, integrations and conventions, each labelled observed or inferred, with file references. Then a reduction across modules.
4. **Reconciliation with foreign artifacts (§7.5).** Each documented item is classified:
   - ✅ declared and found in code → observed;
   - ⚠️ declared and not found → open question or `open` REQ;
   - ❓ in code and not documented → inferred, to confirm.
5. **Proposal**, all written in merge mode:
   - `.clike/project.json`: roots, commands, git, origin;
   - `docs/harper/IDEA.md`: from the attachment, foreign PRDs or answers. Anything unknown stays **open**, never invented from code;
   - `docs/harper/SPEC.md`: capabilities "as is", interfaces, data, integrations, NFRs observed;
   - `docs/harper/TECH_CONSTRAINTS.yaml`: observed stacks and versions;
   - `docs/harper/PLAN.md` and `plan.json`: adopted REQs (§7.4), plus `open` REQs for unfinished foreign work;
   - lane guides and `.clike/skills` from the conventions found (CLAUDE.md, AGENTS.md, rules);
   - `.gitignore`, merged.
6. **Verification.** Per adopted REQ, `runs/kit/<REQ>/ci/LTC.json` lists the existing tests of its area as **baseline checks** (native commands, filtered to the area's tests). Where an area has no tests, `/adopt --characterize "<area>"` (also proposed in the report) generates **characterization tests**:
   - they record the current outputs at a seam (HTTP responses, rendered output, files written), including surprising ones;
   - the user reviews them;
   - on approval they are locked like KIT tests.
7. **Report** `docs/harper/ADOPT_<date>.md`:
   - survey and baseline results;
   - REQ to files and tests mapping;
   - the reconciliation table;
   - characterization proposals;
   - open questions and risks;
   - everything that will be written.

   Applying it locks the baseline. From then on the regression protects the adopted behavior.

### 7.3 After adoption

The project is a CLike project:

- `/idea --extend` evolves it;
- the regression runs the adopted REQs' baseline checks on every gate;
- `--refresh` re-reconciles when the code moves outside CLike.

### 7.4 Adopted REQ

```json
{
  "id": "REQ-003",
  "title": "Invoices",
  "status": "done",
  "origin": "adopted",
  "files": ["backend/app/invoices/**", "frontend/src/app/invoices/**"],
  "acceptance": ["(observed) An issued invoice gets a sequential number per fiscal year", "..."],
  "baseline_checks": ["pytest backend/tests/invoices", "npm --prefix frontend test -- invoices"],
  "failing_at_adoption": ["backend/tests/invoices/test_pdf.py::test_logo"],
  "test_profile": "baseline",
  "gate_policy_ref": "adopted"
}
```

- **`done` requires baseline checks or approved characterization tests.** An area with neither is adopted as `open` ("documented, not verified").
- **`failing_at_adoption` checks are reported, never blocking**, until a REQ fixes them; that REQ then supersedes the entry (§6.4).
- **Promotion merge base** for adopted files: the adoption commit.
- **Granularity:** one REQ per capability or area, not per file and not per historical feature. There is no reconstruction of past history.

### 7.5 Importers of foreign artifacts

Each importer is a small reader: it recognizes the files, maps them, and labels everything
`declared` until reconciliation (§7.2, step 4) confirms it in code. Foreign files are never
modified or deleted; they are recorded in `project.json` `origin.from`.

| Source | Files | Mapping |
|---|---|---|
| GitHub Spec Kit | `.specify/memory/constitution.md`, `specs/<feature>/{spec,plan,tasks}.md` | constitution → TECH_CONSTRAINTS and policies; spec → SPEC capabilities and acceptance; tasks → REQ mapping (done tasks still need verification) |
| BMAD | `_bmad-output/` or `docs/`: `prd.md`, `architecture.md`, epics, stories | PRD → IDEA and SPEC; architecture → SPEC and TECH_CONSTRAINTS; stories → REQs (implements `docs/integrations/bmad/FUTURE_IMPORTER.md`) |
| Kiro | `.kiro/specs/<feature>/{requirements,design,tasks}.md`, `.kiro/steering/{product,tech,structure}.md` | EARS requirements → acceptance; steering → IDEA and TECH_CONSTRAINTS |
| OpenSpec | `openspec/specs/`, `openspec/changes/`, `changes/archive/` | specs → SPEC; open changes → `open` REQs with ADDED/MODIFIED/REMOVED; archive → history |
| Agent context files | `CLAUDE.md`, `AGENTS.md`, `.cursor/rules/`, `.claude/rules/` | conventions → lane guides, skills, TECH_CONSTRAINTS |
| Git history | commits, PR titles and descriptions | IDEA hints and capability timeline (inferred) |

Unfinished foreign work (open stories, open changes, unchecked tasks) becomes `open` REQs with
`origin: "import:<tool>:<id>"`, so work continues where the other tool left it.

### 7.6 `--refresh` (drift)

For projects built with CLike and changed outside it (manual fixes, conflict resolutions,
hot fixes), or adopted earlier:

- it diffs the code against the promotion reports and the adopted `files`;
- it proposes SPEC and PLAN corrections and new baseline checks;
- it records the out-of-CLike changes as known, so the next promotion does not treat them as conflicts.

## 8. Changes by component

| Component | Change |
|---|---|
| Extension | `/adopt` and `/idea --extend` parsing; extend mode for IDEA/SPEC/PLAN; report review; roots resolver; promotion with delete/rename; live checks runner (`LIVE_LTC.json`) |
| Orchestrator | `adopt` phase (survey, baseline run, map-reduce analysis, importers, reconciliation); extend-mode prompts for idea/spec/plan; validator (§6.6); impact (§6.7); regression exclusions and audit (§6.4); lock `retired` section |
| Eval runner | roots from `project.json`; native commands in the sandbox; deselect of superseded tests; regression composition fix (D2) |
| Gate integrity | `retired` checks in locks; `failing_at_adoption` non-blocking; audit of supersessions |
| Gateway | canonical-code RAG namespace for KIT and extend context (promoted code, not only dependency KITs) |
| Templates and docs | `project.json` schema; `/init` merge mode; GET_STARTED, harper-workflow, commands, git-and-promotion |

## 9. Roadmap

| Phase | Content | Done when |
|---|---|---|
| **F0** ✅ done | D1 validator for `/extend`; D2 reproduced and fixed; D3 code files in `context.yaml`; D4 `/init` merge mode | each has a failing test before the fix and a passing one after |
| **F1** | `project.json` roots and commands honored everywhere; KIT mirror of declared roots; `PROMOTION.json` delete/rename | a fixture repo with `backend/app` and `frontend/src` goes KIT → eval → gate → promotion; existing CLike projects unchanged (the full suite passes) |
| **F2** | `/idea --extend` cascade with ADDED/MODIFIED/REMOVED, supersedes and lock retirement, living SPEC, impact, integration acceptance (contract and live) | **B2B pilot:** the real financial-data adapter behind `EvidencePort` as a MODIFIED change of REQ-006, gated with superseded checks audited and the live check attached |
| **F3** | `/adopt`: survey, baseline run, map-reduce analysis, proposal, baseline lock, characterization | a non-CLike fixture repository is adopted, and a deliberately breaking change to an adopted area is blocked by the regression |
| **F4** | importers (Spec Kit, BMAD and CLAUDE.md/AGENTS.md first, then Kiro and OpenSpec); `--refresh` drift | **VoiceSurveyAgent pilot** (built with CLike, grown outside it): `--refresh` reconciles it, `/idea --extend` evolves it |

## 10. Risks and open questions

- **Characterization tests lock bugs in.** They are intended to: changing that behavior later is a `MODIFIED` change with superseded checks, visible and approved.
- **Flaky native tests at adoption.** The baseline runs each test twice; tests with different outcomes are marked flaky, non-blocking and reported.
- **Large monorepos.** Analysis cost and time grow with the repository. Consider area-scoped adoption (`/adopt --area packages/billing`), extending the scope later.
- **Native commands with side effects** (databases, network): they run only in the sandbox, with the eval environment (`docker/eval.env`, provisioned databases). Commands that need what the sandbox lacks are reported, not run.
- **Test-ID deselection per runner:** pytest and vitest/jest first; other runners fall back to whole-check supersession.
- **Open:**
  - whether a `MODIFIED` change may also amend NFR or security criteria, or only functional ones;
  - who may approve a supersession in team settings (a role, or the same audit as overrides);
  - whether live checks become blocking for `/finalize` by default.

## 11. Non-goals

- Rebuilding the full feature history of a repository as `done` REQs.
- Running two methods in parallel as equal sources of truth after adoption.
- Editing or deleting foreign tool artifacts.
- Any change that alters locked tests in place; supersession only.
- Live provider calls inside the eval sandbox.
