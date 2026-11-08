---
name: web-e2e-harness
description: Use when a REQ ships or tests a web UI, to make the frontend build, component tests and browser journeys run the same way in the CLike eval sandbox as on a laptop — deterministic installs, a started app, loopback-safe auth and stable selectors.
phases: ["plan", "kit", "eval", "gate"]
lanes: ["typescript", "frontend", "nextjs", "react", "web", "node"]
domains: ["enterprise", "startup", "consumer", "developer-tooling", "ai-native"]
runtime_profiles: ["local", "cloud", "local-cloud", "on-prem", "hybrid", "air-gapped"]
gate_required: true
obligations:
  - Install dependencies from the lockfile only, and declare the Node version the project uses
  - Start the application under test from the test runner itself, on a loopback port, and wait for it to answer
  - Run auth and cookies over the HTTP loopback origin the eval uses (no Secure-only cookie without HTTPS)
  - Select elements by role, label or test id, never by generated class names or layout position
  - Wait on conditions (a visible element, a network response), never on fixed sleeps
  - Prove every UI journey scenario with a browser test that asserts what the user sees, including error text
eval_checks:
  - frontend-build-passes
  - component-tests-cover-ui-states
  - browser-journeys-run-against-started-app
gate_implications:
  - block-if-e2e-depends-on-a-manually-started-server
  - block-if-selectors-or-timing-are-unstable
evidence_required:
  - The test runner configuration that starts the app (command, port, readiness URL)
  - One browser test per UI journey scenario, tagged with the scenario id
---

# Web E2E Harness

## Intent

Frontend REQs lose most of their eval cycles to the harness, not to the product: an install that
differs from the lockfile, a browser test that expects a server nobody started, a session cookie
marked Secure on an HTTP loopback origin, a selector that breaks when a class name changes, a fixed
sleep that is too short in the sandbox. This skill makes the frontend checks deterministic so that a
failing check means a product defect.

## Use when

- The REQ adds or changes pages, forms, navigation, client-side state or an API client.
- The LTC runs a frontend build, component tests (Vitest/Jest with Testing Library) or browser tests
  (Playwright or the lane's equivalent).
- A UI journey scenario (journey-ui-states, journey-identity-access) is owned by the REQ.

## Do not use when

The REQ has no web user interface (backend service, batch job, infrastructure, PLC logic, a native
mobile app with its own device harness).

## Install and build

- `npm ci` (or the lockfile command of the package manager in use), never `npm install`, in CI and in
  the LTC; commit the lockfile. Declare the Node version (`engines.node`, `.nvmrc`) and keep it equal
  to the eval environment's.
- Do not add dependencies the REQ does not need; a new dependency goes in the REQ that owns the
  package manifest seam, with the lockfile updated in the same KIT.
- The build check runs the production build (`next build`, `vite build`) with type checking on.

## Start the app from the test runner

- Playwright: `webServer` in `playwright.config` with the start command, a loopback `url`
  (`http://127.0.0.1:<port>`), `reuseExistingServer: !process.env.CI` and a timeout that covers a cold
  build. The same `baseURL` in `use`.
- Backend needed by the journey: start it from `webServer` too (an array of servers), or mock it at
  the network boundary (route interception or a mock service worker) — and say which in HOWTO.
- Never rely on a server started by hand or by a previous check.

## Auth and cookies on loopback

- The eval reaches the app over HTTP on 127.0.0.1. A cookie with `Secure` is dropped there: set
  `Secure` only when the request is HTTPS (or from configuration), keep `SameSite` explicit, and test
  the login over the same origin the browser test uses.
- Prefer a login helper that signs in through the UI once and saves `storageState`, reused by the
  journeys that need an authenticated user; keep one journey that exercises the real login form.
- Session expiry and permission-denied journeys use controlled clocks or test accounts, not real
  waiting.

## Stable tests

- Locate by role and accessible name (`getByRole('button', { name: 'Salva' })`), by label, or by
  `data-testid` for elements without an accessible name. Never by CSS class, nth-child or text that
  changes with data.
- Wait on conditions: `await expect(locator).toBeVisible()`, `page.waitForResponse(...)`. No
  `waitForTimeout` except to prove a debounce, documented.
- Assert what the user sees: the error message text, the empty-state text, the disabled state of the
  submit button while pending, the focus after an error.
- Each test owns its data (fixtures created and removed by the test); tests run in any order.

## Component tests

- Testing Library tests for each UI state of a data surface: loading, empty, error (with the message),
  success, permission denied, pending submit. Mock the API client at its boundary, not `fetch` deep
  inside components.

## Forbidden behavior

- Browser tests that pass only with a running dev server or a developer's local data.
- Sleeps as synchronization; selectors on generated class names.
- Asserting only that a request returned 4xx without asserting the message the user sees.
- Disabling a failing browser test, raising timeouts to hide slowness, or marking the e2e check
  non-blocking to pass the gate.

## Gate implications

Gate blocks when browser journeys depend on a server the test runner does not start, when a UI
journey scenario has no browser test, or when the e2e check is flaky (passes only on retry). Gate may
warn when a journey mocks the backend at the network boundary and HOWTO says so.
