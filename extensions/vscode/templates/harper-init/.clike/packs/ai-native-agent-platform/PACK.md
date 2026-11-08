---
name: ai-native-agent-platform
description: AI-native agent platform scenario: provider abstraction, governed actions, eval/RAG/HITL evidence.
obligations:
  - Abstract model/provider behind boundaries
  - Keep human-in-the-loop for state-changing agent actions
  - Record prompt/eval/RAG provenance
eval_checks:
  - provider-abstraction-present
  - eval-and-gate-evidence-present
  - rag-provenance-recorded
  - hitl-on-state-changes
gate_implications:
  - block-if-ungoverned-autonomous-writes
  - block-if-missing-eval-evidence
evidence_required:
  - Eval/gate artifacts
  - Provenance logs
---

# Pack: AI-Native Agent Platform

## Intent

Guide CLike generation for AI-native platforms, agentic workflows, LLM orchestration, RAG systems, eval-driven AI features, model routing, and tool-mediated automation.

This pack keeps agentic systems governed: agents may diagnose, repair, propose, and produce evidence, but they must not override deterministic policy or Gate.

## Scenario signals

- AI-native platform, agent, LLM, RAG, embeddings, model router, prompt orchestration, evals, tool calling, MCP, coding agents, tool platforms, workflow automation, autonomous repair, code generation, or multi-model routing.
- Requirements involving model/tool orchestration, generated code review, AI evals, provider adapters, context retrieval, or tool/plugin integration.
- Acceptance criteria requiring evidence-based AI behavior.

## Use when

Use this pack when the solution itself is an AI platform, agent platform, LLM application, RAG system, code generation system, evaluation harness, or model/tool orchestration layer.

## Do not use when

Do not use this pack for ordinary CRUD applications with no AI/model/tool orchestration concerns.

## Required capabilities

Recommended skills:

- journey-ai-guardrails
- enterprise-solution-architecture when the AI feature is part of an enterprise product
- e2e-slice-runnability for runnable AI feature slices
- backend-contract-boundary
- journey-runtime-config for provider keys, prompt redaction, tools, egress, or runtime config
- eval-contract-writer
- gate-risk-reviewer
- journey-ui-states when UI is involved
- backoffice-workflow-ux when AI is exposed inside an operator or admin console

Recommended design profiles:

- developer-tooling-console for developer-facing AI tools
- enterprise-console for governed enterprise AI platforms

## Runtime assumptions

- Provider/model choice must be abstracted where practical.
- Local deterministic tests must not require live provider calls.
- External model/provider evals may be optional or non-blocking unless explicitly required.
- Tool execution should default to dry-run for write operations.
- Human approval is required for destructive or external write actions.
- Agent output must be reproducible through versioned inputs, context, and evidence artifacts.

## Security/compliance assumptions

- Prompt injection must not override policy or system constraints.
- Secrets, source code, and proprietary context must be minimized and protected.
- Tools must follow least privilege.
- Model/provider outputs must be treated as untrusted until validated.
- Audit trails are required for tool-mediated actions.
- No plugin/tool/agent may promote code or override Gate.

## Architecture constraints

- Separate retrieval, prompt assembly, model call, parsing, evaluation, and action execution.
- Keep provider-specific code behind adapters.
- Keep tool adapters evidence/action-oriented, not magic.
- Prefer deterministic contracts for model-facing functions.
- Avoid vendor lock-in in core abstractions.
- Do not build a plugin marketplace before the adapter contract is stable.

## Eval expectations

- Deterministic unit tests for prompt assembly, routing, parsing, and tool-policy behavior.
- Fixture-based provider tests or fake model responses for local validation.
- RAG retrieval tests when retrieval affects behavior.
- Eval datasets or cases when output quality is acceptance-critical.
- HOWTO must separate local deterministic checks from live provider checks.
- LTC must distinguish blocking deterministic checks from optional model/provider checks.

## Gate implications

Gate should block promotion when:

- AI behavior lacks eval evidence.
- RAG behavior lacks retrieval evidence.
- Structured model output is consumed without validation.
- Live provider calls are required for local unit tests.
- Tool/agent output can override policy, Gate, or promotion.
- Write tools are not approval-gated.

Gate may allow non-blocking warnings when:

- Live provider evals are unavailable but deterministic fixture tests pass.
- Cost/latency evaluation is documented but not required for the current REQ.
- Tool integrations are stubbed behind a stable adapter contract for future implementation.

---

# CLike Pack Overlay

## Skills

Select only the skills the REQ, lane, runtime profile and acceptance justify: the journeys whose
scenarios the REQ owns (`journey-*`), `eval-contract-writer` for every REQ that ships code,
`backend-contract-boundary` for backend contracts, `e2e-slice-runnability` for user or service
flows, plus the scenario-specific skills listed by this pack.

## Gate

The gate promotes on PASS and on PASS_WITH_WARNINGS (non-blocking checks failed or
environment-blocked, reported and tracked), unless the project enables strict warnings. A check
belongs in the blocking set when it proves an acceptance criterion or scenario in the sandbox; it is
non-blocking only when it needs infrastructure the sandbox does not have, with the reason stated.
