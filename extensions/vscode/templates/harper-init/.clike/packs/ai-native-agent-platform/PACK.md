# Pack: AI-Native Agent Platform

## Intent

Guide CLike generation for AI-native platforms, agentic workflows, LLM orchestration, RAG systems, eval-driven AI features, model routing, and tool-mediated automation.

This pack keeps agentic systems governed: agents may diagnose, repair, propose, and produce evidence, but they must not override deterministic policy or Gate.

## Scenario signals

- AI-native platform, agent, LLM, RAG, embeddings, model router, prompt orchestration, evals, tool calling, MCP, Codex, Claude, Composio, workflow automation, autonomous repair, code generation, or multi-model routing.
- Requirements involving model/tool orchestration, generated code review, AI evals, provider adapters, context retrieval, or tool/plugin integration.
- Acceptance criteria requiring evidence-based AI behavior.

## Use when

Use this pack when the solution itself is an AI platform, agent platform, LLM application, RAG system, code generation system, evaluation harness, or model/tool orchestration layer.

## Do not use when

Do not use this pack for ordinary CRUD applications with no AI/model/tool orchestration concerns.

## Required capabilities

Recommended skills:

- ai-rag-eval-guardrails
- backend-contract-boundary
- eval-contract-writer
- gate-risk-reviewer
- local-cloud-parity
- frontend-state-accessibility when UI is involved

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
- PASS_WITH_WARNINGS is the final status.

Gate may allow non-blocking warnings when:

- Live provider evals are unavailable but deterministic fixture tests pass.
- Cost/latency evaluation is documented but not required for the current REQ.
- Tool integrations are stubbed behind a stable adapter contract for future implementation.
