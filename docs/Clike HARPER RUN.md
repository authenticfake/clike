# HARPER RUN — Starter Manual & Process Artifacts (Official)

## What This Document Is

This document is the practical **starter manual** for running CLike with the Harper workflow.

It explains:

- what Harper Run is
- which artifacts are produced at each phase
- how the commands are typically used
- which command variants matter in practice
- how the **agentic path** differs from the **cloud path**
- where the developer must stop, review, refine, and approve before moving forward

This is not just a process note.  
It is meant to be used as an **operational guide**.

---

## The Harper Mindset

Harper Run works well only if the developer stays in charge.

The workflow is intentionally AI-native, but it is **not** meant to be blind automation.  
The developer remains:

- the **orchestrator** of the phases
- the **reviewer** of each generated artifact
- the **refiner** when alignment is weak
- the **approver** who decides whether the next phase should start

A strong Harper loop looks like this:

1. generate the artifact
2. inspect it critically
3. improve the inputs or the artifact when needed
4. approve the next move only when the current output is good enough

That principle matters more than any individual command.

---

## End-to-End Shape

The canonical Harper run is:

```text
IDEA.md → /spec → /plan → (/kit → /eval → /gate)* → /finalize → Solution
```

In practical day-to-day use, the developer often experiences it like this:

```text
/init → read bootstrap docs → /idea → review IDEA.md
→ /spec → review SPEC.md
→ /plan → review PLAN.md and plan.json
→ /kit REQ-xxx → /eval → /gate
→ repeat for remaining REQ-IDs
→ /finalize
```

The first half establishes **intent and structure**.  
The second half is an **iterative implementation loop**.

---

## Why Harper Run Exists

Harper Run exists to solve a common problem in AI-assisted development:  
moving fast while losing alignment.

Without a structured run model, teams often end up with:

- impressive text but weak intent alignment
- code before scope is stable
- evaluation without traceability
- promotion decisions without evidence
- generated output that cannot be safely trusted later

Harper Run prevents that by making the workflow:

- **artifact-driven**
- **iterative**
- **reviewable**
- **evidence-based**
- **promotion-aware**

---

## Canonical Artifact Areas

Harper Run uses two distinct but complementary artifact zones.

### 1) Canonical Harper documents

```text
docs/harper/
  IDEA.md
  SPEC.md
  PLAN.md
  plan.json
  KIT.md
  RELEASE_NOTES.md
  constraints.json
```

These are the project-level artifacts that describe what the solution is, how it is broken down, and how it evolves.

### 2) Run-scoped evidence

```text
runs/<runId>/
  kit.report.json
  eval.summary.json
  gate.decisions.json
  telemetry.json
  logs/
```

These capture what happened during a specific iteration.

### Why both exist

The canonical docs explain the **solution**.  
The run artifacts explain the **execution history**.

You need both to keep the workflow understandable.

---

## Knowledge Model and Context Inputs

Each Harper phase uses a scoped context model instead of blindly loading everything.

Typical shared inputs include:

- chat history in Harper mode
- canonical docs in `docs/harper/`
- RAG attachments when the material is too large to inline
- synced constraints in `constraints.json`

### Core document behavior

CLike can rely on:

- an explicit core set, such as `IDEA.md` and `SPEC.md`
- prefix-based discovery, where related files can be pulled in by name family

### Why scoped context matters

Too little context creates hallucination.  
Too much context creates blur.

Harper works best when each phase sees **just enough** information to act accurately.

---

## Before Starting a Real Run

A clean run usually starts with these steps:

1. initialize the workspace
2. read the bootstrap material
3. verify Git health
4. choose the execution model consciously
5. start generation only after the basics are grounded

A practical startup flow is:

```text
/init <project_name> [folder]
```

Then:

- read `README.md`
- read `README_1st.md` if present
- verify Git
- verify model availability
- verify whether the local agent path is actually usable

---

## How to Activate Execution Modes from CLike Chat

This is the operational section that most teams need early.

The key rule is simple:

- for **IDEA**, **SPEC**, **PLAN**, and usually **FINALIZE**, prefer the **cloud path**
- for **KIT** and, when applicable, **EVAL**, activate the **agent path** only when the local executor is truly ready

### A) How to activate the cloud scenario from CLike Chat

For these phases:

- `/idea`
- `/spec`
- `/plan`
- `/finalize`

the recommended execution selection is typically:

- `Cloud Only`

or, if you want the platform to decide safely:

- `Auto`

### Practical guidance

When you are in the CLike Chat UI:

1. choose the **model**
2. set **Execution** to `Cloud Only` for deterministic cloud usage
3. run the Harper command

Typical examples:

