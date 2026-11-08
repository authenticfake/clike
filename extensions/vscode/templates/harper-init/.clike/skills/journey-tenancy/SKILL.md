---
name: journey-tenancy
description: Use when one deployment serves several customers, organisations or workspaces, to prove tenant isolation everywhere data can flow — requests, lists, search, exports, jobs, caches and files — and that cross-tenant access is impossible, audited when privileged, and purged on tenant deletion.
phases: ["spec", "plan", "kit", "eval", "gate"]
lanes: ["python", "typescript", "node", "java", "dotnet", "go", "rust", "backend"]
domains: ["enterprise", "startup", "consumer", "ai-native", "developer-tooling"]
runtime_profiles: ["local", "cloud", "local-cloud", "on-prem", "hybrid"]
gate_required: true
scenario_prefix: TEN
scenarios:
  - TEN-01 | required | Tenant from the identity | When a request is processed, the system shall take the tenant from the authenticated identity and ignore any tenant named in the path, query or body that differs from it.
  - TEN-02 | required | Cross-tenant access refused | If a user requests, updates or deletes a record of another tenant by its identifier, then the system shall answer as not found and change nothing.
  - TEN-03 | required | Collections filtered by tenant | When the system returns lists, search results, counts, reports or exports, it shall include only the caller's tenant data.
  - TEN-04 | required | Background work keeps the tenant | When a job, message, cache entry or stored file is created for a tenant, the system shall carry and enforce that tenant when it is processed or read.
  - TEN-05 | conditional | [Unique values per tenant] Uniqueness per tenant | When two tenants create records with the same business key, the system shall accept both; within one tenant it shall reject the duplicate.
  - TEN-06 | conditional | [Operators can act across tenants] Privileged cross-tenant action audited | When an operator acts on another tenant's data, the system shall require the operator role, record who, which tenant and why, and show it to that tenant's administrators where the SPEC says so.
  - TEN-07 | conditional | [Tenants can be offboarded] Tenant deletion purges data | When a tenant is deleted, the system shall remove or anonymise its data in every store within the stated period and prevent any further access.
obligations:
  - Enforce the tenant in one place (repository or query layer, row-level security), never by each handler remembering a filter
  - Seed at least two tenants in every test that touches tenant data
  - Prove each included scenario with a blocking check recorded in docs/ACCEPTANCE.json
eval_checks:
  - scenario-coverage
gate_implications:
  - block-if-included-scenario-unproven
  - block-if-cross-tenant-read-possible
evidence_required:
  - One blocking check per included scenario, named in ACCEPTANCE.json
---

# Journey: Tenancy and Data Isolation

## Intent

The most damaging multi-tenant defect is a quiet one: a list, an export or a background job that
forgets the tenant filter once. Tests with a single tenant can never catch it. This journey makes
isolation a tested scenario on every path data can take, always with two tenants seeded.

## Use when

Organisations, workspaces, accounts, customers or sites share one deployment and one or more stores.

## Do not use when

Single-customer deployments (one database per customer with no shared runtime) — state it in SPEC.

## How the pipeline uses it

- **SPEC**: list every scenario in `## Scenarios`; state the isolation model (shared tables with a
  tenant column, schema per tenant, database per tenant) and where it is enforced.
- **PLAN**: the REQ that creates the data layer owns TEN-01/02 and the enforcement point; every REQ
  that adds a list, export, job or cache owns TEN-03/04 for it.
- **KIT**: tests seed tenants A and B with look-alike data and assert B's data never appears to A.

## Valid exclusions

- No background work or caches: TEN-04. No privileged operators: TEN-06.
- Not valid: "the UI only shows the user's tenant" — isolation is proved at the API and data layer.

## Proof per scenario

- TEN-01: authenticate as A and send B's tenant id in the body; assert A's data is used.
- TEN-02: create a record as B, request it as A by id (read, update, delete); assert not found and B's record unchanged.
- TEN-03: seed both tenants with matching search terms; assert counts and exports contain only A.
- TEN-04: enqueue a job for A, process it, assert it never reads or writes B's data; cache keys include the tenant.

## Forbidden

- Tenant id taken from the client for authorization.
- Tests with one tenant only; filters added per handler instead of at the enforcement point.
- Cache keys, file paths or queue names without the tenant.

## References

- references/test-idioms.md
