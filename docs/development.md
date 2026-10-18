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
cd docker && ./rebuild.sh            # or ./rebuild.sh gateway | orchestrator
```

The script prunes the dangling layers of earlier builds, builds with the layer cache (a source edit
reruns only `COPY . /app`; dependencies reinstall only when `uv.lock` changes, from a uv cache
mount that never lands in the image), recreates the containers (`podman-compose up -d` keeps the
old container when only the image changed), waits for `(healthy)` and checks that each container
runs the image just built. The orchestrator and the eval sandbox share one image
(`localhost/clike-orchestrator`), built once. Do not use `--no-cache`: the cache keys on file
contents, so it only slows the build and fills the VM disk (`podman system df`).

The eval sandbox runs generated tests and is capped by `CLIKE_EVAL_SANDBOX_MEM_LIMIT` (docker/.env,
default `4g`). Keep it below the memory of the container VM (`podman machine inspect`; the
default machine has 2 GB → `1g`), otherwise a runaway test can exhaust the VM and the kernel kills
another service (seen as the orchestrator exiting with 137).
**Eval environment.** CLike creates what the checks need from what the KIT declares in
`ci/LTC.json` (`orchestrator/eval_environment.py`):

| `provision` | What CLike does |
|---|---|
| `token`, `uuid`, `timestamp` (`offset_s`) | generates the value for this eval run |
| `template` (`value`: `"${OTHER}"`) | builds it from other variables (e.g. the same session for two processes) |
| `postgres_database` (`scheme`) | drops and creates `clike_<project>_<req>_<hash>` on the `CLIKE_EVAL_POSTGRES_URL` server, every run |
| `service` | URL exported by a `services[]` entry |
| `external` | nothing: the developer sets it in `docker/eval.env` |

`services: [{name, req, cwd, setup, start, env, port_env, ready: {http_path}, exports}]` start,
before the checks, from the composed source and dependencies (venv / npm) of another REQ (`req`,
e.g. the API of REQ-001 for the integration tests of REQ-002) or of the candidate, on a free
loopback port (`${PORT}`); setup commands (migrations) run first; they are stopped after the
checks, and their log is in the eval `logs/services/`. Each step is reported as an
`env::provision::<NAME>` / `env::service::<name>` case; a failure is blocking.

`setup: [{id, command, cwd, timeout}]` (or plain command strings) runs **before** the variables
and the services: what the services need installed or built first — the solution profile of
`/finalize` installs and builds every component there, since its services are the solution
itself. Each step is a blocking `setup::<id>` case; a failing one stops the eval before any
service starts. `pre` commands, instead, run after the services, just before the checks.

The developer configures once, in `docker/eval.env` (git-ignored; template
`docker/eval.env.example`, loaded only by the eval sandbox): `CLIKE_EVAL_POSTGRES_URL` (an admin
URL of a local PostgreSQL, e.g. `postgresql://me@host.containers.internal:5432/postgres`; from the
sandbox the Mac host is `host.containers.internal`) and the `external` values. A value already in
the environment wins over provisioning. Credential-like names (`TOKEN`, `PASSWORD`, `SECRET`, …)
make the sandbox refuse to start. After editing the file recreate the containers
(`./rebuild.sh` or `podman-compose up -d --force-recreate`).

When a required variable is neither set nor creatable, the eval is `BLOCKED`
(`EVAL_ENVIRONMENT_MISSING`) before any check runs. If a repair can fix it (the variable is not
declared as `external`), `/eval --fix` runs a KIT repair that completes the LTC `environment` /
`services` (an audited, non-weakening amendment of the lock); otherwise it stops without spending
tokens. KITs written before this contract (`environment: {NAME: "Required ..."}`) are understood
too, and a `*DATABASE_URL` described as PostgreSQL is provisioned as a test database.

An eval whose caller disconnects (VS Code closed, benchmark stopped, client timeout) is
cancelled: the orchestrator closes its request to the sandbox (HTTP 499), the sandbox kills the
running check with its process group and skips the remaining ones.

Eval work dirs (venvs, `node_modules`, the npm cache, Playwright browsers) live on the `eval_work`
disk volume (`CLIKE_EVAL_BASE_DIR=/var/clike-eval`), not on the 1 GB tmpfs `/tmp`. Browser e2e
checks (Playwright) download Chromium there at the first run: give the sandbox at least `3g` and
the VM at least 4 GB (`podman machine stop && podman machine set --memory 6144 && podman machine
start`). The image carries only the browser's system libraries (`ENABLE_BROWSER` build arg,
default on). Native tools a check needs beyond the image come from the eval tools catalog
(`/tools`, see [auto-eval.md](auto-eval.md#native-tools-of-the-sandbox-tools)).

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
Milestones are tagged (`v0.9.0` = M1, `v0.9.5` = M2, `v1.0.0` = M3, then `v1.1.0`, `v1.2.0`, `v1.2.1`, `v1.2.2`, `v1.2.3`, `v1.2.4`, `v1.3.0`, `v1.4.0` … `v1.4.4`, `v1.5.0`); semantic versioning from `1.0.0`. Changes are recorded in
[CHANGELOG.md](../CHANGELOG.md).
