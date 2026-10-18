# HOWTO — From `/init` to `/finalize` with BMAD, driven by Claude Code (MCP)

This guide runs a whole CLike project from a Claude Code session, through MCP, with the BMAD
methodology: each phase is guided by the BMAD role that owns it, and CLike keeps the governance
(contracts, locked tests, regression, gate, promotion). The setup of the MCP servers is in
[howto-mcp-project.md](howto-mcp-project.md); the picture of the whole is in
[clike-at-a-glance.md](clike-at-a-glance.md).

## The sequence

| # | Phase | Tool (`clike-ext`) | BMAD role | What it produces |
|---|---|---|---|---|
| 0 | INIT | `harper_init` | — | `docs/harper/`, `.clike/`, `runs/`, templates (existing files kept) |
| 1 | IDEA | `harper_run_phase {phase: "idea", methodology: "bmad", agent: "analyst", attachments: [...]}` | analyst | `docs/harper/IDEA.md` (+ `docs/harper/bmad/idea/` brief, assumptions) |
| 2 | SPEC | `harper_run_phase {phase: "spec", methodology: "bmad", agent: "pm"}` | pm | `docs/harper/SPEC.md` (+ PRD, epics, acceptance model) |
| 3 | UX (optional) | `harper_run_phase {phase: "spec", methodology: "bmad", agent: "ux"}` | ux | `docs/harper/ux/` journeys, states, design — SPEC untouched |
| 4 | PLAN | `harper_run_phase {phase: "plan", methodology: "bmad", agent: "architect"}` | architect | `docs/harper/PLAN.md`, `plan.json` (the REQs), lane guides |
| 5 | per REQ: KIT | `harper_run_phase {phase: "kit", req_id, methodology: "bmad", agent: "developer"}` | developer | `runs/kit/<REQ>/` code, tests, eval profile |
| 6 | per REQ: EVAL | `eval_run {req_id, fix: true}` | (CLike) | the verdict; failures repaired, tests locked |
| 7 | per REQ: GATE | `gate_check {req_id}` | (CLike only) | PASS → promoted into `src/`, `test/`, root files |
| 8 | FINALIZE | `harper_run_phase {phase: "finalize", methodology: "bmad", agent: "tech-writer"}` | tech-writer | solution running and configured, `FINALIZE_REPORT.md`, setup/start scripts |

Roles allowed per phase: idea → analyst; spec → pm, ux; plan → architect, pm; kit → developer;
finalize → tech-writer; `/idea --extend` → analyst, pm (default), architect, ux. The gate is
CLike's alone: no methodology there.

## Step by step

### 0. Prepare (once per project)

1. Create an empty folder under `CLIKE_PROJECTS_DIR` (e.g. `~/dev/projects/pingboard`) and open it
   in VS Code with the CLike extension active and `clike.mcp.extensionServerEnabled` on.
2. Copy the `.mcp.json` of [howto-mcp-project.md](howto-mcp-project.md) (servers `clike` and
   `clike-ext`) into the folder; export `CLIKE_API_TOKEN` and `CLIKE_EXT_MCP_TOKEN`.
3. Start `claude` in that folder and check both servers with `/mcp`.

### 1. Init

Ask Claude: *"Initialize this folder as a CLike project with harper_init."* CLike creates the
Harper structure in place and keeps any file already there.

### 2. Inputs

Put the requirement documents in `docs/inputs/` (for a later release: `docs/inputs/v2/`), UI
material in `docs/harper/ux/`, background in `docs/reference/`. Claude can write or copy them
there; they are read-only for the phases.

### 3. Documents with BMAD

```text
harper_run_phase {phase: "idea", methodology: "bmad", agent: "analyst", attachments: ["docs/inputs/brief.docx"]}
harper_run_phase {phase: "spec", methodology: "bmad", agent: "pm"}
harper_run_phase {phase: "spec", methodology: "bmad", agent: "ux"}          # optional, UI projects
harper_run_phase {phase: "plan", methodology: "bmad", agent: "architect"}
```

Each call returns a `run_id`; a long phase answers `status: running` — poll
`harper_run_status {run_id}`. Read the results with the `clike` tools (`harper_plan_read`,
`harper_req_list`, `harper_doc_read`) or ask Claude to open the files.

### 4. The REQ loop

```text
harper_next_action                                   # in-progress REQ, else first open REQ with dependencies done
harper_run_phase {phase: "kit", req_id: "REQ-001", methodology: "bmad", agent: "developer"}
eval_run {req_id: "REQ-001", fix: true}              # repair loop, tests locked
gate_check {req_id: "REQ-001"}                       # PASS → promoted; verdict reused if nothing changed
```

Repeat until `harper_next_action` answers `finalize_only`. If it answers `blocked`, the open REQs
wait for dependencies that are not done: finish those first.

### 5. Finalize

```text
harper_run_phase {phase: "finalize", methodology: "bmad", agent: "tech-writer"}
```

With REQs not promoted, it stops and says so; `confirm: true` runs it anyway. The developer then
reads `docs/harper/FINALIZE_REPORT.md` and starts the solution with `scripts/start_solution_local`.

### 6. Next release

```text
harper_run_phase {phase: "idea", extend: true, release: "v2", methodology: "bmad", agent: "analyst", dry_run: true}
harper_run_phase {phase: "idea", extend: true, release: "v2", methodology: "bmad", agent: "analyst"}
```

then steps 4 and 5 for the new REQs.

## One instruction for Claude Code

> Use the clike-ext MCP tools to deliver this project with BMAD. Run harper_init. Then idea
> (analyst, attach every file in docs/inputs/), spec (pm), plan (architect); show me the REQ list
> and wait for my OK. Then, for each REQ from harper_next_action: kit (developer), eval_run with
> fix, gate_check; poll harper_run_status for long runs; if a gate fails twice, stop and report the
> failures. When harper_next_action says finalize_only, run finalize (tech-writer) and summarize
> FINALIZE_REPORT.md.

Keeping a human check after PLAN is deliberate: the REQs decide everything that follows.

## Good to know

- One phase runs at a time; `cancel_run {run_id}` stops one.
- Confirmations the chat would ask (finalize with REQs not promoted, extend on an undelivered
  baseline) are answered with `confirm: true`; without it the run stops and says why.
- MCP never overrides a gate, never edits locked tests, never runs git commands: the developer
  keeps those in VS Code.
- The VS Code chat mirrors every MCP run (`▶ MCP KIT REQ-001 (requested by an external agent)`),
  so you can follow it there.

Troubleshooting: see [howto-mcp-project.md](howto-mcp-project.md#6-troubleshooting).
