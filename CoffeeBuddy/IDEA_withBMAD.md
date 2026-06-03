# IDEA — CoffeeBuddy

## Vision
CoffeeBuddy reduces office coffee-run coordination from scattered Slack threads to a controlled, on-prem Slack workflow. Users get a fast, simple, transparent experience: submit an order, see the run summary, and know who is assigned in under 2 minutes. Its differentiator is enterprise-safe deployment inside the corporate network using existing Kubernetes, OIDC, Kafka, Postgres, and observability standards. Slice-1 delivers a Slack-triggered coffee run with order capture, fair runner assignment, reminders, and confirmation within 10 calendar days.

## Problem Statement
Office teammates coordinate coffee orders in ad-hoc Slack threads, where messages get buried, preferences are forgotten, and runners are assigned unevenly. The pain appears during informal team breaks in Slack and creates wasted time, missed orders, and avoidable social friction. Current workarounds are manual messages, pinned notes, or memory, which fail when teams are busy or regulated environments restrict external cloud tools. Problem solved for slice-1 means one Slack workflow can collect orders, assign one runner fairly, send reminders, and produce a clear order summary without public-cloud dependency.

## Target Users & Context
- **Primary user:** office teammate; place a coffee order quickly, volunteer or accept runner duty, confirm pickup/completion in Slack.
- **Secondary stakeholders:** office managers seeking fair participation and reduced coordination overhead; IT/security teams seeking internal-only deployment, OIDC control, auditability, and operational visibility.
- **Operating context:** Enterprise Slack workspace with events proxied through on-prem gateway; on-prem Kubernetes; internal identity and gateways only; assumed pilot volume of 5–50 users and 1–10 coffee runs/day; accessibility via Slack-native interactions and concise copy; i18n deferred.

## Value & Outcomes (with initial targets)
- Outcome 1: Reduce coffee-run coordination time to ≤2 minutes from `/coffee` start to order summary.
- Outcome 2: Reduce missed or ambiguous orders to ≤5% of submitted orders in pilot runs.
- Outcome 3: Improve runner fairness with no eligible teammate assigned more than 2 consecutive runs.
- Outcome 4: Increase transparency with 100% of active runs showing runner, order list, and current status.
- Outcome 5: Improve adoption with ≥60% of invited pilot users completing at least one order in week 1.

## Out of Scope (slice-1)
- Payments, reimbursements, expense handling, or payroll integration.
- Delivery logistics, café/vendor ordering APIs, POS integration, menu synchronization, or inventory management.
- Mobile app, web portal, email channel, Teams integration, or non-Slack channels.
- Advanced analytics, AI recommendations, nutrition tracking, loyalty features, or automation beyond reminders.
- Multi-office routing, cross-time-zone scheduling, and global preference/i18n rollout.

