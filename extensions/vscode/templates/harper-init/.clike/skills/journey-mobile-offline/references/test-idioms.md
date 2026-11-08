# Test idioms: mobile and offline

Fake network, fake server and fake clock; storage is real (in a temp location) so restarts are real.

## TypeScript / web

- React Native / PWA: the sync engine as plain TypeScript tested with vitest or Jest; the network adapter returns offline/online; storage in an in-memory or temp-file implementation of the same interface; recreate the engine to simulate a restart.
- PWA: keep the service worker's caching and queue logic in plain functions tested with vitest; Playwright `context.setOffline(true)` for the journey.
- Device E2E: Detox or Maestro flows (non-blocking unless an emulator is provided).

## Mobile

- Android: Room with a file-backed database in a temp folder (an in-memory one loses its data on reopen, so it cannot prove MOB-01), WorkManager test helpers (`TestDriver`) for deferred sync, Espresso for screens; permission denial with `UiAutomator` or a fake permission provider.
- iOS: XCTest with an in-memory store, a URLProtocol stub for the network, XCUITest for screens; `XCUIApplication.resetAuthorizationStatus` for permissions.
- Flutter: `flutter_test` with fake repositories; `integration_test` for device flows.

## Java

- Kotlin/Java sync logic in plain JVM tests with fakes for network and clock; MockWebServer for the server side.

## .NET

- .NET MAUI: sync and storage in a class library tested with xUnit; fakes for connectivity (`IConnectivity`) and permissions.
