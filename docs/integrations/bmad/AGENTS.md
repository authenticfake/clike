# BMAD Agents

BMAD roles in CLike are expressive methodology personas. They may be detailed and opinionated, but they do not own workflow authority.

## Supported Roles

| Role | Primary use |
| --- | --- |
| `analyst` | Intent framing, users, outcomes, constraints, assumptions |
| `pm` | Requirements, acceptance criteria, scope, prioritization |
| `architect` | Architecture, dependencies, technical slicing, integration boundaries |
| `developer` | Candidate implementation guidance for KIT |
| `ux` | User journeys, accessibility, interaction acceptance criteria |
| `qa` | Advisory eval repair guidance |
| `tech-writer` | Release notes, README quality, final documentation |

## Agent Boundaries

BMAD agents may:

- enrich phase guidance
- suggest files to inspect
- describe risks and contract gaps
- recommend repair strategy
- improve clarity and completeness

BMAD agents may not:

- choose execution provider
- change allowed write roots
- write outside candidate roots
- modify forbidden paths
- replace EvalRunner
- decide gate outcomes
- promote artifacts
- mutate Git state

## QA Role

BMAD QA is advisory only. It can provide:

- root-cause hypotheses
- files to inspect
- missing tests
- contract gaps
- risk notes
- recommended repair strategy
- next commands such as `/kit REQ-001 --repair --methodology bmad --agent developer`
- checks to rerun

BMAD QA cannot decide pass/fail or promotable status.

