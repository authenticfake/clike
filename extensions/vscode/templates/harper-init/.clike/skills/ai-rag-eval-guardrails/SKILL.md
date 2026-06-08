---
name: ai-rag-eval-guardrails
description: Guardrails for AI/RAG features: provenance, prompt-injection defense, output validation before business action, and eval evidence.
obligations:
  - Record retrieval provenance and context scope
  - Validate model output before any business action
  - Guard against prompt injection overriding system policy
eval_checks:
  - retrieval-provenance-recorded
  - prompt-injection-guarded
  - output-validated-before-action
gate_implications:
  - block-if-ungoverned-model-writes
  - block-if-missing-rag-provenance
evidence_required:
  - Eval artifacts under reports
  - Retrieval provenance logs
---

# Skill: AI RAG Eval Guardrails

## Intent

Ensure AI, LLM, RAG, prompt, routing, and agentic requirements are grounded, evaluated, observable, and safe to operate.

This skill prevents model confidence from replacing evidence.

## Use when

Use this skill when a REQ touches LLM calls, prompts, model routing, RAG, embeddings, vector stores, agent workflows, tool calling, response parsing, hallucination reduction, eval datasets, model quality, or AI safety behavior.

## Do not use when

Do not use this skill for deterministic application logic with no AI/model/RAG behavior.

## Signals

- The REQ mentions LLM, model, prompt, RAG, embeddings, vector search, context, retrieval, hallucination, agent, tool call, MCP, model router, evaluator, grounding, citations, summarization, classification, extraction, or AI quality.
- The output includes prompt templates, retrieval code, provider clients, eval fixtures, model routing rules, tool definitions, or AI response parsers.
- Acceptance criteria depend on generated text quality, structured model output, or retrieval correctness.

## Required behavior

- Keep provider-specific code behind a small adapter boundary when practical.
- Keep prompts versionable and traceable.
- Define deterministic input/output contracts for model-facing functions.
- Add eval cases for representative success and failure behavior.
- Separate retrieval, prompt assembly, model call, and output parsing where the project structure allows it.
- Treat missing retrieval evidence as a quality risk.
- Document cost, latency, and fallback assumptions when relevant.
- Ensure tool outputs are evidence or proposed actions, not autonomous policy decisions.

## Forbidden behavior

- Do not let model output override SPEC, PLAN, policy, or Gate.
- Do not claim factual grounding without retrieved context, citations, or test fixtures.
- Do not parse free-form model text when a structured contract is required and supported.
- Do not expose secrets or raw proprietary context unnecessarily.
- Do not allow prompt injection content to become system or policy instructions.
- Do not make eval pass/fail depend only on another model's opinion without deterministic checks or human-defined rubric.
- Do not hardcode one provider as an architectural dependency unless the REQ explicitly requires it.

## Evidence required

- Eval cases covering normal, edge, and failure scenarios.
- Fixtures or mocked provider responses for deterministic local tests.
- Retrieval tests or documented retrieval smoke checks when RAG is involved.
- Structured output schema or parser tests when model output is consumed by code.
- HOWTO instructions for local deterministic evals and optional provider-backed evals.
- Gate notes distinguishing deterministic checks from external/model-dependent checks.

## Repair guidance

- If prompts are embedded invisibly in code, move them to versionable constants or files.
- If parsing is brittle, add structured schema validation or robust parser tests.
- If retrieval is untested, add minimal indexed fixture retrieval tests or documented manual checks.
- If provider calls happen in unit tests, replace with fake provider responses.
- If the model can choose actions, add allowlists, approval boundaries, and audit logs.

## Gate implications

Gate should block promotion when:
- AI behavior is required but no eval evidence exists.
- RAG behavior is claimed but retrieval evidence is missing.
- Structured model output is consumed without validation.
- Provider calls are required for local unit tests.
- Tool or agent output can override Gate, policy, or promotion decisions.

Gate may allow non-blocking warnings when:
- Provider-backed evals cannot run locally but deterministic fixtures pass.
- Latency/cost evaluation is documented but not enforced for the current REQ.

