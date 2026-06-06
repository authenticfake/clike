yaml
tech_constraints:
  version: 1
  metadata:
    name: "CoffeeBuddy"
    domain: "enterprise office workflow"
  classification:
    solution_type: "slack-integrated workflow application"
    deployment_context: "on-prem kubernetes"
    data_sensitivity: "internal workplace preferences and activity"
  runtime:
    language: "python"
    platform: "kubernetes"
    ingress:
      - "nginx"
      - "kong gateway"
    public_cloud_backend: false
  integrations:
    slack:
      required:
        - "slack events"
        - "slack workflows or interactions"
        - "rest"
    identity:
      - "oidc"
      - "ory hydra"
      - "ory kratos"
  data:
    relational_store: "postgres"
    messaging: "apache kafka"
    secrets: "hashicorp vault"
  observability:
    metrics: "prometheus"
    dashboards: "grafana"
  delivery:
    ci: "jenkins"
  assumptions:
    - "Slack Enterprise is approved for internal use."
    - "Slack events can be securely proxied through on-prem gateway routes."
    - "Users can be identified by Slack user IDs and optionally mapped to OIDC identities."
  evaluation:
    required_checks:
      - "Slack request signature verification"
      - "on-prem deployment configuration validation"
      - "order workflow tests"
      - "runner assignment fairness tests"
      - "Slack rate-limit and retry behavior tests"
      - "metrics exposure checks"
```

## Risks & Assumptions

- Business risk: users may continue using informal Slack threads if the structured flow takes too long or feels intrusive.
- Business assumption: teams value fair runner assignment enough to accept a lightweight automated workflow.
- Technical risk: Slack rate limits or delivery failures may delay notifications; Kafka buffering, idempotent processing, and retry/backoff are expected mitigations.
- Technical risk: the Slack-to-on-prem ingress path may be the highest-risk integration and should be proven early.
- Delivery assumption: on-prem Kubernetes, Postgres, Kafka, Vault, Prometheus, Grafana, Kong/NGINX, Ory, and Jenkins are available enterprise standards for this project.
- UX assumption: Slack modals, commands, or interactions are acceptable for structured order capture.
- Data assumption: coffee preferences and runner history are internal workplace data and should be minimized, retained intentionally, and stored only on approved infrastructure.
- Compliance assumption: public cloud application processing and storage are excluded.

## Success Metrics

- Time from first `/coffee` action to order confirmation is under 2 minutes for the first slice.
- A user can start a run, submit an order, receive confirmation, and produce a runner summary through Slack.
- The runner assignment is explainable and uses available participation or runner history.
- Weekly active coffee runs and active channels increase during pilot usage.
- Missed or late order rate decreases versus ad-hoc Slack threads.
- Slack API failure and rate-limit events are measured and visible in operational metrics.
- Critical workflow error rate remains low enough that teams can complete pilot coffee runs without manual recovery.
- First-slice acceptance criteria: no public cloud backend is required; Slack events are verified; orders are persisted in Postgres; workflow events can be buffered through Kafka; secrets are not hardcoded; Prometheus metrics are exposed.