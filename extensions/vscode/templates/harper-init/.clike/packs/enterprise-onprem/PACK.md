---
name: enterprise-onprem
description: Use for enterprise, regulated, on-prem, hybrid, air-gapped, or internal platform scenarios.
domains: ["enterprise"]
default_runtime_profiles: ["local", "on-prem", "hybrid", "air-gapped", "local-cloud"]
recommended_skills: ["local-cloud-parity", "eval-contract-writer", "gate-risk-reviewer"]
gate_required: true
---

# Enterprise On-Prem Pack

## Intent

This pack guides CLike when generating software for enterprise environments where governance, auditability, controlled deployment, reproducibility, and runtime constraints matter.

## Planning Constraints

- Do not assume public SaaS availability unless explicitly allowed.
- Prefer explicit adapters and configuration seams.
- Keep local execution possible when external systems are unavailable.
- Treat secrets, credentials, tokens, certificates, and endpoints as external configuration.
- Do not hardcode credentials or endpoint-specific assumptions.
- Document runtime assumptions clearly.
- Keep generated implementation promotable and reviewable.

## KIT Constraints

- Generated code must be modular but not over-engineered.
- Runtime profile behavior must be explicit.
- Unit tests must avoid real external calls.
- Integration tests must be opt-in when external systems are required.
- HOWTO must include local execution steps and enterprise/runtime notes.
- If an enterprise runner such as Jenkins, GitLab CI, Azure DevOps, or SonarQube is required, document how artifacts are expected to be collected.

## Gate Expectations

- tests
- lint
- types where applicable
- security where applicable
- runtime_profile_adherence
- skill_adherence
- documentation completeness
- future compatibility safety