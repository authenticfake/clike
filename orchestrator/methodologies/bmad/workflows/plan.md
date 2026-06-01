# BMAD-Aware PLAN Workflow

CLike-owned compact workflow guidance. Make requirements implementation-legible for `/kit`.

- Each REQ must cover Functional Scope, Technical Scope, Non-Functional Requirements, Security Requirements, Compliance and Privacy Requirements when applicable, and Observability and Operations.
- Declare Integration Contracts, Data Contracts, dependencies, runtime and deployment constraints, and dependency assumptions.
- Include acceptance criteria, test strategy, risk and mitigation, main module boundary, and gate expectations when relevant.
- Carry TECH_CONSTRAINTS obligations into REQ details, including cloud/on-prem parity, air-gapped mode, provider portability, internal registry use, identity constraints, and deployment-specific behavior.
- State what `/kit` must build now, what this REQ builds now, what this REQ intentionally defers, and what downstream REQs may assume.
- Keep `plan.json` machine-readable with functional_scope, technical_scope, non_functional_requirements, security_requirements, compliance_requirements, operational_requirements, integration_contracts, data_contracts, test_strategy, risk_notes, main_module_boundary, runtime_profile when known, and gate_expectations when relevant.
- Do not assume Python, Node, cloud-only delivery, or any stack unless TECH_CONSTRAINTS, SPEC, repository evidence, or explicit user input supports it.
- Keep PLAN and `plan.json` canonical under CLike control.
