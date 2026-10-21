# Changelog

All notable changes to CLike. Extension, orchestrator and gateway share one version.

## [Unreleased]

### Performance

- **The regression no longer repeats a promoted REQ's own regression checks**: a check named
  `regression` / `…-regression` of a promoted REQ re-runs tests of earlier REQs, which CLike's
  regression already runs on their promoted tests (`regression-checks::not-run` lists the skipped
  ones). The KIT prompt asks not to copy other REQs' tests into a KIT. On the B2B project this
  removes about 4 of the 25 minutes of an eval.

### Added

- **`harper_init` MCP tool**: `/init` of the folder open in VS Code, in place (existing files kept),
  so an agent can run a project from `/init` to `/finalize` through MCP.
- **`docs/howto-mcp-bmad-claude.md`**: the sequence `/init` → IDEA (analyst) → SPEC (pm, ux) → PLAN
  (architect) → KIT (developer) / EVAL --fix / GATE → FINALIZE (tech-writer) driven by Claude Code,
  with one ready instruction and a human check after PLAN.
- **`docs/clike-at-a-glance.md`**: the overview picture with a description area by area; the
  README gets a *Highlights* section linking to it (the picture is no longer embedded there).
- **Community files**: `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md` (Contributor Covenant 2.1),
  `SUPPORT.md`, `NOTICE`, issue forms (bug, feature request) and a pull request template.

### Changed

- **`LICENSE` is now the verbatim Apache License 2.0 text**, so it is recognised as Apache-2.0
  (the previous file was a reformatted copy with a modified section 9). Copyright moves to
  `NOTICE`; both `pyproject.toml` declare `license = "Apache-2.0"`, the extension declares its
  issue tracker.
- **Chat sessions are no longer tracked**: `.clike/sessions/` is ignored as a whole and the
  hygiene check rejects it.

### Fixed

- **A REQ phase run from another branch is committed on the REQ branch**: `/kit REQ-021` run on
  `main` (after the gate of REQ-020 merged and left you there) wrote `runs/kit/REQ-021/` files that
  `feature/req-021` tracks, the switch was refused and the KIT stayed uncommitted. Those files are
  now carried onto the REQ branch and committed there; the same holds for the handoff documents of
  `/finalize` and `/spec` run from a REQ branch, carried onto `main`. Any other blocking file still
  stops the sync and loses nothing.
