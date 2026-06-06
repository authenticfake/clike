yaml
tech_constraints:
  version: 1
  metadata:
    name: "CoffeeBuddy"
    domain: "enterprise office workflow automation"
    criticality: "medium"
  classification:
    solution_type: "enterprise"
    deployment_context: "on-prem"
    data_sensitivity: "internal"
  lanes:
    - name: "app-core"
      lane: "python service on Kubernetes"
      purpose: "Handle Slack coffee-run workflows, fair runner assignment, order state, reminders, and summaries."
    - name: "ai-rag"
      lane: "unknown"
      purpose: "Optional future retrieval lane for internal help or policy documents; not required for slice-1 coffee workflow."
  profiles:
    - name: "app-core"
      runtime: "python"
      platform: "on-prem Kubernetes"
      ingress: "nginx via internal-only Kong Gateway"
      api:
        - "Slack Events API"
        - "REST"
      storage:
        - "Postgres"
      messaging:
        - "Apache Kafka"
      auth:
        - "OIDC via Ory Hydra and Ory Kratos"
      secrets_management:
        - "HashiCorp Vault"
      observability:
        - "Prometheus"
        - "Grafana"
      ci:
        - "Jenkins"
    - name: "ai-rag"
      runtime: "unknown"
      platform: "on-prem Kubernetes"
      api:
        - "unknown"
      storage:
        - "unknown"
      messaging:
        - "unknown"
      auth:
        - "OIDC via Ory Hydra and Ory Kratos"
      observability:
        - "Prometheus"
        - "Grafana"
      supported_rag_formats:
        - "docx"
        - "pdf"
        - "xlsx"
        - "pptx"
      slice_1_required: false
  security:
    authentication: "OIDC via internal identity provider"
    authorization: "unknown role model; assume Slack workspace membership plus internal service authorization for slice-1"
    data_protection: "Internal-only routing; secrets in Vault; no payment data in slice-1"
  evaluation:
    required_checks:
      - "tests"
      - "security"
