# Test idioms: identity and access

Prove each IAM scenario through the real entry point, with a controlled clock and asserted message text.

## Python

- pytest + httpx `AsyncClient` / framework `TestClient` against the app factory with an in-memory or containerized store.
- Expiry, reset links, lockout windows: `freezegun` (`freeze_time`, `tick`) or an injected clock.
- Assert `response.status_code` and `response.json()["detail"]` (or the error body field) together.
- Logout / revocation: keep the cookie or bearer token, call logout, replay, expect 401.
- Parametrize the role matrix: `@pytest.mark.parametrize("role,expected", [...])` for IAM-08.

## TypeScript / web

- Unit and component: vitest + Testing Library; render the login form, submit wrong credentials, `expect(await screen.findByRole("alert")).toHaveTextContent(/invalid email or password/i)`.
- Timers: `vi.useFakeTimers()` for session expiry prompts.
- API: supertest or the framework test client against the real handlers.
- Journeys: Playwright; `page.getByLabel("Password").fill(...)`, `await expect(page.getByRole("alert")).toHaveText(...)`; use `context.clearCookies()` / stored state to test expiry and logout replay; `page.clock` for time.
- Permission deny: log in as a restricted user and assert the deny page text and that the action control is absent or disabled.

## Java

- JUnit 5 + Spring `MockMvc` (`with(user("u").roles("VIEWER"))`) or RestAssured against a started app.
- Assert `status().isForbidden()` and `jsonPath("$.message")`.
- Clock: inject `java.time.Clock`, use `Clock.fixed` / offset in tests.
- Journeys: Playwright for Java with the same visible-text assertions.

## .NET

- xUnit + `WebApplicationFactory<Program>`; a test authentication handler only for tests that are not proving authentication itself.
- Time: `TimeProvider` with `FakeTimeProvider`.
- Assert `HttpStatusCode.Forbidden` and the ProblemDetails `title`/`detail`.
- Journeys: Playwright .NET.

## Go

- `testing` + `httptest.NewServer` / `httptest.NewRecorder` on the real router and middleware.
- Inject a clock interface for expiry; table-driven tests for the role matrix.
- Assert status and decoded error body message.

## Mobile

- Component tests for login, error and deny screens (visible text, accessibility labels).
- Device or emulator E2E (for example Espresso, XCUITest, Detox, Maestro) for login, wrong password, session expiry and logout.
- Verify secure token storage is cleared on logout.

## IaC

- Plan-level policy tests (for example OPA/Conftest, Checkov, `terraform test`) that roles, policies and identity-provider settings grant least privilege, enforce MFA where required and set session lifetimes.

## PLC / SCADA / industrial

- Operator login and role levels on the HMI or SCADA layer tested against a simulator; critical commands rejected for insufficient level, with the alarm or message text asserted.
- Session timeout on the operator station returns to the read-only level.