## Technology Constraints (SPEC-ready)
```yaml
tech_constraints:
  version: "1.1.0"
  metadata:
    name: "CoffeeBuddy"
    description: "On-prem Slack workflow for coordinating office coffee runs with fair runner assignment, reminders, and auditable order summaries."
    owner: "assumption: internal workplace-tools team"
    environment:
      - dev
      - qa
      - uat
      - prod
    criticality: "low"
    complexity: "medium"
    domain: "workplace_collaboration"
    compliance:
      - "GDPR"
      - "internal audit logging"
  classification:
    solution_type: "enterprise"
    location: "onprem"
    cloud_provider: "onprem"
    tenant_model: "single"
    data_sensitivity: "internal"
  project_definition:
    type: "enterprise_platform"
    framework: "FastAPI"
    language: "python"
    deployment_target: "on-prem Kubernetes"
  technology_stack:
    core:
      framework: "FastAPI"
      language: "Python 3.12"
      runtime: "ASGI on Kubernetes"
    frontend:
      primary: "Slack modal and message interactions"
      web_ui: "none for slice-1"
    database_and_backend:
      orm: "SQLAlchemy"
      database: "PostgreSQL"
      cache: "none for slice-1"
      auth: "OIDC via Ory Hydra and Ory Kratos"
    messaging:
      broker: "Apache Kafka"
      event_stream: "Slack events via Kong Gateway to Kafka-backed workers"
    observability_stack:
      logging: "structured application logs"
      tracing: "OpenTelemetry-compatible tracing, if platform sink exists"
      metrics: "Prometheus and Grafana"
  lanes:
    - name: "backend"
      lane: "python"
      purpose: "Slack event handling, order workflow, runner assignment, reminders, and REST health/admin endpoints"
      allowed_frameworks:
        - "FastAPI"
        - "Pydantic"
        - "SQLAlchemy"
      forbidden_technologies:
        - "Public-cloud-only managed bot backend"
        - "Unauthenticated internal APIs"
      default_test_profile:
        coverage_min: 80
        required_checks:
          - tests
          - lint
          - types
          - security
          - build
    - name: "slack-workflow"
      lane: "js-ts"
      purpose: "Slack app manifest, command/action contract tests, and interaction schema fixtures"
      allowed_frameworks:
        - "Slack Block Kit schemas"
        - "TypeScript test utilities"
      forbidden_technologies:
        - "External SaaS workflow host"
      default_test_profile:
        coverage_min: 70
        required_checks:
          - tests
          - lint
          - build
    - name: "ai-rag"
      lane: "python"
      purpose: "Reserved profile for future internal knowledge ingestion; disabled for slice-1"
      allowed_frameworks:
        - "FastAPI"
        - "Pydantic"
      forbidden_technologies:
        - "Sending confidential documents to public AI providers without approval"
      default_test_profile:
        coverage_min: 80
        required_checks:
          - tests
          - lint
          - security
  profiles:
    - name: "app-core"
      runtime: "python@3.12"
      platform: "on-prem-kubernetes"
      api:
        - "slack.events"
        - "rest"
      storage:
        - "postgres"
      messaging:
        - "kafka"
      auth:
        - "oidc"
        - "ory-hydra"
        - "ory-kratos"
      ingress:
        - "kong-gateway"
        - "nginx"
      secrets_management:
        - "hashicorp-vault"
      observability:
        - "prometheus"
        - "grafana"
        - "structured-logs"
    - name: "ai-rag"
      enabled: false
      runtime: "python@3.12"
      platform: "on-prem-kubernetes"
      purpose: "Future internal document Q&A only; not required for CoffeeBuddy slice-1"
      supported_formats:
        - "docx"
        - "pdf"
        - "xlsx"
        - "pptx"
      storage:
        - "postgres"
      vector_store:
        - "none-for-slice-1"
      messaging:
        - "kafka"
      auth:
        - "oidc"
      observability:
        - "prometheus"
        - "grafana"
  ci_cd:
    system: "jenkins"
    runners: "on-prem agents"
    pipelines:
      main_branch: "assumption: Jenkinsfile"
      deploy_pipeline: "assumption: Jenkins deployment job to Kubernetes"
    external_quality_gates:
      sonar:
        enabled: false
        project_key: "not-specified"
      security_scanner:
        enabled: true
        tool: "assumption: Trivy"
    default_branch_protection:
      require_pr: true
      require_reviews: 1
      require_status_checks: true
  security:
    internet_egress: "restricted"
    allowed_endpoints:
      - "Slack enterprise endpoints through approved gateway"
    secrets_management: "HashiCorp Vault"
    dependency_policy:
      allowlist:
        - "fastapi"
        - "pydantic"
        - "sqlalchemy"
        - "psycopg"
        - "confluent-kafka"
      denylist:
        - "hardcoded-secrets"
        - "public-cloud-only workflow runtimes"
    authentication:
      user_auth: "OIDC via Ory Hydra and Ory Kratos"
      service_auth: "Kubernetes service account plus Vault-managed secrets"
    authorization:
      method: "RBAC"
      policies_source: "OIDC groups or app database"
    data_protection:
      encryption_at_rest: true
      encryption_in_transit: true
      pii_handling: "Store Slack user IDs, display names, and preferences as internal data; mask tokens in logs; retain pilot data only per retention policy."
  data_management:
    primary_stores:
      - name: "coffeebuddy-db"
        engine: "postgres"
        location: "on-prem datacenter"
    backup_policy:
      rpo_minutes: 60
      rto_minutes: 240
    retention_policy:
      transactional_data_days: 365
      logs_days: 90
    migration_strategy: "Alembic"
  eval_profiles:
    default:
      coverage_min: 80
      max_critical_vulns: 0
      lint_must_be_clean: true
      allow_snapshot_tests: true
    relaxed_non_prod:
      coverage_min: 60
      max_critical_vulns: 0
      allow_flaky_tests: false
  ai_policies:
    enabled_for_slice_1: false
    allowed_providers: []
    allowed_models: []
    rag_supported_formats:
      - "docx"
      - "pdf"
      - "xlsx"
      - "pptx"
    data_boundary: "on-prem only unless separately approved"
    logging:
      prompt_logging_enabled: false
      redaction_required: true
```

