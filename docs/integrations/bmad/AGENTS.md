# BMAD Agents

BMAD roles in CLike are expressive methodology personas. They help a Harper phase reason with a role-specific focus, but they do not own workflow authority. CLike still owns canonical artifacts, execution packaging, eval, gate, telemetry, audit, and promotion.

## Analyst

The `analyst` role is used during idea shaping. It helps turn a loose product or engineering intent into a clearer problem statement with users, outcomes, assumptions, constraints, risks, and discovery questions.

In CLike, the analyst enriches `IDEA.md` without bypassing CLike. It can challenge weak assumptions, suggest research framing, identify missing domain context, or propose a PRFAQ-style stress test. It cannot create a parallel discovery pipeline or promote an idea directly into implementation.

## Product Manager

The `pm` role is used during specification and planning. It focuses on product intent, scope boundaries, acceptance criteria, implementation readiness, and story quality.

During `/spec`, PM guidance should make `SPEC.md` more testable and less ambiguous. During `/plan`, it should help produce REQs that explain what is built now, what is deferred, which dependencies matter, and what downstream REQs may assume. PM guidance is especially useful when a requirement is product-heavy but risks becoming a vague implementation task.

## Architect

The `architect` role is used during planning. It focuses on technical slicing, main module boundaries, dependency graphs, integration contracts, data contracts, runtime constraints, security implications, and operational shape.

In CLike, the architect helps make `PLAN.md` and `plan.json` implementation-legible for `/kit`. It should convert TECH_CONSTRAINTS obligations into concrete REQ obligations and avoid ungrounded technology assumptions. The architect does not choose an executor and does not override CLike candidate boundaries.

## Developer

The `developer` role is used for KIT and developer-oriented eval repair advisory. It focuses on candidate-first implementation, concrete files to inspect, repair strategy, local evidence, and test generation.

For `/kit`, developer guidance should help the local or cloud executor implement only the current REQ under `runs/kit/<REQ-ID>/...`. For `/kit --repair`, it should focus on failed checks and avoid unrelated rewrites. The developer role cannot write directly to canonical `src/`, canonical tests, `PLAN.md`, or `plan.json`, and it cannot promote code.

## UX

The `ux` role is used during specification when user experience is central to the requirement. It focuses on user journeys, interaction states, accessibility, terminology, empty states, error states, and user-visible acceptance criteria.

UX guidance can reference controlled companion artifacts such as `docs/harper/ux/DESIGN.md` and `docs/harper/ux/EXPERIENCE.md` when those files exist. It should make behavior easier to build and evaluate, not introduce speculative scope outside the current Harper intent.

## QA

The `qa` role is advisory only. It is used around eval to explain canonical failures and recommend repair strategy after EvalRunner has completed.

BMAD QA can provide root-cause hypotheses, files to inspect, missing tests, contract gaps, risk notes, recommended repair strategy, next commands such as `/kit REQ-001 --repair --methodology bmad --agent developer`, and checks to rerun. It cannot decide pass/fail, change `promotable`, replace EvalRunner, mark gate outcomes, or promote artifacts.

## Tech Writer

The `tech-writer` role is used during finalize. It focuses on release notes, README quality, concept explanation, Mermaid diagrams when useful, document validation, and final artifact clarity.

Finalize remains CLike-owned. The tech-writer role can make documentation more coherent and usable, but it cannot rewrite governance history, change eval/gate results, or promote code.

## Shared Boundaries

All BMAD agents may enrich phase guidance, suggest files to inspect, describe risks and contract gaps, recommend repair strategy, and improve clarity. They may not choose the execution provider, change allowed write roots, write outside candidate roots, modify forbidden paths, replace EvalRunner, decide gate outcomes, promote artifacts, or mutate Git state.
