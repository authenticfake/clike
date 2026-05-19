# Clike HOWTO

> **Developer-first reminder**
>
> In CLike, the developer has the primary role in **validating every phase** and **refining generated documents**.
>
> If alignment with the requirements is still weak, the developer can progressively add more detail to the requirement or source material so the process becomes more efficient as the work advances.

This document explains the recommended **step-by-step operational flow** to start and drive a project with CLike and the Harper process.

It is written as a practical onboarding guide and is meant to be linked from the main `README.md`.

---

## Why this HOWTO matters

A good HOWTO should do more than explain commands.  
It should help a developer become operational **quickly**, **confidently**, and **with the right mindset**.

For CLike, that mindset is simple:

- the platform accelerates the work
- the models generate artifacts
- the developer stays in charge

The example used in this guide is a new project called:

- **Project name:** `CoffeeBuddy`

---

## The Operating Principle

CLike is not a passive content generator.  
It is a **developer-led orchestration workflow**.

The developer remains responsible for:

- orchestrating the phases
- validating every generated artifact
- refining documents when alignment is weak
- deciding when a phase is approved
- intentionally triggering the next phase only after review

The best way to use Harper in practice is:

1. generate the artifact
2. read it critically
3. refine it where needed
4. approve it by moving to the next phase

That makes the workflow both efficient and controlled.

---

## Prerequisites

Before you start, make sure you already have:

- the CLike VS Code extension installed
- CLike services configured and reachable
- Git installed and working
- a local repository or target folder
- at least one model configured in the extension

If you want to use the **agentic local execution path**, also make sure you have:

- **Claude Code** and/or **GPT Codex** installed locally
- local agent execution correctly configured in your environment

Recommended preparation:

- read the repository `README.md`
- read `README_1st.md` if present
- verify authentication, model access, and runtime configuration first

---

## End-to-End Flow at a Glance

```text
/init → read README_1st.md → configure git → /idea → review IDEA.md
→ /spec → review SPEC.md
→ /plan → review PLAN.md and plan.json
→ (/kit → /eval → /gate) repeated for each REQ-ID
→ /finalize
```

The first phases define intent and structure.
The middle loop delivers the actual solution requirement by requirement.
The final phase closes the work and prepares the project for final documentation and pull request material.

---

## Step 1 — Initialize the Project

Create or register the project workspace with CLike.

### Command

```text
/init CoffeeBuddy
```

Optional folder override:

```text
/init CoffeeBuddy ./coffeebuddy
```

### What this does

* initializes the CLike project context
* binds the working folder to the project
* prepares the workspace for Harper commands
* creates the initial metadata used by extension and orchestrator

### Developer checkpoint

Before doing anything else, verify that:

* the correct project name is set
* the correct folder is bound
* the workspace context is the one you actually want to use

A wrong `/init` poisons everything that follows.

---

## Step 2 — Read `README_1st.md`

Before generating any Harper artifact, read the bootstrap document if it exists.

### What to look for

* local setup prerequisites
* repo conventions
* folder structure
* service/runtime notes
* dependencies
* constraints and caveats
* project-specific expectations for CLike or Harper

### Why it matters

This is the fastest way to avoid generating documents that are beautifully written but badly grounded.

### Developer checkpoint

If something important is missing, unclear, or implicit, note it immediately before moving on.

---

## Step 3 — Configure Git

Before entering the generation flow, make sure Git is in a healthy state.

### Typical checks

```bash
git status
git branch
git remote -v
```

If needed:

```bash
git init
git add .
git commit -m "chore: initial workspace setup"
```

### What “good” looks like

* clean working tree
* correct branch selected
* remotes configured
* repository ready to track Harper artifacts and generated outputs

### Developer checkpoint

Do not start the Harper flow on top of a vague or unstable repository situation.

---

## Step 4 — Generate `IDEA.md`

Create the initial Harper idea document starting from an attached source file.

### Command

```text
/idea
```

### What to attach

Attach the file that best represents the initial project intent, for example:

* a product note
* a workshop summary
* a concept draft
* a customer request
* a requirements outline
* a business brief

### Model and execution selection

At this stage select:

* **Model**
* **Execution**

  * `Auto`
  * `Cloud Only`

> For `/idea`, the usual recommendation is **Auto** or **Cloud Only**.

### Objective

