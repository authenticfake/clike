# CLike Harper Telemetry Portal

## Overview

The CLike Harper Telemetry Portal is a lightweight operational dashboard for inspecting Harper pipeline execution data across IDEA, SPEC, PLAN, KIT, EVAL, GATE, and FINALIZE phases.

It provides engineering teams with a centralized view of model usage, run duration, token consumption, generated artifacts, evaluation outcomes, and gate decisions. The portal supports the CLike objective of making AI-native development observable, auditable, and continuously improvable.

Default local URL:

```text
http://localhost:8000/v1/metrics/harper/ui
```

The portal is served by the Gateway telemetry routes under:

```text
/v1/metrics/harper
```

---

## Functional Purpose

The Telemetry Portal helps product engineers and platform owners answer practical questions such as:

- Which Harper phases were executed for a project?
- Which model/provider was used for each run?
- How many tokens were consumed?
- How long did each phase take?
- Which REQs passed or failed evaluation?
- Which REQs were promoted or blocked by the gate?
- Which runs are expensive, slow, unstable, or repeatedly failing?
- How does Agent execution compare with Cloud execution?

The portal is not only a reporting UI. It is part of the Eval-Driven Development feedback loop: telemetry data helps identify bottlenecks, model quality issues, prompt regressions, and pipeline defects.

---

## Technical Architecture

The telemetry UI is exposed by the Gateway service.

```text
VS Code Extension
  -> Orchestrator
      -> Gateway
          -> /v1/metrics/harper/ui
          -> /v1/metrics/harper/*
```

Telemetry files are read from the configured Harper telemetry directory:

```text
HARPER_TELEMETRY_DIR
```

Default directory:

```text
/workspace/telemetry
```

Each Harper phase can emit telemetry containing:

- project ID
- phase name
- run ID
- provider
- model
- context window
- prompt/input tokens
- completion/output tokens
- duration
- generated or changed files
- test counts
- eval status
- gate decisions
- error and warning metadata

---

## Main Endpoints

### Telemetry UI

```http
GET /v1/metrics/harper/ui
```

Browser-based dashboard for interactive telemetry inspection.

### Projects

```http
GET /v1/metrics/harper/projects
```

Lists projects with available telemetry data.

### Files

```http
GET /v1/metrics/harper/files
```

Lists raw telemetry files available to the Gateway.

### Aggregate Metrics

```http
GET /v1/metrics/harper/aggregate?project_id=<PROJECT_ID>
```

Returns aggregated metrics for a project.

Typical use cases:

- total runs by phase
- total token usage
- total duration
- pass/fail counts
- model/provider distribution

### Time Series

```http
GET /v1/metrics/harper/series?project_id=<PROJECT_ID>
```

Returns time-series telemetry for trend analysis.

Typical use cases:

- token usage over time
- phase duration trend
- evaluation stability
- gate pass/fail trend

### Top Runs

```http
GET /v1/metrics/harper/top?project_id=<PROJECT_ID>&limit=10
```

Returns top runs by cost, duration, token usage, or other ranking criteria exposed by the Gateway.

### Raw Telemetry

```http
GET /v1/metrics/harper/raw?project_id=<PROJECT_ID>
```

Returns raw telemetry records for debugging or external analysis.

---

## Why It Matters

CLike is designed as an AI-native software engineering pipeline where human intent is translated into verifiable software through short, governed iterations.

Telemetry is essential because AI-generated software must not be treated as a black box. Every run should be observable and explainable.

The portal supports:

- governance
- auditability
- reproducibility
- cost control
- model comparison
- eval-driven improvement
- agent vs cloud execution analysis
- detection of recurring prompt or pipeline failures

---

## Example Workflow

A typical usage flow is:

```text
/spec
/plan
/kit REQ-003
/eval REQ-003
/gate REQ-003
```

Then open:

```text
http://localhost:8000/v1/metrics/harper/ui
```

Use the portal to inspect:

1. The model used for each phase.
2. Duration and token usage.
3. Whether `/eval` passed or failed.
4. Which test or lint case failed.
5. Whether `/gate` promoted or blocked the REQ.
6. Whether the failure came from code, runtime setup, missing dependencies, or structural gate blockers.

---

## Operational Value

The Telemetry Portal gives CLike a measurable feedback loop.

Without telemetry, AI-native development risks becoming opaque: models generate code, agents execute actions, and developers only see the final output.

With telemetry, every phase becomes measurable:

```text
intent -> generation -> evaluation -> gate -> promotion
```

This allows the team to improve:

- prompt quality
- model routing
- agent package design
- eval contracts
- gate policies
- dependency handling
- cloud vs local agent performance

---

## Recommended Slide Summary

The CLike Harper Telemetry Portal provides a real-time operational view of the AI-native development pipeline. It captures model, token, duration, artifact, eval, and gate data for each Harper phase, enabling teams to compare Cloud and Agent executions, detect failures, control costs, and continuously improve prompt, eval, and gate quality. It turns vibe coding into an auditable, eval-driven engineering workflow.

---

## Recommended Checks

Before using the portal, verify:

```bash
echo "$HARPER_TELEMETRY_DIR"
```

Start the Gateway and open:

```text
http://localhost:8000/v1/metrics/harper/ui
```

If the portal shows no data:

1. Confirm that Harper commands generated telemetry files.
2. Confirm the Gateway can read `HARPER_TELEMETRY_DIR`.
3. Confirm the project ID matches the telemetry records.
4. Check Gateway logs for file parsing or path errors.

---

## Future Improvements

Recommended next improvements:

- Add Cloud vs Agent comparison panels.
- Add cost estimation per provider/model.
- Add failure taxonomy: code failure, runtime failure, dependency failure, gate failure.
- Add per-REQ trend analysis.
- Add downloadable CSV/JSON exports.
- Add model quality scorecards.
- Add gate blocker visualization.
- Add eval case drill-down with raw logs.
