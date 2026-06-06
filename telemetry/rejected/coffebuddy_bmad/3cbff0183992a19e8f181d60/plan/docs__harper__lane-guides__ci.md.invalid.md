## Lane Guide — ci

### Lane Purpose
- Supports Jenkins-compatible verification and promotion evidence for CoffeeBuddy.
- Applies to command documentation, test execution, lint, type checks, security scans, build evidence, and runtime-profile validation.
- CI lane is most visible in REQ-005 but every REQ must leave deterministic evidence usable by Jenkins.

### Tools
- tests: run REQ-specific test suites with explicit commands and no hidden local assumptions.
- lint: run selected language and asset linters where KIT emits code or configuration.
- types: run Python type checks where selected during KIT.
- security: run secret scanning, dependency scanning, and configuration checks where tools are available.
- build: build package or container artifacts only from internal-compatible sources.

### CLI Examples
- Local: `python -m pytest /runs/kit/<REQ-ID>/test`
- Local full gate: `python -m pytest /runs/kit/<REQ-ID>/test && python -m ruff check /runs/kit/<REQ-ID>/src` when Ruff is selected.
- Containerized: `docker run --rm -v "$PWD":/workspace -w /workspace python:3.12-slim sh -lc "python -m pytest /runs/kit/<REQ-ID>/test"`
- Jenkins stage: `jenkins-agent run install test lint security build` is illustrative only; KIT must document actual project commands.

### Default Gate Policy
- min coverage: every REQ acceptance criterion must map to at least one deterministic test or reviewable artifact.
- max criticals: zero critical security findings, zero missing required output artifacts, zero unexplained skipped mandatory tests.
- required evidence: command list, test results, security scan or secret scan result, runtime-profile statement, and known limitations.
- forbidden shortcuts: unverifiable manual-only acceptance, hidden external dependencies, public-cloud-only CI steps, and missing failure-path tests.

### Enterprise Runner Notes
- SonarQube: recommended for Python and configuration analysis when enterprise runner has it available.
- Jenkins: primary CI system required by TECH_CONSTRAINTS; pipeline should separate install, test, lint, type, security, build, and evidence stages.
- Credentials: Jenkins secrets must come from approved secret bindings or Vault integration, never repository literals.
- Network: pipeline must be compatible with restricted network operation and internal artifact registries.

### TECH_CONSTRAINTS integration
- air-gap: full air-gap is not explicitly required, but restricted internal enterprise CI compatibility is required.
- registries: internal registry compatibility is expected for container and dependency promotion.
- ci: Jenkins is required.
- secrets: HashiCorp Vault-compatible secret supply must be supported.
- evaluation: checks must prove Slack workflow, no public-cloud hosting dependency, secret handling, and metrics exposure.