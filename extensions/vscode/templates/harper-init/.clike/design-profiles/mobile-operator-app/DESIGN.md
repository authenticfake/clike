---
name: mobile-operator-app
description: Mobile operator app UX: offline/sync/conflict states, large tap targets, interrupted-workflow recovery.
ui_obligations:
  - offline-sync-conflict-states
  - large-tap-targets
  - interrupted-workflow-recovery
  - minimal-typing
accessibility_expectations:
  - large-targets
  - readable-in-field-conditions
  - keyboard-and-screenreader-support
eval_checks:
  - offline-states-tested
  - recovery-flow-tested
gate_implications:
  - block-if-no-offline-states
  - block-if-data-loss-on-interruption
---

# Design Profile: Mobile Operator App

## Intent

Guide UI/UX generation for mobile, tablet, field-operator, technician, logistics, maintenance, and industrial/enterprise mobile workflows.

This profile prioritizes task completion under constrained conditions: small screens, gloves, poor connectivity, glare, urgency, interruptions, and offline/reconnect states.

It must not clone external products, device vendor interfaces, or proprietary design systems.

## Use when

Use this profile when a REQ touches:

- mobile apps
- tablet apps
- field operator workflows
- maintenance workflows
- inspection flows
- offline capture
- reconnect/sync behavior
- handheld device UI
- technician workflows
- industrial or enterprise mobile operation
- PWA/mobile-first application behavior

## Do not use when

Do not use this profile for:

- desktop-only enterprise consoles
- startup marketing/product pages
- backend-only services
- developer tooling consoles
- static documentation
- dense control-room dashboards intended for large displays

## Visual principles

- Prioritize readability at a glance.
- Use large tap targets.
- Keep layouts single-purpose and task-oriented.
- Avoid dense grids unless the device is tablet-sized and the REQ requires them.
- Use strong section grouping.
- Keep critical status visible without scrolling when possible.
- Make offline/sync state always visible when relevant.
- Avoid decorative animation.
- Avoid tiny icons without labels for critical actions.
- Use clear contrast and simple status hierarchy.

## UX principles

- Support interrupted workflows.
- Support offline, syncing, failed sync, and conflict states when relevant.
- Make permission-denied states actionable.
- Make destructive actions explicit and reversible when possible.
- Avoid silent data loss.
- Reduce typing when the context suggests field usage.
- Prefer scan/select/confirm flows over long free-text input where appropriate.
- Show progress for multi-step tasks.
- Preserve user input during network failures.

## Components/patterns

Recommended patterns:

- step-by-step task cards
- inspection checklist
- offline status banner
- sync queue indicator
- large primary action button
- bottom action bar
- simple tab navigation
- scan/input confirmation flow
- field validation summary
- reconnect retry panel
- conflict resolution screen
- permission recovery panel

Avoid:

- hidden sync status
- small critical controls
- desktop-only tables on mobile
- hover-only interactions
- long forms without sectioning
- modal flows that trap the operator during urgent actions

## Accessibility expectations

- Controls must be reachable by touch and keyboard/switch-equivalent patterns where applicable.
- Tap targets must be large enough for field usage.
- Important states must not rely only on color.
- Error text must be specific and visible near the action or field.
- Screen-reader labels must exist for critical controls.
- Focus order must follow the task flow.
- UI must remain understandable under zoom or larger text settings when the stack supports it.

## Evidence required

A UI/UX-scoped REQ using this profile should produce evidence such as:

- source files implementing the mobile/operator flow
- offline/sync/error state handling when relevant
- tests or documented checks for primary task and failure path
- mobile viewport/manual verification notes
- HOWTO commands for local UI validation
- notes explaining permission, offline, and reconnect assumptions

## Gate implications

Gate should block promotion when:

- the UI assumes always-on connectivity for an offline/mobile REQ
- sync status or failure is hidden
- user input can be silently lost
- critical actions are too ambiguous or unlabeled
- required frontend/mobile checks fail
- permission-denied behavior is missing when device APIs are used

Gate may allow non-blocking warnings when:

- real-device validation is unavailable but local/mobile viewport checks pass
- push notification or app-store checks are documented as external
- offline conflict resolution is future scope and explicitly out of scope for the REQ
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