- **A deliberate edit of a REQ's locked tests / LTC no longer needs a new `/kit`**: `/eval <REQ>
  --accept "reason"` (`POST /v1/acceptance/accept`) accepts edits that weaken nothing into the
  lock, with author and reason in the audit log. The stop message of `/eval --fix` / `/gate --fix`
  now names the REQ whose surface changed — often a promoted REQ run by the regression, not the
  candidate — and its files, instead of always suggesting `/kit` of the candidate.
- **A service broken by the candidate is explained**: when a promoted REQ's service starts without
  the candidate but not with it, the repair is told the candidate made a configuration mandatory
  (keep it optional with a safe default, or declare the change), instead of only "service failed".
- **A promoted REQ already broken blocked every new REQ**: a regression failure that the candidate
  did not cause (B2B: REQ-002's service lacks `LEADINTEL_EXECUTION_CONFIG`, required since
  REQ-003) blocked REQ-020 and went to its repair. A remaining failure is now re-run on the
  promoted tree without the candidate; failing there too, it is a warning naming the REQ to fix.
- **The promoted version of a test missed its helpers, and services ran stale code**: a promoted
  reconciled test now gets the support files it imports from the canonical test tree (B2B:
  `req017_support.py`, `identity/__init__.py`); a service of another promoted REQ runs its
  promoted code with the candidate's source (B2B REQ-005's REQ-004 service imported an older
  `ports.py`).
- **Cancel did not stop an eval**: the chat's Cancel aborted only chat requests, so `/eval`,
  `/gate` and their `--fix` loops went on (also with VS Code closed, the eval kept running in the
  sandbox). Cancel (and MCP `cancel_run`) now closes the eval/gate request, which stops the eval
  in the sandbox, stops every local agent CLike started, and ends the repair loop; a cancelled
  agent's files are not sent to the orchestrator.
- **Reconciliations did not last**: the regression of a promoted REQ ran the original tests of its
  KIT, not the version a later REQ had reconciled and promoted, so every following REQ had to
  reconcile the same tests again (B2B: the migration head pinned by REQ-015/017/018 failed at
  each new migration). The promoted version now runs when it is newer in git; the shared root
  `conftest.py` stays the REQ's own.
- **A candidate carrying a promoted file replaced every REQ's copy**: B2B REQ-020 shipped the
  canonical `test/conftest.py` unchanged and the regression put it in place of the root
  `conftest.py` of eight promoted REQs (missing fixtures). A file identical to its promoted copy
  is no longer a reconciliation.
- **A promoted dependency without a promotion record brought old files back**: a REQ done before
  gate promotion records existed (B2B REQ-003) had its KIT overlaid over the canonical tree, so an
  older `ports.py` replaced the one later REQs had changed, and REQ-019 failed on names that were
  already promoted. Such a KIT file now wins only when its canonical copy is not newer in git.
- **Local agent timeouts**: `clike.localAgent.codex.timeoutMinutes` and
  `clike.claudeCode.timeoutMinutes` were ignored (the common `clike.localAgent.timeoutMinutes`
  always won); now the executor's own timeout applies when set. A run that times out is no
  longer thrown away: CLike checks the files the agent wrote and, if the required outputs are
  there, the phase continues (normalization, eval); otherwise the error names the setting to raise.
- **Regression ran the old test after a reconciliation**: when a candidate reconciles a promoted
  REQ's test in its own test root (as the *Shared files changed* diagnosis asks), the regression of
  that REQ now runs the candidate's version, which is what promotion delivers. It is reported as
  the warning `regression::<REQ>::reconciled-tests`. Before, the repair could never converge.
- **A reconciled test could not import its new neighbours**: the candidate's new support files next
  to the promoted REQ's tests (`__init__.py`, `conftest`, helpers; never tests, by name or content)
  now come with the reconciled test. Before, a relative import (`from .conftest import …`) failed in
  the regression only.
- **A reconciled test could not import a helper outside its directory**: a reconciled test in
  `test/v2/` importing a helper the candidate put at the test root failed with
  `ModuleNotFoundError` in the regression only, and the repair could not fix it. A reconciled test
  now gets the support modules it imports (also through another helper) from anywhere in the
  candidate's test tree, plus a package marker or `conftest` beside it; a `conftest` elsewhere stays
  out, since the test runner would load it into the promoted REQ's own tests.
- **A repair of an unlocked test was undone**: governance rejected any change to a `test/` file
  without a digest in the acceptance lock, so a test added after the lock (a reconciled test of a
  promoted REQ) could not be fixed by a later repair, and the extension restored it. Such files
  are not locked acceptance: they are kept (returned as `unlocked`), for cloud repairs as for
  Claude Code and Codex.
- **`clike.localAgent.allowEval: false` was ignored**: `/eval` ran the local-agent pre-pass whenever
  a local executor was selected. The setting now skips it and the eval goes straight to the sandbox.
- **Merge-on-gate blocked by a KIT file of the REQ**: a tracked file of `runs/kit/<REQ>/` changed
  after its phase (e.g. `ci/HOWTO.md` updated by an eval pre-pass) was left out of the gate commit,
  and the switch to the default branch failed ("Your local changes … would be overwritten"). Every
  tracked change of the REQ's own KIT is now committed with the KIT, eval and gate phases.

## [1.5.1] — 2026-10-18 — CLike from Claude Code and Codex: MCP hardened, eval repairs that converge

### Added

- **`docs/howto-mcp-project.md`**: run a whole CLike project from Claude Code or Codex through MCP —
  setup (`.mcp.json` with `${CLIKE_API_TOKEN}`, Codex, the extension server), the phase loop with
  the tool calls, the next release, what MCP does not do, troubleshooting.
- **`harper_run_phase` takes `attachments`** (workspace-relative files, as *Attach → Workspace
  files*): `/idea` and `/idea --extend` can run fully through MCP.
- **`docs/images/clike-overview.svg`**: CLike at a glance (lifecycle, release loop, who writes,
  governance, runtime, MCP, outputs), in the README.

### Fixed (MCP)

- **Run reports of other locations could be read through the orchestrator MCP**: `runs_read`,
  `eval_read_summary` and `gate_read_decision` accepted any `run_id` (`..` left the runs
  directory). A run id is now a run directory name only, CLike's `state/` is never a run, and with
  `project_root` + `req_id` the eval/gate tools read that project's latest report.
- **Claude Code reported "Dynamic Client Registration rejected (HTTP 401)"** when the
  `Authorization` header was missing: OAuth discovery and `/register` answered 401, so the client
  attempted OAuth. They answer 404 now (orchestrator and extension), and the docs show the
  `.mcp.json` with `${CLIKE_API_TOKEN}` and `localhost`.
- **Extension operational MCP**: streamable HTTP as clients expect (202 for notifications, 405 for
  GET, `ping`, negotiated protocol version); one phase at a time, locked before the run starts;
  every run gets a `run_id` (also `harper_kit_next`, `harper_continue_loop`, `await: false`), the
  registry is bounded, `cancel_run` stops a run; a run that stops early says why, and confirmations
  are answered with `confirm: true` instead of a modal nobody sees; `harper_run_phase` takes `text`,
  `methodology`, `agent` and `extend` / `release` / `dry_run` (`/idea --extend`);
  `harper_next_action` follows `dependsOn` and finishes an in-progress REQ first.
- CLike's own Claude Harper runs load no MCP server (`--strict-mcp-config`). The orchestrator MCP
  states that its `rag_reindex_*` tools write the RAG index.

### Fixed

- **`/eval --fix` could not remove a root conftest it was asked to remove.** The repair moved the
  REQ's fixtures into its package and deleted the KIT root `test/conftest.py` that
  `structure::shared-conftest` flagged, but CLike restored every deleted locked file: the same
  failures came back at every cycle. A test-support file that defines no test and that the eval
  itself named can now be removed (audited, out of the lock); a test file never.
- The eval reports saved by the extension keep each check's `duration_s`.

## [1.5.0] — 2026-10-18 — Release after release: /idea --extend, faster eval and gate, cloud context parity

### Added

- **`/idea --extend` — the next release of a delivered project.** One command runs the cascade
  IDEA → SPEC → PLAN in continuity with what exists. The release inputs live in versioned folders,
  `docs/inputs/vN/` (requirements) and `docs/reference/vN/` (background), plus any attached file (an
  attachment is required only when `docs/inputs/vN/` is empty); earlier
  releases are read as history, never as new requirements. IDEA, SPEC and TECH_CONSTRAINTS are
  merged, not regenerated (a document that drops a section of the earlier release is restored);
  the PLAN gets new REQs typed `ADDED`, `MODIFIED` (`amends`, `supersedes` the checks it replaces,
  `unchanged`) or `REMOVED` (`retires`), with `release` and `origin`, while delivered REQs stay
  read-only. CLike checks the baseline is delivered, tags it `harper/v<N-1>`, validates the delta
  and appends its own verification to the EXTEND report; `--dry-run` writes only the report. Then
  `/kit`, `/eval --fix`, `/gate` and `/finalize` as usual. BMAD works on it:
  `--methodology bmad --agent analyst|pm|architect|ux` (default `pm`), also on `/extend`.
- **The regression follows declared changes.** Checks a `MODIFIED` REQ supersedes are not run for
  the REQ it amends (reported as `superseded`, with the reason); a REQ retired by a `REMOVED` REQ
  leaves the regression set. Every other check of delivered REQs keeps running.

### Changed (cloud context = local agent context)

- **A cloud KIT now receives what a local agent reads**: the REQ's slice of PLAN.md, the code its
  dependencies delivered (dependency surface, chosen deterministically from the promotion reports,
  interfaces first, with their HOWTOs), the repository and promotion manifests, the locked tests of
  acceptance-first, the REQ and BMAD companion documents — before, the KIT message kept only their
  names. The KIT follow-ups get the REQ's slice of PLAN.md and plan.json instead of the whole files.
- **Dependency sources via RAG were mostly missed**: the prefix lookup scanned only the first 200
  points of the collection; it now scans the whole collection.
- **Cloud FINALIZE** receives IDEA, SPEC, TECH_CONSTRAINTS, a PLAN digest, a plan.json index and the
  solution surface (it used to get their names and 12 chunks of `src/`); **`/idea --extend`** sees the
  IDEA it merges into; **PLAN** gets IDEA; companion documents go with their content.
- The acceptance stage of an acceptance-first KIT reads the context sources and the dependency
  sources; a manual `/kit --repair` carries the latest failures and files; the local KIT and
  FINALIZE packages receive the attachments; cloud `/idea` accepts the project's context sources.
- The repair receives the head and the tail of a long check output (CLike's diagnosis is at the
  head, the runner's error at the end; only the tail was kept). Lane guides are indexed again after
  `/extend` and `/idea --extend`, and the KIT `root/` files are indexed with the candidate. The
  selected-capability guidance reaches the cloud KIT up to 20k chars (8k before).
- **A cloud run that cannot fit is refused with its size** (`cloud_context_too_large`,
  `CLIKE_CLOUD_MAX_PROMPT_CHARS`, `CLIKE_CLOUD_MAX_OUTPUT_CHARS`) instead of overflowing the model.

### Changed (speed, same verdicts)

- **The gate does not run the eval again when nothing changed.** A full `/eval` records its
  verdict with a digest of its inputs computed by the orchestrator (canonical code, root
  deliverables, the REQ's KIT, every LTC, `plan.json`, CLike version); `/gate` on the same inputs
  reuses a passing verdict and still checks acceptance integrity and required outputs. Any change
  runs it again.
- **The regression runs only what guards behaviour.** Lint, types, security scans, coverage,
  syntax and SBOM checks of promoted REQs (non-blocking there, passed at their own gate) are not
  run; tests, installs and builds are. On B2B this is about two thirds of the regression cases.
- **Installed `node_modules` are shared** across work copies by package.json + lockfile digest
  (hard links), instead of an npm install per REQ and per eval.
- **Each check reports its duration** (`duration_s`).

### Added (KIT)

- **A KIT can deliver repository-root files.** Run and setup scripts, deployment scripts,
  infrastructure and root manifests go under `runs/kit/<REQ>/root/<path>`; the gate promotes them
  to `<path>` with the same 3-way merge and report, the eval and the regression see them at the
  workspace root, and the regression names them when a promoted check fails on them. Allowed:
  `scripts/`, `deploy/`, `infra/`, `ops/`, `config(s)/`, `migrations/`, `db/`, `.env.example`, compose
  files, `Dockerfile`, `Makefile`, `Procfile`, plus `root_folders` / `root_files` in
  `.clike/project.json`; never `.git`, `.clike`, `runs`, `docs`, `src`, `test`, `ci` or private files.

### Fixed

- **A KIT that rewrote the shared root `conftest.py` passed the gate and then stopped the
  promotion on a conflict** (B2B REQ-015 replaced `test/conftest.py` and dropped 15 fixtures of the
  delivered REQs). The eval now checks it (`structure::shared-conftest::test`, blocking): a root
  conftest of a KIT keeps every fixture and helper of the canonical one; the REQ's own fixtures go in
  its package conftest. `/eval --fix` repairs it before the gate.
- **Cloud KITs could not deliver repository-root files**: the gateway accepted only
  `runs/kit/<REQ>/{src,test,docs,ci}` file blocks, so `root/` deliverables were dropped on the cloud
  path; cloud, Codex and Claude Code now share the same KIT roots.
- **A document phase run from a REQ branch hid the KIT.** `/spec` (and the other document
  phases) committed on the default branch and stayed there: the REQ's KIT disappeared from the
  working tree. CLike now switches back to the REQ branch and merges the documents into it.
- **`/spec --methodology bmad --agent ux` overwrote TECH_CONSTRAINTS.yaml** from the IDEA block,
  dropping the release additions of `/idea --extend`, and its prompt told the agent to regenerate
  SPEC.md without reading it. The UX role is companion-only: it reads the canonical SPEC and never
  writes SPEC or TECH_CONSTRAINTS; `/spec` no longer derives TECH_CONSTRAINTS once the project has
  releases. Its commit names the UX documents.
- After `/idea --extend`, the PLAN.md sections that index every REQ (REQ-IDs table, dependency
  graph, per-REQ test strategy and KIT readiness) did not list the new REQs when the agent put them
  only in the `## Release vN` section: CLike now adds them (table rebuilt from plan.json, pointers to
  the REQ's own subsections) and says so in its verification.
- The chat could not send any message (Enter or Send) after the previous fix: the webview copy of
  the command parser missed a constant; it is now included and tested by running that copy.
- A command pasted with a terminal border or a quote marker in front (`│ /idea --extend`) was sent
  as plain chat text to the agent; decoration before the `/` is now ignored.

### Changed

- Context sources: release folders (`docs/inputs/vN/`, `docs/reference/vN/`) split the current
  release from history (role `previous_release`); `docs/reference/**` is part of the default
  convention. `/extend` never changes TECH_CONSTRAINTS, and its cloud prompt now carries the
  request of the command (anchor, REQ id, text).

## [1.4.4] — 2026-10-18 — The solution running and configured on the developer's machine

### Changed

- **The README written by `/finalize` says it is a CLike project**: CLike, Harper and Finalize
  badges linked to the CLike repository, its Harper lifecycle and `FINALIZE_REPORT.md`, and a
  closing *Made with CLike* section with links to the Harper documents, the report and the
  solution evidence (cloud and local agents). A README without it fails the solution
  verification (`structure::readme-clike`) and the repair adds it.
