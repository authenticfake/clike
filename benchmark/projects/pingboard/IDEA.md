# IDEA — PingBoard

## Vision
A tiny internal web page that shows whether three internal HTTP services answer `/health`.

## Problem Statement
Developers check service health by hand with curl several times a day.

## Target Users & Context
Developers of a 5-person team, on the internal network.

## Value & Outcomes
One page with green/red status; saves a few minutes per developer per day.

## Out of Scope
Authentication, alerting, history, more than three services.

## Technology Constraints
```yaml
tech_constraints:
  runtime: python
  version: "3.12"
  framework: fastapi
  storage: none
```

## Risks & Assumptions
Services answer within 2 seconds; the page polls every 30 seconds.

## Success Metrics
Status of all three services visible within 1 second of opening the page.
