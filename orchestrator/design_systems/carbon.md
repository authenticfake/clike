# Design system: Carbon (IBM)

IBM Carbon — dense, data-heavy enterprise consoles, operations and analytics.

## Setup
- React / Next.js: `@carbon/react` with its styles (`@carbon/styles`, Sass) imported once in the global
  stylesheet; icons from `@carbon/icons-react`. Non-React stacks: Carbon Web Components (`@carbon/web-components`).
- Pin the versions in the lockfile.

## Theme and tokens
- Themes `white`, `g10` (light) and `g90`, `g100` (dark) through the `Theme` component (zones are allowed: e.g. a
  g100 shell around a g10 content area). Colours, spacing and type through Carbon tokens (`$layer-01`,
  `$text-primary`, `$spacing-05`, `$support-error`, …) — never literal values.
- Status: `$support-success`, `$support-warning`, `$support-error`, `$support-info` with an icon and a label.

## App shell
- UI Shell: `Header` (name, global actions), `SideNav` (sections, links), `Content`; the user menu in a
  `HeaderPanel`. Sign-in outside the shell (centred `Tile` or a split layout).

## Components by need
| Need | Component |
|---|---|
| KPI / summary | `Tile` |
| List of records | `DataTable` (toolbar, search, sorting, batch actions, pagination) |
| Status, tier, tag | `Tag` with icon |
| Progress, budget | `ProgressBar` with label and helper text |
| Filters | `Search`, `Dropdown`, `MultiSelect`, `ContentSwitcher` |
| Forms | `Form`, `TextInput`, `TextArea`, `Select` with `invalidText` |
| Confirmation | `Modal`; notices: `InlineNotification`, `ToastNotification` |
| Loading / empty | `DataTableSkeleton`, `SkeletonText`, `Loading`; empty state with text and action |
| Tabs, hints | `Tabs`, `Tooltip`, `Toggletip` |

## Rules
- Carbon components and tokens only; the 2x grid (`Grid`, `Column`); no second CSS framework.

## Verify
- Component tests; a browser test of the main journey; axe reports no serious violation.
