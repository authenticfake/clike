# Developer Guide

## Repository layout

| Path | Content |
|---|---|
| `orchestrator/` | FastAPI orchestrator (Python 3.12, `pyproject.toml` + `uv.lock`) |
| `gateway/` | FastAPI model gateway (Python 3.12, `pyproject.toml` + `uv.lock`) |
| `extensions/vscode/` | VS Code extension (CommonJS, `package-lock.json`) |
| `configs/` | Model catalog and routing |
| `docker/` | Compose stack (Podman or Docker) |
| `tools/` | Repository tooling (hygiene check) |
| `docs/` | Documentation |

The two Python services are separate projects because they pin different FastAPI lines.

## Running locally

### With containers

```bash
cp .env.example .env               # provider keys + CLIKE_API_TOKEN
cp docker/.env.example docker/.env # CLIKE_PROJECTS_DIR
cd docker && podman-compose up -d --build
```

Code is baked into the images. After a change:

```bash
podman-compose build && podman-compose up -d --force-recreate
```

`podman-compose` does not recreate containers when only the image changed, hence `--force-recreate`.

The eval sandbox runs generated tests and is capped by `CLIKE_EVAL_SANDBOX_MEM_LIMIT` (docker/.env,
default `4g`). Keep it below the memory of the container VM (`podman machine inspect`; the
default machine has 2 GB → `1g`), otherwise a runaway test can exhaust the VM and the kernel kills
another service (seen as the orchestrator exiting with 137).
Browser e2e checks (Playwright) download Chromium into the sandbox's `/tmp` (tmpfs, counted in
the cap) at the first run: give the sandbox at least `3g` and the VM at least 4 GB
(`podman machine stop && podman machine set --memory 6144 && podman machine start`). The image
carries only the browser's system libraries (`ENABLE_BROWSER` build arg, default on).

### Without containers

```bash
# orchestrator
cd orchestrator && uv sync --frozen
CLIKE_API_TOKEN=… DEV_FOLDER=/path/to/projects uv run uvicorn app:app --host 127.0.0.1 --port 8080 --reload

# gateway
cd gateway && uv sync --frozen
CLIKE_API_TOKEN=… MODELS_CONFIG=$(pwd)/../configs/models.yaml uv run uvicorn main:app --host 127.0.0.1 --port 8000 --reload
```

Both services refuse protected requests (HTTP 503) when `CLIKE_API_TOKEN` is not set.

### Extension

```bash
cd extensions/vscode
npm ci
npm run check        # ESLint + node:test
code .               # F5 launches an Extension Development Host
./build_ext_vs.sh    # package (.vsix) and install; CLIKE_INSTALL_VSIX=0 to skip installing
```

## Tests

| Suite | Command |
|---|---|
| Orchestrator | `cd orchestrator && uv run pytest -q` |
| Gateway | `cd gateway && uv run pytest -q` |
| Extension | `cd extensions/vscode && npm test` |
| Repository hygiene | `python3 tools/check_repo_hygiene.py --all` and `python3 -m unittest discover -s tools/tests` |

Notable suites:

- **Golden snapshots** (`orchestrator/tests/golden`, `gateway/tests/golden`) freeze the phase
  boundary: payloads sent by the orchestrator to the gateway, local-agent execution packages, and
  the exact messages sent to providers. The gateway suite consumes the orchestrator snapshots, so the
  chain extension → orchestrator → gateway → provider is covered end to end. After an **intended**
  change, regenerate (orchestrator first, then gateway) and review the diff:
  ```bash
  cd orchestrator && CLIKE_GOLDEN_UPDATE=1 uv run pytest tests/golden -q
  cd ../gateway   && CLIKE_GOLDEN_UPDATE=1 uv run pytest tests/golden -q
  ```
- **Contract fixtures**: gateway tests never import orchestrator code; they use methodology
  contexts recorded in `gateway/tests/fixtures/methodology_contexts/`, kept in sync by
  `orchestrator/tests/test_gateway_methodology_context_fixtures.py` (`CLIKE_GOLDEN_UPDATE=1` to refresh).
- **Security suites**: `test_service_auth.py` and `test_confinement.py` in both services; in the
  extension `service-auth`, `mcp-request-guard`, `safe-workspace`, `chat-ui-webview` and `git-sync`
  (the latter runs against real temporary Git repositories).

## Static analysis

ESLint runs with a **frozen baseline** (`eslint-suppressions.json`): existing errors are recorded,
any new violation fails. When a change removes recorded debt, ESLint asks to prune the baseline:

```bash
npx eslint . --prune-suppressions
```

Commit the updated file. The baseline can only shrink.

## Repository hygiene

The repository is public. `tools/check_repo_hygiene.py` blocks telemetry, private notes
(`docs/_private/`), `.env` files, keys/certificates, virtualenvs, builds and key-shaped secrets.
Install it as a pre-commit hook in every clone:

```bash
printf '#!/bin/sh\nscript="$(git rev-parse --show-toplevel)/tools/check_repo_hygiene.py"\n[ -f "$script" ] || exit 0\nexec python3 "$script" --staged\n' > .git/hooks/pre-commit
chmod +x .git/hooks/pre-commit
```

CI runs the same check with `--all`.

## Continuous integration

`.github/workflows/ci.yml` runs on pushes to `main` and `hardening/**` and on pull requests:
repository hygiene, orchestrator and gateway tests (Python 3.12, `uv sync --frozen`), extension
lint/tests on Linux and Windows (Windows is informational), and `.vsix` packaging (artifact).

## Versioning

Extension and services share one version (`package.json`, both `pyproject.toml`).
Milestones are tagged (`v0.9.0` = M1, `v0.9.5` = M2, `v1.0.0` = M3, then `v1.1.0`); semantic versioning from `1.0.0`. Changes are recorded in
[CHANGELOG.md](../CHANGELOG.md).
