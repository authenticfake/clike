yaml
tech_constraints:
  version: 1
  metadata:
    name: "CoffeeBuddy"
    domain: "enterprise internal productivity"
  classification:
    solution_type: "Slack-integrated workflow bot"
    deployment_context: "on-prem Kubernetes"
    data_sensitivity: "internal workplace orders, preferences, participation history"
  runtime:
    language: "python"
    platform: "kubernetes"
    ingress:
      - "nginx"
      - "Kong Gateway"
    interfaces:
      - "Slack events"
      - "Slack slash commands"
      - "REST"
    storage:
      relational: "Postgres"
    messaging:
      stream: "Kafka"
    auth:
      - "OIDC"
      - "Ory Hydra"
      - "Ory Kratos"
    secrets:
      - "HashiCorp Vault"
    observability:
      metrics: "Prometheus"
      dashboards: "Grafana"
    ci:
      - "Jenkins"
  network:
    allowed_deployment: "internal-only"
    slack_events_path: "proxied through on-prem gateway"
    public_cloud_backend: false
  required_checks:
    - "Slack request signature verification"
    - "on-prem gateway ingress validation"
    - "structured coffee run happy-path test"
    - "runner assignment fairness evidence"
    - "Slack rate-limit retry or backoff behavior"
    - "Prometheus metric exposure"
```

## Risks & Assumptions

- Business assumption: Slack Enterprise usage is approved internally for the target teams.
- Business risk: users may return to ad-hoc Slack threads if the ordering flow has too much friction.
- Technical assumption: Slack events and interactive requests can be securely proxied through the on-prem gateway.
- Technical risk: Slack rate limits or event delivery delays may affect reminders and confirmations; buffering, retries, and backoff are required.
- Delivery risk: the enterprise network path from Slack to on-prem services may be the highest-risk early integration.
- UX assumption: users will accept structured Slack modals or messages for order submission.
- UX risk: automatic runner assignment may be resisted unless opt-out and fairness explanations are clear.
- Data assumption: coffee preferences and participation history can be stored internally with appropriate retention controls.
- Compliance risk: preference or participation data may be treated as sensitive workplace data and require minimization or audit controls.
- Dependency assumption: approved enterprise infrastructure includes Kubernetes, Postgres, Kafka, OIDC/Ory, Kong/NGINX, Vault, Prometheus, Grafana, and Jenkins.

## Success Metrics

- Time from first `/coffee` action to order confirmation is under 2 minutes for the first supported workflow.
- Weekly active coffee runs per active user increases after pilot launch.
- Order submission success rate is at least 95% during pilot runs.
- Critical Slack workflow error rate stays below 1% for command handling, order submission, reminders, and summary generation.
- Runner assignment distribution is explainable and visibly balanced across recent eligible participants.
- First-slice acceptance criteria:
  - A user can start a coffee run from Slack.
  - Teammates can submit structured orders before cutoff.
  - CoffeeBuddy can remember or reuse a user preference.
  - A reminder is sent before cutoff.
  - A runner is assigned or confirmed fairly.
  - The runner receives a consolidated summary.
  - Run history is persisted on-prem.
  - Metrics are available for run creation, order submission, notifications, and failures.