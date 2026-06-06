## Lane Guide — infra

### Tools
- tests: Validate Kubernetes manifests, internal ingress, Kong route assumptions, Vault secret references, Prometheus scrape configuration, probe paths, and runbook smoke checks.
- lint: Use manifest linting selected by KIT for Kubernetes and gateway descriptors.
- types: Not applicable unless infra schemas are generated.
- security: Run no-secret scans, internal-only ingress checks, least-privilege review, and OIDC boundary checks.
- build: Render or validate deployment descriptors without applying them to a real enterprise cluster.

### CLI Examples
- Local: `python -m pytest /runs/kit/<REQ-ID>/test/infra`
- Local security: `python -m pytest /runs/kit/<REQ-ID>/test/security`
- Containerized: `docker run --rm -v "$PWD":/workspace -w /workspace python:3 python -m pytest /runs/kit/<REQ-ID>/test/infra`

### Default Gate Policy
- min coverage: manifest parse validation, probe path alignment, internal-only ingress, Vault reference presence, metrics scrape path, and no-secret evidence.
- max criticals: zero hardcoded secrets, zero public ingress defaults, zero unauthenticated internal operations routes.
- required evidence: deployment descriptors consume app contracts, runbook exists, rollback notes exist, and Jenkins validation commands are documented.
- forbidden shortcuts: cloud-only deployment files, source rewrites inside infra REQs, placeholder secrets, and gateway rules that bypass OIDC.

### Enterprise Runner Notes
- SonarQube: Include infrastructure descriptors and scripts where supported.
- Jenkins: Run static validation before any environment-specific deployment. Archive rendered manifests and validation reports.
- Review: Platform and security reviewers should inspect ingress, gateway, secret, and service account boundaries before promotion.

### TECH_CONSTRAINTS integration
- air-gap: Deployment validation must not require public-cloud services.
- registries: Container image references should support internal registry substitution.
- platform: Kubernetes is the required deployment platform.
- ingress: nginx is the required ingress component.
- gateway: Kong Gateway is the required API gateway capability.
- identity: OIDC with Keycloak-compatible IdP protects internal REST APIs.
- secrets: HashiCorp Vault is the required enterprise secrets manager capability.
- observability: Prometheus and Grafana compatibility are required.