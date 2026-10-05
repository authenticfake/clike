---
name: design-tokens-sync
description: Use named design tokens (color, spacing, typography, radius) instead of magic values, sourced from Figma Variables when an MCP source is available and mapped to the project's token system. Advisory by default.
phases: ["plan", "kit", "eval", "gate"]
lanes: ["frontend", "typescript", "javascript", "react", "nextjs", "angular", "svelte", "vue", "web", "html"]
domains: ["enterprise", "startup", "consumer", "developer-tooling", "ai-native"]
gate_required: false
obligations:
  - Use named tokens for themed properties instead of hardcoded magic values
  - When a Figma MCP source exists, map Figma Variables to the project token names and preserve the Figma variable name in the mapping
  - Resolve the token system from TECH_CONSTRAINTS and never introduce a competing token system
  - When no token source exists, define a small coherent token set and record it as an assumption
ui_obligations:
  - named-tokens-used
  - figma-variable-to-token-map-when-mcp
  - single-token-system
eval_checks:
  - themed-properties-use-named-tokens
  - figma-variable-token-map-present-when-mcp
  - no-duplicate-token-systems
gate_implications:
  - warn-on-magic-values
  - warn-on-duplicate-token-systems
evidence_required:
  - Token map (Figma Variable to project token) when applicable, or the recorded default token set
  - List of remaining magic values with justification
---

# Skill: Design Tokens Sync

## Intent

Keep visual values expressed as named design tokens instead of magic values, and — when
a Figma MCP source is available — derive those tokens from Figma Variables, mapping them
onto the project's existing token system (Code Connect code-syntax when present).

This skill is **advisory** (`gate_required: false`): it surfaces findings and does not
block promotion on token adherence unless a pack or design profile elevates it.

## Use when

Use this skill for frontend REQs that produce themed UI, especially when a design system
or Figma Variables are available.

## Do not use when

Do not use this skill for backend-only, infrastructure, or documentation-only work.

## Behavior by source

- Figma MCP available: read Variables, map Figma variable names to project token names,
  use the project tokens in code, and record the mapping.
- No Variables / attachment-only / no Figma: define a small coherent token set, apply it
  consistently, and record it as an assumption.

## Stack resolution

Read `docs/harper/TECH_CONSTRAINTS.yaml` to find where tokens live for the declared
stack (CSS custom properties, a theme config, a tokens module, etc.) and use that single
location. Do not invent a second token system.

## Evidence required

- Token map (Figma Variable to project token) for MCP sources, or the recorded default
  token set.
- List of any remaining magic values with justification.

## Gate implications

Advisory: surface magic values and duplicate token systems as findings. Promotion is not
blocked on token adherence unless a pack or design profile marks it required.