- **`/finalize` brings the solution to running and configured, without running the tests
  again.** Every REQ passed its tests at its gate: the solution profile now installs, builds,
  configures and starts the solution and smoke-checks it while it runs (health, one real request
  per main capability, the main pages). The repair looks for configuration causes first
  (variables, URLs, ports, services, migrations), then tools, wiring and code. `/finalize` writes
  `docs/harper/FINALIZE_REPORT.md` for the developer — how to start and see the solution, every
  variable, the information only the developer can give, every change and why, the problems met
  and how they were solved — and `scripts/setup_local` / `start_solution_local`; after a passing
  verification CLike offers to configure and start it on the developer's machine.
  `docs/harper/SOLUTION_EVAL.md` also lists the verification cycles and the last gate of every
  REQ.

### Fixed

- **The solution started by `/finalize` could not start on the developer's machine when a host
  port was taken** (the CLike gateway listens on 8000): the setup script now picks a free port
  and updates the values derived from it, the start script names the busy port and its variable,
  and the report lists the ports.
- **The chat stayed busy after a passing `/finalize`** until the developer answered the offer to
  configure and start the solution locally; the offer no longer holds the chat.
- **`/finalize` committed only part of the solution it verified.** Files in a new directory were
  missed (`git status` listed only the directory), and the work of an earlier `/finalize` run that
  ended before its commit was taken for the developer's own changes. The developer's changes are
  now recorded once per round (`runs/finalize/DIRTY_BEFORE.json`, by content) and the record is
  dropped only after a finalize commit succeeds; the developer report accumulates the changes and
  problems of every run.
- **A local-agent `/finalize` was rejected for writing the solution.** The extension checked its
  files with the KIT rule (no `src/`, no `docs/harper/`): `/finalize` writes exactly there. It is
  now checked against the write roots and forbidden paths of its own package (never `test/`,
  `runs/`, `.git`, `.env` or caches). The finalize run scripts detect `docker compose`,
  `podman compose` or `podman-compose`, and offer the native run when no container runtime is
  installed.
- **A solution's services started before it was installed.** The eval starts the services before
  the checks, so an install written as a check came too late (the frontend could not find its
  framework). Eval profiles get a `setup` step that runs before the variables and the services;
  the `/finalize` profile installs and builds there.
- **A REQ promoted by its gate was not merged into `main`, without a word.** A CLike agent file
  of the REQ (`runs/kit/<REQ>/docs/AGENT_*`, rewritten at every eval) was modified and blocked
  the switch; it is now committed with the phase, and a failed merge-on-gate shows the cause and
  the commands. `/finalize` warns when REQ branches are not merged into the default branch it
  commits on. Git status paths no longer lose their first character in the log.
- **`/finalize` left its verification uncommitted.** `ci/SOLUTION_LTC.json`, the smoke scripts,
  the evidence and the report are committed when the verification ends; compose files are
  finalize outputs too. Changes the developer had in the working tree before `/finalize`, and that
  it did not touch, stay out of its commits. `/finalize` lists the REQs not promoted yet and asks
  before it runs; a repair cycle that cannot run says so.
- **Promotion repeated code at every gate.** Where both sides only added lines, auto-merge kept
  both even when `src/` already had the candidate's additions (an earlier REQ promoted them, or
  the same REQ was gated again, against a KIT base older than `src/`): composition files such as
  `app.py`, `conftest.py`, CSS tokens and `.env.example` grew a copy per promotion, up to code
  that no longer compiled — unseen by the gates, which run the KIT copy. Now the side that
  contains the other wins, overlapping additions are a conflict, a merge that would repeat lines
  both sides added is a conflict, and merged Python/JSON/JS files are checked before they are
  written. Promoting the same REQ twice changes nothing.
- **A resolved promotion conflict came back at every gate.** After the developer writes the
  right content into `src/` and deletes the `.conflict-…` file, the next gate keeps `src/` for that
  file (while the KIT file is the one that conflicted). KIT rules: a shared file several REQs
  extend keeps what the others put there, and REQ-specific test fixtures go in the REQ's own
  test package, not in the root conftest.
- **A REQ that broke an earlier REQ through a shared file had to guess why.** When a promoted
  REQ's check fails in the regression, the eval now names the files of that REQ the candidate
  replaced, with a short diff, and the repair notes list them (any language: test runner configs
  whose selectors no longer find the earlier tests, compose files and manifests, changed
  components). KIT rules: test runner configs, infrastructure and build manifests are shared
  files that keep the earlier entries; checks assert what their REQ adds, never an exact set.
- **A REQ with promotion conflicts was merged into `main`.** Merge-on-gate now runs only for a
  promoted REQ; otherwise CLike says it stays on its branch until the conflicts are resolved.

## [1.4.3] — 2026-10-17 — A sandbox that stays healthy, tools when an eval needs them

### Added

- **Eval tools stay current, on purpose.** `/tools update` and `./rebuild.sh --update-tools`
  rebuild every installed tool at its latest version (the image's PostgreSQL client too) and show
  `old → new`; a failed rebuild keeps the previous version. Versions are otherwise locked: each
  tool records an exact lock (micromamba explicit spec, `pip freeze`, archive digest), the
  orchestrator keeps a copy and the rebuild restores a new volume identically. `/tools` and the
  rebuild remind you after 30 days. Eval and gate reports record the tool versions they ran with.
- **One environment per tool**, so two tools never change each other's versions (`jdk@17` and
  `maven`), and two new kinds of catalog entry: `pip` for CLIs published on PyPI (`azure-cli`,
  whose conda-forge package does not resolve) and `download` for vendor archives, https only,
  verified by sha256 before they are unpacked. All catalog entries checked on conda-forge for
  linux-64 and linux-aarch64.

- **Native tools in the eval sandbox, installed when an eval needs them.** A catalog of clients
  and toolchains (databases, messaging, AWS/Azure/GCP CLIs, Kubernetes/IaC, quality scanners, JDK,
  Maven/Gradle, .NET, Go, Rust — conda-forge, both architectures). Before an eval CLike finds
  what the REQ declares (`environment.tools`) or runs and the sandbox lacks, asks the developer
  (`clike.evalTools.install`: ask | always | never) and installs it into a volume the sandbox
  mounts read-only; a check that stops on a missing program is installed for and run again, never
  repaired. `.clike/eval-tools.yaml` approves tools for a project and adds its own conda-forge
  packages. `/tools` lists, searches, adds and removes.

### Improved

- **Eval disk under control.** One npm cache per project instead of one per eval directory (40
  copies, 7.6 GB on a real project), and stale eval directories are pruned before an eval (the
  3 REQs used last kept; least recently used removed when the volume runs low; no eval below 2 GB).

### Fixed

- **A flaky test of a promoted REQ blocked the gate of another REQ.** A blocking regression test
  that fails is run once more; passing then, it is a nondeterministic warning naming its REQ, not
  a regression, and is not sent to the candidate's repair.
- **A cache a local agent wrote inside the KIT broke the eval.** The KIT copy now skips scratch and
  caches (`.tmp`, `.cache`, `.npm-cache`, `.next`, `local-eval-workspaces`) like the overlay copy,
  skips files removed during the copy, retries the preparation once, and a workspace CLike cannot
  compose is environment-blocked: `--fix` stops instead of "repairing" it. KIT and repair rules ask
  agents to keep their caches outside `runs/kit/<REQ>/`.
- **`/eval --fix` repeated the same errors when a locked test was wrong for the type checker.** A
  mypy/pyright error reported on a test file (`test_a.py:286: error: … [arg-type]`) now counts as
  evidence that the test is wrong, like a TypeScript error: the fix, with every assertion
  unchanged, is accepted for review instead of being reverted at every cycle.
- **A local agent's rejected test change was committed.** The phase commit ran before the
  governance restored the file: `HEAD` held the rejected change, the working tree the locked test.
  The governance now runs before the commit.
- **Backup/restore checks failed for a missing `pg_dump`.** The eval sandbox image has the
  PostgreSQL client tools (`psql`, `pg_dump`, `pg_restore`, major 18 from PGDG).
- **A blocking check that needs Docker could never pass.** The sandbox has no container runtime:
  such a failure is recognised (`docker: not found`, `Docker Compose … required`, daemon not
  reachable), the repair is told to make the check non-blocking and the governance accepts that one
  change; non-blocking, it is a warning. The KIT rules list what the sandbox has and lacks.
- **Acceptance governance ignored LTC files written with `commands`.** Checks are read in every
  shape the runner accepts, so removing or relaxing a check is detected there too.

- **`/gate --fix` repaired correct code for a broken sandbox.** The eval sandbox ran with uvicorn
  as PID 1, which never reaps the processes the checks orphan (servers, browsers, esbuild): their
  zombies filled `pids_limit` within a day of evals, and every check then failed with
  `spawn EAGAIN`, `pthread_create: Resource temporarily unavailable`, a closing browser or a web
  server that "exited early". Those failures were treated as code defects and sent to the repair,
  with the note "the failure most likely comes from that change". Now:
  - the sandbox runs with an init (`init: true`) and what a check or a service leaves in its
    process group is stopped when it ends;
  - the OS refusing a process, thread, memory or disk is environment-blocked, the report says
    `EVAL_SANDBOX_EXHAUSTED` / `GATE_BLOCKED_SANDBOX_EXHAUSTED` and `--fix` (eval, gate, finalize
    verification) stops with how to recover; a local agent's `eval-check` answers `BLOCKED`;
  - an eval does not start in a sandbox already at 60% of its process limit;
  - environment-blocked failures get no "passed in earlier runs" note;
  - the sandbox `/health` shows processes in use, zombies and PID 1.

