## Lane Guide — sql

### Tools
- tests: Validate schema creation, migrations, repository contract behavior, idempotency constraints, and rollback or forward-only migration safety where applicable.
- lint: Use SQL formatting or lint tooling selected by KIT. Keep migrations readable and reviewable.
- types: Not applicable unless a schema typing generator is introduced by KIT.
- security: Check for unsafe dynamic SQL, credential exposure, and migration scripts containing secrets.
- build: Verify migrations or schema definitions can be applied to a Postgres-compatible database in a clean environment.

### CLI Examples
- Local: `python -m pytest /runs/kit/<REQ-ID>/test/integration`
- Local migration check: `python -m pytest /runs/kit/<REQ-ID>/test/contracts -k migration`
- Containerized: `docker compose run --rm test python -m pytest /runs/kit/<REQ-ID>/test/integration` when KIT supplies compose assets

### Default Gate Policy
- min coverage: repository and migration behavior must cover create, read, update, idempotency, and invalid-state rejection.
- max criticals: zero hardcoded credentials or destructive migration behavior without explicit acceptance.
- required evidence: Postgres is the primary persistence target, schemas match data contracts, and tests verify audit and idempotency fields.
- forbidden shortcuts: schema defined only in prose, local-only in-memory storage as primary, duplicate table ownership across feature modules.

### Enterprise Runner Notes
- SonarQube: Include SQL and migration files where supported. Flag dynamic SQL and credential patterns.
- Jenkins: Run migration checks against an ephemeral Postgres-compatible service when available. Publish migration logs and test reports.
- Database lifecycle: Prefer clean database setup per test run to avoid hidden state.

### TECH_CONSTRAINTS integration
- air-gap: Database tests must run without public services.
- registries: Container images for Postgres-compatible testing should come from approved internal registries when required.
- storage: Postgres is the required storage technology.
- data sensitivity: Internal employee preference and coffee order data must not be logged as raw fixture secrets or production data.
- on-prem: Connection settings must align with Kubernetes and Vault-provided configuration.