```text
/idea
/spec
/plan
/finalize
```

### When to prefer `Cloud Only`

Use `Cloud Only` when:

- you are producing or refining canonical Harper documents
- you do not need a local external executor
- you want the cleanest hosted flow
- the phase is more document-centric than code-execution-centric

### B) How to activate the agent scenario from CLike Chat

For these phases:

- `/kit`
- `/eval` (when your workflow wants local agent-assisted execution behavior or an explicitly agent-led path)

you first need to activate the local agent preference.

#### Step 1 — choose the default local agent

Run one of:

```text
/agent-default codex
/agent-default claude
/agent-default auto
```

Meaning:

- `codex` → prefer GPT Codex as the local executor
- `claude` → prefer Claude Code as the local executor
- `auto` → let CLike select the best available local executor

#### Step 2 — set Execution in chat

In the CLike Chat UI, select one of:

- `Prefer Agent`
- `Agent Only`

#### Step 3 — run the command

Typical examples:

```text
/kit REQ-001
/eval
```

### When to use `Prefer Agent`

Use `Prefer Agent` when:

- you want the local agent path when available
- but still want some flexibility in fallback behavior

### When to use `Agent Only`

Use `Agent Only` when:

- you want the phase to execute explicitly through the local agent path
- you do not want the system to silently fall back to cloud behavior for that phase

### Important prerequisite

Do not activate the agent scenario unless at least one local executor is installed and working:

- Claude Code
- GPT Codex

If the agent is not available, `Agent Only` is the wrong choice.

### Recommended operational mapping

A pragmatic mapping is:

- `/idea` → `Cloud Only`
- `/spec` → `Cloud Only`
- `/plan` → `Cloud Only`
- `/kit REQ-xxx` → `Prefer Agent` or `Agent Only`
- `/eval` → usually follow the validation strategy of the implementation loop
- `/finalize` → `Prefer Agent` or `Agent Only` or `Cloud Only` - Preferred: `Prefer Agent`

### Safe default

If you are unsure:

- use `Cloud Only` for documentation and planning phases
- use `Prefer Agent` for implementation phases
- use `Agent Only` only when the local-agent toolchain is already verified

---

## Phase 0 — `/init`

### Purpose

Bind the project name and working folder to the CLike workspace.

### Typical usage

```text
/init CoffeeBuddy
/init CoffeeBuddy ./coffeebuddy
```

### What this step establishes

- project identity
- working folder
- initial CLike metadata
- baseline workspace context

### Developer checkpoint

A wrong initialization contaminates everything downstream.  
Check the workspace before moving on.

---

## Phase 1 — IDEA

### Human intent before automation

Although many practical runs start from `/spec`, the strongest Harper runs begin with a clear idea source.

Typical inputs for the idea stage:

- a project brief
- a customer problem note
- a workshop summary
- a concept outline
- a requirement sketch

### Practical command

```text
/idea
```

### Recommended execution modes

Usually:

- `Auto`
- `Cloud Only`

### Expected artifact

```text
docs/harper/IDEA.md
```

### What IDEA should contain

A strong `IDEA.md` should capture:

- vision
- problem statement
- target users
- value and outcomes
- constraints
- operating context

### Developer checkpoint

Do not move to `/spec` if IDEA is still fuzzy.  
A weak idea produces an expensive plan.

---

## Phase 2 — `/spec` → `SPEC.md`

### Purpose

Turn the idea into a clear, testable contract.

### Inputs

- `IDEA.md`
- relevant Harper chat history
- canonical docs
- optional RAG attachments

### Typical command

```text
/spec
```

### Execution modes

In most runs:

- `Auto`
- `Cloud Only`

### Output

```text
docs/harper/SPEC.md
```

### What good looks like

A strong spec is:

- concise
- explicit
- testable
- stable enough to drive planning

### Developer checkpoint

Before going to `/plan`, confirm that the spec is not just “nice prose” but a real execution contract.

---

## Phase 3 — `/plan` → `PLAN.md` + `plan.json`

### Purpose

Translate the specification into implementable slices.

### Typical command

```text
/plan
```

### Outputs

```text
docs/harper/PLAN.md
docs/harper/plan.json
```

### Typical `plan.json` shape

```json
{
  "req": [
    {
      "id": "REQ-001",
      "title": "Example requirement",
      "acceptance": ["..."],
      "dependsOn": [],
      "status": "open"
    }
  ]
}
```

### What PLAN should achieve

A good plan should:

- create stable REQ-IDs
- make dependencies explicit
- keep implementation slices reasonable
- reduce ambiguity before `/kit`

### Developer checkpoint

This is the last cheap place to sharpen scope.  
If REQs are too large, too vague, or too tangled, fix them here.