```

## Deployment Portability Rule (MANDATORY WHEN APPLICABLE)
- Portability across public cloud and on-prem is not a slice-1 requirement because the attachment states the solution must run fully on-prem and avoid reliance on public cloud.
- Primary delivery profile is on-prem Kubernetes with internal gateway, identity, storage, messaging, and observability.
- Secondary delivery profile is not required for slice-1.
- Business APIs, lifecycle states, audit semantics, and operator workflows should still be kept infrastructure-adapter-safe so future hybrid support does not alter Slack user flows.

## Technology Constraints Profile Rule
- Infrastructure portability is not required for slice-1, but constraints are profile-oriented with separate `app-core` and `ai-rag` profiles.
- `app-core` is the only required slice-1 profile.
- `ai-rag` is explicitly optional and non-blocking for slice-1; supported document formats are docx, pdf, xlsx, and pptx if later activated.
- Vendor-specific elements from the attachment are treated as evidenced enterprise standards, not as a mandate to add public cloud dependencies.

## Risks & Assumptions
- **Business assumptions:** Pilot users are office teammates in an enterprise Slack workspace; office managers will sponsor a small pilot; target metrics are estimates until baseline timing is measured.
- **Technical assumptions:** Slack enterprise usage and event delivery through an on-prem gateway are approved; Kubernetes, Postgres, Kafka, OIDC, Vault, Jenkins, Prometheus, and Grafana access are available to the delivery team; Slack rate limits require buffering and backoff.
- **Delivery risks:** Internal gateway, Slack app approval, identity provider configuration, and Kubernetes namespace access may delay a 10-day demo if not pre-approved.
- **UX risks:** Users may resist structured ordering if modal copy is too slow; fair runner assignment must be explainable; reminder timing must avoid noisy channel behavior.
- **AI/RAG assumption:** The ai-rag profile is included only to satisfy downstream capability readiness and is not evidenced as a CoffeeBuddy slice-1 feature.

## Success Metrics (early slice)
- **TTFA (Time-to-First-Action):** first `/coffee` or Slack action to run-created confirmation in under 60 seconds.
- **Task success (slice flows):** at least 85% of pilot users submit or edit an order without assistance.
- **Critical error rate:** no more than 2% incorrect, missing, or duplicated orders in final summaries.
- **Idea→Demo lead time:** ≤ 10 calendar days.
- **CSAT/NPS (pilot):** CSAT ≥ 4.0/5 from pilot users after the first week.
- **Coordination time:** average active coordination time under 2 minutes per coffee run.

## Sources & Inspiration
- Internal notes: attached `IDEA.md` for CoffeeBuddy, including Slack workflow, on-prem Kubernetes, internal identity, gateway, Postgres, Kafka, Vault, Jenkins, Prometheus, and Grafana constraints.
- Market scan / baseline: no external competitor or benchmark scan was attached; baseline is current ad-hoc Slack thread coordination.

## Non-Goals
- Replace Slack, HR systems, ERP, identity provider, or corporate gateway infrastructure.
- Build a payments, wallet, reimbursement, or e-signature system.
- Provide full admin analytics, fairness audits across departments, or enterprise reporting before value validation.
- Optimize for extreme scale, multi-region deployment, or cloud portability before the on-prem pilot works.
- Activate AI/RAG assistance as a required slice-1 capability.

## Constraints
- **Budget:** unknown; assume a small 2-week delivery slice with existing enterprise infrastructure.
- **Timeline:** slice-1 demo target is ≤ 10 calendar days.
- **Compliance:** internal-only operation is required; privacy, retention, and audit obligations are unknown and must be confirmed.
- **Legal:** no payment, receipt, or signature obligations are in scope; Slack app approval and data storage policy must be confirmed.
- **Platform limits:** Slack API rate limits are a known risk; Kubernetes, Kafka, Postgres, Vault, OIDC, Jenkins, and observability SLAs are unknown.

## Strategic Fit
- Link to company OKRs/initiatives: supports employee-experience automation, internal productivity, and enterprise on-prem delivery confidence; exact OKRs are unknown.
- Executive sponsors and “go/no-go” gates: office manager, IT/security, and Slack workspace owner approval are assumed gates before pilot launch.
- Cross-function impacts: IT Sec validates internal-only routing and secrets; platform team supports Kubernetes and CI; office managers review fairness; data/privacy owner confirms order preference retention.

## /spec Handoff Readiness (bridge section)
- **Functional anchors:** Start coffee run from Slack; capture structured order; edit or cancel order before cutoff; assign fair runner; send cutoff reminder; publish final summary; persist lightweight preferences; expose health and audit-relevant operational signals.
- **Non-functional anchors:** P95 Slack interaction acknowledgement under 3 seconds where Slack requires it; final summary generation under 5 seconds after cutoff; pilot throughput of 5 runs/day and 30 users; service availability target 99% during office hours; OIDC-backed internal access for service/admin surfaces; internal data only with no payment data; structured logs, metrics, and traces suitable for Prometheus/Grafana; preference retention policy to be confirmed before production.
- **Acceptance hooks:** Start coffee run capability: given an authorized Slack user invokes `/coffee`, when required fields are supplied, then a coffee run is created and confirmed in under 60 seconds; given missing fields, then the user receives a clear correction prompt; given duplicate active run creation, then the service prevents ambiguity or asks for confirmation.
- **Acceptance hooks:** Structured order capability: given a participant opens the order flow, when drink details are submitted, then the order appears in run state; given the participant edits before cutoff, then the latest order replaces the prior version; given cutoff has passed, then edits are rejected with a clear message.
- **Acceptance hooks:** Fair runner assignment capability: given a run reaches assignment time, when eligible participants exist, then one runner is selected; given the final summary is posted, then the runner and selection reason are visible; given no eligible runner exists, then the initiator is prompted to assign or volunteer.
- **Acceptance hooks:** Reminder capability: given a run has a cutoff, when reminder time arrives, then a Slack reminder is sent; given Kafka or Slack delivery is delayed, then retry/backoff is used; given the reminder was already sent, then duplicate reminders are avoided.
- **Acceptance hooks:** Final summary capability: given cutoff passes, when orders exist, then a single summary lists runner, orders, and notes; given no orders exist, then the run is closed with a no-orders message; given Slack posting fails, then the failure is logged and retried or surfaced to the initiator.
- **Acceptance hooks:** Preference persistence capability: given a user submits an order, when preference saving is enabled, then the last simple preference is available next time; given a user changes the order, then the preference updates only after confirmation; given retention policy is disabled or unknown, then preferences can be omitted without blocking ordering.
- **Acceptance hooks:** Operational evidence capability: given the service is deployed, when health is requested, then readiness and liveness reflect dependencies; given an operation completes or fails, then structured logs include correlation identifiers; given metrics are scraped, then counts for runs, orders, reminders, errors, and Slack failures are visible.