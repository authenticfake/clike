---
name: industrial-control-room
description: High-trust, data-dense, operator-focused UI for industrial monitoring, manufacturing workflows, and control-room dashboards.
domains: ["industrial", "manufacturing"]
lanes: ["frontend", "typescript", "nextjs", "react"]
inspired_by: ["IBM Carbon", "ClickHouse", "BMW", "NVIDIA"]
strictness: "medium"
---

# Industrial Control Room Design Profile

## Intent

Use this profile for industrial dashboards, manufacturing consoles, shop-floor monitoring, telemetry views, and operational control-room experiences.

## Visual Principles

- Prioritize clarity, state visibility, and operator confidence.
- Use dense but readable layouts for telemetry and process status.
- Use color primarily for severity, status, alarms, and action priority.
- Avoid decorative visuals that reduce scan speed.
- Keep typography, spacing, and alignment consistent.
- Make dangerous or irreversible actions visually distinct and confirmation-based.

## UX Principles

- Current system state must be visible.
- Alarm, degraded, offline, warning, and nominal states must be distinguishable.
- Prefer dashboards, tables, timelines, status cards, and detail panels.
- Do not hide operationally critical information behind excessive animations.
- Provide clear empty, loading, stale-data, and disconnected states.
- Treat command/write flows as safety-sensitive.

## Evaluation

A UI REQ satisfies this profile only if:
- operator state visibility is clear;
- status and severity states are represented;
- error/disconnected/stale-data states are considered;
- unsafe actions are not made casual;
- generated docs mention runtime and safety assumptions.