## [1.4.2] — 2026-10-15 — Conflicts you can read, plans that stay intact

### Added

- **`conflicts.md` in the promotion report**: every spot still in conflict, readable without
  conflict markers: what `src/` has now, what the REQ wants, the diff between the two, the base,
  and what to do. The report and the chat point to it.

### Improved

- **Fewer promotion conflicts**: a spot where the candidate holds the whole canonical side plus
  its own additions (a later KIT rewrote a line an earlier REQ had already promoted) now merges,
  keeping the candidate: nothing of `src/` is lost and it is what the gate tested. A file with
  both kinds of spot is merged where it can be; its `.conflict-…` file holds only the rest.
- **The "nondeterministic failure" diagnosis needs the same code**: each eval/gate report stores
  `inputs_fingerprint` (canonical roots + KIT); a check is called nondeterministic only when it
  passed earlier on the same code. Otherwise the repair is told the failure most likely comes from
  what changed since.

### Fixed

- **Eval and regression ran on stale code of promoted REQs.** The eval workspace overlaid the KIT
  of every dependency, and the regression of a promoted REQ its own KIT, over the canonical tree:
  a file a later promoted REQ had changed came back in its old version (a candidate using it
  failed, a regression ran on code that does not exist). A REQ that is done with a successful
  auto-merge promotion is now taken from the canonical tree only; REQs without a promotion record
  are composed as before.
- **`/extend` could change existing REQs**: the append-only rule was only in the prompt. The
  extension now checks the returned plan.json: changed or removed existing REQs are restored,
  broken ids/sequence/anchor/dependencies reject the result (a local agent's plan is put back).
- **`/init --force` overwrote an existing project** (README, docs, every template file) and
  replaced `.gitignore`. `--force` now only allows a non-empty folder: missing template files are
  added, existing ones kept, `.gitignore` gets the CLike rules it lacks.
- **Context sources skipped source code** (`.py`, `.java`, `.go`, … were "unsupported format").
  They are read now, with the new role `existing_code`.
- **A `.conflict-…` file left in `src/` failed the gate**: the eval workspace copied CLike's
  promotion leftovers (`.conflict-…`, `.incoming-…`, `.bak-…`) and a format check read them
  (`trailing whitespace`). They are never copied now.

## [1.4.1] — 2026-10-13 — The gate repairs what it finds

### Added

- **`/gate REQ --fix ["hint"]`: the gate repairs what it finds.** A gate re-runs every check and
  the regression, so it can fail where the eval passed. With `--fix` a failing gate gets the same
  KIT repair as `/eval --fix` (tests locked, governed test/ci changes, same cycle limits and stop
  rules), then a full gate again: only a gate run on the repaired candidate promotes it. Missing
  required outputs reach the repair as failures; a tampered acceptance surface and promotion
  conflicts are not repaired.
- **Intermittent failures are diagnosed without a hint.** Before a repair (`/eval --fix`,
  `/gate --fix`) CLike reads the earlier eval/gate reports of the REQ; a failing check (or test)
  that passed before reaches the repair flagged as nondeterministic: make the code deterministic,
  do not change the asserted value. Found on a test whose count depended on jobs ordered by random
  UUIDs: it passed in 3 of 5 runs.
- **What each repair received is written next to the report**:
  `runs/<eval|gate>/<REQ>/repair_<REQ>_<ts>.md` (the developer hint, if any, CLike's diagnosis,
  the failing checks).

### Improved

- **`/eval --fix` repairs from all the errors, in both modes.** Measured on a Next.js REQ, three
  defects hid the errors from the model:
  - the cloud repair prompt filled its 160k-character file budget alphabetically with CLike's own
    context files, so **no `src/` or `test/` file** reached the model; the files named in the
    errors now come first, then tests, sources, CI and docs, and CLike context files and lockfiles
    are listed, not shown;
  - a failed check carried only the **tail** of its output, with ANSI codes and DOM dumps (the
    first failing test was lost), and the local-agent prompt cut it to 1500 characters on one line;
    the eval runner now extracts the error blocks of the whole output (`excerpt`, `fingerprint` in
    the report) and both prompts get them whole;
  - a test that ran and failed (`element(s) not found`, a missing module of the candidate) was
    classified **environment-blocked**, i.e. "the sandbox, do not change code".
  Checks with the same errors are listed once, non-blocking regression warnings of other REQs are
  left out, the repair rules ask to group the failures by root cause and fix them all, and "no
  progress" now means the same errors, not only the same check names.
- **The local agent re-runs the failed checks in the real eval sandbox while it repairs**
  (`node .clike/bin/eval-check.mjs <check>…`, served by the extension; `clike.autoEval.agentEvalChecks`,
  default 8 runs): it iterates until they pass in one session instead of one attempt per cycle. The
  agent gets neither the orchestrator token nor network access; a partial run (`/v1/eval/run`
  `checks`) is never a verdict.

- **`/finalize` verifies that the integrated solution runs end to end, and repairs it** (no flag;
  `clike.finalize.verify`, `clike.finalize.verifyMaxCycles`). `/finalize` writes
  `ci/SOLUTION_LTC.json`, the eval profile of the whole solution (install, the promoted test
  suites on the canonical tree, build, the solution started as services, e2e), derived from the
  REQs' eval profiles it now receives; CLike runs it in the sandbox against the canonical tree
  (without `runs/`, `.git`, `.clike/`) and, while it fails, runs `/finalize` again with its errors.
  A local agent checks the profile in the sandbox while it works and runs the local scripts on the
  developer's machine. On-prem: the local run is the target; cloud: guarded, non-mutating deploy
  checks. Evidence in `docs/harper/SOLUTION_EVAL.md`.
- The eval-check helper resumes the same run when an agent's command timeout stops it (Claude
  Code stops shell commands after 2 minutes by default); Claude Code gets `--allowedTools` for it.

### Fixed

- **Extension dev dependencies: 0 known vulnerabilities.** `@vscode/vsce` 3.9.2 → 4.0.0 (packaging
  tool only, not in the VSIX): its `secretlint → globby → fast-glob → micromatch → braces` chain had a
  high-severity DoS (`braces`, no patched version). Requires Node ≥ 22 to build the VSIX.
- **Merge-on-gate left `main` unpushed when the remote `main` had moved** (e.g. a PR merged on
  GitHub): the push was rejected as non-fast-forward and only logged, so the REQ branch reached
  the remote and `main` did not. CLike now fetches and merges `origin/main` before merging the
  REQ, then pushes; a conflict or a failed push is shown as a warning with the command to run.

- **Git: the KIT of an `/eval --fix` repair (and every eval report) was staged but never committed.**
  The phase files included paths the project ignores (`runs/eval/…`, `runs/kit/<REQ>/reports`,
  `ci/reports`): one ignored path makes `git add` fail, and the phase commit was skipped. Ignored
  paths are now left out (logged) and the rest of the phase is committed.
- **`/gate` auto-merge: a new file under a Next.js dynamic route (`app/runs/[run_id]/page.tsx`) was
  a false conflict** ("removed from the canonical root after the KIT", no marker file): for a path
  with `[ ]` that is not in the base commit `git show rev:path` exits 0 with no output, so the base
  looked like an empty file. The base is read with `git cat-file blob`, which fails on a missing path.
- **`/eval --fix`: the eval pre-pass undid a verified repair, and every cycle took ~15 minutes.**
  On a Next.js REQ the local-agent pre-pass of the eval after a repair rewrote the fix the repair
  had just verified in the sandbox (unit tests 37/37 → the same failures again). The eval after a
  repair now runs without the pre-pass, and the regression of the promoted REQs runs only once the
  REQ's own blocking checks pass (~4 of ~6 minutes saved per failing cycle). A local agent's run
  timeout is extended by the eval checks it may wait for.

- **A local-agent KIT failed with `LOCAL_AGENT_REQUIRED_OUTPUTS_MISSING` although it wrote `src/`
  and `test/`.** The artifacts sent to the orchestrator are capped (500 files, 8 MB) and were kept
  in discovery order: an agent's scratch in `ci/.tmp` (27 MB of tool installs) filled the budget
  and the code and tests were dropped. Scratch (`.tmp`, `.npm-cache`, `.npm`,
  `local-eval-workspaces`) is never sent, and within the budget `src/` and `test/` come first, then
  the CI profile and the docs; dropped files are logged.

- **`/kit` failed with `CLIKE_SELECTED_CAPABILITIES_MISSING` on a REQ run again.** The selected
  capability context was read from the first blob named like it: a copy left in the REQ's KIT by an
  earlier run, sent back truncated, was not valid JSON and the context the orchestrator had just
  built was ignored. This run's context now comes first, then the REQ's copy, and unreadable copies
  are skipped (context envelope and cloud prompt).

