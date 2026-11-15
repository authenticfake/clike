# Design system: Fluent 2 (Microsoft)

Fluent UI React v9 — the Microsoft 365 look: enterprise consoles, productivity tools, Teams/Office-like apps.

## Setup
- React / Next.js: `@fluentui/react-components` (v9 — never the v8 `@fluentui/react` package, the two APIs
  differ). Wrap the app in `FluentProvider` with a theme; with Next.js server rendering follow the Fluent SSR
  setup (renderer provider) so styles are emitted on the server.
- Non-React stacks: `@fluentui/web-components` with the same design tokens.
- Pin the versions in the lockfile.

## Theme and tokens
- `webLightTheme` / `webDarkTheme`; a brand is a `BrandVariants` ramp passed to `createLightTheme` /
  `createDarkTheme`. Styles use `makeStyles` with `tokens` (`tokens.colorNeutralBackground1`,
  `tokens.colorBrandBackground`, `tokens.spacingHorizontalM`, `tokens.borderRadiusMedium`, …) — never literal values.
- Status: `colorPaletteGreen*`, `colorPaletteYellow*`, `colorPaletteRed*` tokens with an icon and a label.

## App shell
- `NavDrawer` (navigation with sections) + a top bar with the page title and actions; the user menu with
  `Avatar` + `Menu`. One shell for every authenticated page; sign-in outside it (a centred `Card`).

## Components by need
| Need | Component |
|---|---|
| KPI / summary | `Card` + `CardHeader` |
| List of records | `DataGrid` (sorting, selection) or `Table` |
| Status, tier, tag | `Badge` / `Tag` with icon |
| Progress, budget | `ProgressBar` inside a `Field` with label and value |
| Filters | `SearchBox`, `Dropdown`, `Combobox`, `ToggleButton` |
| Forms | `Field` (label, hint, validation message) + `Input`, `Textarea`, `Select` |
| Confirmation | `Dialog`; notices: `Toaster` + `Toast` |
| Loading / empty | `Skeleton`, `Spinner`; empty state with text and next action |
| Tabs, hints | `TabList`, `Tooltip` |

## Rules
- Fluent components only, styled with `makeStyles` + `tokens`; icons from `@fluentui/react-icons`.
- Respect Fluent density and spacing; no second CSS framework.

## Verify
- Component tests with the provider; a browser test of the main journey; axe reports no serious violation.
