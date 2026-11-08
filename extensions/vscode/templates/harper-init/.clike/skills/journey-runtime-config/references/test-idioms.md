# Test idioms: runtime and configuration

Start the real entrypoint with controlled configuration; assert what starts, what fails and what is logged.

## Python

- Settings with pydantic-settings (or the framework's): `monkeypatch.setenv` / `delenv`, then build the app factory; CFG-02 asserts `pytest.raises(ValidationError)` naming the field.
- CFG-01: `TestClient(create_app())` with only `.env.example` values loaded (`dotenv_values`), call `/health`, assert the adapter class in use.
- CFG-04: `caplog` around a request carrying secrets; assert the masked form and that the raw values are absent.
- CFG-03: a small test that walks the candidate files with secret regexes (AWS/GCP keys, PEM private-key headers, `password=` in URLs) and fails on a hit.

## TypeScript / web

- Validate the environment with a schema (zod or similar) at startup; tests use `vi.stubEnv` and assert the thrown message names the variable.
- CFG-07: import the API client's route table (or collect `fetch` URLs through a typed client) and the server's route list, compare in a vitest test.
- Frontend: only `PUBLIC_`/`VITE_`/`NEXT_PUBLIC_` values reach the bundle; a test asserts no secret variable is referenced from client code.

## Java

- `@ConfigurationProperties` + `@Validated`; `new ApplicationContextRunner().withPropertyValues(...)` asserts startup failure and the property named (CFG-02) and the local profile's beans (CFG-01/06).
- Log redaction: a Logback `ListAppender` in the test, assert masked values.

## .NET

- Options with `ValidateDataAnnotations().ValidateOnStart()`; `WebApplicationFactory` with `ConfigureAppConfiguration` overrides; assert `OptionsValidationException` names the key.
- Logs: a test logger provider capturing messages; assert redaction.

## Go

- Config loaded into a struct (envconfig or own parser) returning an error naming the missing key; table-driven tests with `t.Setenv`.
- CFG-01: `httptest.NewServer` on the router built from local config; assert the fake adapter.

## Rust

- Config with `envy`/`figment` into a struct; tests with temp env (`temp-env` crate) assert the error names the key.
- Redaction: wrap secrets in `secrecy::SecretString` so `Debug` prints a mask; assert the formatted log line.

## IaC

- Plan-level tests (`terraform test`, Conftest/OPA, Checkov) that no secret is a literal, storage and endpoints are not public by default, and egress rules match the allowlist.