- **`/init`: the project CI workflow failed on every project** (it installed a root
  `requirements.txt` and ran a CLike-internal module). It now runs repository checks that fit any
  Harper project: `plan.json` valid, no `.env`/local state committed, no promotion leftovers or
  conflict markers in `src/`/`test/`. The generated `.gitignore` also ignores eval reports
  (`runs/**/ci/reports/`, `runs/**/reports/`), which, tracked, kept the tree dirty and blocked the
  switch to the next REQ branch.

- **Eval: `CLIKE_EVAL_TEMP_ROOT` is exported to the checks.** The KIT prompts tell CI scripts
  that CLike provides it, but it was only in the internal path map: scripts that require it
  failed (`build`, `e2e`, `integration` of a Next.js KIT).
- **Regressions no longer receive the candidate's installed dependencies.** The candidate's
  source overlaid into the workspaces of promoted REQs included `node_modules` (and `.next`,
  `.venv`, caches): another REQ's tests loaded the wrong Vitest ("cannot be imported in a CommonJS
  module") and its secret scans flagged files inside `node_modules`. Overlays skip installed and
  generated directories.
- Context files CLike writes for the local agent end with a newline (KIT format checks).
- `ci/FILE_REQUIREMENTS.json`, `ci/TARGET_CONTRACT.json` and `ci/REQ_PROMOTION_MANIFEST.md` are
  written by CLike from the plan at every package: they are not part of the acceptance lock (a
  rewrite reported `ACCEPTANCE_TAMPERED`).

## [1.4.0] — 2026-10-11 — Autonomous eval and gate

### Added

- **Test infrastructure for the eval sandbox** (`docker/eval.env`, git-ignored, template
  `docker/eval.env.example`): variables the projects' tests need, such as a real PostgreSQL test
  database URL, reach the sandbox only. Credential-like names are still refused.
- **Eval environment provisioning** (`orchestrator/eval_environment.py`): CLike creates what the
  checks declare in `ci/LTC.json` instead of asking the developer: `environment.required_variables`
  with `provision` `token` / `uuid` / `timestamp` / `template` (generated per run),
  `postgres_database` (a disposable database per REQ, recreated every run, on the server of
  `CLIKE_EVAL_POSTGRES_URL` in `docker/eval.env`), `service` or `external`; and
  `services: [{name, req, cwd, setup, start, env, port_env, ready, exports}]`, started before the
  checks from the composed source and dependencies of another REQ (e.g. the API of REQ-001 for the
  integration tests of REQ-002) or of the candidate, on a free loopback port, and stopped after.
  Values set in `docker/eval.env` win. KIT prompts (cloud and local agent) and `ci/HOWTO.md`
  follow the contract.
- **`/eval --fix` repairs a missing environment** when a repair can declare it (`BLOCKED` with
  `environment_repairable`): the repair completes the LTC `environment` / `services` (an audited,
  non-weakening amendment). Only values marked `external` or the database server stop it without
  spending tokens.
- **Locked JS/TS tests can be fixed when the eval shows the test itself is wrong** (a TypeScript
  error reported on the test file, a TypeError/ReferenceError raised in it, an unresolvable
  import), with every test title and assertion unchanged and no skip/only/todo added; flagged
  `review_required` at the gate. Until now only Python tests had this, so a correct repair of a
  TS fixture was reverted and `--fix` kept failing on it. The eval pre-pass now receives the
  previous failures as evidence too.
- **`/gate` promotes by auto-merge, without prompts** (`clike.gate.autoPromote`, default `merge`):
  a 3-way merge per file of `runs/kit/<REQ>/{src,test,tests}` into the canonical roots (base =
  the canonical state before the KIT), conflicting files never written (a `.conflict-<REQ>-<ts>`
  file holds the markers and the REQ stays in progress), installed/generated content never
  promoted, and a report with per-file outcome and unified diff in
  `runs/kit/<REQ>/promotion/<ts>/` (`report.md`, `report.json`, `promotion.diff`), opened at the
  end and summarized in the chat. `/gate --ask` / `--no-promote` override it for one run.
- **Auto-merge base = what the KIT started from**: per file, the last direct dependency KIT
  (`plan.json` `dependsOn`, the same composition the eval uses) that has it, else the canonical
  file at the KIT commit, else at the last commit before the KIT was generated (KIT never
  committed). Lines added at the same place by both sides (e.g. new `.env.example` entries) are
  kept both; changes to the same existing lines stay a conflict. Conflict files show the base
  (`|||||||`).
- **Git: a new REQ branch no longer fails on an unmerged previous REQ.** With merge-on-gate off,
  `feature/req-<n+1>` was created from `main`; local changes (plan, reports) made the switch fail
  and every phase of the REQ stayed uncommitted, silently. The new branch is stacked on the
  current branch when it is not merged into the default branch (it carries the code it depends
  on; creating it never conflicts with local changes), and Git failures are shown as warnings.
- **`/eval --fix` keeps going while it improves**: after `clike.autoEval.maxCycles`, up to
  `clike.autoEval.extraCyclesOnProgress` (default 3) more cycles as long as each one leaves fewer
  failing checks.
- **RAG indexing is batched and incremental.** The orchestrator embedded one chunk per gateway
  call (a project re-index took 5 minutes inside every `--fix` cycle); it now sends batches
  (`RAG_EMBED_BATCH_SIZE`, default 64, `RAG_EMBED_CONCURRENCY` 4) and skips files whose content
  is already indexed (point ids derive from path + content). The gateway `/v1/embeddings` accepts
  a list input and returns one vector per item in one provider call (it joined the items before).
- **`/eval` checks the required variables first.** The KIT declares them in `ci/LTC.json`
  (`environment.required_variables: [{name, purpose, example}]`; the free-form
  `environment: {NAME: "Required ..."}` of earlier KITs is understood too). When one is missing
  from the sandbox, the eval reports `BLOCKED` (`reason_code: EVAL_ENVIRONMENT_MISSING`) with the
  variable names and the `docker/eval.env` line to add, runs no check, and `/eval --fix` stops
  without a repair (no tokens spent on code that is not at fault).
- KIT (cloud and local agent): `ci/HOWTO.md` gets a mandatory `## Run with CLike /eval` section
  (required variables, `docker/eval.env` lines, one-time setup, rebuild, `/eval` and `--fix`).

### Fixed

- **`/eval` failed with `ACCEPTANCE_TAMPERED` from the second run on.** The acceptance lock hashed
  the files the eval itself writes (`ci/reports/**`: test/coverage/bandit reports, built wheels),
  so every later run found them "modified". Eval outputs (`reports/`, coverage files, `dist/`,
  `build/`, caches, `*.whl`, `*.pyc`, `*.log`) are no longer part of the acceptance surface, and
  locks written by earlier versions ignore their entries for those paths, without re-locking.
- **`/eval` with a local agent failed with `ACCEPTANCE_TAMPERED` after its own pre-pass.** The
  eval pre-pass agent repairs the candidate and could edit locked files under `test/` and `ci/`
  (e.g. add a test, rewrite a CI record) with no governance, so the canonical eval that follows
  found the surface changed. The acceptance surface is now locked before the pre-pass and the
  pre-pass changes go through the same audited amendment as the `--fix` repair: accepted ones are
  recorded, the others are restored. The eval agent is told that `test/` and `ci/` are locked and
  that evidence goes under `reports/`.
- **Telemetry: prompt-cache tokens priced** (cloud and local-agent runs). OpenAI cached input was
  charged at the full input price and Anthropic cache reads/writes were not charged at all; costs
  now use the list prices of `configs/models.yaml` (`cached_input_per_1k`, and for Anthropic
  `cache_write_per_1k` / `cache_write_1h_per_1k`, added from the Anthropic price page), rows
  recorded before are recomputed when shown, and the portal shows the cached tokens.
- Files CLike writes as JSON (promotion manifest, contexts, state) end with a newline: a KIT
  format check failed on the promotion manifest of a promoted REQ.
- **Telemetry portal: cost always 0 for Codex runs.** Codex reports tokens but no cost, so its
  rows had an empty `pricing`. The portal now estimates the API-equivalent cost from
  `configs/models.yaml` (new optional `cached_input_per_1k`; set for `gpt-6.1-sol`), also for the
  rows already recorded, marked `pricing.estimated`.
- **Eval sandbox OOM-killed on large JavaScript installs** (`503 eval sandbox unavailable`, then
  `npm install` exit 137 and every check `ENOENT`). Its work dirs (venvs, `node_modules`, npm
  cache) lived on the tmpfs `/tmp`, which counts against the container memory limit. They now live
  on the `eval_work` disk volume (`CLIKE_EVAL_BASE_DIR=/var/clike-eval`); `/tmp` is 1 GB. The image
  ships Node.js 22 LTS instead of 20 (current Next/Vitest/ESLint need it) with npm 11 (the
  bundled npm 10 crashed resolving some peer sets: `reading 'edgesOut'`); Playwright browsers and
  other tool caches (`XDG_CACHE_HOME`, `PLAYWRIGHT_BROWSERS_PATH`) are on the volume as well.
