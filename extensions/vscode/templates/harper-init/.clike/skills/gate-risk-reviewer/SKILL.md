---
name: gate-risk-reviewer
description: Enforce evidence-based promotion decisions and prevent risky or ambiguous KIT outputs from being promoted.
phases: ["eval", "gate", "finalize"]
lanes: ["python", "typescript", "java", "dotnet", "go", "rust", "iac", "frontend", "backend", "industrial", "ai-native"]
domains: ["consumer", "startup", "enterprise", "industrial", "manufacturing", "ai-native", "developer-tooling"]
runtime_profiles: ["local", "cloud", "local-cloud", "on-prem", "edge", "hybrid", "air-gapped"]
gate_required: true
---

# Gate Risk Reviewer Skill

## Intent

Promotion must be based on evidence, policy, and REQ satisfaction.

This skill prevents generated prose, optimistic assumptions, partial success, or `PASS_WITH_WARNINGS` from being treated as promotable output.

## Use when

Use this skill for every GATE phase, every EVAL summary review, every FINALIZE readiness review, and any REQ touching runtime safety, public contracts, persistence, integrations, security, UI behavior, AI behavior, industrial workflows, mobile offline behavior, or deployment.

## Do not use when

Do not use this skill as a subjective style reviewer.

It must not block promotion for taste, formatting preference, or architectural opinion unless the issue violates a policy, acceptance criterion, selected capability, or executable evidence requirement.

## Signals

Apply this skill when any of these are present:

- generated source code;
- generated tests;
- generated LTC/HOWTO;
- public API changes;
- auth/security changes;
- persistence changes;
- external integrations;
- frontend workflows;
- AI/RAG/tool behavior;
- runtime profile requirements;
- selected skills/packs/design profiles;
- warnings from EVAL;
- missing reports;
- missing commands;
- partial evidence.

## Gate Decision Model

Gate must evaluate in this order:

1. REQ dependency status.
2. Functional acceptance criteria.
3. Technical acceptance criteria.
4. Required local validation evidence.
5. Runtime profile adherence.
6. Selected skill adherence.
7. Selected pack adherence.
8. Selected design-profile adherence.
9. Security/config/secrets risk.
10. Promotion safety and future compatibility.

Promotion is allowed only when the final status is full `PASS`.

`PASS_WITH_WARNINGS` must not promote.

## Required Behavior

Gate must:

- cite concrete evidence for every pass/fail decision;
- block promotion when evidence is missing;
- block promotion when required checks fail;
- block promotion when generated artifacts are incomplete;
- block promotion when selected capabilities are ignored;
- block promotion when runtime assumptions are unsafe;
- block promotion when candidate files are not mapped to the REQ;
- identify future compatibility risks that could break later REQs;
- distinguish blocking failures from non-blocking external validation gaps.

## Forbidden Behavior

- Do not promote on generated prose.
- Do not promote on “looks good”.
- Do not promote on partial evidence.
- Do not promote `PASS_WITH_WARNINGS`.
- Do not promote if LTC/HOWTO are missing for runnable code.
- Do not promote if acceptance-critical tests are missing.
- Do not promote if external checks are required but absent.
- Do not promote if candidate output modifies forbidden canonical paths.
- Do not treat a fake adapter as proof of production integration.
- Do not ignore selected capabilities.

## Required Evidence

A promotable REQ should have:

- candidate source mapped to the REQ;
- candidate tests mapped to acceptance criteria;
- valid `ci/LTC.json`;
- valid `ci/HOWTO.md`;
- EVAL evidence for blocking checks;
- clear external validation status if applicable;
- capability adherence notes;
- no unresolved blocking risks.

## Solution and MVP Blocking Conditions

When `mvp-e2e-promotability`, `enterprise-solution-architecture`, `backoffice-workflow-ux`, `secure-config-secrets`, or enterprise packs are selected, Gate must additionally block when:

- the REQ claims MVP/E2E behavior but lacks an executable local or documented external validation path;
- a multi-capability backoffice UI is implemented only as a decorative single-page dashboard without justified scope;
- frontend/backend route parity is broken for acceptance-critical calls;
- runnable code lacks local scripts, exact commands, or HOWTO evidence;
- FINALIZE claims solution runnability without composition root, manifest validation, script validation, or route/API checks where applicable;
- security-sensitive config lacks `.env.example` or equivalent documentation;
- local-dev auth/config is presented as production-ready;
- secrets, tokens, provider keys, production endpoints, or raw prompts are hardcoded or logged;
- selected skill, pack, or design-profile obligations are ignored without upstream correction.

## Blocking Conditions

Gate must BLOCK promotion when any of these are true:

- required tests fail;
- lint/type/build/security checks fail when required;
- LTC is missing or invalid for runnable code;
- HOWTO is missing or not executable enough;
- generated source has no acceptance mapping;
- acceptance-critical behavior has no evidence;
- local/cloud/on-prem parity is violated for runtime REQs;
- secrets or production endpoints are hardcoded;
- external integration is acceptance-critical and has no local contract test or external evidence;
- UI acceptance behavior is decorative only;
- selected design profile is ignored for UI work;
- selected pack constraints are contradicted;
- candidate code writes outside allowed KIT target roots;
- dependencies are not satisfied;
- status is `PASS_WITH_WARNINGS`.

## Warning Conditions

Gate may emit WARNING when:

- optional external validation was not executed but local deterministic checks passed;
- docs are thin but executable evidence is complete;
- future hardening is recommended but not required by the current REQ;
- non-critical observability or polish improvements remain;
- manual smoke testing is documented for UI where automated frontend tooling is unavailable.

Warnings must not promote by themselves.

## Repair Guidance

If evidence is missing:

- return to KIT;
- add tests/checks;
- repair LTC/HOWTO;
- document external validation status.

If source is too broad:

- reduce candidate scope;
- align with `main_module_boundary`;
- remove speculative files.

If selected capabilities are ignored:

- update code/tests/docs to satisfy them;
- or document why the selected capability is not applicable and update the selection upstream.

If status is `PASS_WITH_WARNINGS`:

- do not promote;
- either fix warnings that affect promotion or downgrade them to non-blocking with evidence.

## Gate Decision Output Expectations

Gate decision should clearly state:

- `req_id`;
- final decision: `PASS`, `FAIL`, or `BLOCKED`;
- whether promotion is allowed;
- blocking reasons;
- warning reasons;
- evidence paths;
- affected files;
- next repair action.

## Success Definition

This skill is satisfied when promotion can be defended from artifacts and logs alone, without trusting the LLM that generated the code.
