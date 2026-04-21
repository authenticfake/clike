# Skill: Mobile Offline Parity

## Intent

Ensure mobile and mobile-like requirements handle offline, intermittent connectivity, device constraints, and synchronization explicitly.

This skill applies to native mobile, hybrid mobile, PWA, field apps, and operator apps running in constrained environments.

## Use when

Use this skill when a REQ touches mobile apps, PWA behavior, offline mode, local storage, synchronization, field operations, device APIs, push notifications, camera, location, poor connectivity, or mobile UX.

## Do not use when

Do not use this skill for desktop-only backend services, server-only APIs, or frontend pages with no mobile/offline/device behavior.

## Signals

- The REQ mentions mobile, iOS, Android, React Native, Flutter, PWA, offline, sync, local storage, cache, device, camera, geolocation, push notification, field operator, tablet, handheld, or intermittent network.
- Acceptance criteria include offline behavior or mobile responsiveness.
- Design profile mentions mobile operator app, field app, industrial operator UI, or consumer mobile app.

## Required behavior

- Define online, offline, reconnecting, synced, conflict, and failed-sync states when relevant.
- Keep offline data boundaries explicit.
- Avoid silent data loss.
- Make synchronization idempotent where practical.
- Document device permission assumptions.
- Keep mobile UI accessible and usable on constrained screens.
- Provide local tests for offline state transitions when the stack allows it.
- Mark real device/cloud push checks as opt-in unless infrastructure is available.

## Forbidden behavior

- Do not assume always-on connectivity.
- Do not silently discard local changes after reconnect.
- Do not hardcode device identifiers or production endpoints.
- Do not require real device hardware for unit tests unless explicitly scoped.
- Do not claim offline support if only cached static UI exists.
- Do not ignore permission-denied states for device capabilities.

## Evidence required

- Tests or documented checks for offline/reconnect behavior.
- Source code showing explicit local persistence or cache boundaries when offline behavior is required.
- HOWTO explaining local simulation and optional device checks.
- UI states for sync progress, sync failure, and conflict when relevant.
- Configuration separating local/dev/prod runtime endpoints.

## Repair guidance

- If connectivity assumptions are implicit, add explicit network state handling.
- If sync can duplicate operations, add idempotency keys or conflict handling.
- If offline data is unbounded, document retention and cleanup assumptions.
- If tests require hardware, introduce adapter boundaries and local fakes.
- If permissions are missing, add permission-denied behavior and documentation.

## Gate implications

Gate should block promotion when:
- Offline/mobile behavior is acceptance-critical but not implemented.
- Data loss is possible during reconnect without documented handling.
- Required mobile checks fail.
- Device permissions are used without denied-state behavior.
- Runtime endpoints are hardcoded.

Gate may allow non-blocking warnings when:
- Real-device validation is documented but unavailable.
- Push notification or app-store checks are outside current REQ scope.

## Examples

- A field app REQ stores inspections locally, retries sync, and shows conflict status.
- A PWA REQ handles offline read-only mode and documents cache invalidation.
- A mobile form REQ validates locally and queues submission until reconnect.

## Non-examples

- A responsive page that claims mobile readiness without touch, layout, or state evidence.
- An offline toggle that only hides API errors.
- A mobile feature that crashes when geolocation permission is denied.
