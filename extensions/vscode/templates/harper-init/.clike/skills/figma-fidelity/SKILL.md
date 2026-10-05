---
name: figma-fidelity
description: Generate frontend UI that faithfully reflects a Figma design when one is provided (remote Figma MCP or an attached export), and degrade gracefully to default-styled generation when no Figma source exists. Framework-agnostic; the stack comes from TECH_CONSTRAINTS.
phases: ["spec", "plan", "kit", "eval", "gate"]
lanes: ["frontend", "typescript", "javascript", "react", "nextjs", "angular", "svelte", "vue", "web", "html"]
domains: ["enterprise", "startup", "consumer", "developer-tooling", "ai-native"]
gate_required: true
obligations:
  - Declare the Figma source mode per REQ (mcp, attachment, or none)
  - When a Figma source exists, reproduce layout, hierarchy, primary components, and visible text from the referenced frame
  - Map each Figma frame to exactly one SPEC page REQ and record unmapped frames and pages as gaps
  - Implement the design in the stack declared in TECH_CONSTRAINTS, never assuming a framework
  - When no Figma source exists, apply a coherent default style and record it as an assumption
ui_obligations:
  - figma-source-mode-declared
  - frame-to-page-mapping
  - primary-components-reproduced
  - visible-text-matches-frame
  - default-style-recorded-when-no-source
eval_checks:
  - figma-source-mode-declared
  - frame-to-page-mapping-present-when-source
  - primary-components-present-when-source
  - frame-discrepancy-list-present-when-source
  - default-style-assumptions-recorded-when-no-source
gate_implications:
  - block-if-source-provided-and-page-has-no-frame-mapping
  - block-if-source-provided-and-primary-components-missing
  - warn-only-when-no-figma-source-provided
evidence_required:
  - Declared source mode (mcp | attachment | none)
  - Frame-to-page mapping table when a source was provided, or assumptions list when none
  - Per-page render evidence (component test or screenshot) compared against the frame when a source was provided
---

# Skill: Figma Fidelity

## Intent

Turn a Figma design into faithful, testable frontend pages when a design source is
available, while staying honest about gaps, and degrade gracefully to a coherent
default style when no Figma source is provided.

This skill governs **fidelity to the design source**. It composes with
`frontend-state-accessibility` (UI states, accessibility) and the selected design
profile; it does not replace them. The concrete framework, routing, styling, and
component library come from `docs/harper/TECH_CONSTRAINTS.yaml`.

## Use when

Use this skill when a frontend REQ should reproduce a specific Figma design provided
either through the remote Figma MCP (`https://mcp.figma.com/mcp`) or as an attached
export (image / PDF / HTML), or when the IDEA/SPEC references Figma frames as the
visual source of truth.

## Do not use when

Do not use this skill for backend-only logic, infrastructure, documentation-only work,
or frontend work that has no design source and no design intent to preserve.

## Source modes

- `mcp` — remote Figma MCP configured for the active executor (Claude or Codex).
  Highest fidelity: node tree, Auto Layout, component names, and Variables are the
  visual source of truth; prefer real node/component/variable names over guesses.
- `attachment` — a Figma export attached to the request and materialized under
  `runs/<phase>/attachments/` (HTML > PDF > image fidelity).
- `none` — no Figma source. Generate a coherent, accessible default style from the
  SPEC and record it as an assumption. This is a valid, non-blocking outcome.

## Signals

- The REQ, IDEA, or SPEC mentions Figma, a Figma file/frame/node, a design link, or an
  attached design export.
- A design profile is selected and acceptance criteria describe specific screens.
- The Figma MCP is configured for the executor.

## Required behavior

- Detect and declare the source mode for each FE REQ.
- In `mcp`/`attachment` mode, reproduce the frame's layout regions, primary components,
  and visible text; map every frame to exactly one page and report discrepancies.
- In `none` mode, apply a coherent default style and record the applied decisions as
  assumptions; never fabricate a specific design that was not provided.
- Keep generation framework-agnostic: resolve the stack from TECH_CONSTRAINTS.
- Preserve honesty: report ambiguous or missing frames instead of inventing content.

## Forbidden behavior

- Do not invent a Figma design or claim fidelity when no source was provided.
- Do not clone external brands or proprietary design systems.
- Do not hardcode a framework when TECH_CONSTRAINTS declares another.
- Do not silently drop frames or pages from the mapping.

## Evidence required

- Declared source mode.
- Frame-to-page mapping table (mcp/attachment) or assumptions list (none).
- Per-page render evidence compared against the frame when a source was provided.

## Repair guidance

- If a page has no frame mapping in source mode, add the mapping or record the page as
  a gap.
- If primary components are missing, add them or document why they are intentionally
  out of scope.
- If fidelity cannot be verified because no render tooling exists, document a manual
  verification path and keep generation consistent with the declared stack.

## Gate implications

Gate should BLOCK promotion when:
- a Figma source was provided and a page has no frame mapping;
- a Figma source was provided and a page omits its frame's primary components.

Gate should WARN (not block) when:
- no Figma source was provided: default-styled generation is acceptable and the applied
  style is recorded as an assumption;
- automated visual verification tooling is unavailable but manual evidence is documented.

## Examples

- A REQ with a Figma MCP link reproduces the dashboard frame's layout, cards, and
  labels, maps the frame to the page, and lists no discrepancies.
- A REQ with an attached HTML export rebuilds the page structure and records two minor
  spacing discrepancies.
- A REQ with no Figma source generates an accessible default layout and records the
  applied style as an assumption.

## Non-examples

- Claiming a page matches Figma when no design source was attached or linked.
- Cloning an external product's visual brand.