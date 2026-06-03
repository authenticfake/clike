## Lane Guide — ci

### Tools
- tests: Jenkins should execute deterministic tests for Python units, integration contracts, API contracts, workflow idempotency, manifest validation, and security checks.
- lint: Run the selected Python and infrastructure linters from the generated project.
- types: Run type checks when Python modules declare type checking as part of KIT output.
- security: Run secret scanning, dependency checks where tooling is available, and validation for deny-by-default auth behavior.
- build: Verify importability or package build plus deployment manifest validation.

### CLI Examples
- Local: `python -m pytest /runs/kit/<REQ-ID>/test`
- Local all checks: `make test` only when KIT creates an explicit Makefile target
- Containerized: `docker run --rm -v "$PWD":/workspace -w /workspace python:3 python -m pytest /runs/kit/<REQ-ID>/test`

### Default Gate Policy
- min coverage: each REQ must show evidence for happy path, deny path where auth applies, failure path, side-effect assertions, and dependency contracts.
- max criticals: zero critical security findings and zero hardcoded secrets.
- required evidence: command output, test reports, lint reports where configured, security scan result, and manifest validation for infra.
- forbidden shortcuts: Jenkins stages that only echo success, skipped tests without documented reason, public network dependency for core validation.

### Enterprise Runner Notes
- SonarQube: Add source and test analysis stages after unit tests and before promotion.
- Jenkins: Use separate stages for setup, unit tests, integration tests, contract tests, security scan, manifest validation, and artifact archive.
- Credentials: Jenkins credentials must be injected securely and must not be written into artifacts.
- Promotion: Promotion requires passing canonical REQ gates and preserving plan.json dependency assumptions.

### TECH_CONSTRAINTS integration
- air-gap: CI must be runnable in restricted enterprise networks using internal registries and no public-cloud hosting.
- registries: Base images and dependencies should be resolved from approved internal registries where required.
- ci: Jenkins is the required CI capability.
- secrets: Jenkins must consume Vault or enterprise credentials without logging secret values.
- observability: CI smoke checks should verify metrics and health endpoints once implemented.