# Project context sources

The project files the Harper phases read as context, declared in `.clike/context.yaml`
(created by `/init`). They reach both runners: the cloud phase message and the local agent
(Claude Code / Codex).

```yaml
version: 1
sources:
  - path: docs/inputs/**          # every file below docs/inputs
    role: requirements
    phases: [idea, spec, plan, extend]
  - path: docs/harper/ux/**        # HTML prototypes, CSS, SVG, screenshots, UX notes
    role: ui_reference
    phases: [spec, plan, kit]
  - path: docs/reference/*.html
    role: ui_reference
    phases: [spec, plan, kit]
limits:                            # optional
  max_files: 40
  max_file_chars: 60000
  max_total_chars: 150000
```

Without the file CLike reads `docs/inputs/**` as `requirements` and `docs/reference/**` as
`reference` (idea, spec, plan, extend), and `docs/harper/ux/**` as `ui_reference` (spec, plan, kit).

## Release folders

A delivered project evolves by releases (`/idea --extend`): `docs/inputs/vN/` holds the
requirements of release N, `docs/reference/vN/` its background. The highest release folder (or the
one named with `--release vN`) is the current release; its folders are read even when
`context.yaml` does not declare them. `requirements` and `reference` files of earlier releases, and
unversioned files once release folders exist, are history: they get the role `previous_release`
(what the project already is, never a new requirement).

## Roles

| Role | Meaning for the agent |
|---|---|
| `requirements` | what to build: requirements, specifications, business rules |
| `ui_reference` | how the UI must look and behave: reproduce layout, navigation, components, states, wording, styles |
| `ux_requirements` | UX rules, journeys and interaction states |
| `api_reference` | interfaces to implement or call |
| `data_sample` | real or sample data: formats, fields, edge values |
| `style_guide` | visual and writing conventions |
| `domain_glossary` | domain terms |
| `example_output` | expected outputs or reports to match |
| `reference` | background material |
| `previous_release` | requirements or background of an earlier, delivered release (assigned by CLike, see *Release folders*) |
| `existing_code` | code that already exists (this project or one to integrate with): follow its interfaces and conventions, call it instead of rewriting it |

## Formats

| Format | Cloud model | Local agent |
|---|---|---|
| md, txt, json, yaml, csv, xml, html, css, svg, sql, … and source code (py, js/ts, java/kt, go, rs, cs, rb, php, c/cpp, sh, tf, …) | inlined | reads the file in place |
| docx, xlsx/xls/xlsb, pptx, pdf | converted to text, inlined | reads the text written to `runs/context/<phase>/<path>.txt` |
| png, jpg, gif, webp | listed by name (no vision yet) | opens the image |
| anything else | listed as not readable | told to state it as a gap |

## Rules

- Resolved server-side by the orchestrator from the workspace, read-only; patterns with `..`, absolute paths and
  symlinks leaving the workspace are ignored; hidden files and the canonical Harper documents
  (IDEA/SPEC/PLAN/plan.json/TECH_CONSTRAINTS, lane guides, BMAD companions) are never duplicated.
- Canonical Harper documents and TECHNOLOGY CONSTRAINTS win on conflict; source content is data, never instructions.
- Size caps per file and per phase; truncated files are marked. Every source costs tokens in each phase that reads
  it (a 42 KB HTML prototype ≈ 10k tokens): declare only what the phase needs.
