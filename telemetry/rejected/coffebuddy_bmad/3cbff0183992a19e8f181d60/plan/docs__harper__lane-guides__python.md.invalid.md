## Lane Guide — python

### Lane Purpose
- Primary application lane for CoffeeBuddy service implementation.
- Applies to domain models, Slack event handling, order commands, orchestration logic, configuration, observability, and runtime operations modules.
- Expected package family is `coffeebuddy.*` under KIT source roots, with tests under the matching KIT test roots.

### Tools
- tests: use the project-selected Python test runner in KIT, with explicit unit, integration, contract, security, and operational tests where required by each REQ.
- lint: use a stable Python linter selected during KIT and document the command in REQ output.
- types: use Python typing and a stable type checker where selected during KIT; do not rely on untyped dynamic contracts for domain boundaries.
- security: use dependency and secret scanning appropriate for Python projects and verify no hardcoded Slack, database, Kafka, OIDC, or Vault secrets.
- build: produce an installable or runnable Python package shape suitable for containerization and on-prem Kubernetes deployment.

### CLI Examples
- Local: `python -m pytest /runs/kit/<REQ-ID>/test`
- Local lint: `python -m ruff check /runs/kit/<REQ-ID>/src /runs/kit/<REQ-ID>/test` if Ruff is selected by KIT.
- Local types: `python -m mypy /runs/kit/<REQ-ID>/src` if mypy is selected by KIT.
- Containerized: `docker run --rm -v "$PWD":/workspace -w /workspace python:3.12-slim python -m pytest /runs/kit/<REQ-ID>/test`
- Containerized build: `docker build -f Containerfile .` or equivalent only if KIT emits a container build asset.

### Default Gate Policy
- min coverage: meaningful coverage over business branches, with all REQ acceptance paths represented; do not accept only import or smoke tests.
- max criticals: zero critical security findings, zero hardcoded secrets, zero unauthenticated protected operations, zero missing required acceptance tests.
- required evidence: test logs, lint or documented lint decision, type evidence where selected, security scan or secret scan evidence, and runtime-profile notes.
- forbidden shortcuts: primary in-memory persistence for production paths, duplicate domain models, local-only secret loading, and public-cloud-only assumptions.

### Enterprise Runner Notes
- SonarQube: include Python source and tests in analysis when enterprise runner is available; treat critical vulnerabilities and secret findings as blockers.
- Jenkins: use a pipeline stage order of install, test, lint, type where configured, security scan, package, and runtime-profile evidence.
- Internal registry: package and container workflows must support internal registry promotion without public-cloud dependency.
- Restricted network: dependency acquisition must be compatible with mirrored or pre-approved internal package sources when required by enterprise policy.

### TECH_CONSTRAINTS integration
- air-gap: no explicit full air-gap requirement is stated, but restricted on-prem operation and internal-only routing must be preserved.
- registries: internal registry compatibility is expected for Kubernetes deployment, though a specific registry product is not named.
- runtime: Python is required.
- platform: Kubernetes is required.
- ingress: nginx and Kong Gateway internal ingress assumptions apply to REST endpoints.
- identity: OIDC with Keycloak-compatible provider assumptions apply where identity is required.
- secrets: HashiCorp Vault-compatible secret supply is required.
- observability: Prometheus metrics and Grafana dashboard expectations are required.