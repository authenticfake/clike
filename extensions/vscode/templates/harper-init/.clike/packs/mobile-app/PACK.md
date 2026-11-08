---
name: mobile-app
description: Mobile app scenario: offline/sync states, touch ergonomics, interrupted-flow recovery.
obligations:
  - Handle offline/sync states
  - Optimize for touch and interrupted flows
eval_checks:
  - offline-handled
  - touch-targets-adequate
  - interrupted-flow-recovered
gate_implications:
  - block-if-no-offline-handling
evidence_required:
  - Mobile state tests
---

# Pack: Mobile App

## Intent

Guide CLike generation for mobile, tablet, PWA, hybrid, and field-operator applications where device constraints, offline behavior, permissions, and synchronization must be explicit.

This pack applies mobile discipline without forcing a specific mobile framework.

## Scenario signals

- Mobile, iOS, Android, React Native, Flutter, PWA, tablet, handheld, field operator, offline, sync, local storage, push notification, camera, location, QR code, device permission, or intermittent connectivity.
- Requirements involving mobile UX, offline capture, reconnect behavior, device APIs, or app-like frontend behavior.
- Design profile mobile-operator-app is selected.

## Use when

Use this pack for native mobile apps, hybrid apps, PWAs, mobile-first product flows, field apps, and tablet/operator apps.

## Do not use when

Do not use this pack for desktop-only admin consoles, backend services, or responsive web pages with no mobile/device/offline requirements.

## Required capabilities

Recommended skills:

- journey-mobile-offline
- journey-ui-states
- backend-contract-boundary when APIs are involved
- journey-runtime-config when sync/cloud services are involved
- eval-contract-writer
- gate-risk-reviewer

Recommended design profiles:

- mobile-operator-app for field and operator apps
- startup-product-app for consumer/mobile SaaS flows

## Runtime assumptions

- Connectivity may be intermittent.
- Device permissions may be denied.
- Local persistence may be required.
- Sync must be explicit and should avoid silent data loss.
- Real device checks may be external/non-blocking unless available.
- Local tests should use simulator/fake device boundaries when possible.

## Security/compliance assumptions

- Sensitive local data must be treated explicitly.
- Tokens and endpoints must not be hardcoded.
- Permission-denied states must be handled for device capabilities.
- Offline data retention and cleanup assumptions must be documented when relevant.

## Architecture constraints

- Separate device APIs behind small boundaries where practical.
- Separate local state, sync state, and remote API state.
- Avoid assuming always-on connectivity.
- Keep UI states clear for offline, syncing, failed sync, and conflict behavior.
- Avoid framework lock-in unless the REQ or repository dictates the stack.

## Eval expectations

- Tests or documented checks for offline/reconnect behavior when required.
- UI checks for mobile-critical flows.
- Local fake/simulator checks for device APIs where possible.
- HOWTO must document local checks and optional real-device checks.
- Build/lint/type checks must follow the project lane.

## Gate implications

Gate should block promotion when:

- Offline behavior is acceptance-critical but missing.
- Device permission failure states are ignored.
- Required mobile checks fail.
- Sync behavior can silently lose data.
- Runtime endpoints or credentials are hardcoded.

Gate may allow non-blocking warnings when:

- Real-device validation is unavailable but simulator/local checks pass.
- App-store, push notification, or production mobile deployment checks are outside current REQ scope.

---

# CLike Pack Overlay

## Skills

Select only the skills the REQ, lane, runtime profile and acceptance justify: the journeys whose
scenarios the REQ owns (`journey-*`), `eval-contract-writer` for every REQ that ships code,
`backend-contract-boundary` for backend contracts, `e2e-slice-runnability` for user or service
flows, plus the scenario-specific skills listed by this pack.

## Gate

The gate promotes on PASS and on PASS_WITH_WARNINGS (non-blocking checks failed or
environment-blocked, reported and tracked), unless the project enables strict warnings. A check
belongs in the blocking set when it proves an acceptance criterion or scenario in the sandbox; it is
non-blocking only when it needs infrastructure the sandbox does not have, with the reason stated.
