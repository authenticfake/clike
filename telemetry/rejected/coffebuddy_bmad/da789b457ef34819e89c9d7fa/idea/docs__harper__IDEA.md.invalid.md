yaml
tech_constraints:
  version: 1
  metadata:
    name: "CoffeeBuddy"
    domain: "enterprise office workflow"
    criticality: "low"
  classification:
    solution_type: "enterprise"
    deployment_context: "on-prem"
    data_sensitivity: "internal"
  lanes:
    - name: "app-core"
      lane: "python on kubernetes"
      purpose: "Handle Slack workflow events, coffee-run lifecycle, order capture, fair runner assignment, reminders, and summaries."
    - name: "ai-rag"
      lane: "unknown"
      purpose: "Not required for slice-1; reserved only if later internal help or policy retrieval is approved."
  profiles:
    - name: "app-core"
      runtime: "python"
      platform: "on-prem kubernetes"
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
        - "kafka"
      ingress:
        - "nginx"
      gateway:
        - "Kong Gateway internal-only routes"
      identity_provider:
        - "Ory Hydra"
        - "Ory Kratos"
      secrets:
        - "HashiCorp Vault"
      ci:
        - "Jenkins"
    - name: "ai-rag"
      runtime: "unknown"
      platform: "on-prem kubernetes"
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
      rag_formats_supported:
        - "docx"
        - "pdf"
        - "xlsx"
        - "pptx"
      status: "deferred"
  security:
    authentication: "oidc"
    authorization: "Assumption: Slack workspace membership plus internal service authorization"
    data_protection: "internal-only network paths; secrets in HashiCorp Vault; coffee preferences treated as internal user data"
  evaluation:
    required_checks:
      - "tests"
      - "security"
