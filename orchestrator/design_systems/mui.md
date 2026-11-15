# Design system: MUI (Material Design)

MUI Material — the Material Design look; very complete, widely known.

## Setup
- React: `@mui/material` with `@emotion/react` and `@emotion/styled`; icons `@mui/icons-material`; tables
  `@mui/x-data-grid` when lists need sorting, filtering and pagination. Next.js App Router: `@mui/material-nextjs`
  (`AppRouterCacheProvider`) in the root layout.
- Pin the versions in the lockfile.

## Theme and tokens
- One `createTheme` (palette primary/secondary/error/warning/info/success, typography, shape.borderRadius,
  spacing) in `ThemeProvider` with `CssBaseline`; components use `sx` with theme keys (`'primary.main'`,
  `theme.spacing(2)`) — never literal colours. CSS variables mode (`cssVariables: true`) for light/dark.
- Status: palette `success`, `warning`, `error`, `info` with an icon and a label.

## App shell
- Permanent `Drawer` with `List` navigation + `AppBar`/`Toolbar` with the page title and actions; user menu with
  `Avatar` + `Menu`. Sign-in outside the shell (centred `Card`).

## Components by need
| Need | Component |
|---|---|
| KPI / summary | `Card` + `CardContent` |
| List of records | `DataGrid` (MUI X) or `Table` + `TablePagination` |
| Status, tier, tag | `Chip` with icon |
| Progress, budget | `LinearProgress` (determinate) with label and value |
| Filters | `TextField`, `Select`, `Autocomplete`, `ToggleButtonGroup` |
| Forms | `TextField` with `helperText` / `error` |
| Confirmation | `Dialog`; notices: `Snackbar` + `Alert` |
| Loading / empty | `Skeleton`, `CircularProgress`; empty state with text and action |
| Tabs, hints | `Tabs`, `Tooltip` |

## Rules
- MUI components and the theme only; no second CSS framework.

## Verify
- Component tests; a browser test of the main journey; axe reports no serious violation.
