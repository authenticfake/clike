# IDEA — SkillMesh

## Vision
SkillMesh builds a live, internal “skill graph” of the organization, connecting people, skills, and opportunities. It surfaces matches directly in Slack when new initiatives appear—enabling startup-like staffing speed inside an enterprise-grade environment, starting from a minimal app+DB setup and evolving to an event-driven architecture when needed.

## Problem Statement
Enterprises struggle to quickly find people with the right skills and availability for new projects, innovation spikes, or short-term task forces. Information about skills, interests, and learning goals is scattered across HR systems, static CVs, personal notes, and ad-hoc Slack messages.

Existing tools are either heavy HR platforms or external SaaS solutions that may not be acceptable in regulated environments. There is a need for a lightweight, Slack-native, event-ready solution that can run fully on-prem, but that does not require complex infrastructure just to get started.

SkillMesh must provide:
- A frictionless way for employees to declare and maintain skills and interests inside Slack.
- A simple flow for project leads to describe opportunities and request profiles.
- A matching engine that can initially run inside a single service with a relational database, and later leverage Kafka and more advanced processing without changing the external behaviors.

## Target Users & Context
- Primary: Project leads, engagement managers, and product owners who need to staff initiatives quickly with the right mix of skills.
- Secondary: Employees who want to advertise their skills, interests, and growth areas to find better-fitting opportunities.
- Context:
  - Enterprise Slack workspace as the main collaboration and notification channel.
  - HRIS (e.g., Workday, SAP SuccessFactors) as the system of record for basic employee data.
  - Minimal deployment: one backend service + relational database for profiles and opportunities.
  - Optional enterprise deployment: on-prem Kubernetes, internal API gateways, Kafka, and central identity providers.

## Value & Outcomes
- Faster staffing of internal initiatives and PoCs by making skills and interests queryable and discoverable.
- Better visibility of hidden or emerging skills in the organization, beyond static CVs and job titles.
- Higher employee engagement by matching people to work aligned with their interests and learning goals.
- Architecture that can grow: from a simple CRUD + matching service to an event-driven “skill graph” platform that feeds analytics and AI-based recommenders.

## Out of Scope
- Formal performance management, compensation, or promotion workflows.
- External contractor management or vendor sourcing.
- Replacement of the HRIS as the master system for employment and legal data.

## Technology Constraints
```yaml
tech_constraints:
  version: 1.0.0
  profiles:
    - name: minimal
      description: Minimal profile to support end-to-end matching without heavy infra.
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
      description: Optional enterprise profile for high-scale and tighter governance.
      runtime: python
      platform: kubernetes
      ingress: nginx
      api:
        - slack.events
        - rest
        - hris.webhooks
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
        ha: false
    - type: db.relational
      vendor: postgres
      params:
        ha: true
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
- HRIS exposes at least read-only APIs or data feeds to retrieve employee identifiers, departments, job families, and possibly locations.
- Slack enterprise is adopted as the primary messaging platform in the organization.
- Employees are willing to maintain their skill profiles if the Slack UX is simple and non-intrusive.

Risks:
- Data quality of self-declared skills may vary; mitigated with endorsements, usage signals from real projects, and optional manager validation.
- Perception of surveillance or ranking if communication is not clear; mitigated by explicit “opt-in” flows and avoiding any scoring or ranking used for performance evaluations.
- Integration complexity with HRIS in the enterprise profile; mitigated by allowing a CSV/flat-file ingestion path in the minimal profile and evolving later.

## Success Metrics (early)
- Time-to-staff for small initiatives and PoCs (from opportunity creation to first set of suggested candidates).
- Number of active profiles with up-to-date skills and interests compared to total eligible employees.
- Percentage of opportunities that receive at least N suitable candidate suggestions within a target time window (e.g., 48 hours).
- Qualitative signal: satisfaction with match quality collected via short Slack surveys (“Were these suggestions useful?”).

## Sources & Inspiration
- Internal talent marketplace and skill graph concepts used in large enterprises.
- Startup-style “internal gig marketplace” tools, reimagined for on-prem and event-driven setups.
- Clike/Harper methodology to keep the solution decomposed into IDEA → SPEC → PLAN → KIT, enabling continuous refinement and governance.
