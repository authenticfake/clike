---
name: enterprise-console
description: Clean, structured, high-trust enterprise console UI for internal platforms and operational dashboards.
domains: ["enterprise", "developer-tooling", "ai-native"]
lanes: ["frontend", "typescript", "nextjs", "react"]
inspired_by: ["IBM Carbon", "HashiCorp", "Linear", "Cohere"]
strictness: "medium"
---

# Enterprise Console Design Profile

## Intent

Use this profile for enterprise consoles, internal platforms, admin dashboards, observability views, and AI-native control planes.

## Visual Principles

- Clear hierarchy over decorative visuals.
- Dense but readable information layout.
- Strong empty, loading, and error states.
- Minimal color usage for status and action emphasis.
- Consistent spacing and alignment.
- Accessible contrast and keyboard-friendly interactions.

## UX Principles

- Make system state obvious.
- Make user actions reversible or confirm destructive actions.
- Prefer tables, panels, filters, timelines, and detail drawers for operational workflows.
- Avoid playful consumer-only patterns unless the SPEC explicitly asks for them.
- Use clear labels and practical microcopy.

## Evaluation

A UI REQ satisfies this profile only if:
- the layout is coherent for enterprise use;
- loading, error, and empty states are represented;
- accessibility is considered;
- the UI avoids brand cloning or affiliation claims;
- generated docs mention relevant assumptions.
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
