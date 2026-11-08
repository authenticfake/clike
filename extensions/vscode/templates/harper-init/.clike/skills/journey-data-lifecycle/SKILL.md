---
name: journey-data-lifecycle
description: Use when a capability creates, lists, updates or deletes records, to enumerate and prove the data lifecycle scenarios (validation, conflicts, empty, not found, partial failure) beyond the single successful create.
phases: ["spec", "plan", "kit", "eval", "gate"]
lanes: ["python", "typescript", "java", "dotnet", "go", "rust", "frontend", "backend", "mobile", "iac", "industrial", "plc-scada", "ai-native"]
domains: ["enterprise", "startup", "consumer", "industrial", "ai-native", "developer-tooling"]
runtime_profiles: ["local", "cloud", "local-cloud", "on-prem", "hybrid", "air-gapped", "edge"]
gate_required: true
scenario_prefix: DAT
scenarios:
  - DAT-01 | required | Create with valid data | When a user submits a complete and valid record, the system shall persist it once and show or return the created record with its identifier.
  - DAT-02 | required | Per-field validation | If a submitted record has missing or invalid fields, then the system shall reject it without persisting anything and report a readable message for each invalid field.
  - DAT-03 | required | Duplicate or uniqueness conflict | If a record would violate a uniqueness rule, then the system shall reject it with a conflict message that names the conflicting value and keep the existing record unchanged.
  - DAT-04 | required | Update with concurrency conflict | If a user saves changes to a record that was modified by someone else since it was read, then the system shall reject the stale write and tell the user to reload or merge.
  - DAT-05 | required | Delete with confirmation | When a user deletes a record, the system shall ask for confirmation, delete only after confirmation and remove the record from lists and lookups.
  - DAT-06 | required | Empty list | When a list or search has no records at all, the system shall show an empty state that explains why and offers the next action.
  - DAT-07 | required | Pagination, sort and filter | When a user pages, sorts or filters a list, the system shall return a stable, correctly ordered page and show a distinct no-results state when the filter matches nothing.
  - DAT-08 | required | Not found | If a user requests a record that does not exist or was deleted, then the system shall return not found and the UI shall show a not-found state with a way back.
  - DAT-09 | conditional | [Soft delete or undo offered] Soft delete and restore | When a user undoes or restores a deleted record within the allowed window, the system shall restore it intact and exclude it again from active lists when deleted.
  - DAT-10 | conditional | [Bulk operations exist] Bulk partial failure | If some items of a bulk operation fail, then the system shall report which items succeeded and which failed with the reason, and never report full success.
  - DAT-11 | conditional | [Audit required] Audit trail | When a record is created, changed or deleted, the system shall record who, when and what changed in an audit trail that ordinary users cannot alter.
  - DAT-12 | required | Boundary values | If a value is at, just inside or just outside its documented limit (length, range, zero, negative, empty), then the system shall accept exactly the values inside the limit and reject the others with the per-field message.
  - DAT-13 | conditional | [Records have dependent records] Delete with dependents | If a user deletes a record that other records depend on, then the system shall block the deletion with a message naming the dependents, or cascade exactly as the SPEC states.
  - DAT-14 | conditional | [Schema changes on tables that already hold data] Data-preserving migration | When a migration runs on a database that already holds data, the system shall preserve and convert the existing records, and running the migration again shall change nothing.
  - DAT-15 | conditional | [Dates and times are shown or entered] Time zones | When dates and times are stored, the system shall store them in UTC; when they are shown or entered, it shall use the user's time zone and state it where ambiguity matters.
  - DAT-16 | conditional | [One operation writes several records or stores] No partial write | If a step of a multi-record write fails, then the system shall leave none of the operation's changes in place and report the failure.
obligations:
  - Enumerate every DAT scenario in SPEC and include it or exclude it with a written reason
  - Map each included scenario ID to a REQ in plan.json and to an acceptance item prefixed with the ID
  - Prove each included scenario with one blocking check recorded in docs/ACCEPTANCE.json
  - Enforce validation and uniqueness on the server, with client validation as a convenience only
  - Prove failed writes leave persisted data unchanged
eval_checks:
  - scenario-coverage
  - failure-message-asserted
  - no-side-effect-on-failure-tested
gate_implications:
  - block-if-included-scenario-unproven
  - block-if-validation-only-client-side
evidence_required:
  - One blocking check per included scenario, named in ACCEPTANCE.json
  - Exclusion reasons in SPEC for every scenario not included
---

# Journey: Data Lifecycle

## Intent

Every entity has a life: created, validated, listed, found or not found, changed concurrently, deleted, sometimes restored and audited. This skill makes those journeys explicit so a CRUD slice is not promoted with only "create works" as evidence.

## Use when

- Use cases or REQs mention create, add, register, edit, update, delete, remove, archive, list, table, search, filter, sort, page, import, catalog, inventory, records, orders, items.
- A data model, migration, repository or API resource is introduced.
- Recipes, setpoints or configuration sets are stored on an industrial system.

## Do not use when

The REQ stores no user-managed records (pure computation, stateless proxy, read-only reporting over data another system owns).

## How the pipeline uses it

- **SPEC**: list every scenario in `## Scenarios`; include each `required` one or exclude it with a reason; include each `conditional` one when its bracketed condition holds.
- **PLAN**: assign each included scenario ID to one owning REQ in plan.json `scenarios`; add acceptance items prefixed with the ID (for example `DAT-04: a stale save returns 409 and the form shows "This record was changed by someone else"`).
- **KIT**: one blocking check per included scenario, recorded in docs/ACCEPTANCE.json with the scenario ID.
- **EVAL / GATE**: an included scenario without a passing blocking check blocks promotion.

## Valid exclusions

- Read-only reference data loaded by migration: DAT-02 to DAT-05 excluded, DAT-06 to DAT-08 remain.
- Single-writer system (one device, one operator, no concurrent edits): DAT-04 excluded with that reason; state how single-writer is guaranteed.
- No natural unique key: DAT-03 excluded with that reason.
- Not a valid reason: "the database will enforce it" without a test that exercises the constraint through the entry point.

## Proof per scenario

- Exercise the real persistence path (in-memory or containerized store with the same constraints), not a mock that returns success.
- Failure scenarios assert three things: the rejection code, the message text per field or conflict, and that stored data is unchanged afterwards.
- Concurrency: read version A twice, save the first, save the second, expect rejection.
- Pagination: seed more than one page, assert order, page size, last page and no duplicates across pages.
- UI scenarios assert the visible empty, no-results and not-found text and the offered action.

## Forbidden

- Happy-path-only tests.
- Asserting only status codes without the field or conflict message.
- Mocking the repository in the test that claims to prove a uniqueness or concurrency rule.
- Last-write-wins silently on shared records.
- Bulk operations that report success when any item failed.
- Hard delete without confirmation on user-facing data.

## References

- references/test-idioms.md
