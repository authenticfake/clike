## Lane Guide — kafka

### Tools
- tests: Validate event contracts, producer and consumer behavior, retry handling, idempotency, dead-letter or terminal failure semantics where implemented, and local/on-prem configuration parity.
- lint: Use language-level linting for adapters and static validation for event schema files if generated.
- types: Event payload structures should be typed or schema-validated in the implementation language.
- security: Verify broker credentials are never hardcoded and event payloads do not expose secrets.
- build: Verify workflow modules import cleanly and event contract tests run without requiring a public broker.

### CLI Examples
- Local: `python -m pytest /runs/kit/<REQ-ID>/test -k workflow`
- Local contract: `python -m pytest /runs/kit/<REQ-ID>/test/contracts`
- Containerized: `docker compose run --rm test python -m pytest /runs/kit/<REQ-ID>/test` when KIT supplies a Kafka-compatible test harness

### Default Gate Policy
- min coverage: event happy path, retry path, duplicate delivery idempotency, terminal failure behavior where applicable, and persisted WorkflowEvent transitions.
- max criticals: zero hardcoded broker secrets or secret-bearing event logs.
- required evidence: event names are documented, idempotency is persisted, retry behavior is observable, and local tests preserve on-prem contract names.
- forbidden shortcuts: timer-only local workers as primary workflow implementation, duplicate queue ledgers, non-idempotent Slack message posting.

### Enterprise Runner Notes
- SonarQube: Analyze workflow adapter source and flag unsafe logging or broad exception swallowing.
- Jenkins: Run broker-independent contract tests first, then broker-backed integration tests when runner services are available.
- Artifact handling: Publish event contract documentation and workflow test reports.

### TECH_CONSTRAINTS integration
- air-gap: Tests must not rely on public Kafka services.
- registries: Kafka test images must use internal registries where enterprise policy requires them.
- messaging: Kafka is the required asynchronous workflow messaging technology where async behavior is needed.
- secrets: Broker credentials must use Vault-compatible configuration.
- on-prem: Worker configuration must support Kubernetes deployment and internal network routes.