# Future MCP Write Tools

MCP write tools are a future roadmap item. They are not implemented in the current CLike MCP server.

## Current State

The current orchestrator MCP surface is read-only. It supports repository and Harper visibility, but not mutation.

Current MCP does not provide:

- phase execution
- file writes
- Git mutation
- shell execution
- promotion
- gate override

## Future Requirements

If MCP write tools are added later, they must:

- use explicit CLike governance contracts
- preserve allowed write roots and forbidden paths
- require auditable intent
- avoid arbitrary filesystem writes
- avoid arbitrary shell execution
- separate read-only planning from mutation
- never allow BMAD or any methodology profile to override eval/gate authority

BMAD methodology context may inform future MCP-assisted workflows, but it must not grant authority or permissions.

