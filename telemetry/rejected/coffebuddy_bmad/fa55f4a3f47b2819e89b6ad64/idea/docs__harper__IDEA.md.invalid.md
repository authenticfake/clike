yaml
tech_constraints:
  version: 1
  metadata:
    name: "CoffeeBuddy"
    domain: "enterprise employee experience"
    criticality: "low"
  classification:
    solution_type: "enterprise"
    deployment_context: "on-prem"
    data_sensitivity: "internal"
  lanes:
    - name: "app-core"
      lane: "python service on Kubernetes"
      purpose: "Slack workflow handling, order state, reminders, fair runner assignment, and summaries"
    - name: "ai-rag"
      lane: "unknown"
      purpose: "Harper-compatible document context and evaluation lane only; not a slice-1 product feature"
  profiles:
    - name: "app-core"
      runtime: "python"
      platform: "on-prem Kubernetes"
      api:
        - "Slack Events API"
        - "REST"
      storage:
        - "Postgres"
      messaging:
        - "Kafka"
      auth:
        - "OIDC via Ory Hydra and Ory Kratos"
      observability:
        - "Prometheus"
        - "Grafana"
      broker:
        - "Kafka"
      ingress:
        - "nginx"
        - "Kong Gateway internal-only routes"
      secrets:
        - "HashiCorp Vault"
      ci:
        - "Jenkins"
    - name: "ai-rag"
      runtime: "unknown"
      platform: "unknown"
      api:
        - "unknown"
      storage:
        - "supported RAG formats: docx"
        - "supported RAG formats: pdf"
        - "supported RAG formats: xlsx"
        - "supported RAG formats: pptx"
      messaging:
        - "unknown"
      auth:
        - "unknown"
      observability:
        - "unknown"
      broker:
        - "unknown"
  security:
    authentication: "OIDC via internal identity provider"
    authorization: "unknown role model; assume Slack workspace membership and internal gateway controls for slice-1"
    data_protection: "internal employee preferences and Slack identifiers; retention policy unknown"
  evaluation:
    required_checks:
      - "tests"
      - "security"
