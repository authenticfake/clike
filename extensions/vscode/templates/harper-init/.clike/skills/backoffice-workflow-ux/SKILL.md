---
name: backoffice-workflow-ux
description: Generate enterprise backoffice workflows with route-based capability pages, scalable lists, task flows, filters, actions, and role-aware UX.
phases: ["spec", "plan", "kit", "eval", "gate", "finalize"]
lanes: ["frontend", "typescript", "python", "backend", "ai-native"]
domains: ["enterprise", "developer-tooling", "ai-native"]
runtime_profiles: ["local", "cloud", "local-cloud", "on-prem", "hybrid"]
gate_required: true
obligations:
  - Implement list/detail workflow states (loading/empty/error/success)
  - Respect backend as source of truth for authorization and data
eval_checks:
  - ui-states-tested
  - workflow-flow-tested
gate_implications:
  - block-if-missing-error-empty-states
  - block-if-ui-bypasses-backend-authority
evidence_required:
  - Component tests for workflow states
---

# Backoffice Workflow UX Skill

## Intent

Backoffice software is operational software.

This skill prevents CLike from generating a single superficial dashboard when the requirement describes multiple capabilities, task workflows, search-heavy archives, validation operations, export actions, AI assistance, or enterprise operator journeys.

## Use when

Use this skill when a REQ touches:

- backoffice;
- admin console;
- operator console;
- task inbox;
- workflow;
- validation;
- archive/search;
- export;
- document management;
- approvals;
- configuration;
- AI assistant page;
- enterprise dashboard;
- internal tools.

## Do not use when

Do not use this skill for landing pages, pure marketing pages, simple static forms, or backend-only modules with no operator/user workflow.

## Required UX shape

When this skill is selected, generated frontend should prefer:

- one route/page per major capability;
- a shared shell/navigation;
- clear page title and purpose;
- list/detail or master/detail patterns for operational data;
- server-side filters and pagination for large datasets;
- loading, empty, error, permission-denied, and success states;
- role-aware navigation and actions;
- confirmation for destructive or irreversible actions;
- audit/provenance visibility where relevant;
- API client boundaries instead of hidden fetches inside presentation components.

## Capability page expectations

For a backoffice MVP, prefer explicit pages such as:

- `/ingest`;
- `/validation`;
- `/archive`;
- `/export`;
- `/qa`;
- `/settings`;
- `/extraction-profiles`;
- equivalent routes for the selected framework.

Do not hardcode these exact paths unless the SPEC/PLAN supports them. Use idiomatic routing for the detected stack.

## Large-data behavior

For archive, records, tasks, users, logs, or document lists:

- do not load all records client-side;
- use server-side filtering when backend exists;
- include pagination or cursor semantics;
- include stable sorting;
- include search input with clear scope;
- include filter reset;
- avoid expensive client-only filtering as the primary strategy;
- document backend/source-of-truth assumptions.

## Configuration UX

When users need to configure extraction, classification, rules, workflows, prompts, policies, or routing:

- create a dedicated configuration page or route;
- distinguish technical keys from user-facing labels;
- support add/edit/remove flows;
- show examples and validation hints;
- avoid hiding important business configuration in source constants only;
- persist configuration through backend if the REQ requires it;
- otherwise document the UI-local limitation.

## AI assistant UX

For AI-enabled backoffice pages:

- explain what AI can and cannot do;
- state that AI does not modify business state unless explicitly required;
- show citation or source policy;
- show no-source behavior;
- provide guided prompt examples;
- make provider/runtime profile visible where relevant;
- avoid anthropomorphic claims or unsupported autonomy.

## Backend/source-of-truth rule

The frontend must not duplicate backend business rules.

Forbidden frontend-only duplication includes:

- lifecycle transition rules;
- authorization rules;
- archive eligibility;
- AI document eligibility;
- export permission rules;
- validation preconditions.

The frontend may hide/disable actions for UX, but backend denial remains authoritative.

## Evidence required

A REQ using this skill should provide:

- route/page source files;
- shared shell or navigation when multiple pages exist;
- API client boundary or typed contract;
- at least one list/filter/task/action flow;
- state handling evidence;
- build/type/lint/test checks when available;
- manual smoke path when automation is unavailable.

## Regression Test Reconciliation

When a backoffice REQ adds a new capability page, navigation item, route, visible section, action, filter, or configuration workflow, candidate tests must reconcile existing operator-console regression tests included by CLike EvalRunner.

Do not leave older tests expecting the previous navigation or section list unchanged when the new behavior is intentionally additive.

Do not use brittle positional selectors for repeated labels or buttons. Prefer route-scoped rendering, `within(...)`, unique accessible labels, or test-specific component roots.

## Gate implications

Gate must BLOCK promotion when:

- a multi-capability backoffice REQ is implemented as a single decorative dashboard only;
- required capability pages/routes are missing;
- loading/error/empty/permission states are absent for critical workflows;
- large data lists are implemented as unbounded client-only lists without justification;
- backend-source-of-truth rules are duplicated or contradicted;
- selected enterprise-console design profile is ignored.

Gate may WARN when:

- a route exists but advanced filtering is deferred and documented;
- accessibility automation is unavailable but semantic controls are present;
- configuration UI is UI-local only and persistence is explicitly out of scope.

