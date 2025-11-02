# IDEA — CoffeeBuddy

## Vision
CoffeeBuddy is a Slack mini-app that organizes office coffee runs: teammates submit orders via Slack, one person (the runner) is assigned automatically, reminders are sent, and preferences are remembered.

## Problem Statement
Teams waste time coordinating coffee orders in ad-hoc threads. Orders are lost, someone forgets, and preferences are not tracked. CoffeeBuddy standardizes the flow inside Slack and reduces coordination time.

## Target Users & Context
- Primary: office teammates who want to place and pick up coffee orders.
- Secondary: office managers who care about fairness and time savings.
- Context: Slack workspace; lightweight serverless backend; mobile-friendly interactions.

## Value & Outcomes
- Faster coordination (<2 minutes per coffee run).
- Fewer errors (consistent order summaries).
- Fair runner assignment across the team.

## Out of Scope
Payments, delivery logistics, vendor integrations beyond Slack interactions.

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
        slash_commands: ["/coffee", "/coffee-status"]
    - type: db.relational
      vendor: postgres
      params:
        plan: serverless
    - type: secrets.manager
      vendor: aws.secretsmanager
      params: {}
    - type: ci.ci
      vendor: github.actions
      params: {}
```


## Risks & Assumptions

Assumption: Slack workspace admin can install apps.

Risk: Rate limits on Slack events; mitigated via queue buffering.

## Success Metrics (early)

Weekly active coffee runs per active user.

Time from first command to order confirmation.

## Sources & Inspiration

Slack platform patterns and internal team feedback sessions.