---

## Phase 4 — `/kit` → code + tests + docs

### Purpose

Implement one or more REQ-IDs through requirement-scoped candidate artifacts.

### Canonical usage

```text
/kit
/kit REQ-001
```

### Default behavior

- `/kit` without an argument usually targets the next open REQ that satisfies dependencies
- `/kit <REQ-ID>` targets a specific requirement

### Main outputs

- source changes
- tests
- `docs/harper/KIT.md` with an iteration block
- iteration README material where useful
- `runs/<runId>/kit.report.json`

### Typical KIT iteration contents

A good KIT iteration records:

- targeted REQ-ID(s)
- rationale
- scope boundaries
- prerequisites
- run expectations
- product-owner notes
- deltas versus the previous iteration

---

## `/kit` Execution Modes

This is the phase where command variation matters the most.

### Option A — Cloud path

Use the hosted generation path when the implementation should run through the cloud model route.

Typical execution selection:

- `Cloud Only`

This path is the simplest when:

- no local agent is installed
- you want a consistent hosted flow
- the environment is not prepared for local agent execution

---

### Option B — Agentic path

Use the local agent path when implementation should be executed through a local external agent.

This is where **Claude Code** and **GPT Codex** matter.

#### First choose the default agent

```text
/agent-default codex
/agent-default claude
/agent-default auto
```

#### Then choose execution preference

Common options in practice:

- `Prefer Agent`
- `Agent Only`

#### When this path makes sense

Use it when:

- the local toolchain is already installed
- you want repository-aware local execution
- you want to exploit the strengths of Codex or Claude Code locally
- you want the implementation pass to be executed by an explicit local agent path instead of pure cloud generation

### Prerequisites for the agentic path

Before relying on it, make sure:

- the agent is actually installed
- the extension is configured to use it
- the execution preference is set intentionally
- the workspace is reachable to the local executor

### Execution context

The local-agent path depends on a bounded execution context, typically represented through an artifact such as:

```text
AGENT_EXECUTION_CONTEXT.json
```

This is important because the local agent is not supposed to improvise over the entire machine.  
It should receive a controlled, reviewable execution boundary.

---

## `/kit` Is Often More Than One Pass

Even when the chat surface exposes `/kit` as a single command, the underlying implementation loop may contain internal follow-up phases that improve promotability.

Typical follow-up phases that may appear around the implementation flow include:

- `kit`
- `integrity_eval`
- `promotion_hardener`
- `promotion_eval`

### What they mean conceptually

- **kit**: initial generation and artifact creation
- **integrity_eval**: immediate structural sanity checking
- **promotion_hardener**: focused refinement for promotability
- **promotion_eval**: final evaluation before promotion-oriented decisions

This matters because the real goal of `/kit` is not merely “produce files.”  
The goal is “produce files that are credible candidates for promotion.”

---

## Candidate Artifact Model

A key Harper concept is that generation should not immediately overwrite canonical code roots without evidence.

Typical requirement-scoped candidate artifacts live under a structure such as:

```text
runs/kit/<REQ-ID>/
  src/
  test/
  ci/
  docs/
```

This allows the workflow to separate:

- generated candidate output
- evaluation evidence
- promotion decisions

That separation is one of the reasons Harper remains governable.

---

## Phase 5 — `/eval` → `eval.summary.json`

### Purpose

Run or ingest validation evidence for the generated requirement slice.

### Typical usage

```text
/eval
/eval --all
```

### Common evaluation areas

Depending on stack and profile, `/eval` may include:

- tests
- lint
- type checks
- formatting checks
- build validation
- optional security or SCA checks

### Scoping

- default: validate only the REQ-IDs targeted in the last kit batch
- `--all`: broader regression-style validation

### Primary output

```text
runs/<runId>/eval.summary.json
```

### What a strong eval summary answers quickly

- what was checked
- which REQ was affected
- what passed
- what failed
- where the logs are
- whether the output is promotable

### Manual evaluation reality

In some workflows, `/eval` is also the place where the developer manually executes the required tests and confirms that the evidence is solid before proceeding to `/gate`.

### Agent-aware usage

When your team intentionally wants the implementation loop to stay on the local-agent path as long as possible, `/eval` may be paired operationally with the same chat-side selection used for `/kit`:

- set `/agent-default codex|claude|auto`
- choose `Prefer Agent` or `Agent Only`
- run `/eval`

If the evaluation step in your environment is primarily evidence collection and manual validation rather than agent execution, keep the phase simple and use the execution mode that best matches the current workflow.

### Developer checkpoint

Do not use `/eval` as ceremony.  
It is the evidence layer that protects the rest of the pipeline.

