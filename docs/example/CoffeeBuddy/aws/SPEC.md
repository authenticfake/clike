
---

## `docs/harper/SPEC.md`
```markdown
# SPEC — CoffeeBuddy

## Problem
Coffee coordination in Slack is fragmented: messages get buried, someone forgets to pick up, and preferences are not captured. The result is wasted time and inconsistent experiences.

## Objectives
1) Enable a complete coffee run in Slack within 2 minutes.  
2) Ensure fairness by balancing runner assignments over time.  
3) Remember user preferences to pre-fill orders.

## Scope
- Slack slash commands and interactive messages to create/join a run, select drinks, and confirm pickup.
- Automatic runner assignment and reminders.
- History of orders and user preferences.

## Non-Goals
- Payments, delivery, and vendor-specific integrations.

## Constraints
- Operate within Slack app permissions and rate limits.
- Comply with company security policies for secrets and PII storage.

## KPIs
- Median time from `/coffee` to confirmation ≤ 2 minutes.
- Runner fairness index ≥ 0.8 (balanced assignments).
- Error rate per run ≤ 1%.

measurement: KPIs are measured via Slack event logs and CloudWatch metrics aggregated daily and reported weekly.

## Assumptions
- Slack workspace admin approves the app installation.
- Users understand basic slash command flows.

## Risks
- Slack rate limits or interactive latency.
- Low adoption due to missing reminders.

## Acceptance Criteria
- **REQ-001 — Create a coffee run via `/coffee`**  
  Test: functional (Slack event simulation)  
  Evidence: passing e2e test + logs
- **REQ-002 — Join/submit order with preferences**  
  Test: unit + functional  
  Evidence: unit coverage for preference model + e2e order flow
- **REQ-003 — Automatic runner assignment**  
  Test: integration (deterministic assignment algorithm)  
  Evidence: contract test verifying assignment fairness
- **REQ-004 — Reminders and status updates**  
  Test: scheduled job (time-shifted test)  
  Evidence: passing timer/queue tests with recorded logs
- **REQ-005 — Order history and audit trail**  
  Test: integration (DB)  
  Evidence: migration + repository tests, data retention checks
- **REQ-006 — Security baseline**  
  Test: SAST + secrets scanning  
  Evidence: clean Bandit/Semgrep report and no leaked secrets

## Sources & Evidence
- Slack API documentation (Events API, Interactivity, App Manifests).  
- Internal guidelines for serverless deployments on AWS and data handling.  
- Test artifacts stored under `runs/<ts>/eval/`.

## Technology Constraints
```yaml
tech_constraints:
  version: 1.0.0
  profiles:
    - name: cloud
      runtime: nodejs@20
      platform: serverless.aws
      api:
        - slack.events
        - rest
      storage:
        - postgres
      messaging:
        - sns-sqs
      auth:
        - slack.oauth2
      observability:
        - cloudwatch
  capabilities:
    - type: api.slack
      vendor: slack
      params:
        app_manifest: true
        signing_secret: env:SLACK_SIGNING_SECRET
    - type: db.relational
      vendor: postgres
      params:
        plan: serverless
    - type: queue
      vendor: aws.sqs
      params: {}
    - type: secrets.manager
      vendor: aws.secretsmanager
      params: {}
    - type: ci.ci
      vendor: github.actions
      params: {}
