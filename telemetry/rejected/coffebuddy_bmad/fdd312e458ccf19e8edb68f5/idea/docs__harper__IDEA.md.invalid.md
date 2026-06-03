yaml
tech_constraints:
  version: 1
  metadata:
    name: "CoffeeBuddy"
    domain: "enterprise office workflow"
  classification:
    solution_type: "Slack workflow service"
    deployment_context: "on-prem Kubernetes"
    data_sensitivity: "employee orders, preferences, Slack identifiers, runner history"
  runtime:
    language: "python"
    platform: "kubernetes"
    ingress:
      - "nginx"
      - "Kong Gateway"
    interfaces:
      - "Slack events"
      - "REST"
    storage:
      relational: "Postgres"
    messaging:
      stream: "Apache Kafka"
    identity:
      oidc: "Ory Hydra and Ory Kratos"
    secrets:
      manager: "HashiCorp Vault"
    observability:
      metrics: "Prometheus"
      dashboards: "Grafana"
    ci:
      system: "Jenkins"
  network:
    routing: "internal-only gateway routes for application APIs"
    slack_events: "assumed proxied through on-prem gateway"
  repository_evidence:
    local_snapshot_verified: true
    github_remote_verified: false
    existing_application_entrypoint_detected: false
  assumptions:
    - "Slack Enterprise usage is approved internally."
    - "Slack events and interactions can be securely routed to the on-prem service."
    - "Slack user identifiers can be mapped to internal identity where required."
  evaluation:
    required_checks:
      - "Slack request signature verification"
      - "on-prem configuration without public cloud backend dependency"
      - "secret values loaded from approved secret management, not hardcoded"
      - "order workflow tests for create, submit, preference reuse, lock, runner assignment, and summary"
      - "observability evidence for coffee runs, orders, notifications, failures, and rate limits"
```

## Risks & Assumptions
- Business assumption: teams want a structured Slack workflow rather than continuing ad-hoc threads.
- Business risk: users may reject automatic runner assignment; mitigate with transparent explanation and opt-out rules if approved.
- Technical assumption: Slack events can be proxied securely through the internal gateway path.
- Technical risk: Slack rate limits or event delivery failures may delay notifications; mitigate with Kafka buffering, retries, backoff, and idempotent handling.
- Delivery assumption: the existing repository has documentation and CLike capability context but no detected application entry point.
- UX risk: too much order-form friction could push users back to Slack threads; mitigate with saved preferences and a minimal order flow.
- Data/compliance assumption: coffee preferences and runner history are acceptable to store internally with retention controls.
- Dependency risk: Kubernetes, OIDC, gateway, Vault, Postgres, Kafka, Prometheus, Grafana, and Jenkins availability must be confirmed in the target enterprise environment.

## Success Metrics
- Time from first coffee-run command to order confirmation: target under 2 minutes for slice-1.
- Weekly active coffee runs per active user.
- Percentage of created runs that reach locked summary state.
- Order submission success rate.
- Critical workflow error rate for create, submit, lock, assign runner, and summarize.
- Slack notification failure or rate-limit retry rate.
- Runner assignment distribution over time to indicate fairness.
- Pilot satisfaction from teammates, runners, and office managers.