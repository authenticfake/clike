# UI design systems

A design profile (`.clike/design-profiles/`) says how a user interface must **behave**: states, accessibility,
list and detail, role-aware actions. A design system says how it **looks and is built**: the component library,
its theme tokens, the app shell, the component to use for each need. With a profile alone a KIT writes a few
lines of CSS — a UI that works and that nobody wants to show. CLike gives every solution with a user interface
a design system.

## Choosing it

In `docs/harper/TECH_CONSTRAINTS.yaml`:

```yaml
tech_constraints:
  ui:
    design_system: shadcn-ui      # the default
```

| Value | Design system | Fits |
|---|---|---|
| `shadcn-ui` (**default**) | shadcn/ui — Radix primitives + Tailwind CSS, components copied into the repository | product apps and consoles; modern, accessible, what code models build best |
| `fluent2` | Fluent 2 — Fluent UI React v9 | Microsoft 365-style enterprise and productivity tools |
| `carbon` | IBM Carbon | dense, data-heavy enterprise and operations consoles |
| `mui` | MUI (Material Design) | the Material look, very complete component set |
| `antd` | Ant Design | admin and back-office apps with many tables and forms |
| `none` | — | no design system guidance (the design profile still applies) |

Aliases are accepted (`shadcn`, `shadcn/ui`, `fluent`, `material`, `ant-design`, …). `/idea` writes `ui.design_system`
when the sources name one; when they name none it writes `shadcn-ui` as an assumption. Without the key CLike uses
`shadcn-ui`. Change it in `TECH_CONSTRAINTS.yaml` before the first REQ with a UI is built: the first UI REQ sets the
design system up (packages, tokens, app shell) and the later ones extend it.

### Your own design system

Put its guide in `.clike/design-systems/<id>.md` and name it: `design_system: <id>`. A file with the id of a
bundled design system overrides CLike's guide (for example your brand's shadcn theme). The bundled guides are in
`orchestrator/design_systems/` and share one structure: when to use it, setup, theme and tokens, app shell,
components by need, rules, verification. A named design system without any guide is still applied: the KIT
follows its official documentation.

## What each phase receives

The same text for the cloud prompt and for the local agents (Codex, Claude Code), from the quality context:

- **`/plan` and `/idea --extend`:** a short rule — the solution's UI is built with the design system; the first
  UI REQ sets it up and owns it as a seam (packages, theme tokens, app shell); every UI lane guide names it.
- **`/kit` of a REQ with a UI** (a UI lane, or a design profile): the whole guide of the design system, with the
  rules that apply to every one — build every screen with its components and tokens, extend the app shell, no
  literal colours or ad-hoc CSS frameworks, a missing value becomes a token.

## UI references

A visual reference of the solution — an HTML prototype, mockups, screenshots — goes in **`docs/harper/ux/`**:
`/spec`, `/plan` and every `/kit` read it as `ui_reference` (reproduce its layout, navigation, components, states,
wording and tokens). `docs/reference/` is background for `/idea`, `/spec` and `/plan` only: the KIT does not read
it. For a new release, the requirement goes in `docs/inputs/vN/` and the prototype in `docs/harper/ux/`; the
requirement names the prototype and the design system.
