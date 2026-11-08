# Test idioms: UI states

Force each state through the data boundary and assert visible text and roles.

## TypeScript / web

- Component tests: vitest (or Jest) + Testing Library.
  - Loading: a never-resolving or delayed fake; `expect(screen.getByRole("status")).toHaveTextContent(/loading/i)`.
  - Empty / error: fake client or MSW handlers returning `[]` or a 500; `await screen.findByRole("alert")` and assert the product-language text and the retry button.
  - Double submit: `user.dblClick(submit)`; assert the fake was called once and `toBeDisabled()` while pending.
  - Validation: submit empty form, assert per-field messages (`toHaveAccessibleDescription`) and focus on the summary or first invalid field (`toHaveFocus()`).
- Accessibility: `jest-axe` / `vitest-axe` or `@axe-core/playwright` for automated checks; plus explicit `getByRole(name)` queries.
- Journeys: Playwright.
  - Offline: `context.setOffline(true)`, assert the offline message, restore, retry.
  - Timeout / errors: `page.route()` to delay or fail requests.
  - Keyboard: `page.keyboard.press("Tab")` sequences and `expect(locator).toBeFocused()`.
  - Language: launch with `locale` and assert translated text.
  - Responsive: `page.setViewportSize({ width: 360, height: 740 })`, assert actions visible and no horizontal overflow.

## Java

- Server-rendered UI: MockMvc / HtmlUnit to assert error, empty and denied templates render the catalog message.
- Desktop UI: TestFX (JavaFX) for states and keyboard traversal.
- Journeys: Playwright for Java with the same assertions as web.

## .NET

- Blazor: bUnit for component states (`cut.Find("[role=alert]").TextContent`).
- Razor / MVC: `WebApplicationFactory` + AngleSharp to assert rendered states.
- Desktop: UI automation (for example FlaUI) for keyboard and accessible names.
- Journeys: Playwright .NET.

## Mobile

- Component tests: React Native Testing Library, Compose UI tests (`onNodeWithText`, `assertIsNotEnabled`), SwiftUI/XCTest view tests.
- Accessibility: content descriptions / accessibility labels asserted; platform accessibility scanners where available.
- Device or emulator E2E (Espresso, XCUITest, Detox, Maestro): airplane mode for offline, slow network for loading, locale switch for language, small device profiles for layout.

## HMI screens (industrial)

- Screen states (comm loss, no data, alarm, denied) driven by a simulator; assert displayed text and colour/state indicator according to the alarm philosophy.