## Examples

- A RAG REQ includes fixture documents, retrieval tests, prompt assembly tests, and parser validation.
- A model-router REQ includes deterministic routing tests and provider-agnostic adapter behavior.
- An extraction REQ validates structured output with failure cases and rejects malformed model responses.

## Non-examples

- A prompt-only change with no eval cases.
- A RAG feature that sends all files directly to the model without retrieval tests.
- An agent tool that directly promotes code based on model judgment.
---

# CLike Promotable KIT Enforcement Layer

## Purpose

This layer makes the skill operational for CLike `/kit` generation.

The goal is not to produce plausible code. The goal is to produce candidate artifacts that can be evaluated, repaired, and promoted through EVAL and GATE with minimal human rework.

## Promotable Code Obligations

When this skill is selected for a REQ, the KIT must:

- respect `main_module_boundary`;
- respect `functional_scope` and `technical_scope`;
- generate the smallest complete implementation slice;
- prefer repository-native conventions over invented abstractions;
- produce source files only under the target KIT source root;
- produce tests only under the target KIT test root;
- keep canonical `src/`, `test/`, and `tests/` read-only during candidate generation;
- document any intentional limitation instead of pretending completeness;
- avoid broad rewrites unless explicitly required by the REQ.

## Required Candidate Artifacts

The KIT should produce or update:

```text
runs/kit/<REQ-ID>/src/
runs/kit/<REQ-ID>/test/
runs/kit/<REQ-ID>/ci/LTC.json
runs/kit/<REQ-ID>/ci/HOWTO.md
runs/kit/<REQ-ID>/docs/KIT_<REQ-ID>.md
```

If the REQ is documentation-only or policy-only, the KIT must explicitly state why source/test artifacts are not required.

## Code Shape Expectations

Generated code should favor:

- explicit boundaries;
- dependency injection or constructor/function injection where practical;
- small cohesive modules;
- deterministic local behavior;
- typed schemas/contracts when the stack supports them;
- error paths that are visible and testable;
- safe defaults;
- clear adapter seams for external systems.

Generated code must avoid:

- hidden global state;
- hardcoded environment assumptions;
- silent fallbacks;
- fake success;
- speculative framework layers;
- broad unrelated refactors;
- acceptance criteria implemented only in prose.

## Test Expectations

Tests must map to acceptance criteria.

Prefer:

- deterministic unit tests;
- contract tests around adapters and payloads;
- failure-path tests;
- local fake/simulator tests for external dependencies;
- smoke checks only when deeper tests are not possible.

Avoid:

- placeholder tests;
- tests that only import modules when behavior is required;
- tests that require production credentials;
- network-dependent blocking tests unless explicitly scoped.

## LTC Expectations

`ci/LTC.json` must be valid JSON and include enough information for EvalRunner or a local agent to execute checks.

It should include:

- target `req_id`;
- lane/runtime profile when known;
- blocking local commands;
- optional external commands;
- report paths when available;
- environment-blocked status for unavailable infrastructure;
- gate-relevant policy hints.

## HOWTO Expectations

`ci/HOWTO.md` must be clear enough for a developer to run without guessing.

It should include:

- where to run commands from;
- prerequisites;
- local commands;
- expected result;
- troubleshooting;
- required environment variables;
- optional external validation steps;
- limitations and non-goals.

## Gate Impact

GATE should BLOCK promotion when this selected skill is materially violated.

Blocking examples:

- source is not mapped to the target REQ;
- acceptance-critical behavior has no test or executable evidence;
- LTC/HOWTO are missing for runnable code;
- production services or credentials are required for local blocking checks;
- selected capability obligations are ignored;
- generated files modify forbidden canonical roots;
- code claims completeness without evidence.

GATE may WARN when:

- optional external validation is not available but a deterministic local contract check exists;
- documentation is thin but executable evidence is complete;
- future hardening is correctly documented as out of scope.
