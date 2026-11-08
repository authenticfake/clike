---
name: journey-mobile-offline
description: Use when a mobile app, PWA or field/operator app must work with intermittent connectivity or device capabilities, to prove offline work survives restarts, syncs exactly once, surfaces conflicts, handles denied permissions and resumes interrupted flows.
phases: ["spec", "plan", "kit", "eval", "gate"]
lanes: ["mobile", "typescript", "frontend", "java", "dotnet"]
domains: ["consumer", "startup", "enterprise", "industrial", "logistics"]
runtime_profiles: ["local", "cloud", "local-cloud", "edge", "hybrid"]
gate_required: true
scenario_prefix: MOB
scenarios:
  - MOB-01 | required | Offline work persists | When the user creates or edits data while offline, the system shall store it locally, show it as pending and keep it across an app restart.
  - MOB-02 | required | Sync exactly once | When connectivity returns, the system shall send the pending changes in order, each applied once on the server even if a send is retried, and mark them synced.
  - MOB-03 | required | Sync conflict surfaced | If a pending change conflicts with a newer server version, then the system shall show the conflict to the user with a way to resolve it and never overwrite silently.
  - MOB-04 | required | Sync failure visible | If a pending change is rejected or keeps failing, then the system shall show which item failed and why, and let the user retry or discard it.
  - MOB-05 | conditional | [Camera, location, notifications or other device permissions used] Permission denied | If the user denies a device permission, then the system shall explain what is unavailable and offer an alternative path, without crashing or looping on the prompt.
  - MOB-06 | conditional | [Multi-step forms or long flows] Interrupted flow resumes | If the app is sent to the background or killed in the middle of a flow, then the system shall restore the flow at the same step with the entered data.
  - MOB-07 | conditional | [Large offline data] Local storage limits | If local storage approaches its limit, then the system shall warn the user and keep pending changes rather than evicting them.
obligations:
  - Keep the network, storage and device capabilities behind adapters with fakes for tests
  - Give every offline change a client id so the server can deduplicate retries
  - Prove each included scenario with a blocking check recorded in docs/ACCEPTANCE.json
eval_checks:
  - scenario-coverage
gate_implications:
  - block-if-included-scenario-unproven
  - block-if-local-changes-can-be-lost
evidence_required:
  - One blocking check per included scenario, named in ACCEPTANCE.json
---

# Journey: Mobile and Offline

## Intent

Field and mobile users lose connectivity, switch apps, deny permissions and come back hours later.
A feature that works only online with a fresh app is not done. Each case below is a tested scenario;
the offline UI states of journey-ui-states (UI-05) cover the screen, this journey covers the data.

## Use when

Native or cross-platform mobile apps, PWAs with offline mode, tablet or handheld operator apps,
local storage and synchronization, device APIs (camera, location, push).

## Do not use when

Always-online web pages (use journey-ui-states UI-05), server-only work.

## How the pipeline uses it

- **SPEC**: list every scenario in `## Scenarios`; state the conflict policy (who wins, how the user
  resolves), what is available offline and the retention of pending data.
- **PLAN**: the REQ that introduces local storage and sync owns MOB-01..04; feature REQs own MOB-05/06
  for their screens.
- **KIT**: sync logic tested against a fake server and a fake clock; device E2E (emulator) is a
  non-blocking case with `environment_requirements` unless the eval provides a device.

## Valid exclusions

- Read-only offline cache: MOB-02/03/04 excluded, MOB-01 reduced to "cached data shown with its age".
- No device permissions: MOB-05.
- Not valid: "connectivity is good on site".

## Proof per scenario

- MOB-01: write through the store while the fake network is offline, recreate the app/store from
  disk, assert the pending item.
- MOB-02: go online with a fake server that fails the first send after applying it; assert one
  server record (client id) and the synced state.
- MOB-03: server holds a newer version; assert the conflict UI and both versions available.
- MOB-05: permission adapter returns denied; assert the explanation text and the alternative action.

## Forbidden

- Assuming connectivity; discarding local changes on reconnect or logout without asking.
- Unit tests that need real hardware or a real backend.
- Claiming offline support when only static assets are cached.

## References

- references/test-idioms.md
