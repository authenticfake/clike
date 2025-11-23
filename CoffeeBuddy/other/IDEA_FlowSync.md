# IDEA — FlowSync

## Vision
FlowSync orchestrates focus time, meetings, and interruptions across distributed teams by using Slack, calendars, and event streams. It protects deep work windows while ensuring urgent requests still reach the right people—without leaving the enterprise perimeter and without requiring heavy infrastructure from day one.

## Problem Statement
Knowledge workers are constantly interrupted by ad-hoc Slack pings, fragmented calendars, and overlapping meetings. Deep work time is squeezed out, and there is no shared, transparent way to coordinate “do not disturb” vs “available for collaboration” states at team level.

Existing approaches are either individual hacks (manual status changes, personal calendar blocks) or heavy external SaaS products that are not suitable for regulated environments. Many enterprises also cannot depend on public cloud services for coordination logic and data residency reasons.

FlowSync must provide:
- A Slack-native experience to declare focus time and availability.
- A policy engine to orchestrate status, notifications, and exceptions.
- A minimal deployment model (single app + database) that can later evolve into a fully event-driven, Kafka-backed architecture without breaking the functional contract.

## Target Users & Context
- Primary: Knowledge workers and engineers who need recurring focus blocks and predictable interruption patterns.
- Secondary: Team leads and project managers who want visibility into focus vs collaboration time without reading private calendar details.
- Context:
  - Enterprise Slack workspace as the main collaboration channel.
  - Corporate calendars (Google Workspace or Microsoft 365) as the source of truth for meetings.
  - Minimal deployment: one backend service and a relational database.
  - Optional enterprise deployment: on-prem Kubernetes, internal API gateways, centralized identity, and Kafka for event-driven processing.

## Value & Outcomes
- Protect predictable daily/weekly focus blocks with team-aware rules instead of ad-hoc status changes.
- Reduce unplanned interruptions and Slack noise during focus time, while preserving a safe channel for urgent matters.
- Provide a shared, visual understanding of “focus vs collaboration” time at team level, without exposing sensitive calendar contents.
- Offer an incremental architecture: start with minimal app+DB, then plug in Kafka, observability, and enterprise identity when needed.

## Out of Scope
- Full calendar replacement or complex meeting scheduling algorithms.
- Performance evaluation, employee ranking, or intrusive productivity scoring.
- Cross-company federation between different enterprises or external tenants.

## Technology Constraints
```yaml
tech_constraints:
  version: 1.0.0
  profiles:
    - name: minimal
      description: Minimal viable deployment to keep end-to-end flow simple.
      runtime: python
      platform: container
      api:
        - slack.events
        - rest
      storage:
        - postgres
      messaging: []
      auth: []
      observability: []
    - name: enterprise_onprem_optional
      description: Optional enterprise profile for regulated environments.
      runtime: python
      platform: kubernetes
      ingress: nginx
      api:
        - slack.events
        - rest
        - calendar.webhooks
      storage:
        - postgres
      messaging:
        - kafka
      auth:
        - oidc
      observability:
        - prometheus
        - grafana
  capabilities:
    - type: db.relational
      vendor: postgres
      params:
        ha: false         # minimal
    - type: db.relational
      vendor: postgres
      params:
        ha: true          # optional enterprise
    - type: mq.stream
      vendor: apache.kafka
      params:
        partitions: 6
        optional: true
    - type: api.gateway
      vendor: Kong Gateway
      params:
        routes: internal-only
        optional: true
    - type: idp
      vendor: Ory Hydra
      params:
        oidc: true
        optional: true
    - type: secrets.manager
      vendor: hashicorp.vault
      params:
        optional: true
```

## Risks & Assumptions

Assumptions:
- Slack enterprise workspaces are available and allowed internally.
- Calendar APIs (Google Workspace or Microsoft Graph) can be accessed either directly or through an internal gateway.
- Teams are willing to adopt simple conventions (e.g., always triggering focus mode via a Slack command or shortcut).

Risks:
- Misconfigured focus rules could block genuinely urgent communication; mitigated via “priority contacts”, emergency override commands, and a visible “break glass” option in Slack.
- Calendar data privacy concerns; mitigated by storing only time windows and categories instead of event titles/descriptions.
- Overly complex enterprise integration could slow down adoption; mitigated by keeping the minimal profile (single app + DB) as the default onboarding path.

## Success Metrics (early)
- Increase in average daily uninterrupted focus blocks per user (e.g., at least one 90-minute block per day for active users).
- Reduction in Slack messages sent during declared focus windows for teams actively using FlowSync.
- Number of teams with at least one active focus policy configured.
- Qualitative satisfaction: lightweight Slack surveys after focus sessions (e.g., “Was this focus window protected enough?”).

## Sources & Inspiration
- Deep work principles and maker/manager schedule ideas (Cal Newport, industry best practices).
- Internal standards for Slack apps, calendar integration, Kafka, and observability, where available.
- Existing Clike/Harper patterns for IDEA → SPEC → PLAN → KIT flows, to keep the solution evolvable and testable.
