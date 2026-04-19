# Documentation Rewrite Report

## Basis of rewrite

This rewrite was produced from:
- the attached Harper / RAG / Git / process reference docs
- direct inspection of the packaged source tree
- runtime config and route inspection across:
  - `extensions/vscode`
  - `orchestrator`
  - `gateway`
  - `configs`
  - `docker`

## Main drift found

### Still correct
- The architecture split between extension, orchestrator, and gateway
- Harper as the central workflow model
- Candidate-first KIT artifact generation
- RAG as an implemented capability
- Eval/Gate as explicit phases
- Git and promotion as first-class concerns

### Partially correct but outdated
- Some docs described local execution only in Claude-centric terms, while the current extension supports both Claude Code and GPT Codex behind a normalized local-agent layer
- Some docs treated `/kit` as a single step without fully reflecting the implemented follow-up phases:
  - `integrity_eval`
  - `promotion_hardener`
  - `promotion_eval`
- Some docs described MCP directionally; the current source already mounts a read-only MCP server with a concrete tool inventory
- Some docs described RAG in broad terms but did not fully reflect the current orchestrator endpoint set
- Some docs described Git naming patterns too rigidly even though the current inspected materials show multiple conventions

### Wrong or too strong
- Any claim that local agents freely own all Harper phases
- Any claim that local agent execution directly writes canonical `src/` / `test/` roots
- Any claim that MCP currently executes phases or mutates Git
- Any claim that a chat slash command currently changes the default local executor
- Any claim that GPT Codex is absent from the local execution path

### Missing in prior material
- `AGENT_EXECUTION_CONTEXT.json`
- local eval pre-pass model
- current normalized execution preference values
- explicit local executor inventory
- orchestrator and gateway endpoint census
- telemetry endpoint census
- MCP tool census
- follow-up KIT phase details

## Files produced

- `README.md`
- `architecture.md`
- `setup-and-runtime.md`
- `commands.md`
- `harper-workflow.md`
- `artifacts.md`
- `local-agents.md`
- `rag.md`
- `git-and-promotion.md`
- `mcp.md`
- `api-reference.md`

## Editorial policy used

- Code wins over prose
- Conservative wording for unstable or mixed areas
- Current behavior is separated from future direction
- Experimental or restricted capabilities are labeled as such
- No product-marketing filler