- `configs/models.yaml`: prices re-checked against the OpenAI and Anthropic price pages
  (2026-10-11); `gpt-5.4` input corrected to $2.50/M; `cached_input_per_1k` added where listed.
- **Git automation silently off when enabled in the project.** `clike.git.autoCommit` (like every
  machine-scoped setting: binaries, agent permissions, service URLs, push) is read by VS Code only
  from User settings, so a value in `.vscode/settings.json` was ignored without a word. CLike now
  warns at startup and on change, with **Apply in User settings**.
- `/init` wrote `.gitignore` with indented lines, so only `node_modules/` was ignored: chat
  sessions, telemetry, `.vscode/` and `.env` files could be committed. Lines are no longer
  indented, and `.clike/sessions/`, `.clike/telemetry/`, `.env.*` (except `.env.example`) and the
  eval scratch under `runs/` (`runs/eval/`, `node_modules/`, `.tmp/`, caches) are ignored;
  `runs/kit/<REQ>/` stays committable by the phase commits.
- **False `ACCEPTANCE_TAMPERED` ("removed: ci/LTC.json…") when a repair left scratch in `ci/`.**
  The acceptance manifest is capped at 2000 files and a repair agent's `ci/.tmp` (5,700 tool files)
  filled it, so the real files fell outside and were reported removed. Scratch and cache dirs
  (`.tmp`, `tmp`, `.cache`, `.npm-cache`, `.next`, `coverage`, `local-eval-workspaces`) are not
  acceptance, and a locked file is reported removed only if it is really gone.
- **A gate PASS with accepted warnings did not promote.** `GATE_PASS_WITH_WARNINGS` (gate `PASS`,
  warnings allowed by `clike.gate.strictWarnings` off) left the REQ `in_progress` without the
  promotion prompt; it is now promotable like a clean PASS.
