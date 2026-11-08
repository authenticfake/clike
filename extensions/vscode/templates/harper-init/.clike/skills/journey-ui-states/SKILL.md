---
name: journey-ui-states
description: Use when a capability has a user interface, to enumerate and prove every UI state (loading, empty, error, denied, offline, pending submit, validation, keyboard, screen reader, language) on each data surface and form.
phases: ["spec", "plan", "kit", "eval", "gate"]
lanes: ["frontend", "typescript", "mobile", "java", "dotnet"]
domains: ["enterprise", "startup", "consumer", "industrial", "ai-native", "developer-tooling"]
runtime_profiles: ["local", "cloud", "local-cloud", "on-prem", "hybrid", "air-gapped", "edge"]
gate_required: true
scenario_prefix: UI
scenarios:
  - UI-01 | required | Loading state | When data for a surface is being fetched, the system shall show a loading indicator that is announced to assistive technology and does not shift the layout when content arrives.
  - UI-02 | required | Empty state | When a data surface has nothing to show, the system shall show an empty state that explains why and offers the next action.
  - UI-03 | required | Error visible and actionable | If a request fails, then the system shall show a readable error message in product language with a retry or next step, and never a raw stack trace or error code alone.
  - UI-04 | required | Permission denied | If the user lacks permission for a surface or action, then the system shall show a permission-denied state that says what is missing and whom to ask.
  - UI-05 | required | Offline, timeout and retry | If the network is unavailable or a request times out, then the system shall tell the user, keep entered data and let them retry without reloading the page.
  - UI-06 | required | Pending submit and double-submit protection | When a form is submitted, the system shall disable the submit control and show progress until the request ends, so that a double click produces a single request.
  - UI-07 | required | Form validation inline and summary | If a submitted form has invalid fields, then the system shall show a message next to each field and a summary that moves focus to the first error.
  - UI-08 | required | Keyboard and focus | When a user operates the surface with the keyboard only, the system shall make every action reachable in a logical order with a visible focus indicator and manage focus on dialogs and route changes.
  - UI-09 | required | Screen-reader labels | When the surface is used with a screen reader, the system shall expose accessible names, roles and states for every control, and announce errors and status changes.
  - UI-10 | required | Product language of all messages | When any message is shown (labels, errors, empty states, confirmations), the system shall show it in the product language from the message catalog, with no untranslated or developer text.
  - UI-11 | conditional | [Narrow or mobile viewports supported] Responsive layout | When the surface is shown on a narrow viewport, the system shall keep all actions usable without horizontal scrolling or overlapping content.
obligations:
  - Enumerate every UI scenario in SPEC and include it or exclude it with a written reason
  - Map each included scenario ID to a REQ in plan.json and to an acceptance item prefixed with the ID
  - Prove each included scenario with one blocking check recorded in docs/ACCEPTANCE.json
  - Assert the visible message text, not only the presence of an element or a CSS class
  - Use semantic controls, accessible names and announced status regions
eval_checks:
  - scenario-coverage
  - visible-text-asserted
  - keyboard-flow-tested
gate_implications:
  - block-if-included-scenario-unproven
  - block-if-raw-error-shown-to-user
evidence_required:
  - One blocking check per included scenario, named in ACCEPTANCE.json
  - Exclusion reasons in SPEC for every scenario not included
---

# Journey: UI States

## Intent

A screen that renders the populated state is a picture, not a feature. Users meet the loading, empty, failed, denied, offline and invalid states constantly. This skill makes each state an explicit, tested scenario on every data surface and form, and it complements frontend-state-accessibility with traceable scenario IDs.

## Use when

- Use cases or REQs mention page, screen, view, dashboard, form, table, list, wizard, dialog, console, HMI screen, mobile app, operator UI.
- The KIT will produce `.tsx`, `.jsx`, `.vue`, `.svelte`, templates, XAML, Razor, mobile views or HMI screens.
- A product language or locale is set in the project.

## Do not use when

The REQ has no user interface (backend, batch, infrastructure, PLC logic without HMI).

## How the pipeline uses it

- **SPEC**: list every scenario in `## Scenarios`; include each `required` one or exclude it with a reason; state which surfaces and forms each applies to.
- **PLAN**: assign each included scenario ID to the REQ that owns the surface in plan.json `scenarios`; add acceptance items prefixed with the ID (for example `UI-03: when the orders request fails the table shows "We could not load orders. Retry"`).
- **KIT**: one blocking check per included scenario recorded in docs/ACCEPTANCE.json with the scenario ID; component tests for states, journey tests for keyboard and offline.
- **EVAL / GATE**: an included scenario without a passing blocking check blocks promotion.

## Valid exclusions

- No forms on the surface: UI-06 and UI-07 excluded.
- Single-language product with messages in a catalog already: UI-10 still applies (no developer text), the multi-locale part does not.
- Fixed-size operator panel: UI-11 excluded with the panel resolution stated.
- Not a valid reason: "the component library handles accessibility" without an assertion.

## Proof per scenario

- Control the data boundary (fake server, request interception, test double of the client) to force each state deterministically.
- Assert the exact or pattern-matched visible text and the role (`alert`, `status`, `dialog`), not a class name.
- Double submit: click twice fast, assert one request and the disabled control during pending.
- Keyboard: drive the journey with Tab, Shift+Tab, Enter, Space and Escape only; assert focus targets.
- Accessibility: run an automated checker where available and assert accessible names of key controls.
- Language: assert messages come from the catalog in the product language; fail on raw keys or English fallbacks when the product language differs.

## Forbidden

- Testing only the populated state.
- Asserting element presence without the message text.
- Raw exceptions, stack traces, HTTP codes or internal keys shown to users.
- Clickable non-semantic elements without role and keyboard handling.
- Real network calls or sleeps in component tests.
- Snapshot tests as the only proof of a state.

## References

- references/test-idioms.md
