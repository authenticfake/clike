# CLike Orchestrator

FastAPI service that owns the Harper domain: phase semantics and contracts, execution policy
(cloud vs local agent), local-agent execution packages, eval runner and gate, RAG API and the
read-only MCP server. It delegates model calls to the [gateway](../gateway).

## Layout

| Path | Content |
|---|---|
| `app.py` | Application, authentication middleware, MCP mount |
| `routes/` | `harper.py` (`/v1/harper/*`), `v1.py` (chat, generate, models), `routes_eval.py` (eval/gate), `rag.py`, `agent.py`, `git.py`, `router.py`, `health.py` |
| `services/harper.py` | Phase pipeline (`run_phase`), contracts, KIT stages |
| `services/local_agent_package.py` | Execution packages for local agents |
| `services/methodologies/` | Methodology profiles (BMAD resolver, quality contracts) |
| `eval_runner.py` | Deterministic execution of LTC profiles |
| `mcp_server.py` | Read-only MCP tools |
| `utils/service_auth.py`, `utils/safe_paths.py` | Service authentication and path confinement |
| `tests/` | Unit, contract, security and golden-snapshot tests |

## Run

```bash
uv sync --frozen
CLIKE_API_TOKEN=… DEV_FOLDER=/path/to/projects GATEWAY_URL=http://127.0.0.1:8000 \
  uv run uvicorn app:app --host 127.0.0.1 --port 8080 --reload
uv run pytest -q
```

In containers see [../docs/setup-and-runtime.md](../docs/setup-and-runtime.md).

## Security-relevant configuration

| Variable | Purpose |
|---|---|
| `CLIKE_API_TOKEN` | Required. Bearer token for every endpoint except `/health`; also sent on calls to the gateway |
| `CLIKE_ALLOWED_HOSTS` | Accepted `Host` names (default `localhost,127.0.0.1,::1,gateway,orchestrator`) |
| `DEV_FOLDER`, `CLIKE_EVAL_ALLOWED_ROOTS` | Roots under which eval/gate may operate |
| `CLIKE_ALLOW_INLINE_LTC` | `1` to accept inline-only LTC profiles (default: workspace file is authoritative) |
| `CLIKE_MCP_SERVER_ENABLED` | Mount the MCP server at `/mcp` (token-protected) |

## API

See [../docs/api-reference.md](../docs/api-reference.md) and [../docs/mcp.md](../docs/mcp.md).