```

## Deployment Portability Rule (MANDATORY WHEN APPLICABLE)
- Primary delivery profile: on-prem Kubernetes using internal ingress, gateway, identity, Postgres, Kafka, Vault, Prometheus, Grafana, and Jenkins as evidenced in the attachment.
- Secondary supported profile: local development or demo profile may be needed by downstream phases, but no production cloud profile is evidenced.
- Functional parity expectation: local/demo and on-prem profiles should preserve Slack workflow behavior, order lifecycle states, runner assignment rules, audit-relevant events, and operator-visible health checks.
- Allowed differences: infrastructure adapters for ingress, secrets, storage provisioning, message transport endpoints, and observability sinks may vary by profile.
- Unchanged across profiles: business APIs, order lifecycle, runner assignment semantics, reminder behavior, final summary format, and operator troubleshooting workflow.

## Risks & Assumptions
- **Business assumptions:** initial metric targets are assumptions until pilot baseline is measured; stakeholder commitment from office managers and pilot teammates is assumed; internal policy approval for Slack bot usage is assumed.
- **Technical assumptions:** Slack Enterprise is allowed internally; incoming Slack events can be proxied through an on-prem gateway; credentials, signing secrets, and OIDC client setup can be provided; Slack rate limits can be managed with Kafka buffering and backoff.
- **Delivery risks:** external dependency on Slack app configuration may delay the 10-day demo; enterprise gateway, Ory, Vault, Kafka, or Jenkins access may require IT coordination; no existing application entry point was detected in the local repository snapshot.
- **UX risks:** users may prefer informal threads unless the flow is faster; runner fairness microcopy must be clear to avoid perceived bias; too many Slack modal fields could reduce adoption; training may be needed for slash command or shortcut discovery.

## Success Metrics (early slice)
- **TTFA (Time-to-First-Action):** under 60 seconds from `/coffee` or equivalent first action to visible run creation confirmation.
- **Task success (slice flows):** at least 80% of pilot users submit or update an order without assistance.
- **Critical error rate:** no more than 5% of finalized runs contain a missing order, duplicate order, or wrong runner assignment.
- **Idea→Demo lead time:** ≤ 10 calendar days.
- **CSAT/NPS (pilot):** CSAT at least 4.0/5 from pilot teammates after demo week.

## Sources & Inspiration
- Internal notes: attached `IDEA.md` for CoffeeBuddy; BMAD companion artifacts for assumptions, brief, PRFAQ notes, and research questions; local repository snapshot with docs and images only.
- Market scan / baseline: no external market research or competitor benchmark was attached; Slack platform patterns are cited only as an internal reference from the attachment.

## Non-Goals
- CoffeeBuddy will not replace Slack, HR tools, expense systems, café POS systems, or office facility management platforms.
- CoffeeBuddy will not automate payments, legal approvals, or reimbursement.
- CoffeeBuddy will not provide full e-signature, procurement, or vendor-management workflows.
- CoffeeBuddy will not optimize for extreme scale, multi-region SaaS tenancy, or consumer app distribution before pilot value is validated.
- CoffeeBuddy will not introduce AI recommendation, RAG search, or preference inference into slice-1.

## Constraints
- **Budget:** unknown; slice-1 should minimize new platform spend by using evidenced internal components.
- **Timeline:** slice-1 demo target is ≤ 10 calendar days.
- **Compliance:** on-prem execution and internal-only routes are required by the attachment; privacy, retention, and audit obligations are unknown.
- **Legal:** storage rules for Slack identifiers, preferences, and order history are unknown; no payment or signature obligations are in scope.
- **Platform limits:** Slack event delivery, signing verification, and rate limits must be considered; exact quotas, SLAs, sandbox access, and production app approval process are unknown.

## Strategic Fit
- Link to company OKRs/initiatives: assumed fit with employee-experience improvement, internal automation reuse, and enterprise on-prem delivery standards.
- Executive sponsors and “go/no-go” gates: unknown; recommended gate is pilot approval from office manager plus IT/Security confirmation of Slack, gateway, identity, and secrets setup.
- Cross-function impacts: IT Security for gateway, secrets, identity, and rate-limit posture; DPO/Privacy for employee preference retention; office managers for pilot adoption; platform operations for Kubernetes, Kafka, Postgres, and observability readiness.

## /spec Handoff Readiness (bridge section)
- **Functional anchors:** Create coffee run from Slack command or shortcut for office teammate, linked to Outcome 1.
  - Acceptance hook: Given an eligible Slack user, when they start a run, then CoffeeBuddy confirms the run in Slack within 60 seconds.
  - Acceptance hook: Given required run inputs are missing, when the user submits, then CoffeeBuddy shows clear validation guidance without creating a broken run.
  - Acceptance hook: Given a run is active, when another start request occurs in the same channel, then the response prevents accidental duplicate active runs or clearly separates them.
- **Functional anchors:** Submit and update structured coffee orders before cutoff for office teammate, linked to Outcomes 1 and 2.
  - Acceptance hook: Given an active run, when a teammate submits drink details, then the order appears in the run state and can be summarized.
  - Acceptance hook: Given the cutoff has not passed, when the teammate edits an order, then only the latest version appears in the final summary.
  - Acceptance hook: Given the cutoff has passed, when a teammate attempts an edit, then CoffeeBuddy denies the edit with a clear reason.
- **Functional anchors:** Remember simple user preferences for repeat ordering, linked to Outcome 2.
  - Acceptance hook: Given a teammate previously submitted an order, when they join a later run, then CoffeeBuddy can prefill or suggest the last known simple preference.
  - Acceptance hook: Given a teammate changes their preference, when the order is finalized, then the stored preference reflects the latest confirmed value.
  - Acceptance hook: Given preference storage is unavailable, when the user orders, then the flow still works without preference recall.
- **Functional anchors:** Assign a fair runner transparently for office manager and teammates, linked to Outcome 3.
  - Acceptance hook: Given eligible teammates and assignment history, when cutoff occurs, then CoffeeBuddy selects a runner according to the configured fairness rule.
  - Acceptance hook: Given all eligible teammates have not yet been assigned, then CoffeeBuddy does not assign the same teammate twice unless no alternative is eligible.
  - Acceptance hook: Given a runner is assigned, then the Slack message explains the selection in human-readable terms.
- **Functional anchors:** Send cutoff reminder for active coffee run participants, linked to Outcome 4.
  - Acceptance hook: Given an active run with a cutoff time, when the reminder threshold is reached, then CoffeeBuddy posts a reminder in Slack.
  - Acceptance hook: Given the run is cancelled or finalized before cutoff, when the reminder threshold is reached, then no stale reminder is posted.
  - Acceptance hook: Given Slack delivery fails transiently, then CoffeeBuddy retries or records a recoverable failure for operators.
- **Functional anchors:** Post final source-of-truth order summary, linked to Outcomes 2 and 5.
  - Acceptance hook: Given cutoff occurs, when orders exist, then CoffeeBuddy posts one final summary containing orders, runner, and run status.
  - Acceptance hook: Given no orders exist, when cutoff occurs, then CoffeeBuddy posts a clear no-orders outcome or closes the run without assigning unnecessary pickup.
  - Acceptance hook: Given summary posting fails, then the run records failure state and exposes enough information for retry or operator review.
- **Functional anchors:** Provide minimal operational health and audit-relevant events for IT/Security, linked to Outcome 5.
  - Acceptance hook: Given the service is running, when a health check is called, then it reports dependency readiness without exposing secrets.
  - Acceptance hook: Given key workflow transitions occur, then logs include run ID, state transition, and non-sensitive diagnostic context.
  - Acceptance hook: Given a secret or credential is missing, then startup or readiness fails safely with actionable operator messaging.
- **Non-functional anchors:** Performance target: Slack interaction acknowledgement should meet Slack platform timing expectations, with internal P95 command-to-confirmation latency target under 2 seconds after event receipt for healthy dependencies.
- **Non-functional anchors:** Throughput target: pilot supports at least 5 active runs and 50 orders per day as an assumption until volume is measured.
- **Non-functional anchors:** Availability/SLA target: pilot availability target is 99% during office hours as an assumption, excluding Slack or enterprise platform outages.
- **Non-functional anchors:** Security target: OIDC/internal gateway controls, Slack request verification, no secrets in logs, Vault-backed secrets where available, and least-privilege access to Postgres and Kafka.
- **Non-functional anchors:** Observability target: structured logs, Prometheus metrics, Grafana dashboards or equivalent sink, and trace/correlation IDs where feasible.
- **Non-functional anchors:** Data lifecycle target: retain Slack identifiers, order history, and preferences only as long as pilot policy allows; PII handling and deletion policy must be specified in /spec.