```

## Deployment Portability Rule (MANDATORY WHEN APPLICABLE)
- Deployment portability is not a slice-1 requirement because the provided IDEA requires fully on-prem operation and no public cloud reliance.
- Primary delivery profile: on-prem Kubernetes behind internal gateway/ingress with internal identity, Postgres, Kafka, Vault, Prometheus, Grafana, and Jenkins.
- Secondary supported profile: none for slice-1.
- Functional parity requirement if a future secondary profile is approved: Slack run lifecycle, order states, audit semantics, and operator workflows must remain unchanged.
- Allowed differences in future profiles must be limited to infrastructure adapter configuration for ingress, storage, messaging, secrets, and observability sinks.

## Risks & Assumptions
- **Business assumptions:** Assumption: pilot teams will commit to using Slack workflow interactions for at least 1 week; Assumption: office managers accept fair rotation logic; Assumption: remembering coffee preferences is policy-approved.
- **Technical assumptions:** Assumption: Slack enterprise events can be proxied through the on-prem gateway; Assumption: credentials for Slack, OIDC, Postgres, Kafka, and Vault are available in a sandbox; Assumption: Slack rate limits are manageable with buffering and backoff.
- **Delivery risks:** Slack app approval, internal gateway routing, IDP setup, and Kafka/Postgres provisioning could exceed the ≤ 10 day demo target.
- **UX risks:** Users may prefer informal threads unless commands/modals are faster; unclear cutoff microcopy could cause missed orders; fairness logic must be explainable to avoid perceived bias.

## Success Metrics (early slice)
- **TTFA (Time-to-First-Action):** Assumption: ≤ 30 seconds from first Slack action to visible run/order confirmation.
- **Task success (slice flows):** Assumption: ≥ 85% of pilot users start/join a run without assistance.
- **Critical error rate:** Assumption: ≤ 2% per order, reminder, or summary operation.
- **Idea→Demo lead time:** ≤ 10 calendar days.
- **CSAT/NPS (pilot):** Assumption: CSAT ≥ 4.0/5 after first pilot week.

## Sources & Inspiration
- Internal notes: attached `IDEA.md` for CoffeeBuddy, including Slack, on-prem Kubernetes, internal identity/gateways, Python, Postgres, Kafka, OIDC, Prometheus/Grafana, Kong Gateway, Ory Hydra/Kratos, HashiCorp Vault, Jenkins, and NGINX constraints.
- Market scan / baseline: no external market scan attached; baseline is current manual Slack-thread coordination from the attached IDEA and BMAD companion notes.

## Non-Goals
- We will not replace Slack or build a standalone collaboration platform.
- We will not build payment, reimbursement, vendor ordering, or delivery automation.
- We will not introduce public-cloud managed services for slice-1.
- We will not build a full admin portal, analytics warehouse, or AI preference engine before value validation.
- We will not optimize for extreme scalability beyond the pilot team volumes stated as assumptions.

## Constraints
- **Budget:** unknown; Assumption: slice-1 should fit a small pilot build with no new external SaaS spend beyond existing enterprise Slack and on-prem platforms.
- **Timeline:** slice-1 demo target is ≤ 10 calendar days and demonstrable within ≤ 2 weeks.
- **Compliance:** internal-only deployment is required; privacy obligations for user preferences are unknown and must be confirmed.
- **Legal:** Slack app approval, user preference storage policy, and retention policy are unknown and must be confirmed before production.
- **Platform limits:** Slack rate limits are a known risk; on-prem Kubernetes, gateway, IDP, Postgres, Kafka, Vault, Jenkins, Prometheus, and Grafana availability must be confirmed.

## Strategic Fit
- Link to company OKRs/initiatives: Assumption: supports employee-experience automation, internal platform reuse, and secure on-prem delivery standards.
- Executive sponsors and “go/no-go” gates: Assumption: office manager sponsors pilot; IT/security must approve Slack event ingress, secrets handling, and identity integration before production promotion.
- Cross-function impacts: IT Sec validates internal-only routing and secrets; DPO/privacy reviews preference storage; office managers review fairness; platform team supports Kubernetes, Postgres, Kafka, and observability.

## /spec Handoff Readiness (bridge section)
- **Functional anchors:** Start coffee run from Slack for a teammate, tied to TTFA and setup-time outcomes.
  - Acceptance hook: Given an authorized Slack user, when they start a coffee run, then a run record is created with owner, channel, cutoff, and status.
  - Acceptance hook: Given successful creation, when the run is active, then Slack shows a confirmation visible to the requester.
  - Acceptance hook: Given invalid or missing cutoff input, then the user receives an actionable error without creating a partial run.
- **Functional anchors:** Submit structured coffee order for a teammate, tied to final-summary accuracy.
  - Acceptance hook: Given an active run, when a user submits drink details, then the order is stored against that run and user.
  - Acceptance hook: Given a duplicate submission before cutoff, then the latest valid order replaces or updates the previous order according to the specified rule.
  - Acceptance hook: Given a closed run, then new orders are rejected with clear Slack feedback.
- **Functional anchors:** Remember simple user preferences, tied to lower repeat-entry friction.
  - Acceptance hook: Given a user has submitted an order before, when they join a new run, then their last preference can be reused or edited.
  - Acceptance hook: Given stored preferences, then only necessary coffee preference data is retained for slice-1.
  - Acceptance hook: Given a user requests not to reuse preferences, then the next order can be entered manually.
- **Functional anchors:** Assign fair runner for each run, tied to transparency and perceived fairness.
  - Acceptance hook: Given eligible participants, when cutoff is reached or assignment is triggered, then exactly one runner is selected.
  - Acceptance hook: Given runner selection, then Slack summary includes the selected runner and a short fairness reason.
  - Acceptance hook: Given insufficient eligible participants, then the workflow reports a clear exception state.
- **Functional anchors:** Send reminder before cutoff, tied to fewer forgotten orders.
  - Acceptance hook: Given an active run with a cutoff, when reminder time is reached, then a Slack reminder is posted or sent according to the selected channel rule.
  - Acceptance hook: Given Slack delivery failure or rate limiting, then the event is retried or marked failed with observable evidence.
  - Acceptance hook: Given a run is cancelled or closed, then no further reminders are sent.
- **Functional anchors:** Post final order summary, tied to one source of truth for pickup.
  - Acceptance hook: Given a run reaches cutoff, when orders exist, then a structured summary lists runner, orders, and notes.
  - Acceptance hook: Given no orders exist, then the run closes with a no-orders message instead of assigning pickup work.
  - Acceptance hook: Given summary posting succeeds, then run status changes to summarized/closed.
- **Functional anchors:** Expose operational health and audit evidence, tied to enterprise-safe pilot operation.
  - Acceptance hook: Given core workflow events occur, then logs include non-secret correlation identifiers for run, order, reminder, and summary operations.
  - Acceptance hook: Given service startup, then health endpoints or equivalent checks report dependencies needed for Slack workflow operation.
  - Acceptance hook: Given security review, then no Slack tokens, OIDC credentials, database passwords, or Vault secrets are logged.
- **Non-functional anchors:** Performance target Assumption: P95 Slack action response ≤ 3 seconds for immediate acknowledgements; throughput target Assumption: 10 runs/day and 50 users/team for pilot; availability target Assumption: business-hours pilot availability ≥ 99%; security model: OIDC/internal authorization plus Slack workspace authorization; data classes: internal user identity, coffee preferences, run/order metadata; observability: structured logs, metrics, and traces where available via Prometheus/Grafana; data lifecycle: Assumption: retain active run/order data for pilot period and confirm preference retention with privacy stakeholders.