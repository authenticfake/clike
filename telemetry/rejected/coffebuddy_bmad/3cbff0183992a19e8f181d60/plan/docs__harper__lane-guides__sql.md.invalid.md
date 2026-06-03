## Lane Guide — sql

### Lane Purpose
- Supports Postgres persistence contracts for CoffeeBuddy domain records.
- Applies to schema contracts, migration-ready definitions, repository tests, indexes, constraints, and audit fields.
- SQL lane work must align with `coffeebuddy.core` data contracts and must not invent alternate entity names.

### Tools
- tests: run repository contract tests against a Postgres-compatible database or documented ephemeral Postgres test container.
- lint: use SQL formatting or migration linting selected during KIT when schema files are emitted.
- types: not generally applicable, but generated query models must align with Python typed contracts.
- security: scan for unsafe SQL construction, credential literals, overbroad privileges, and sensitive data exposure.
- build: migration packaging must be deterministic and suitable for on-prem deployment.

### CLI Examples
- Local: `python -m pytest /runs/kit/<REQ-ID>/test -k persistence`
- Local database: `docker run --rm -e POSTGRES_PASSWORD=postgres -p 5432:5432 postgres:16` when local Docker is available.
- Containerized: `docker compose -f /runs/kit/<REQ-ID>/test/docker-compose.postgres.yml up --abort-on-container-exit` if KIT emits compose assets.
- Migration check: use the migration tool selected by KIT and document exact commands in the REQ output.

### Default Gate Policy
- min coverage: all state-changing repository methods and schema constraints used by REQs must be tested.
- max criticals: zero destructive migrations without rollback notes, zero plaintext credentials, zero missing audit fields on lifecycle-bearing records.
- required evidence: schema contract tests, repository behavior tests, cutoff and idempotency persistence tests, and migration readiness notes.
- forbidden shortcuts: primary production storage in memory, schema names that diverge from PLAN data contracts, and unindexed idempotency keys.

### Enterprise Runner Notes
- SonarQube: include SQL or migration files where supported and flag unsafe query construction.
- Jenkins: provision Postgres service container or approved internal database fixture before repository tests.
- Change review: migrations must be reviewable, deterministic, and compatible with controlled on-prem rollout.
- Rollback: destructive changes require explicit mitigation or must be avoided for MVP slices.

### TECH_CONSTRAINTS integration
- air-gap: no full air-gap requirement is stated, but Postgres operation must work without public-cloud managed database dependency.
- registries: Postgres test images should come from internal registry when enterprise runner requires it.
- storage: Postgres is required.
- data sensitivity: internal employee order and preference data must be protected by schema, access, and audit practices.
- runtime: application repositories must be Python-compatible and Postgres-backed.