## Deployment Portability Rule (MANDATORY WHEN APPLICABLE)
- Primary delivery profile is on-prem Kubernetes with Kong Gateway, Ory Hydra/Kratos, PostgreSQL, Kafka, Vault, Prometheus, Grafana, and Jenkins.
- Secondary supported profile is not required for slice-1; local developer execution may emulate dependencies but is not a production deployment target.
- Functional parity is required between local test mode and on-prem deployment for Slack event handling, order lifecycle, runner assignment, reminders, and audit records.
- Allowed differences are limited to infrastructure adapters for ingress, secrets, local test doubles, and observability sinks.
- Business APIs, coffee-run lifecycle states, audit semantics, and operator workflows must remain unchanged across local and on-prem profiles.

## Technology Constraints Profile Rule
- Profile-based options are defined for `app-core` and reserved `ai-rag`.
- Platform is on-prem Kubernetes for production; local mode is for development/testing only.
- Object storage is not required for slice-1.
- Messaging uses Kafka in production; local test mode may use deterministic Kafka-compatible test fixtures.
- Secrets management uses HashiCorp Vault in production; local mode must use non-committed environment variables or sealed test secrets.
- Observability sinks are Prometheus/Grafana and structured logs; local mode may write console logs and test metrics.
- AI serving runtime is disabled for slice-1; future RAG must remain on-prem unless separately approved.

## Risks & Assumptions
- **Business assumptions:** Slack enterprise is allowed internally; pilot team agrees to use `/coffee`; estimated targets assume 5–50 users and 1–10 coffee runs/day; office managers accept fairness rules.
- **Technical assumptions:** Slack events can be proxied through on-prem Kong Gateway; Ory Hydra/Kratos OIDC is available; Kafka, Postgres, Vault, Prometheus, Grafana, Jenkins, and Kubernetes namespaces are provisioned.
- **Delivery risks:** Slack rate limits, gateway approvals, IDP group mapping delays, and Kubernetes access may block the 10-day demo; mitigations include Kafka buffering, backoff, and mocked Slack fixtures for tests.
- **UX risks:** Adoption may be low if slash-command copy is unclear, runner assignment feels unfair, or reminders are noisy; mitigate with concise microcopy, opt-out rules, and transparent assignment history.

## Success Metrics (early slice)
- **TTFA (Time-to-First-Action):** ≤2 minutes from Slack `/coffee` command to published order summary.
- **Task success (slice flows):** ≥80% of pilot users complete order submission without assistance.
- **Critical error rate:** ≤2% failed Slack interactions or lost orders per coffee run operation.
- **Idea→Demo lead time:** ≤10 calendar days.
- **CSAT/NPS (pilot):** CSAT ≥4.0/5 from pilot teammates after week 1.

## Sources & Inspiration
- Internal notes: provided `IDEA.md` describing CoffeeBuddy, on-prem Slack workflow, Kubernetes, Kong Gateway, Ory Hydra/Kratos, PostgreSQL, Kafka, Vault, Jenkins, Prometheus, and Grafana.
- Market scan / baseline: Slack platform patterns referenced in the provided attachment; no external competitor scan was provided.

## Non-Goals
- Replace Slack as the user interface.
- Replace enterprise identity, gateway, CI, messaging, database, or observability platforms.
- Build a full workplace-services platform.
- Automate payments, purchasing, delivery, or café/vendor fulfillment.
- Support extreme scalability before validating the pilot workflow.
- Introduce AI/RAG behavior into slice-1.

