# Future MCP Write Tools

MCP write tools are a future roadmap item. They are not implemented in the current CLike MCP server.

The current orchestrator MCP surface is read-only. It supports repository and Harper visibility, but not mutation. Current MCP does not provide phase execution, file writes, Git mutation, shell execution, promotion, or gate override.

## Future Requirements

If MCP write tools are added later, they must be scoped, idempotent, audited, dry-run capable, approval-gated, controlled-root-only, and unable to bypass eval or gate.

Future write tools must:

- use explicit CLike governance contracts
- preserve allowed write roots and forbidden paths
- require auditable intent
- support dry-run previews before mutation
- be approval-gated for any material write
- write only inside controlled roots
- avoid arbitrary filesystem writes
- avoid arbitrary shell execution
- produce deterministic reports where possible
- be idempotent or clearly report non-idempotent effects
- never directly promote artifacts
- never mutate Git state unless a separate governed Git flow authorizes it
- never allow BMAD or any methodology profile to override eval/gate authority

BMAD methodology context may inform future MCP-assisted workflows, but it must not grant authority, permissions, write access, promotion rights, or gate authority.