Generate an `IDEA.md` that is coherent with the Harper process and captures:

* vision
* problem statement
* target users
* value and outcomes
* constraints
* context

### Developer checkpoint

Read `IDEA.md` carefully.

Ask:

* does it describe the real business intent?
* is the problem stated correctly?
* are users and context believable?
* are constraints present?
* would I be comfortable using this as the base for the rest of the solution?

If not, refine the input or the generated document before moving on.

---

## Step 5 — Generate `SPEC.md`

Once `IDEA.md` is acceptable, generate the specification.

### Command

```text
/spec
```

### Model and execution selection

At this stage select:

* **Model**
* **Execution**

  * `Auto`
  * `Cloud Only`

### Objective

Generate a Markdown specification that turns intent into a testable contract.

Typical contents include:

* scope
* functional requirements
* non-functional requirements
* constraints
* acceptance criteria
* exclusions or non-goals

### Developer checkpoint

Read `SPEC.md` like a demanding reviewer.

Validate that:

* the scope is correct
* the requirements are clear
* the constraints are explicit
* acceptance criteria are testable
* the document is useful for planning, not just pleasant to read

If alignment is weak, enrich the requirement now.
This is one of the highest-leverage moments in the whole flow.

---

## Step 6 — Generate `PLAN.md` and `plan.json`

Convert the specification into an executable plan.

### Command

```text
/plan
```

### Objective

Generate:

* `PLAN.md`
* `plan.json`

### What these artifacts should contain

* requirement breakdown into stable REQ-IDs
* dependency sequencing
* practical execution order
* acceptance mapping
* both human-readable and machine-readable planning artifacts

### Expected result

You should now have requirement identifiers such as:

* `REQ-001`
* `REQ-002`
* `REQ-003`

### Developer checkpoint

Review both `PLAN.md` and `plan.json`.

Ask:

* is the REQ split sensible?
* are dependencies correct?
* is the sequence practical?
* are requirements too big, too vague, or too coupled?

A sharp plan makes `/kit` dramatically more effective.

👉 Read how to extend PLAN for new REQs
[CLike_Harper_Extend_Feature.md](./CLike_Harper_Extend_Feature.md)

---

## Step 7 — Build a Requirement with `/kit`

Start implementation for a specific requirement.

### Example command

```text
/kit REQ-001
```

This phase supports two execution scenarios.

---

### Scenario A — Agentic path

Use the local-agent path when you want implementation to be executed through **Claude Code** or **GPT Codex**.

#### First select the default local agent

```text
/agent-default codex
```

or

```text
/agent-default claude
```

or

```text
/agent-default auto
```

#### Then choose execution mode

Use one of:

* `Prefer Agent`
* `Agent Only`

#### Prerequisites

You must already have installed at least one supported local agent:

* Claude Code
* GPT Codex

#### What happens here

* CLike prepares the requirement context
* the local agent receives that context
* implementation is generated under the candidate artifact structure
* the REQ is developed through the selected agentic flow

#### Best when

* you want repository-aware local execution
* you want stronger agent-driven implementation loops
* you already have the local tooling ready

---

### Scenario B — Cloud path

Use the cloud path when you want `/kit` to run without local agent execution.

#### Execution mode

Select:

* `Cloud Only`

#### What happens here

* the build is generated through the cloud path
* candidate outputs still follow the Harper artifact model
* no local Claude Code or Codex executor is required

#### Best when

* local agents are not installed
* you want a simpler hosted path
* your environment is set for cloud-only generation

---

### `/kit` is not just one shot

The implementation flow is iterative. Depending on project setup, `/kit` may involve internal follow-up phases such as:

* `kit`
* `integrity_eval`
* `promotion_hardener`
* `promotion_eval`

These phases help improve promotability before final promotion.

### Developer checkpoint

Before moving to `/eval`, review what `/kit` produced.

Validate:

* requirement alignment
* implementation quality
* adequacy of generated tests
* clarity of execution artifacts and docs

If the output is only partially aligned, sharpen the requirement details and re-run the loop.
This is where good developers quietly save hours.

---

## Step 8 — Execute `/eval`

Run the validation phase after `/kit`.

### Command

```text
/eval
```

### Purpose

This phase is used to execute tests and validation checks manually and confirm that the generated implementation behaves correctly.

Typical checks include:

* tests
* linting
* type validation
* build validation
* requirement-level verification

