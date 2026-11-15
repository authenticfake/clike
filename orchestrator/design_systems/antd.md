# Design system: Ant Design

Ant Design (antd v5) — admin and back-office apps with many tables and forms.

## Setup
- React: `antd` and `@ant-design/icons`; Next.js App Router: `@ant-design/nextjs-registry` (`AntdRegistry`) in the
  root layout. Pin the versions in the lockfile.

## Theme and tokens
- `ConfigProvider` with `theme.token` (`colorPrimary`, `borderRadius`, `fontSize`, …) and per-component tokens;
  `theme.useToken()` in custom styles — never literal colours. Dark mode with `theme.darkAlgorithm`.
- Status: `colorSuccess`, `colorWarning`, `colorError`, `colorInfo` with an icon and a label.

## App shell
- `Layout` with `Sider` + `Menu` (grouped items), `Header` with the page title and actions, `Content`; user menu
  with `Avatar` + `Dropdown`. Sign-in outside the shell (centred `Card`).

## Components by need
| Need | Component |
|---|---|
| KPI / summary | `Card` + `Statistic` |
| List of records | `Table` (sorting, filters, pagination, row selection) |
| Status, tier, tag | `Tag` / `Badge` with icon |
| Progress, budget | `Progress` with format text |
| Filters | `Input.Search`, `Select`, `Segmented`, `DatePicker` |
| Forms | `Form` + `Form.Item` (rules, validation messages) |
| Confirmation | `Modal`, `Popconfirm`; notices: `message`, `notification` |
| Loading / empty | `Skeleton`, `Spin`, `Empty` with the next action |
| Tabs, hints | `Tabs`, `Tooltip` |

## Rules
- antd components and tokens only; no second CSS framework.

## Verify
- Component tests; a browser test of the main journey; axe reports no serious violation.
