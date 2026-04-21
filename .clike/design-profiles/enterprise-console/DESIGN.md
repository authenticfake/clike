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
- loading/error/empty states are represented;
- accessibility is considered;
- the UI avoids brand cloning or affiliation claims;
- the generated docs mention relevant assumptions.