## Constraints
- **Budget:** Assumption: limited to a 2-week slice with one small cross-functional delivery team.
- **Timeline:** Slice-1 demo-ready in ≤10 calendar days.
- **Compliance:** Internal-only deployment, GDPR-aware handling of Slack user identifiers and preferences, auditable order lifecycle events.
- **Legal:** No payment, contract, signature, or long-term document retention scope in slice-1.
- **Platform limits:** Slack rate limits and event retry semantics must be handled; production access depends on on-prem gateway, Kubernetes, OIDC, Kafka, Postgres, Vault, and Jenkins availability.

## Strategic Fit
- Link to company OKRs/initiatives: Assumption: supports internal productivity, employee experience, and enterprise-safe automation.
- Executive sponsors and “go/no-go” gates: Assumption: office manager sponsors pilot; IT/security approves Slack app, gateway route, secrets, and audit posture before production.
- Cross-function impacts (IT Sec, DPO, HR, Finance): IT Sec reviews internal-only deployment and secrets; DPO reviews user preference retention; HR/office management reviews fairness and adoption; Finance is not impacted because payments are out of scope.

## /spec Handoff Readiness (bridge section)
- **Functional anchors:** Slack command starts coffee run for the primary user and supports Outcome 1.
- **Functional anchors:** Acceptance hooks: given a user enters `/coffee`, when the command is valid, then CoffeeBuddy opens or posts the active run flow within 3 seconds; given no active run exists, then a new run is created with status `collecting`; given an active run exists, then the user is routed to add an order instead of creating a duplicate run.
- **Functional anchors:** Order capture records drink preference for the primary user and supports Outcomes 1 and 2.
- **Functional anchors:** Acceptance hooks: given a user submits an order, then drink name and optional notes are stored with Slack user ID and timestamp; given required fields are missing, then Slack shows a clear validation message; given submission succeeds, then the order appears in the run summary.
- **Functional anchors:** Fair runner assignment selects one eligible teammate and supports Outcome 3.
- **Functional anchors:** Acceptance hooks: given eligible users exist, then the runner is selected without assigning the same user more than 2 consecutive runs; given a user is unavailable or opted out for a run, then they are excluded; given assignment completes, then the runner and reason are visible in the summary.
- **Functional anchors:** Reminder workflow notifies pending participants and runner and supports Outcomes 1 and 4.
- **Functional anchors:** Acceptance hooks: given a run is collecting, then CoffeeBuddy sends a reminder before close time; given runner assignment is complete, then runner receives pickup reminder; given Slack delivery fails, then the failure is logged and retried with backoff.
- **Functional anchors:** Run summary publishes status, orders, and runner and supports Outcomes 2 and 4.
- **Functional anchors:** Acceptance hooks: given a run is closed, then the summary includes all submitted orders and runner; given an order changes before close, then summary reflects the latest version; given a user views the summary, then no secret tokens or internal IDs are exposed.
- **Functional anchors:** Preference memory reuses previous order details and supports Outcomes 1 and 5.
- **Functional anchors:** Acceptance hooks: given a returning user has a prior order, then the next order flow pre-fills or suggests that preference; given the user edits it, then the new preference is saved; given the user has no prior order, then no suggestion is shown.
- **Functional anchors:** Audit and operations endpoints support IT/security stakeholders and production readiness.
- **Functional anchors:** Acceptance hooks: given a run changes lifecycle state, then an audit event is persisted; given an operator checks health, then REST health endpoints report database and Kafka connectivity; given an incident occurs, then logs include correlation IDs without secrets.
- **Non-functional anchors:** Performance: Slack acknowledgement P95 ≤3 seconds; order submission P95 ≤1 second after acknowledgement; support assumed pilot throughput of 10 runs/day and 50 users.
- **Non-functional anchors:** Availability/SLA: target 99.0% during office hours for pilot; graceful degradation if Kafka or Slack callback delivery is delayed.
- **Non-functional anchors:** Security: OIDC-backed admin/operator access; RBAC for operator endpoints; internal data classification for Slack IDs, display names, orders, and preferences; Vault-managed secrets; restricted egress.
- **Non-functional anchors:** Observability: structured logs with correlation IDs, Prometheus metrics for commands/orders/errors, Grafana dashboard for run volume and error rate, trace propagation where platform support exists.
- **Non-functional anchors:** Data lifecycle: retain transactional coffee-run data for 365 days and logs for 90 days unless policy changes; mask tokens and avoid logging free-text secrets; support deletion of user preferences on request.