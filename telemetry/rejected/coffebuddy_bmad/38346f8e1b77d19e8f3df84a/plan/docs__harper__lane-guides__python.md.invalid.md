## Lane Guide — python

### Tools
- tests: Use the repository-selected Python test runner when introduced by KIT. Prefer deterministic unit, integration, API contract, and security tests under the KIT test roots.
- lint: Use the project Python linter selected by KIT or repository standards. Do not invent multiple competing lint stacks.
- types: Use Python type checking when the generated project declares typed modules. Keep domain and handler interfaces type-readable.
- security: Include secret scanning, dependency vulnerability checks where tooling is available, and explicit tests for deny behavior.
- build: Package or import-check the generated `coffeebuddy` modules and verify no root-level ad-hoc `app.py` is required unless a REQ authorizes it.

### CLI Examples
- Local: `python -m pytest /runs/kit/<REQ-ID>/test`
- Local lint: `python -m ruff check /runs/kit/<REQ-ID>/src /runs/kit/<REQ-ID>/test` when Ruff is selected by KIT
- Local types: `python -m mypy /runs/kit/<REQ-ID>/src` when mypy or equivalent is selected by KIT
- Containerized: `docker run --rm -v "$PWD":/workspace -w /workspace python:3 python -m pytest /runs/kit/<REQ-ID>/test`

### Default Gate Policy
- min coverage: meaningful coverage for implemented business paths, with explicit happy, deny, failure, idempotency, and persistence assertions where applicable.
- max criticals: zero known critical security findings in generated Python code and dependency metadata.
- required evidence: tests pass, import boundaries match plan.json, no hardcoded secrets, runtime config fails closed, and selected skills are evidenced.
- forbidden shortcuts: in-memory-only primary persistence, duplicate domain models, unauthenticated Slack or operations handlers, and local-only configuration behavior.

### Enterprise Runner Notes
- SonarQube: Configure analysis to include generated Python source and tests, exclude transient cache files, and flag secrets or unsafe logging.
- Jenkins: Run tests before packaging. Add separate stages for lint, type checks when configured, security checks, and contract tests. Preserve test reports as artifacts.
- Artifact handling: Generated evidence should remain inside KIT run output until promotion is approved.

### TECH_CONSTRAINTS integration
- air-gap: Public network access must not be required for tests. Slack, OIDC, and external dependencies must have deterministic contract-test seams.
- registries: Use internal package registries when enterprise runner policy requires them. Do not assume public package download in on-prem validation.
- runtime: Python is the required application runtime.
- platform: Generated Python service must support on-prem Kubernetes execution and local deterministic test execution.
- identity: OIDC-protected internal APIs must preserve deny-by-default behavior.
- secrets: Slack, database, Kafka, and OIDC secrets must be supplied through Vault-compatible configuration, not hardcoded.