- **A promoted REQ's check that reaches another REQ by a relative path failed as a regression**
  (`../../../../runs/kit/REQ-001/test` from its work copy: found in its own eval, not when re-run
  inside a later REQ's eval, so the later REQ could never pass). Next to every eval dir, nested
  regression and service runs included, `runs/kit/` now lists this REQ (work copy), its
  dependencies (composed copies) and every other REQ (project KIT, read-only); before only the
  current REQ was linked, and others resolved by chance.
- **Eval path rewriting corrupted paths containing `src`/`test`** (e.g. a project under
  `…/test-projects/` or a temp dir `pytest-of-…`): short keys were replaced as substrings, several
  times. The rewrite is now one pass over whole path segments.
- `ci/HOWTO.md` (and any Markdown under `test/` or `ci/`) is documentation, no longer part of the
  acceptance lock: editing it by hand no longer reports `ACCEPTANCE_TAMPERED`.
- `/init`: `README_1st.md` showed `${project.org}` and escaped backticks; the Git steps now create
  the GitHub repository first (`gh repo create … --source . --remote origin --push`), since pushing
  to a repository that does not exist fails with "Repository not found".

## [1.3.0] — 2026-10-11 — Project context sources

### Added

- **Project context sources** (`.clike/context.yaml`, created by `/init`; see
  [docs/context-sources.md](docs/context-sources.md)): the project files the Harper phases read as
  context, each with a path glob, a role (`requirements`, `ui_reference`, `ux_requirements`,
  `api_reference`, `data_sample`, `style_guide`, `domain_glossary`, `example_output`, `reference`)
  and the phases that read it. Resolved server-side, read-only, and delivered to both runners: the
  cloud phase message gets a `PROJECT CONTEXT SOURCES` block, the local agent the list of files to
  read (converted documents written to `runs/context/<phase>/`). docx, xlsx/xls/xlsb, pptx and pdf
  are converted to text; HTML, CSS, SVG and other text files are passed as they are; images are
  opened by the local agents and listed by name for cloud models. Without the file: `docs/inputs/**`
  → `requirements` (idea, spec, plan), `docs/harper/ux/**` → `ui_reference` (spec, plan, kit).
  Canonical Harper documents win; size caps per file and per phase; unsafe paths ignored.
- `/init` creates `docs/inputs/`, `docs/harper/ux/` and `docs/reference/`.

### Changed

- The office/PDF text extraction of RAG indexing moved to `services/document_text.py`, shared with
  the context sources.

## [1.2.4] — 2026-10-11 — Invalid agent model rejected up front, agent errors shown

### Added

- **Invalid agent model rejected before the agent starts**: `clike.localAgent.codex.model` is checked
  against the models of the Codex login (`~/.codex/models_cache.json`), `clike.claudeCode.model`
  against the Claude aliases (`opus`, `sonnet`, `haiku`) and `claude-*` ids. An invalid id blocks
  every Harper phase and agent chat turn with `LOCAL_AGENT_MODEL_INVALID` and the closest valid id
  (`gpt6-1-sol` → `gpt-6.1-sol`) until it is fixed; VS Code shows the error at start-up and when the
  setting changes (with "Use …" and "Open Settings"), and `/agent-model` refuses an invalid id.
  Without the Codex models cache the Codex id is not checked.

### Changed

- **Faster, always-current container rebuild**: `docker/rebuild.sh` builds with the layer cache,
  recreates the containers, waits for `(healthy)`, checks that each container runs the image just
  built and prunes dangling layers. The orchestrator and the eval sandbox share one image (built
  once instead of twice); the uv download cache is a build cache mount and no longer stored in the
  image layers.

### Fixed

- **A failed agent run showed no cause**: with machine-readable output the agent writes its error on
  stdout (Codex `turn.failed`, Claude `is_error`), not on stderr; `LOCAL_AGENT_EXITED_WITH_ERROR` now
  carries that message (for example the provider's 404 for an unknown model).

## [1.2.3] — 2026-10-10 — Codex Harper phases in a project without git

### Fixed

- **Codex Harper phases in a project that is not a git repository** (a new `harper-init` project):
  Codex exited 1 ("Not inside a trusted directory and --skip-git-repo-check was not specified").
  The local-agent Harper phases now pass `--skip-git-repo-check`, as the agent chat already did.
- **A failed local-agent run reported a misleading error**: when the agent wrote nothing, the
  extension sent the files already on disk (the empty template `IDEA.md`) and the orchestrator
  answered `document_phase_output_incomplete`. The document and EXTEND phases now send only the
  files written during the run, and an agent that exits with an error and writes nothing reports
  `LOCAL_AGENT_EXITED_WITH_ERROR` with its own stderr.

## [1.2.2] — 2026-10-10 — Local document phases with Codex and BMAD companions

### Fixed

- **Codex in the local IDEA / SPEC / PLAN / EXTEND phases**: with `clike.localAgent.codex.sandboxMode`
  = `auto` (the default) these phases started Codex `--sandbox read-only`, so the agent could not
  write `IDEA.md`, `SPEC.md`, `PLAN.md`/`plan.json` or the EXTEND report and the phase failed with
  missing outputs. Every Harper local-agent phase now runs `workspace-write`; an explicit
  `read-only` is rejected up front with `LOCAL_AGENT_WRITE_MODE_UNAVAILABLE`.
- **BMAD companions in the local document phases**: the companion documents of the BMAD agent
  (`docs/harper/bmad/idea|spec|plan|architecture/**`, `docs/harper/ux/**`) are now collected by the
  extension, accepted by the write policy and by the orchestrator (paths re-derived server-side from
  the bundled BMAD manifest, Markdown only, never outside the agent's roots), and listed in the
  package write roots. Missing companions are reported as a warning.
- **BMAD `spec --agent ux` is companion-only locally too**: it no longer requires `SPEC.md`, and
  writing `SPEC.md` is rejected.
- **BMAD artifact policy lost with the workspace vendor manifest**: when the workspace carried
  `.clike/skills/vendor/bmad/manifest.json` (every `harper-init` project), it replaced the bundled
  manifest entirely and dropped its `artifact_policy`, agent profiles, workflows and quality
  contracts. The vendor manifest now overrides only the keys it defines, so the active output
  contract declares the companions again — locally and in the cloud prompt, where they are
  required outputs as documented in `docs/integrations/bmad/COMMANDS.md` (BMAD cloud prompts grow
  by 3–10 KB).
- **BMAD `finalize` in the cloud always failed**: the gateway BMAD artifact filter dropped the native
  finalize documents (`HOWTO_RUN.md`, `RELEASE_NOTES.md`, `SANITY_CHECKS.md`, `TODO_NEXT.md`,
  `PR_BODY.md`) that the active output contract then required. The native required outputs of the
  phase now stay allowed (except for companion-only agents).
- **Local BMAD prompts name the outputs of the role**: canonical outputs, mandatory companions,
  allowed companion roots and forbidden outputs of the selected agent (the workflow list mixed
  `pm` and `ux` files).

## [1.2.1] — 2026-10-06 — Agent chat approvals, Harper chat can write, readable /help

### Added

- **Approvals in the agent chat** (Coding and Harper, `clike.agentChat.approvals`, default `ask`): every
  edit and command of the agent waits for Allow / Allow all this turn / Deny in VS Code; writes
  outside the Coding output root are denied without asking. Claude Code asks through
  `--permission-prompt-tool` (a one-turn local MCP server), Codex runs through `codex app-server`
  (the same sessions as `codex exec`). `auto` keeps the previous behaviour.

### Changed

- **Harper free text with an agent can create files**: a request like "create a script that
  computes N!" in Harper mode no longer gets a read-only refusal; the agent writes only under
  `generated/<id>/` (same sandbox and approvals as Coding) and the files appear in the Files tab.
  Free (Q&A) stays read-only.
- **`/help` is readable on every theme**: VS Code theme colours, commands grouped by topic, a
  filter box, Esc / click outside to close.

### Fixed

- MCP `eval_run` with `fix` returned the report of the first eval: it now returns the report of
  the last eval after the repairs, plus `auto_eval {outcome, cycles, reason}`.
- `gpt-6.1-sol` pricing ($2.00 / $10.00 per 1M input / output tokens), 1,050,000-token context
  window and 128,000 max output tokens (B16).
- MCP setup uses `localhost` URLs (managed Claude Code policies often allow only
  `http://localhost*`); Codex approval of the CLike MCP tools is documented
  (`default_tools_approval_mode = "approve"`).

## [1.2.0] — 2026-10-06 — Native agent chat, CLike from Claude Code / Codex, contract alignment

### Added

- **Native agent chat** (H1): with execution = agent, the CLike chat talks to Claude Code / Codex as
  one continuing session per mode (free, coding, harper) — the first message starts it, the next
  ones resume it (Claude `--session-id`/`--resume`, Codex `exec resume`) and only the new turn is
  sent; the agent's text and the tools it uses stream into a live bubble; Cancel stops the agent.
  `/agent-session [new|new all]` shows or restarts the sessions. Codex chat now runs with the
  mode's sandbox (read-only, workspace-write for coding).
- **CLike from Claude Code / Codex** (H2): the extension MCP server runs phases through the
  governed chat flow and returns their outcome (`harper_run_phase` waits up to `wait_seconds`,
  then `harper_run_status`), plus `eval_run` (optionally the auto-eval `fix`) and `gate_check`;
  no overrides, promotion or git from MCP. The orchestrator MCP Harper read tools accept a
  `project_root` (confined to the projects directory). Verified with Codex calling
  `harper_req_list` on a project.

### Changed

- One FILE_REQUIREMENTS for cloud and local agents (B15): the agent package uses the obligations
  the orchestrator builds for every KIT (the ones the cloud prompt, the output contract and the gate
  use) and keeps its extra guidance as policies; it also writes the copy the gate reads under the
  locked `ci/`. Agent KITs now get concrete file roles, the namespace, and the launcher/runtime
  manifest requirements of their family; the noisy `external_library_obligation` is gone.
- KIT autofix for every ecosystem: final newline in sources, gofmt for Go when installed.
- `/agent-model` shows execution, default agent and models; `/agent-model list` lists the models.

- KIT: `TARGET_CONTRACT.json` and `FILE_REQUIREMENTS.json` are written by CLike (in `ci/` and
  `docs/`, same content) instead of being re-emitted by the model — fewer output tokens and no
  divergent copies (B8). Follow-up KIT stages see their options in the prompt (B7). The agent
  KIT/finalize contracts ask for the same deliverables as the cloud.

- BMAD runs: SPEC, plan.json and lane guides are checked against the BMAD quality contracts
  (deterministic, no LLM) and the gaps are reported as advisory `bmad_quality:` warnings; the
  unused fixture-only IDEA scorecard module was removed (L1).
- Debt: one slash parser in the webview (L4), deterministic repository manifest (B13), lane guides
  Markdown-only in the extension (B12), single finalize auth check (B11), flat agent audit files
  (B9), valid sample documents checked in CI (B14).

### Fixed

- A follow-up KIT stage (`--hardener`, ...) after the first eval started a new KIT generation
  and could rewrite the locked tests: it now keeps the generation and its test/ci changes are
  governed like a repair (L3).
- An eval or gate whose caller disconnected kept running in the sandbox (e.g. after a stopped
  benchmark it delayed the next eval by more than 30 minutes): it is now cancelled, with its
  processes, and the orchestrator answers 499.

## [1.1.0] — 2026-10-06 — Governed auto-eval on both paths, acceptance-first KIT

### Added

- Auto-eval with local agents: the agent package carries the failed checks, the hint and the
  repair rules; the acceptance files the agent changed are governed through
  `POST /v1/acceptance/amend` and the extension restores what is rejected. Benchmark
  `--runner agent --auto-eval N`.
- **Acceptance-first KIT** (`clike.kit.acceptanceFirst`, opt-in): `/kit` first generates only the
  acceptance tests and eval profile from SPEC/PLAN and locks them (`POST /v1/acceptance/lock`),
  then the code KIT writes the implementation against the locked tests (cloud and local agents;
  benchmark `--acceptance-first`). Addresses the known limitation that criteria and code came
  from the same call.
- `/agent-model [claude|codex] [model]`: show or change the local agent model from the chat
  (any mode).
- Local-agent telemetry: usage, API-equivalent cost, model and duration of Claude Code / Codex
  runs, in `.clike/telemetry` and in the gateway portal (`POST /v1/harper/telemetry`).

### Changed

- KIT generation (cloud and local agents): an eval-readiness self-check closes the prompt, with
  one rule per failure class measured by the benchmark (checks the LTC runs, files asserted by
  tests, behaviour over internals, real library APIs, time-bounded tests, read-only project
  root). PLAN acceptance items are stated at their observable boundary.
- Generated KIT files get safe mechanical lint fixes before they are written and locked
  (per-ecosystem registry; Python: ruff import order, unused imports, whitespace).

- Local-agent KIT context: content also written as package files (selected-capability guide,
  FILE_REQUIREMENTS) is referenced by path instead of repeated (smaller context, re-read on
  every agent turn).

### Fixed

- The configured agent model (`clike.claudeCode.model`, `clike.localAgent.codex.model`) applied
  only to chat; Harper phases ran with the CLI default model.
- Local-agent runs (including the eval pre-pass) left no telemetry and were attributed to the
  cloud model selected in the UI.

## [1.0.0] — 2026-10-05 — Milestone M3: ready for evolution

### ⚠️ Breaking changes

- Gateway `POST /v1/harper/run` requires `composed_messages`: the phase messages (system prompt,
  context, output checklist) are composed by the orchestrator. The gateway adds RAG material and
  chat history and calls the provider. Orchestrator and gateway must be updated together.
- Phase prompts moved from `gateway/prompts/harper/` to `orchestrator/phases/<phase>/cloud_*.md`;
  the `PROMPT_*_SYSTEM_PATH` variables are no longer read.

### Added

- **Auto-eval** (`docs/auto-eval.md`): `/eval REQ --fix ["hint"]` runs eval → KIT repair from the
  real failures → eval, up to `clike.autoEval.maxCycles` (default 2); rerunnable with a developer
  hint; `clike.autoEval.afterKit` runs it after `/kit`. Tests stay locked; an LTC command that
  cannot run and `ci/` dependency upgrades are accepted as audited amendments of the acceptance
  lock. When the eval shows that a test itself is wrong (an error raised in the test file, not a
  failed assertion), the test is fixed instead of the code, with every assertion unchanged; the
  gate reports `review_required`. API: `kit.repair` object on `/v1/harper/run`; benchmark
  `--auto-eval N`.
- **Regression of promoted REQs**: `/v1/eval/run` and `/v1/gate/check` accept `regression: true`
  (extension: `clike.eval.regression`, default on) and re-run the acceptance checks of every promoted
  REQ (plan status `done`) against the new code; the gate reports
  `GATE_BLOCKED_REGRESSION`.
- Browser e2e checks in the eval sandbox: Chromium system libraries in the image
  (`ENABLE_BROWSER`), browser downloaded on demand in the project's Playwright version.
- Harper benchmark (`benchmark/`): documented sample projects, cloud and local-agent runners,
  promotability metrics.
- `PhaseContext` v1: the typed, versioned contract of a phase run
  (`docs/contracts/phase_context.v1.schema.json`); the wire `core_blobs` are produced from it.
- Phase definitions as data in `orchestrator/phases/`: per-phase `phase.yaml` (write roots, output
  contract, rules, accepted result paths) and `text.yaml` (local-agent prompt and policy text).
- GPT-6 family support (reasoning models recognized by generation number); `openai:gpt-6.1-sol`
  in the catalog.
- Tests: characterization snapshots for local-agent packages and result normalization, phase
  definition parity with the extension, cloud/local-agent equivalence per phase.

### Changed

- Gate: warnings (failed non-blocking checks) no longer block; the gate passes with
  `GATE_PASS_WITH_WARNINGS` unless strict (`strict: true`, `clike.gate.strictWarnings`,
  `CLIKE_GATE_STRICT_WARNINGS=1`). Eval `promotable` follows the same policy.
- `services/local_agent_package.py` (6,900 lines) split into `services/local_agent/` (one module
  per phase, shared helpers, normalization); the old module is a compatibility facade.
- Local Claude Code never receives `ANTHROPIC_AUTH_TOKEN` (it would override the subscription
  login), like `ANTHROPIC_API_KEY`.

### Fixed

- Cloud `/kit` produced unusable paths for many plans: free text and placeholders became file
  paths (B18), the ecosystem was guessed from scattered words (e.g. `.js` files in a Python
  project, B19), and `__init__.py`, `ci/requirements.txt` or extra tests rejected the whole KIT
  (B20). The cloud KIT contract now matches the local agent's.
- Lane guides and selected capabilities were dropped from the cloud KIT context; the SPEC
  validator and prompt disagreed on the required sections.
- Coding mode wrote generated files to `/generated/...` outside the workspace.
- `kit.repair` sent by the extension (`/kit --repair`) is accepted as a flag or as an auto-eval
  repair request (the gateway rejected the orchestrator's default `false`).
- Eval honors the LTC `run_from` field as the commands' working directory.
- Cloud `/plan` received IDEA.md and SPEC.md by name only and could return an empty plan; it now
  receives them in full. Cloud `/kit` received no project documents and could ignore the
  technology constraints (e.g. Flask for a FastAPI project); its prompt now includes the
  technology constraints, the target REQ with its dependencies, SPEC.md and IDEA.md.
- Chat webview: REQ ids were never recognized and message previews replaced the letter "s" with
  spaces (regexes inside the webview script lost their backslashes).

### Removed

- Dead code: unused KIT/EVAL prompt builders, a shadowed duplicate function, an unused copy of
  the cloud capability renderer, unused gateway helpers.
- WP9 cleanup (about 2,700 lines): modules unreachable from any service entry point
  (`harper_flow/`, `constraints/`, `embeddings.py`, `spec_plan_gates.py`, …), unused functions and
  imports, commented-out code, the extension's `rag.js` and `fix_ext_vs.sh`.
- The gateway's own Qdrant store and embedder (unused): RAG is owned by the orchestrator; the
  gateway is a client of `/v1/rag`. The gateway no longer reads `EMBEDDING_DIM`,
  `RAG_EMBED_FAMILY`, `RAG_SCORE_THRESHOLD`.

### Changed (code quality)

- Duplicated provider result builders and local-agent failure responses consolidated; extension
  lint at zero warnings; code comments in English.

## [0.9.5] — 2026-10 — Milestone M2: correct and governed

### ⚠️ Breaking changes

- `/v1/gate/check` no longer accepts manual verdicts (`mode=manual`): use the new
  `POST /v1/gate/override` (reason required, audited). The extension does this for
  `/gate <REQ> manual pass`.
- Eval/gate refuse to run when the REQ acceptance surface changed after it was locked; re-run
  `/kit` to re-baseline.
- Orchestrator `POST /git/branch`, `/git/commit`, `/git/pr` removed (unused; they ran `git add .`
  in the server directory). The extension remains the only Git actor.
- Error statuses: a provider without an API key on the gateway is `503`
  `{code: provider_not_configured}` (was `401`); an unknown/disabled model is `400`
  `{code: model_selection_error}` (was `500`); gateway failures during any Harper phase keep their
  status and cause (`429`/`503`/`4xx` pass through, others `502`) instead of a generic `500`.
- Gateway: unknown Harper phases are rejected (`400`) and a missing phase prompt is `503`;
  `eval`/`gate` use their own prompts instead of the SPEC prompt.
- Extension settings removed (never read): `verboseLogging`, `docRoot`, `chat.autoOpenOnStartup`,
  `execution.showInChat`, `mcp.clientEnabled`, `mcp.serverEnabled`,
  `localAgent.codex.approvalMode`, `localAgent.codex.printModeFlag`.
- DeepSeek provider and the dedicated vLLM/Ollama modules removed; Ollama is reached through its
  OpenAI-compatible API.

### Added

- Acceptance lock and tamper detection for `runs/kit/<REQ>/test/**` and `ci/**`, taken before any
  local-agent eval pre-pass; reports include an `integrity` section.
- Audited gate override endpoint; overrides are reported as `OVERRIDE` and promoted only with an
  audit id.
- `eval-sandbox` service: eval/gate commands run without credentials, isolated from the gateway
  and vector store, non-root on a read-only filesystem; optional offline mode
  (`compose.eval-offline.yml`). Reports include `executor`.
- Provider support for Claude Opus 5.5 / Sonnet 5.5 and newer OpenAI models, while older models
  receive exactly the requests they did before (provider contract suite with a model matrix).
- Provider retries with backoff on 429/5xx/529 and connection errors (never on read timeouts);
  orchestrator → gateway retries only when the connection could not be opened.
- Opt-in telemetry retention: `CLIKE_TELEMETRY_RETENTION_DAYS` (default: keep everything).

### Fixed

- Anthropic: `tool_choice` `required` was sent as a string; sampling parameters are omitted for
  models that reject them; long system prompts are cached.
- Gateway chat returned provider failures as HTTP 200 with empty text; `temperature: 0` became 0.4.
- The cloud eval phase spent an LLM call whose output was discarded.
- The staged KIT chain crashed at the hardener stage (`NameError`).
- Extension: several runtime `ReferenceError`s, broken/unregistered commands, local agents left
  child processes running after a timeout, chat image previews rendered as text.
- `runId` could travel as the string `"None"`; a request without `flags` was rejected by the gateway.
- Extension `eval`/`gate` requests used `fetch`, which aborts after 300 s without response
  headers; all service calls now share one client with the Harper time budget.
- A passing gate reported `reason_code` `GATE_BLOCKED_STATUS_PASS` (now `GATE_PASS`).
- A gate `mode` passed as a query parameter was ignored.
- KIT stage artifacts were written to a non-persistent path in containers (`RUNS_DIR` now
  `/app/runs`).

## [0.9.0] — 2026-10 — Milestone M1: safe to run

Consolidation release: no new end-user features; security, correctness of Git operations,
reproducibility and test coverage.

### ⚠️ Breaking changes

- **Service token required.** Orchestrator and gateway reject requests without
  `Authorization: Bearer <CLIKE_API_TOKEN>` (503 if the token is not configured). Set
  `CLIKE_API_TOKEN` in `.env` and run *CLike: Set Service Token* in VS Code. MCP clients must send
  the same header.
- **`POST /v1/apply` removed.** The extension applies generated files locally.
- **Eval/gate confinement.** The project root must be under `CLIKE_PROJECTS_DIR` (`DEV_FOLDER`) or
  `CLIKE_EVAL_ALLOWED_ROOTS`; the LTC profile is read from the workspace and an inline profile must
  be identical (`CLIKE_ALLOW_INLINE_LTC=1` re-enables inline-only profiles).
- **Git automation off by default.** `git.autoCommit`, `git.openPR`, `git.gitMergeOnGate` and
  `git.pushRebase` default to `false`; pushing requires the new `git.autoPush`.
- **Extension MCP server off by default**; when enabled it always requires a token.
- **No CORS** on orchestrator and gateway.

### Security

- Authenticated services on loopback, Host-header validation, fail-closed configuration.
- Service-to-service authentication; telemetry UI login with an `HttpOnly`, `SameSite=Strict` cookie.
- Path confinement for workspace writes, KIT stage artifacts, telemetry and MCP reads.
- Eval commands run without credentials; containers run as non-root with the repository read-only.
- Argv-only process execution in the extension; prompt via stdin on Windows.
- Webview: cryptographic nonce, `img-src data:` only, escaped server-provided content.
- 18 security-relevant settings are machine-scoped; untrusted workspaces are not supported.
- Telemetry, certificates and build artifacts removed from the repository and its history.

### Fixed

- Harper Git sync could drop commits from an existing REQ branch and move the default branch
  (`checkout -B`); it also staged unrelated changes (`git add -A`) and committed every file when
  initializing a repository. Sync is now non-destructive and commits only the phase files.
- PR creation through the GitHub CLI never ran (it was invoked as `git gh …`).
- Conventional commit messages and per-REQ draft PRs were disabled by setting-name mismatches.
- `/v1/apply` client path fell through to the local path after a server error.

### Build and quality

- Python 3.12 for both services; `pyproject.toml` + `uv.lock` per service; container images built
  from the lockfiles; healthchecks; optional Ollama profile; Podman supported.
- Golden snapshots of the phase boundary; contract fixtures decoupling gateway tests from the
  orchestrator; security regression suites; Git tests on real repositories.
- ESLint with a frozen baseline; npm scripts; reproducible `.vsix` packaging.
- Repository hygiene check (pre-commit and CI); GitHub Actions CI.

### Removed

- Unused modules that executed shell commands (`new_eval.py`, `services/evals.py`,
  `services/embedded_ops.py`) and dead Git helpers.

## Earlier

Development history before 0.9.0 (Harper lifecycle, local agents for all phases, BMAD
methodology profile, `/extend`, capabilities) is available in the Git log.
