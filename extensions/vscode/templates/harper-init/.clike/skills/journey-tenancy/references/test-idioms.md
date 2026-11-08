# Test idioms: tenancy

Two tenants with look-alike data in every test; assert what one tenant can never see.

## Python

- Fixtures `tenant_a`, `tenant_b` with users and records; `TestClient` with each user's token; parametrize over list, search, export endpoints for TEN-03.
- Row-level security (PostgreSQL): set the tenant setting per connection in the session factory and assert a raw query without the filter still returns only that tenant's rows.

## TypeScript / web

- supertest against the real handlers with two seeded tenants; a table of endpoints asserting no record of tenant B in tenant A's responses.

## Java

- Spring: Hibernate filter or `@TenantId`, tested with two tenants through MockMvc/RestAssured; JUnit `@ParameterizedTest` over endpoints.

## .NET

- EF Core global query filters on the tenant; `WebApplicationFactory` with two tenants; assert `IgnoreQueryFilters` is used only in the audited operator path.

## Go

- Tenant taken from the context set by the auth middleware; `httptest` table tests over endpoints with two tenants.

## Rust

- Tenant extracted from the authenticated identity in an axum extractor; `#[sqlx::test]` (reads `DATABASE_URL`, provisioned as `postgres_database`) with two tenants seeded; table tests over routes.
