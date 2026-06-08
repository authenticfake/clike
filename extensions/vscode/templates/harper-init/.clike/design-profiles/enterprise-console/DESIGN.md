---
name: enterprise-console
description: Route-based, high-trust enterprise console UI for backoffice, admin, workflow, AI, and operational platforms.
domains: ["enterprise", "developer-tooling", "ai-native"]
lanes: ["frontend", "typescript", "nextjs", "react", "web"]
inspired_by: ["IBM Carbon", "HashiCorp", "Linear", "Cohere"]
strictness: "high"
recommended_skills:
  - frontend-state-accessibility
  - backoffice-workflow-ux
  - mvp-e2e-promotability
ui_obligations:
  - route-based-information-architecture
  - list-detail-task-patterns
  - filters-search-pagination-on-lists
  - loading-empty-error-success-states
  - role-aware-actions
accessibility_expectations:
  - accessible-forms-and-tables
  - keyboard-navigable
  - visible-focus-and-status
eval_checks:
  - ui-states-tested
  - accessible-forms-tables-verified
  - list-detail-navigation-tested
gate_implications:
  - block-if-missing-loading-empty-error-states
  - block-if-inaccessible-forms-or-tables
evidence_required:
  - Component/E2E tests for list/detail flows and UI states
  - Accessibility checks for forms and tables
---

# Enterprise Console Design Profile

## Intent

Use this profile for enterprise consoles, internal platforms, admin dashboards, backoffice tools, AI-native control planes, workflow systems, validation tools, archive/search applications, and operator-facing enterprise UI.

This profile is a UI generation contract, not a visual mood board.

A compliant enterprise console must be operationally useful, navigable, stateful, accessible, and testable.

## Use when

Use this profile when a REQ has an enterprise/operator-facing UI surface: console, admin dashboard, backoffice workflow, control plane, or internal platform screen.

## Do not use when

Do not use this profile for backend-only REQs with no UI surface, or for consumer marketing/landing pages where a product-app profile fits better.

## Accessibility Expectations

- Forms and tables must be accessible (labels, roles, headers, keyboard operation).
- Interactive controls must be keyboard-navigable with visible focus and status.
- Error, empty, and loading states must be announced meaningfully, not silently.

## Information Architecture

When a REQ describes multiple business capabilities, prefer route-based information architecture.

Typical capability routes include:

- ingest/intake;
- task inbox;
- validation/review;
- archive/search;
- export/reporting;
- configuration/settings;
- AI assistant/Q&A;
- audit/activity;
- admin/policy.

Do not collapse multiple operational capabilities into a single decorative dashboard unless the SPEC explicitly requires a single-page experience.

## Visual Principles

- Clear hierarchy over decorative visuals.
- Dense but readable information layout.
- Minimal color usage for status and action emphasis.
- Consistent spacing and alignment.
- Accessible contrast and keyboard-friendly interactions.
- Practical microcopy over marketing copy.
- Data and workflow clarity over visual novelty.

## UX Principles

Generated UI should:

- make system state obvious;
- make errors actionable;
- avoid silent failures;
- avoid destructive actions without confirmation;
- keep primary actions clear;
- use accessible labels and semantic controls;
- support keyboard interaction where practical;
- avoid fake data presented as real data;
- avoid brand cloning or copied external product layouts;
- distinguish local/demo data from production data;
- expose role/permission constraints when relevant.

## Mandatory UI States

For interactive UI, generated code must consider:

- loading state;
- empty state;
- success/ready state;
- error state;
- disabled/submitting state;
- permission or unavailable state when relevant.

If a state is not applicable, document why.

## Backoffice Patterns

Prefer these patterns when appropriate:

- sidebar or top navigation for major capabilities;
- list/detail or master/detail for tasks and records;
- server-side filtering and pagination for large datasets;
- saved or reusable filters when the REQ requires repeated operational searches;
- forms with validation hints;
- action bars for workflow operations;
- confirmation dialogs for irreversible actions;
- audit/provenance panels for regulated operations;
- settings/configuration pages for business-managed rules.

## Large Data UX

For records, documents, tasks, logs, search results, or archives:

- do not load all records client-side;
- prefer server-side filtering and pagination;
- support stable sorting;
- make filter scope visible;
- provide empty and no-results states;
- preserve query state when navigation requires it;
- avoid frontend-only lifecycle filtering when backend is source of truth.

## AI UX

For AI-enabled enterprise consoles:

- explain what AI can and cannot do;
- show validated-only or source policy when applicable;
- show citation/source behavior;
- show no-source behavior;
- provide guided prompts when useful;
- display provider/runtime profile when relevant;
- do not imply autonomous business action unless explicitly required;
- handle denial and unavailable-provider states.

## Frontend Evidence

When frontend tooling exists, KIT should produce at least one of:

- component state tests;
- route/page smoke tests;
- interaction tests;
- accessibility-oriented assertions;
- documented manual smoke path when automation is unavailable.

## Code Shape Expectations

Generated frontend should prefer:

- small components;
- explicit props/state;
- reusable view models where appropriate;
- API client boundaries;
- no hidden network calls inside presentational components;
- no duplicated lifecycle/business rules in the frontend;
- test-friendly state boundaries.

## Evaluation

A UI REQ satisfies this profile only if:

- the layout is coherent for enterprise use;
- capability structure matches the REQ scope;
- loading, error, empty, and permission states are represented where relevant;
- accessibility is considered;
- the UI avoids brand cloning or affiliation claims;
- generated docs mention relevant assumptions;
- primary user flows are locally exercisable or documented with concrete checks.

## Gate Impact

GATE should BLOCK promotion when:

- acceptance-critical UI behavior is missing;
- a multi-capability console is collapsed into a superficial single-page dashboard;
- loading/error/empty states are ignored for interactive flows;
- errors are invisible;
- UI cannot be exercised locally and no manual smoke path exists;
- fake data is presented as real;
- selected design profile is ignored;
- frontend duplicates backend lifecycle, archive eligibility, validation, export, or AI authorization rules.

GATE may WARN when:

- visual polish is incomplete but behavior and state evidence are present;
- automated UI tests are unavailable but a clear manual smoke path exists;
- a configuration page is UI-local only and persistence is explicitly out of scope.