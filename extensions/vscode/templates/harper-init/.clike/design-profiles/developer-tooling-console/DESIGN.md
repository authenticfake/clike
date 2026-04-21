# Design Profile: Developer Tooling Console

## Intent

Guide UI/UX generation for developer tools, AI-native tooling, eval dashboards, code generation consoles, pipeline views, model/tool orchestration screens, logs, traces, and configuration interfaces.

This profile prioritizes evidence, traceability, reproducibility, dense-but-readable technical information, and safe action boundaries.

It must not clone external IDEs, cloud consoles, AI tools, or proprietary product interfaces.

## Use when

Use this profile when a REQ touches:

- developer portals
- AI/code generation dashboards
- Harper pipeline UI
- eval/gate result views
- logs and traces
- model routing controls
- tool adapter controls
- CI/test result panels
- configuration consoles
- prompt/eval management UI
- VS Code webview-like interfaces
- internal platform tooling

## Do not use when

Do not use this profile for:

- consumer product onboarding
- mobile field workflows
- industrial control rooms
- backend-only logic
- static documentation
- marketing pages
- UI that must follow a customer-provided design system instead

## Visual principles

- Favor dense clarity over decorative minimalism.
- Make status, evidence, and next action visible.
- Use stable layout regions for navigation, details, logs, and actions.
- Keep technical labels precise.
- Use hierarchy to separate summary, diagnostics, artifacts, and raw logs.
- Avoid hiding critical diagnostics behind purely visual affordances.
- Avoid excessive animation.
- Avoid brand cloning of existing developer tools.
- Use monospace formatting for code, paths, commands, JSON, diffs, and logs when appropriate.

## UX principles

- Make the system state inspectable.
- Make user actions reversible or dry-run by default when they can affect external systems.
- Separate read-only evidence from write/action controls.
- Show provenance: input, run ID, REQ-ID, model/provider when relevant, command, output, and artifact path.
- Make failures actionable.
- Make retry/repair paths explicit.
- Avoid magic buttons without explaining what will run.
- Prefer progressive detail: summary first, expandable diagnostics second, raw evidence last.

## Components/patterns

Recommended patterns:

- pipeline status timeline
- REQ status table
- eval result matrix
- gate decision panel
- artifact browser
- command preview
- dry-run action panel
- log viewer
- diff viewer
- JSON inspector
- model/tool routing summary
- evidence checklist
- warning/error callouts
- copy command button
- audit trail panel

Avoid:

- ambiguous "Fix everything" buttons
- write actions without preview
- model output presented as final truth
- hiding failed checks inside raw logs only
- dense unstructured text blobs
- dashboards with fake metrics
- UI that suggests promotion is possible without Gate evidence

## Accessibility expectations

- Tables and panels must have clear headings.
- Controls must have accessible names.
- Keyboard navigation must support primary workflows.
- Status must not rely only on color.
- Logs and code blocks must remain readable and scrollable.
- Error summaries should link or point to the relevant failing section when possible.
- Action buttons must clearly distinguish read-only, dry-run, and write behavior.

## Evidence required

A UI/UX-scoped REQ using this profile should produce evidence such as:

- source files implementing the developer workflow
- primary and failure-state tests or documented manual checks
- evidence/status mapping from backend/API data to UI state
- dry-run or preview behavior for write/action controls when relevant
- HOWTO commands for frontend checks
- notes explaining how artifacts, logs, or gate evidence are surfaced

## Gate implications

Gate should block promotion when:

- developer UI shows model output as authoritative without evidence
- eval/gate status is misrepresented
- write/action controls lack preview or approval semantics when required
- required frontend checks fail
- critical diagnostics are hidden or inaccessible
- the UI enables promotion-like behavior outside canonical Gate

Gate may allow non-blocking warnings when:

- raw log viewer is basic but evidence paths are available
- advanced filtering/search is future scope
- live backend data is unavailable but fixture-driven UI states are testable
