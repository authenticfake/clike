yaml
tech_constraints:
  version: 1
  metadata:
    name: "CoffeeBuddy"
    domain: "enterprise workplace workflow"
  classification:
    solution_type: "Slack-integrated workflow service"
    deployment_context: "on-prem Kubernetes"
    data_sensitivity: "employee preferences, Slack identifiers, order history"
  runtime:
    language: "python"
    platform: "kubernetes"
    ingress:
      - "nginx"
      - "Kong Gateway"
  integrations:
    slack:
      - "slash commands or events"
      - "interactive workflows"
    api:
      - "REST for internal/admin access"
    identity:
      - "OIDC"
      - "Ory Hydra"
      - "Ory Kratos"
  data:
    relational_store: "Postgres"
    messaging: "Apache Kafka"
    secrets: "HashiCorp Vault"
  observability:
    metrics: "Prometheus"
    dashboards: "Grafana"
  ci:
    system: "Jenkins"
  assumptions:
    - "Slack Enterprise usage is approved internally."
    - "Incoming Slack events can be proxied through on-prem gateway routes."
    - "Internal admin/API access can use enterprise OIDC."
  evaluation:
    required_checks:
      - "Slack request signature verification"
      - "structured order workflow test"
      - "runner assignment fairness/explainability test"
      - "rate-limit retry or backoff behavior test"
      - "metrics exposure test"
```

## Risks & Assumptions

- Business assumption: Teams want a structured Slack-native flow enough to change from informal threads.
- Business risk: Automatic runner assignment may reduce adoption if users perceive it as unfair or inconvenient.
- Technical assumption: Slack events and interactive payloads can be received through approved internal gateways.
- Technical risk: Slack rate limits or event delivery delays can cause missed reminders or slow confirmations; Kafka buffering, retries, and backoff are expected mitigations.
- Delivery assumption: The first slice can use a narrow workflow before adding advanced administration or menu features.
- UX risk: Too much structure in the order form may push users back to free-form Slack threads.
- Data assumption: Stored preferences and order history are acceptable if minimized and retained according to internal policy.
- Compliance risk: Slack identifiers, preferences, and audit history may require retention, access control, or deletion policies not yet specified.
- Dependency risk: Slack platform behavior, enterprise gateway routing, OIDC integration, Vault, Kafka, and Postgres availability are external dependencies for delivery.

## Success Metrics

- Time from first `/coffee` action to order confirmation: target under 2 minutes.
- Weekly active coffee runs per active user or team.
- Order submission success rate for open runs.
- Missed or late order rate after reminders.
- Runner assignment distribution across eligible participants.
- Slack API failure and rate-limit event rate.
- Reminder delivery success rate.
- Pilot satisfaction from teammates, runners, and office managers.