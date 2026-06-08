---
name: startup-product-app
description: Startup product app UX: onboarding, core UI states, responsive layout, accessible forms.
ui_obligations:
  - onboarding-flow
  - loading-empty-error-success-states
  - responsive-layout
accessibility_expectations:
  - accessible-forms
  - keyboard-navigable
  - meaningful-error-messages
eval_checks:
  - ui-states-tested
  - onboarding-tested
gate_implications:
  - block-if-missing-error-empty-states
---

# Design Profile: Startup Product App

## Intent

Guide UI/UX generation for startup, SaaS, MVP, product-led, and consumer-facing application flows.

This profile favors clear value communication, fast comprehension, low-friction workflows, accessible interactions, and practical product polish without decorative complexity.

It must not clone external brands, products, landing pages, or proprietary design systems.

## Use when

Use this profile when a REQ touches:

- SaaS product UI
- onboarding flows
- dashboards for startup/product teams
- user-facing forms
- self-service workflows
- product-led growth flows
- lightweight analytics screens
- consumer or prosumer web apps
- MVP validation interfaces

## Do not use when

Do not use this profile for:

- industrial control rooms
- dense enterprise admin consoles
- safety-critical operator interfaces
- developer tools
- backend-only work
- documentation-only work
- UI that must follow a customer-provided design system instead

## Visual principles

- Prefer clarity over novelty.
- Use generous spacing and simple hierarchy.
- Make the primary action obvious.
- Keep visual density low unless the REQ explicitly requires dense information display.
- Use consistent cards, panels, forms, and navigation patterns.
- Avoid ornamental effects that do not support the user task.
- Avoid copying the look of external SaaS brands.
- Keep empty states helpful and action-oriented.
- Keep error states calm, specific, and recoverable.

## UX principles

- Optimize for the first successful user action.
- Reduce setup friction.
- Make user progress visible.
- Make destructive or irreversible actions explicit.
- Show loading, empty, error, disabled, and success states.
- Prefer short, clear product copy.
- Avoid hidden dependencies and unexplained blocked states.
- Keep flows testable through deterministic state transitions.

## Components/patterns

Recommended patterns:

- onboarding checklist
- simple dashboard summary cards
- focused forms
- settings panels
- searchable tables for moderate datasets
- contextual empty states
- inline validation
- lightweight notification/toast patterns
- confirmation dialogs for destructive actions
- progressive disclosure for advanced options

Avoid:

- fake analytics with hardcoded success data
- excessive animation
- generic hero sections when the REQ requires application behavior
- modal-heavy workflows that block core tasks
- visually impressive but untestable mock screens

## Accessibility expectations

- Use semantic HTML or framework-equivalent accessible components.
- Ensure primary actions are keyboard reachable.
- Provide visible focus states when styling controls.
- Use labels for inputs and controls.
- Do not rely only on color to communicate status.
- Keep text readable at common viewport sizes.
- Provide clear error messages tied to the relevant field or action.

## Evidence required

A UI/UX-scoped REQ using this profile should produce evidence such as:

- source files implementing the required user flow
- tests or documented checks for primary and failure paths
- loading/empty/error/success state handling
- notes explaining how the design profile was applied
- HOWTO commands for frontend checks when available
- screenshots or manual verification notes when automated UI tests are not available

## Gate implications

Gate should block promotion when:

- the UI is decorative only and does not implement acceptance criteria
- primary user flow is missing
- required frontend checks fail
- loading, empty, or error states are missing for data-driven UI
- accessibility-critical controls are unlabeled or non-semantic
- the UI clones an external brand or product design

Gate may allow non-blocking warnings when:

- automated accessibility tooling is unavailable but semantic evidence is present
- visual snapshot tooling is unavailable but manual verification is documented
- advanced product analytics are explicitly out of scope for the current REQ
---

# CLike Promotable UI Generation Overlay

## Purpose

This design profile is a UI generation contract, not a visual mood board.

It must guide `/kit` toward UI code that is usable, testable, accessible, and promotable.

## Mandatory UI States

For interactive UI, generated code must consider:

- loading state;
- empty state;
- success/ready state;
- error state;
- disabled/submitting state;
- permission or unavailable state when relevant.

If a state is not applicable, document why.

## Interaction Rules

Generated UI should:

- make system state visible;
- make errors actionable;
- avoid silent failures;
- avoid destructive actions without confirmation;
- keep primary actions clear;
- use accessible labels;
- support keyboard interaction where practical;
- avoid fake data presented as real data;
- avoid brand cloning or copied external product layouts.

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
- test-friendly state boundaries;
- no hidden network calls inside presentational components;
- adapter/client separation for remote calls.

## Gate Impact

GATE should BLOCK promotion when:

- acceptance-critical UI behavior is missing;
- loading/error/empty states are ignored for interactive flows;
- errors are invisible;
- UI cannot be exercised locally;
- fake data is presented as real;
- selected design profile is ignored.

GATE may WARN when:

- visual polish is incomplete but behavior and state evidence are present;
- automated UI tests are unavailable but a clear manual smoke path exists.
