yaml
tech_constraints:
  version: 1
  metadata:
    name: "CoffeeBuddy"
    domain: "enterprise office coordination"
    criticality: "medium"
  classification:
    solution_type: "enterprise"
    deployment_context: "on-prem"
    data_sensitivity: "internal"
  lanes:
    - name: "slack-workflow"
      lane: "python"
      purpose: "Handle Slack events, coffee-run workflow state, reminders, and REST health/admin endpoints."
    - name: "ai-rag"
      lane: "unknown"
      purpose: "Not in slice-1; reserved only if later office-policy or menu-document retrieval is approved."
  profiles:
    - name: "app-core"
      runtime: "python"
      platform: "kubernetes"
      api:
        - "slack.events"
        - "rest"
      storage:
        - "postgres"
      messaging:
        - "kafka"
      auth:
        - "oidc"
      observability:
        - "prometheus"
        - "grafana"
      broker:
        - "apache.kafka"
      ingress:
        - "nginx"
      gateway:
        - "Kong Gateway"
      idp:
        - "Ory Hydra"
        - "Ory Kratos"
      secrets:
        - "hashicorp.vault"
      ci:
        - "jenkins"
    - name: "ai-rag"
      runtime: "unknown"
      platform: "on-prem"
      api:
        - "unknown"
      storage:
        - "unknown"
      messaging:
        - "unknown"
      auth:
        - "oidc"
      observability:
        - "prometheus"
        - "grafana"
      broker:
        - "unknown"
      supported_formats:
        - "docx"
        - "pdf"
        - "xlsx"
        - "pptx"
      slice_1_status: "out_of_scope"
  security:
    authentication: "oidc"
    authorization: "unknown"
    data_protection: "internal-only routes; secrets managed through hashicorp.vault; no public-cloud backend for slice-1"
  evaluation:
    required_checks:
      - "tests"
      - "security"
      - "slack-event-contract"
      - "onprem-runtime-path"
