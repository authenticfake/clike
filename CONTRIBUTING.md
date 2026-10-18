# Contributing to CLike

Thanks for your interest in CLike. Bug reports, ideas, documentation fixes and code are all
welcome. This page explains how to take part; by participating you agree to the
[Code of Conduct](CODE_OF_CONDUCT.md).

## Ways to contribute

- **Questions and ideas** — open a [Discussion](https://github.com/authenticfake/clike/discussions).
- **Bugs** — open an [issue](https://github.com/authenticfake/clike/issues/new/choose) with the
  *Bug report* form: CLike version, executor (cloud model, Claude Code, Codex), the command, what
  happened and what you expected. Remove secrets, tokens and private project content from logs.
- **Feature requests** — the *Feature request* form; describe the problem before the solution.
- **Security problems** — never in public: see [SECURITY.md](SECURITY.md).
- **Pull requests** — for anything beyond a small fix, open an issue or a discussion first so the
  approach can be agreed before you invest time.

## Development setup

The [developer guide](docs/development.md) has the details. In short:

| Part | Setup | Tests |
|---|---|---|
| Orchestrator (Python 3.12, [uv](https://docs.astral.sh/uv/)) | `cd orchestrator && uv sync --frozen` | `uv run pytest -q` |
| Gateway (Python 3.12, uv) | `cd gateway && uv sync --frozen` | `uv run pytest -q` |
| VS Code extension (Node 22) | `cd extensions/vscode && npm ci` | `npm run check` |
| Repository hygiene | — | `python3 tools/check_repo_hygiene.py --all` |

To run the whole stack locally (Podman or Docker) see [docs/INSTALL.md](docs/INSTALL.md) and
[docs/setup-and-runtime.md](docs/setup-and-runtime.md).

Install the hygiene pre-commit hook in your clone (it blocks telemetry, `.env` files, keys,
private notes and chat sessions — the repository is public):

```bash
printf '#!/bin/sh\nscript="$(git rev-parse --show-toplevel)/tools/check_repo_hygiene.py"\n[ -f "$script" ] || exit 0\nexec python3 "$script" --staged\n' > .git/hooks/pre-commit
chmod +x .git/hooks/pre-commit
```

## Pull requests

1. Fork the repository and create a branch from `main` (`fix/…`, `feat/…`, `docs/…`).
2. Keep the change focused; one topic per pull request.
3. Add or update tests. After an **intended** change to a phase payload or prompt, regenerate the
   golden snapshots (orchestrator first, then gateway) and review the diff — see
   [docs/development.md](docs/development.md#tests).
4. Update the documentation and the in-product help with the behaviour you change, and add a line
   under `## [Unreleased]` in [CHANGELOG.md](CHANGELOG.md).
5. Open the pull request against `main` and fill in the template. CI (hygiene, orchestrator,
   gateway, extension on Linux and Windows) must be green; `main` accepts changes only through
   reviewed pull requests.

### Principles a change must respect

- **Executor parity** — cloud models, Claude Code and Codex must behave the same: same context,
  same contracts, same write rules. A fix for one executor is a fix for all of them.
- **Generic, not project-specific** — CLike is multi-language and stack-agnostic; no rules tied to
  one stack or one project.
- **Governance stays with CLike** — locked acceptance tests, regression of delivered REQs, gate
  and promotion rules are not weakened to make a case pass.
- **Nothing private in the repository** — no telemetry, secrets, `.env`, generated Harper
  documents of real projects or chat sessions.

## Commit messages

Use a short imperative summary with a conventional prefix when it fits (`fix(eval): …`,
`feat(mcp): …`, `docs: …`, `chore: …`), and explain the *why* in the body.

## License

CLike is licensed under the [Apache License 2.0](LICENSE). By submitting a contribution you agree
that it is licensed under the same terms (Apache 2.0, section 5), and that you have the right to
submit it.
