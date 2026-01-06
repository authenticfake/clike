# SPEC — CoffeeBuddy (On-Prem)

## Problem
Coffee coordination in Slack is fragmented: messages get buried, someone forgets to pick up, and preferences are not captured. In regulated networks, cloud services are restricted, so the solution must run fully on-prem with enterprise components and SSO.

## Objectives
1) Complete a coffee run inside Slack within 2 minutes.  
2) Enforce fairness by balancing runner assignments over time.  
3) Persist preferences to pre-fill orders consistently.

## Scope
- Slack slash commands and interactive messages to create/join a run, select drinks, and confirm pickup.
- Automatic runner assignment and reminders.
- Order history and user preference storage.

## Non-Goals
- Payments, delivery, or vendor-specific POS integrations.

## Constraints
- Operate fully on-prem on Kubernetes behind WSO2 API Manager and NGINX ingress.
- Authenticate via Keycloak (OIDC); store secrets in Vault.
- Use PostgreSQL for persistence and Kafka for asynchronous processing.

## KPIs
- Median time from `/coffee` to confirmation ≤ 2 minutes.
- Runner fairness index ≥ 0.8.
- Error rate per run ≤ 1%.

measurement: KPIs are measured via application logs (structured), Prometheus metrics, and Slack event audit logs, aggregated daily and reported weekly in Grafana.

## Assumptions
- Slack enterprise app can be installed and events proxied internally.
- Users understand basic slash command flows.

## Risks
- Slack rate limits or interactive latency; mitigated via Kafka buffering.
- Misconfigured OIDC scopes; mitigated by standard Keycloak realm templates.

## Acceptance Criteria
- **REQ-001 — Create a coffee run via `/coffee`**  
  Test: functional (Slack events simulated via internal proxy)  
  Evidence: e2e test passes and logs captured
- **REQ-002 — Join/submit order with preferences**  
  Test: unit + functional  
  Evidence: unit coverage for preference model + e2e flow
- **REQ-003 — Automatic runner assignment**  
  Test: integration (deterministic assignment with tie-break rules)  
  Evidence: contract test verifying fairness index over a seeded dataset
- **REQ-004 — Reminders and status updates**  
  Test: scheduled job with time-shifted execution  
  Evidence: passing timer/queue tests and notification logs
- **REQ-005 — Order history and audit trail**  
  Test: integration (PostgreSQL)  
  Evidence: migration + repository tests, retention and PII policy checks
- **REQ-006 — Security baseline**  
  Test: SAST + secrets scanning  
  Evidence: clean reports (Semgrep/Bandit for polyglot modules, Vault policy checks)

## Sources & Evidence
- Slack API internal documentation (Events API and Interactivity).
- Enterprise runbooks for Kubernetes, Keycloak, WSO2, Vault, Kafka, and PostgreSQL.
- Test artifacts stored under `runs/<ts>/eval/`.

## Technology Constraints
```yaml
tech_constraints:
  version: 1.0.0
  profiles:
    - name: onprem
      runtime: java17
      platform: kubernetes
      ingress: nginx
      api:
        - slack.events
        - rest
      storage:
        - postgres
      messaging:
        - kafka
      auth:
        - oidc
      observability:
        - prometheus
        - grafana
  capabilities:
    - type: api.gateway
      vendor: wso2.apim
      params:
        routes: internal-only
    - type: idp
      vendor: keycloak
      params:
        oidc: true
    - type: db.relational
      vendor: postgres
      params:
        ha: true
    - type: mq.stream
      vendor: apache.kafka
      params:
        partitions: 3
    - type: secrets.manager
      vendor: hashicorp.vault
      params: {}
    - type: ci.ci
      vendor: jenkins
      params: {}
```