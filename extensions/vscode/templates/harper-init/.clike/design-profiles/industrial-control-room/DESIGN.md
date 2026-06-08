---
name: industrial-control-room
description: High-trust, data-dense, operator-focused UI for industrial monitoring, manufacturing workflows, and control-room dashboards.
domains: ["industrial", "manufacturing"]
lanes: ["frontend", "typescript", "nextjs", "react"]
inspired_by: ["IBM Carbon", "ClickHouse", "BMW", "NVIDIA"]
strictness: "medium"
ui_obligations:
  - status-severity-states
  - stale-disconnected-state
  - safe-command-flows
  - operator-confidence-cues
accessibility_expectations:
  - high-contrast-status
  - keyboard-and-large-targets
  - unambiguous-state-labels
eval_checks:
  - status-states-tested
  - stale-state-tested
  - safe-command-confirmation-tested
gate_implications:
  - block-if-no-stale-state
  - block-if-unsafe-command-without-confirmation
---

# Industrial Control Room Design Profile

## Intent

Use this profile for industrial dashboards, manufacturing consoles, shop-floor monitoring, telemetry views, and operational control-room experiences.

## Visual Principles

- Prioritize clarity, state visibility, and operator confidence.
- Use dense but readable layouts for telemetry and process status.
- Use color primarily for severity, status, alarms, and action priority.
- Avoid decorative visuals that reduce scan speed.
- Keep typography, spacing, and alignment consistent.
- Make dangerous or irreversible actions visually distinct and confirmation-based.

## UX Principles

- Current system state must be visible.
- Alarm, degraded, offline, warning, and nominal states must be distinguishable.
- Prefer dashboards, tables, timelines, status cards, and detail panels.
- Do not hide operationally critical information behind excessive animations.
- Provide clear empty, loading, stale-data, and disconnected states.
- Treat command/write flows as safety-sensitive.

## Evaluation

A UI REQ satisfies this profile only if:
- operator state visibility is clear;
- status and severity states are represented;
- error/disconnected/stale-data states are considered;
- unsafe actions are not made casual;
- generated docs mention runtime and safety assumptions.
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

## Use when

Use for operator-facing industrial control rooms, SCADA/operations consoles, and safety-critical monitoring UI.

## Do not use when

Do not use for consumer marketing pages or backend-only REQs with no operator UI.


## Accessibility Expectations

- Status and severity must be distinguishable beyond color (high-contrast, icon/label), never color-only.
- All critical controls must be keyboard-operable with large, unambiguous targets for gloved/field use.
- Stale/disconnected and alarm states must be announced with explicit, unambiguous labels, not silent styling.
