# IDEA — CoffeeBuddy

## Vision
CoffeeBuddy streamlines office coffee runs entirely within the corporate network: teammates submit orders via Slack, one teammate is fairly assigned as runner, reminders are sent, and preferences are remembered—without relying on public cloud.

## Problem Statement
Teams coordinate coffee orders in ad-hoc Slack threads. Messages get buried, someone forgets to pick up, and no one remembers preferences. In regulated environments, external cloud services are restricted, so the solution must run fully on-prem.

## Target Users & Context
- Primary: office teammates placing and picking up coffee orders.
- Secondary: office managers seeking fairness and reduced coordination time.
- Context: Enterprise Slack workspace; on-prem Kubernetes; internal identity and gateways only.

## Value & Outcomes
- Reduce coordination time to under 2 minutes per run.
- Fewer mistakes with consistent order summaries.
- Transparent, fair runner assignment across the team.

## Out of Scope
Payments, delivery logistics, vendor integrations beyond Slack workflows.

## Technology Constraints
```yaml
tech_constraints:
  version: 1.0.0
  profiles:
    - name: onprem
      runtime: python
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
      vendor: Kong Gateway
      params:
        routes: internal-only
    - type: idp
      vendor: Ory Hydra, Ory Kratos
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
## Risks & Assumptions

Assumption: Slack enterprise is allowed internally; incoming events proxied via on-prem gateway.

Risk: Slack rate limits; mitigated via Kafka buffering and backoff.

## Success Metrics (early)

Weekly active coffee runs per active user.

Time from first /coffee to order confirmation.

## Sources & Inspiration

Slack platform patterns (internal reference).

Existing enterprise standards for Kubernetes, Ory Hydra & Ory Kratos, Kong Gateway, hashicorp as Vault, and Kafka.