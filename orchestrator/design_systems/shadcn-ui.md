# Design system: shadcn/ui (CLike default)

Radix UI primitives styled with Tailwind CSS. The components are copied into the repository (you own their
code), themed by CSS variables. Accessible by construction (Radix), modern, dense enough for consoles.

## Setup
- React / Next.js / Vite: `npx shadcn@latest init` (writes `components.json`, the Tailwind setup, the theme
  variables in the global stylesheet and `lib/utils.ts` with `cn()`), then add only what the screens use:
  `npx shadcn@latest add sidebar card table badge button input textarea select tabs dialog sonner progress tooltip skeleton`.
- Vue: shadcn-vue; Svelte: shadcn-svelte (same components and variables). Server-rendered templates (Jinja,
  Thymeleaf, Razor): Tailwind with the same CSS variables and the same component anatomy.
- Pin the versions in the lockfile; the generated component files are committed like any source.

## Theme and tokens
- All colours are the CSS variables of the theme: `--background --foreground --card --primary
  --primary-foreground --secondary --muted --muted-foreground --accent --destructive --border --input --ring
  --radius`, plus `--chart-1…5` for data and `--sidebar-*` for the shell. A brand or a reference prototype maps
  its colours onto these variables in one place; components never use literal colours.
- Status (success, warning, error, info) gets its own variables (e.g. `--success`, `--warning`), always shown
  with an icon and a label, never colour alone.
- Dark mode, when required, is the `.dark` variable set — never a second stylesheet.

## App shell
- `SidebarProvider` + `Sidebar` (groups, items, collapsible) + `SidebarInset` for the content; a header with
  the page title, breadcrumbs and the page actions; the user menu (`DropdownMenu` + `Avatar`) in the sidebar
  footer. One shell for every authenticated page.
- Sign-in pages live outside the shell (centred `Card`, or a split layout with a brand panel).

## Components by need
| Need | Component |
|---|---|
| KPI / summary | `Card` with title, value, delta |
| List of records | `Table` (with TanStack Table for sorting, filters, pagination) |
| Status, tier, tag | `Badge` (variants) + icon |
| Progress, budget | `Progress` with a label and the value as text |
| Filters | `Input`, `Select`, `ToggleGroup`, `Popover` + `Command` for search |
| Detail beside a list | resizable layout or `Sheet` |
| Forms | `Form` (react-hook-form + zod) with `FormField`, `FormMessage` for errors |
| Confirmation | `AlertDialog`; notices: `Sonner` toasts |
| Loading / empty | `Skeleton`; an empty state with a short text and the next action |
| Hint | `Tooltip` |

## Rules
- Use the generated components; extend them with variants (`cva`), never fork the styling per screen.
- Spacing and type from the Tailwind scale; no inline styles, no second CSS framework.
- Keyboard and focus as Radix provides; every icon-only button has an accessible name.

## Verify
- Component tests render the screens with their states; a browser test walks the main journey; an
  accessibility check (axe) reports no serious violation.
