yaml
tech_constraints:
  version: 1
  metadata:
    name: "CoffeeBuddy"
    domain: "enterprise office coordination"
  classification:
    solution_type: "Slack-integrated workflow service"
    deployment_context: "on-prem Kubernetes"
    data_sensitivity: "employee Slack IDs, coffee preferences, coffee order history, runner history"
  runtime:
    language: "python"
    platform: "kubernetes"
    ingress:
      - "nginx"
      - "Kong Gateway"
    interfaces:
      - "Slack events"
      - "Slack slash commands"
      - "internal REST"
    storage:
      relational: "Postgres"
    messaging:
      stream: "Apache Kafka"
    auth:
      identity_provider:
        - "Ory Hydra"
        - "Ory Kratos"
      protocol: "OIDC"
    secrets: "HashiCorp Vault"
    observability:
      metrics: "Prometheus"
      dashboards: "Grafana"
    ci: "Jenkins"
  network:
    public_cloud_backend: false
    routes: "internal-only except approved Slack event ingress path"
  evaluation:
    required_checks:
      - "Slack request signature verification"
      - "coffee run workflow tests"
      - "runner assignment fairness tests"
      - "Slack rate-limit retry/backoff tests"
      - "Prometheus metrics exposure check"
```

## Risks & Assumptions

- Business assumption: Slack Enterprise usage is approved internally.
- Business risk: users may reject automatic runner assignment unless the reason is transparent and opt-out behavior is supported.
- Technical assumption: Slack commands, events, and interactions can be securely proxied to on-prem infrastructure through approved gateway routes.
- Technical risk: Slack rate limits or event delivery failures may delay reminders or summaries; mitigation is Kafka buffering, idempotent processing, retry, and backoff.
- Delivery risk: proving the Slack-to-on-prem ingress path may be the highest-risk first step.
- UX assumption: users will accept structured Slack modals or interactive messages if preferences reduce repeated typing.
- Data assumption: Slack user IDs and optional OIDC mappings are sufficient for user identity in the first slice.
- Compliance risk: coffee preferences and participation history may still be considered employee data; mitigation is minimization, retention controls, internal-only storage, and auditability.
- Dependency assumption: Postgres, Kafka, Kong Gateway, NGINX ingress, Ory Hydra/Kratos, Vault, Prometheus, Grafana, and Jenkins are acceptable enterprise standards for this project.

## Success Metrics

- Time from first `/coffee` action to order confirmation is under 2 minutes for the first slice.
- Weekly active coffee runs per active user increases after pilot launch.
- Missed or late order rate decreases compared with ad-hoc Slack-thread coordination.
- Runner assignment distribution is explainable and balanced across eligible participants over time.
- Slack API failure and rate-limit events are observable and retried without duplicate orders.
- Pilot users report that CoffeeBuddy is faster and clearer than manual Slack threads.

Acceptance criteria for the first slice:
- A user can start a coffee run from Slack.
- Teammates can submit structured orders before cutoff.
- The system confirms submitted orders.
- The system sends a reminder before cutoff.
- The system assigns or confirms a fair runner.
- The runner receives a consolidated order summary.
- Preferences and runner history are persisted.
- Metrics are exposed for created runs, submitted orders, reminders, Slack failures, and runner assignments.