```

## Deployment Portability Rule (MANDATORY WHEN APPLICABLE)
- Primary delivery profile is on-prem Kubernetes using internal ingress, Kong Gateway, OIDC, Postgres, Kafka, Vault, Prometheus/Grafana, and Jenkins as evidenced in the attached IDEA.
- Secondary supported profile is local development/test only, assumed for deterministic CI and demo validation; production parity outside on-prem is not a slice-1 requirement.
- Functional parity expected across profiles: Slack event handling, coffee-run lifecycle states, runner assignment, reminders, order summaries, preference persistence, audit logs, and health checks must behave the same.
- Allowed differences are limited to infrastructure adapter configuration for ingress, secrets, storage endpoints, messaging endpoints, and observability sinks.
- Business APIs, lifecycle states, audit semantics, Slack user workflows, and operator validation steps must remain unchanged across on-prem and local validation profiles.

## Risks & Assumptions
- **Business assumptions:** Slack Enterprise is allowed internally; stakeholder commitment from office users and IT/security is available for a ≤10-day demo; slice volume target of 5–50 users is an assumption.
- **Technical assumptions:** Slack incoming events can be proxied through the on-prem gateway; credentials, signing secrets, OIDC configuration, Kafka topics, Postgres schema access, Vault paths, and Jenkins pipeline access will be provided; Slack rate limits are handled with Kafka buffering and backoff.
- **Delivery risks:** External Slack platform constraints, internal gateway approval, and identity/secrets setup may delay demo readiness; legal review may be required for storing preferences and Slack user identifiers.
- **UX risks:** Users may ignore slash-command conventions, runner assignment may feel unfair without clear microcopy, and reminder timing may need team-specific tuning; English-only copy for slice-1 is an assumption.

## Success Metrics (early slice)
- **TTFA (Time-to-First-Action):** ≤30 seconds from `/coffee` to first order prompt or confirmation.
- **Task success (slice flows):** ≥85% of pilot users complete start-run, add-order, confirm-summary, and runner-view flows without assistance.
- **Critical error rate:** ≤2% failed Slack operations per coffee-run workflow.
- **Idea→Demo lead time:** ≤10 calendar days.
- **CSAT/NPS (pilot):** CSAT ≥4.0/5 from pilot teammates after at least 3 coffee runs.

## Sources & Inspiration
- Internal notes: attached `IDEA.md` for CoffeeBuddy describing Slack ordering, fair runner assignment, reminders, remembered preferences, enterprise Slack, on-prem Kubernetes, internal identity/gateways, and technology standards.
- Market scan / baseline: Slack platform patterns cited in the attachment as internal reference; no external competitor benchmark was provided.

## Non-Goals
- Do not replace Slack as the user-facing coordination channel.
- Do not build payment, reimbursement, café POS, delivery, or vendor-ordering automation.
- Do not implement full AI recommendations, RAG over office documents, or analytics dashboards in slice-1.
- Do not optimize for extreme scale before validating pilot value.
- Do not deploy the CoffeeBuddy backend to public cloud for slice-1.

## Constraints
- **Budget:** unknown; assumption is a small slice team focused on ≤10 calendar days of demo delivery.
- **Timeline:** slice-1 demo target is ≤10 calendar days.
- **Compliance:** internal-only routing, on-prem execution, OIDC authentication, secrets management, and observable operations are required by the attached enterprise context.
- **Legal:** storage policy for Slack user identifiers, coffee preferences, and audit logs is unknown and must be confirmed before pilot beyond demo.
- **Platform limits:** Slack rate limits and event retry behavior are a known risk; Kong Gateway, Ory Hydra/Kratos, Kafka, Postgres, Vault, Jenkins, Prometheus, and Grafana availability are assumed from the attached technology constraints.

## Strategic Fit
- CoffeeBuddy aligns to enterprise productivity and controlled internal automation by reducing low-value coordination work while respecting on-prem and internal identity standards.
- Executive sponsor is unknown; go/no-go gates should include Slack workspace approval, IT/security runtime approval, and pilot user acceptance after ≥3 coffee runs.
- Cross-function impacts include IT security for gateway/OIDC/secrets, office management for fairness rules, and potential DPO/legal review for preference and Slack user identifier retention.

## /spec Handoff Readiness (bridge section)
- **Functional anchors:** Start coffee run from Slack slash command or event, traceable to primary users and Outcome 1.
  - Acceptance hook: Given an authorized Slack user, when they start `/coffee`, then CoffeeBuddy creates one active run and returns an acknowledgement within 30 seconds.
  - Acceptance hook: Given an active run already exists for the channel, when another start request is received, then the user is shown the current run instead of creating a duplicate.
  - Acceptance hook: Given an unauthorized or invalid event signature, when the event is received, then it is rejected and logged without creating state.
- **Functional anchors:** Capture and update teammate orders in Slack, traceable to primary users and Outcomes 1 and 2.
  - Acceptance hook: Given an active run, when a teammate submits an order, then the order is stored with user, item text, timestamp, and run id.
  - Acceptance hook: Given a teammate changes their mind before cutoff, when they update the order, then the summary shows only the latest order.
  - Acceptance hook: Given malformed or empty order text, when submitted, then the user receives a clear correction prompt.
- **Functional anchors:** Persist and reuse coffee preferences, traceable to repeat users and Outcome 4.
  - Acceptance hook: Given a returning user with a saved preference, when they join a run, then CoffeeBuddy offers reuse or edit in one interaction.
  - Acceptance hook: Given a user edits a preference, when the run completes, then the new preference is available for the next run.
  - Acceptance hook: Given preference storage is unavailable, when reuse is requested, then the user can still type a one-off order and the failure is logged.
- **Functional anchors:** Assign a fair runner, traceable to teammates, office managers, and Outcome 3.
  - Acceptance hook: Given at least 2 eligible runners, when assignment occurs, then the previous runner is not selected again.
  - Acceptance hook: Given only 1 eligible runner, when assignment occurs, then CoffeeBuddy explains why repeat assignment is unavoidable.
  - Acceptance hook: Given runner assignment completes, when the summary is posted, then the assigned runner is visible to all participants.
- **Functional anchors:** Send reminders and cutoff notifications, traceable to primary users and Outcomes 1 and 2.
  - Acceptance hook: Given an active run, when the reminder time is reached, then participants receive a Slack reminder.
  - Acceptance hook: Given the cutoff is reached, when new orders arrive, then CoffeeBuddy rejects or marks them late according to configured slice-1 rule.
  - Acceptance hook: Given Slack delivery fails, when retry policy is exhausted, then the failure is logged and visible in operator diagnostics.
- **Functional anchors:** Generate final order summary, traceable to runner and Outcome 2.
  - Acceptance hook: Given at least 1 order, when the run closes, then CoffeeBuddy posts a complete summary with each participant and latest order.
  - Acceptance hook: Given no orders were submitted, when the run closes, then CoffeeBuddy posts a no-orders message and does not assign a runner.
  - Acceptance hook: Given duplicate submissions exist, when the summary is generated, then only the latest order per user is included.
- **Functional anchors:** Provide operational health and audit trail, traceable to IT/security and Outcome 5.
  - Acceptance hook: Given the app is running, when the health endpoint is called internally, then it reports dependency status for storage, messaging, and Slack event processing.
  - Acceptance hook: Given a workflow state change, when it occurs, then CoffeeBuddy records an audit event with timestamp, actor, run id, and action.
  - Acceptance hook: Given logs are emitted, when reviewed by operators, then no secrets or Slack signing secrets appear in plaintext.
- **Functional anchors:** Buffer Slack events through messaging, traceable to IT reliability goals and Outcome 5.
  - Acceptance hook: Given a valid Slack event, when received by the gateway-facing service, then it is acknowledged quickly and queued for processing.
  - Acceptance hook: Given Kafka is temporarily unavailable, when an event arrives, then CoffeeBuddy fails safely and records the incident without corrupting run state.
  - Acceptance hook: Given duplicate Slack retries arrive, when processed, then idempotency prevents duplicate orders or duplicate runs.
- **Non-functional anchors:** P95 Slack acknowledgement latency ≤3 seconds and TTFA ≤30 seconds; slice throughput assumption is 1–10 runs/day and 5–50 users; availability target for pilot is ≥99% during office hours; authentication uses OIDC and Slack event verification; authorization model is unknown and must be defined; data classes are internal Slack identifiers, order text, preferences, and audit logs; observability requires structured logs, metrics, and dependency health exposed to Prometheus/Grafana; data lifecycle requires retention and deletion policy for preferences and Slack identifiers before wider pilot.
- **Acceptance hooks:** For performance, run a deterministic slice test proving Slack acknowledgement ≤3 seconds P95 under assumed pilot load.
  - Acceptance hook: For security, verify invalid Slack signatures are rejected and secrets are read from Vault/configured secret paths rather than hardcoded.
  - Acceptance hook: For observability, verify health, error, workflow, and retry metrics are visible in Prometheus-compatible output and logs contain correlation ids.