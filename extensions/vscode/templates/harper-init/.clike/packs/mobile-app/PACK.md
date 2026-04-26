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

- mobile-offline-parity
- frontend-state-accessibility
- backend-contract-boundary when APIs are involved
- local-cloud-parity when sync/cloud services are involved
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
- PASS_WITH_WARNINGS is the final status.

Gate may allow non-blocking warnings when:

- Real-device validation is unavailable but simulator/local checks pass.
- App-store, push notification, or production mobile deployment checks are outside current REQ scope.
---

# CLike Promotable KIT Pack Overlay

## Purpose

This pack is a scenario-level orchestrator for CLike `/kit`.

It should help the model choose the right constraints, not generate decorative architecture.

## Default Promotable Skills

For code-producing REQs, prefer selecting relevant skills from:

- `promotable-code-boundary` when available;
- `backend-contract-boundary` for backend/API/service work;
- `frontend-state-accessibility` for UI work;
- `local-cloud-parity` for runtime or external dependencies;
- `eval-contract-writer` for executable validation;
- `gate-risk-reviewer` for promotion safety;
- `secure-config-secrets` when available for credentials/config/runtime;
- `observability-diagnostics` when available for supportability;
- scenario-specific skills already listed by this pack.

Do not select every skill automatically. Select only those justified by the REQ, lane, runtime profile, and acceptance criteria.

## KIT Behavior

When this pack is selected, KIT generation must:

- keep the implementation slice narrow and promotable;
- obey repository conventions before adding new layers;
- generate executable evidence;
- separate local deterministic validation from optional external validation;
- document runtime assumptions;
- preserve future compatibility for dependent REQs;
- avoid fake completeness and broad speculative architecture.

## Required Evidence

The KIT should provide:

- source mapped to the REQ;
- tests mapped to acceptance criteria;
- `ci/LTC.json`;
- `ci/HOWTO.md`;
- capability adherence notes in KIT documentation;
- external infrastructure assumptions when relevant.

## Gate Bias

This pack biases GATE toward safe promotion.

Promotion should require full `PASS`.

`PASS_WITH_WARNINGS` must not promote.

Warnings are acceptable only when the missing evidence is explicitly non-blocking, external, and documented with a deterministic local fallback.
