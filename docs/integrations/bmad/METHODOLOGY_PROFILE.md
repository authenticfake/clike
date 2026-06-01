# BMAD Methodology Profile

The BMAD methodology profile is a CLike-owned integration layer that maps Harper phases to BMAD-style roles. The profile is intentionally compact and operational. It is metadata and guidance, not an executor.

## Supported Methodology

- `bmad`

No external BMAD runtime is required. CLike does not install BMAD, execute BMAD CLIs, or call `npx bmad-method`.

## Request Fields

Methodology-aware requests may include:

- `methodology`
- `agent`
- `methodology_context`

The orchestrator is the single resolver for `methodology_context`. Clients may pass user intent, but resolved authority, defaults, and phase mapping belong to the orchestrator.

## Phase Mapping

| Harper phase | Default BMAD role | Allowed roles | Notes |
| --- | --- | --- | --- |
| `idea` | `analyst` | `analyst` | Discovery and intent framing |
| `spec` | `pm` | `pm`, `ux` | Requirements and UX acceptance detail |
| `plan` | `architect` | `architect`, `pm` | Technical slicing and dependencies |
| `kit` | `developer` | `developer` | Candidate implementation guidance |
| `eval` | `qa` | `qa`, `developer` | Advisory only; EvalRunner remains authoritative |
| `gate` | none | none | CLike-only authority |
| `finalize` | `tech-writer` | `tech-writer` | Release and documentation guidance |

## Methodology Is Not Execution

Methodology identity is separate from:

- `profileHint`
- cloud model routing
- `localAgentExecutor`
- Claude Code or Codex CLI selection
- eval/gate verdicts

BMAD enriches the work style for a phase. It does not decide where execution runs, what model is used, what files can be written, or whether a REQ is promotable.

