## Lane Guide — kafka

### Lane Purpose
- Supports asynchronous CoffeeBuddy workflow events for reminders, cutoff handling, runner assignment, and final summary publication.
- Applies to event envelopes, topic naming, idempotent consumers, producer contracts, retry behavior, and replay safety.
- Kafka lane contracts are owned initially by REQ-001 and exercised primarily by REQ-004.

### Tools
- tests: use contract tests for event envelopes and integration tests with a Kafka-compatible test broker or deterministic adapter preserving Kafka semantics.
- lint: validate event schema files or constants for naming consistency where emitted.
- types: event payloads must align with typed Python models or equivalent schema definitions.
- security: verify no secrets in event payloads and no raw Slack tokens in logs or messages.
- build: package consumer and producer configuration in a deployment-compatible form.

### CLI Examples
- Local: `python -m pytest /runs/kit/<REQ-ID>/test -k kafka`
- Local broker: `docker compose -f /runs/kit/<REQ-ID>/test/docker-compose.kafka.yml up --abort-on-container-exit` if KIT emits compose assets.
- Containerized: `docker run --rm -v "$PWD":/workspace -w /workspace python:3.12-slim python -m pytest /runs/kit/<REQ-ID>/test -k event`
- Replay test: run the duplicate-event test command documented by KIT for REQ-004.

### Default Gate Policy
- min coverage: every produced and consumed event type has serialization, validation, and idempotency tests.
- max criticals: zero unversioned payloads, zero non-idempotent workflow consumers, zero secret-bearing messages.
- required evidence: event contract fixtures, duplicate delivery tests, malformed event tests, and replay-safe processing notes.
- forbidden shortcuts: local-memory-only production scheduling, unversioned topics or payloads, and consumers that mutate before validation.

### Enterprise Runner Notes
- SonarQube: inspect producer and consumer code for unsafe serialization and exception swallowing.
- Jenkins: use approved Kafka test service or deterministic adapter with explicit parity notes when broker integration is unavailable.
- Operations: document consumer group assumptions, retry behavior, dead-letter or quarantine strategy if implemented, and replay safety.
- Internal network: brokers are internal-only and must not require public cloud services.

### TECH_CONSTRAINTS integration
- air-gap: no full air-gap requirement is stated, but Kafka operation must be on-prem compatible.
- registries: Kafka test images should be internal-registry compatible when used in enterprise CI.
- messaging: Kafka is required.
- observability: Kafka workflow metrics must be Prometheus-compatible.
- security: event payloads must not contain Slack tokens or unnecessary employee preference detail.