---

## Phase 6 — `/gate` → promotion decisions

### Purpose

Decide whether a validated REQ can be promoted.

### Typical usage

```text
/gate
/gate --all
/gate REQ-001
/gate REQ-001 manual pass
```

### Supported practical variants

#### Standard gate verification

```text
/gate REQ-001
```

Use this when the system should verify gate criteria in the normal way.

#### Manual positive override

```text
/gate REQ-001 manual pass
```

Use this when the developer has manually verified the evidence and intentionally confirms the promotion.

#### Batch evaluation

```text
/gate --all
```

Use this when multiple open REQs are already green and should be considered together.

### Main outputs

```text
runs/<runId>/gate.decisions.json
```

Plus:

- updated `PLAN.md`
- updated `plan.json`

### What gate should do

- stop promotion when evidence is weak
- mark valid REQs as done
- update plan artifacts
- make the next implementation target obvious

### Developer checkpoint

Gate is where rigor either survives or collapses.  
If evidence is weak, stop here.

---

## Phase 7 — `/finalize`

### Purpose

Close the Harper cycle after all required REQs are done or the agreed scope is reached.

### Typical usage

```text
/finalize
```

### Preferred execution model

In most documentation-oriented and closing scenarios, use:

- `Cloud Only`

or
- `Prefer Agent` or `Agent Only`

Preferred: `Prefer Agent`


### Main outputs

- `docs/harper/RELEASE_NOTES.md`
- summary materials
- PR-oriented outputs
- tag and merge-related material depending on configuration

### What finalize should feel like

It should feel like a clean closure, not like a scramble to explain what happened.

### Developer checkpoint

Before finalizing, confirm that the final documentation set is actually coherent and that the project can be understood by someone who did not live inside the chat.

---

## Git Governance

Harper assumes Git is part of the control plane.

### Typical conventions

- branch naming: `harper/<phase>/<runId>`
- commit messages: `harper(<phase>): <title> [runId=…] [model=…] [profile=…]`

### Typical toggles

- `git.autoCommit=true|false`
- `git.createPR=true|false`
- `git.mergeOnGate=true|false`

### Why this matters

Without Git discipline, the process leaves behind scattered output.  
With Git discipline, every step becomes reviewable and reproducible.

---

## Telemetry

Harper runs are meant to be inspectable, not mysterious.

Typical telemetry includes:

- provider
- model
- context window
- token estimates
- timing breakdowns
- files written or changed
- test counts
- pass/fail counts
- gate decision counts
- prompt system hash

Typical location:

```text
runs/<runId>/telemetry.json
```

Telemetry turns “it looked okay” into “we know what happened.”

---

## RAG in the Workflow

RAG is used when the required context is too large or too numerous to attach inline.

Typical flow:

- index files or folders on demand
- attach RAG references instead of raw content
- retrieve only relevant chunks during Harper or Coding flows

Typical command family:

```text
/ragIndex --path docs/harper
/ragIndex --path <folder> --glob "**/*.md" --tags "spec,plan"
```

Typical supporting APIs include:

- `POST /v1/rag/index`
- `POST /v1/rag/search`

### Why it matters

RAG helps the workflow stay grounded without bloating prompts.

---

## MCP and the Broader Direction

MCP is strategically relevant because it standardizes how tools and context are exposed to AI systems.

A practical implication for this manual is simple:

- Harper should remain portable
- tool access should become more standardized
- local and cloud paths should become easier to reason about

This does not replace the Harper artifacts.  
It strengthens the infrastructure around them.

---

## Recommended Starter Run

A pragmatic starter sequence for a new project looks like this:

```text
/init CoffeeBuddy
/idea
/spec
/plan
/agent-default auto
/kit REQ-001
/eval
/gate REQ-001
/kit REQ-002
/eval
/gate REQ-002
/finalize
```

If using cloud-only implementation:

```text
/init CoffeeBuddy
/idea
/spec
/plan
/kit REQ-001
/eval
/gate REQ-001
/finalize
```

The point is not to memorize the commands.  
The point is to understand the control rhythm.

---

## What Makes a Good Harper Run

A strong Harper run is not the one that generates the most text.  
It is the one that leaves behind:

- a sharp `SPEC.md`
- a practical `PLAN.md`
- stable `plan.json`
- scoped KIT artifacts
- credible evaluation evidence
- disciplined gate decisions
- finalize material that is easy to trust

That is the real standard.

---

## Final Reminder

Harper Run should feel fast, but never rushed.

The right rhythm is:

- **generate**
- **review**
- **refine**
- **approve**
- **advance**

That is what keeps the workflow both productive and promotable.