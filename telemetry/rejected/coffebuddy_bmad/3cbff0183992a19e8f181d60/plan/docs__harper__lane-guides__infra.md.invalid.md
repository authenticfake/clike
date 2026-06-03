## Lane Guide — infra

### Lane Purpose
- Supports on-prem Kubernetes runtime, internal ingress, identity, secret management, observability, and deployment-profile readiness.
- Applies to nginx, Kong Gateway, Keycloak-compatible OIDC, Vault-compatible secrets, Prometheus, Grafana, Postgres, Kafka, and runtime operations.
- Infra lane work must harden required execution constraints without pulling unnecessary platform work before application slices.

### Tools
- tests: run deployment contract tests, configuration validation, OIDC deny-path tests, health/readiness tests, and metrics safety tests.
- lint: validate YAML or deployment templates where emitted by KIT.
- types: not generally applicable, except generated configuration models must align with Python typed settings.
- security: check for public ingress, hardcoded secrets, unauthenticated admin routes, overbroad service permissions, and sensitive metrics.
- build: produce deployment assets or profile documentation suitable for internal registry and on-prem Kubernetes promotion.

### CLI Examples
- Local: `python -m pytest /runs/kit/REQ-005/test`
- Local config validation: `python -m pytest /runs/kit/REQ-005/test -k deploy`
- Containerized: `docker run --rm -v "$PWD":/workspace -w /workspace python:3.12-slim python -m pytest /runs/kit/REQ-005/test`
- Template validation: run the YAML or Kubernetes validation command selected by KIT if deployment assets are emitted.

### Default Gate Policy
- min coverage: all required runtime constraints must have either executable tests or reviewable deployment contract evidence.
- max criticals: zero public ingress for internal APIs, zero hardcoded secrets, zero unauthenticated protected endpoints, zero public-cloud-required runtime paths.
- required evidence: OIDC deny tests, health/readiness tests, metrics tests, deployment profile, secret-source documentation, and Jenkins command notes.
- forbidden shortcuts: treating on-prem as future hardening, cloud-first manifests, placeholder Vault integration, unauthenticated operational APIs, and metrics with sensitive payloads.

### Enterprise Runner Notes
- SonarQube: inspect infra-as-code or configuration files where available.
- Jenkins: run deployment contract validation after application tests and before packaging evidence.
- Kubernetes: runtime profile targets on-prem Kubernetes with internal-only routes.
- Ingress: nginx and Kong Gateway are required integration assumptions.
- Identity: Keycloak-compatible OIDC is required for identity-protected internal APIs.
- Secrets: Vault-compatible secret injection is required.
- Observability: Prometheus scraping and Grafana dashboard expectations are required.

### TECH_CONSTRAINTS integration
- air-gap: full air-gap is not explicitly required, but internal-only and restricted network operation must be preserved.
- registries: deployment must be compatible with internal registry promotion.
- platform: Kubernetes is required.
- ingress: nginx and Kong Gateway are required.
- network: routes must be internal-only.
- idp: Keycloak-compatible OIDC is required despite spelling inconsistency in constraints.
- secrets: HashiCorp Vault is required.
- observability: Prometheus and Grafana are required.