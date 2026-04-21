---
name: local-cloud-parity
description: Use when a requirement integrates with external infrastructure but must remain runnable and testable locally.
phases: ["plan", "kit", "eval", "gate"]
lanes: ["python", "typescript", "java", "dotnet", "go", "iac"]
domains: ["consumer", "startup", "enterprise", "industrial", "manufacturing", "ai-native"]
runtime_profiles: ["local", "cloud", "local-cloud", "on-prem", "edge", "hybrid"]
gate_required: true
---

# Local/Cloud Parity Skill

## Intent

Generated software must support both realistic production/cloud execution and deterministic local execution when the REQ touches external infrastructure.

## Requirements

- Provide a production/cloud adapter when the REQ requires real infrastructure.
- Provide a local deterministic adapter or simulator when the REQ must be testable locally.
- Use explicit configuration to select the runtime implementation.
- Unit tests must not call real cloud services.
- Integration tests that require real services must be opt-in and clearly documented.
- Documentation must explain local execution and production/cloud execution separately.

## Evaluation

The REQ satisfies this skill only if:
- both local and production/cloud paths are represented when applicable;
- the local path is executable without cloud credentials;
- tests cover the local path;
- HOWTO documents both paths;
- missing runtime dependencies are reported truthfully instead of hidden.