### Completion condition

The phase is successful when the required checks complete with acceptable results.

### Developer checkpoint

Review the evidence like someone who will own the output later.

Do not proceed if:

* tests are incomplete
* evidence is weak
* the result is still misaligned
* the implementation “sort of works” but is not truly ready

---

## Step 9 — Execute `/gate`

Once the validation results are acceptable, use `/gate` to verify or promote the requirement.

Two common paths are available.

### Path A — Manual promotion after successful manual verification

```text
/gate REQ-001 manual pass
```

Use this when:

* the requirement was validated manually
* the evidence is strong
* you want to explicitly confirm readiness

### Path B — Standard gate verification

```text
/gate REQ-001
```

Use this when:

* you want CLike to verify gate criteria and KPIs
* the requirement should go through the standard gate path

### Developer checkpoint

The developer remains the final validator of whether the requirement is actually acceptable for progression or promotion.

If needed, go back, refine the requirement, and rerun the loop.

---

## Step 10 — Repeat for All REQ-IDs

Steps **7, 8, and 9** are iterative.

Repeat them for each requirement:

```text
/kit REQ-002
/eval
/gate REQ-002
```

```text
/kit REQ-003
/eval
/gate REQ-003
```

Continue until all planned requirements are implemented and validated.

### Developer checkpoint

As the project advances, keep improving precision where needed.
Small requirement refinements at the right time usually produce outsized gains later.

---

## Step 11 — Finalize the Solution

Once all REQ-IDs are completed, run the final closing step.

### Command

```text
/finalize
```

### Purpose

This phase finalizes the documentation and prepares the delivery artifacts.

Typical outputs may include:

* release-oriented documentation
* final Harper status updates
* PR-oriented material
* release notes or summary docs

### Developer checkpoint

Before considering the work complete, perform one last serious review of the full documentation set and confirm that the final result matches the intended solution.

---

## Practical Example for CoffeeBuddy

A minimal example sequence:

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

If you prefer cloud-only execution for build:

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

In that case, set execution mode to **Cloud Only** before running `/kit`.

---

## Smart Operating Advice

* review `IDEA.md`, `SPEC.md`, and `PLAN.md` before building code
* do not skip Git preparation
* choose execution mode consciously for `/idea`, `/spec`, and especially `/kit`
* use the agentic path only when local agents are correctly installed
* treat `/kit`, `/eval`, and `/gate` as a controlled loop, not as a slot machine
* keep requirements small, explicit, and verifiable
* finalize only after all required REQ-IDs are truly validated

---

## Troubleshooting Notes

### `/kit` does not use the local agent as expected

Check:

* local agent installed
* `/agent-default` already set
* execution mode is `Prefer Agent` or `Agent Only`

### `/idea` or `/spec` produce weak output

Check:

* the quality of the attached source file
* the selected model
* whether execution mode is appropriate

### `/gate` does not promote the requirement

Check:

* missing or failed validation evidence
* incomplete `/eval`
* requirement not actually ready

---

## Summary

For a new project such as **CoffeeBuddy**, the recommended operational journey is:

1. initialize the project
2. read the bootstrap docs
3. prepare Git
4. generate `IDEA.md`
5. review and refine `IDEA.md`
6. generate `SPEC.md`
7. review and refine `SPEC.md`
8. generate `PLAN.md` and `plan.json`
9. review and refine planning artifacts
10. implement each REQ with `/kit`
11. validate with `/eval`
12. promote or verify with `/gate`
13. repeat until all REQs are complete
14. close with `/finalize`

---

## Final Reminder — Developer-Centered Approach

The Harper flow in CLike works best when the developer stays fully engaged as:

* the **orchestrator** of the phases
* the **validator** of every output
* the **refiner** of generated documents
* the **approver** of each transition

Remember these operating principles:

* every generated document must be reviewed before moving forward
* each phase is approved by the developer through the execution of the next one
* when output alignment is weak, the developer should enrich the requirement, context, or source material with sharper details
* efficiency improves progressively when the developer keeps refining intent and constraints throughout the journey

This is not a passive generation flow.
It is a **developer-led orchestration workflow** supported by CLike.


> **Approach reminder**
>
> The developer remains the orchestrator and approver of every phase.
> If output alignment is weak, enrich the requirement or source material with sharper details before proceeding.

