# CLike Orchestrator

FastAPI service that owns the Harper domain: phase semantics and contracts, execution policy
(cloud vs local agent), local-agent execution packages, eval runner and gate, RAG API and the
read-only MCP server. It delegates model calls to the [gateway](../gateway).

## Layout

| Path | Content |
|---|---|
| `app.py` | Application, authentication middleware, MCP mount |
| `routes/` | `harper.py` (`/v1/harper/*`), `v1.py` (chat, generate, models), `routes_eval.py` (eval/gate), `rag.py`, `agent.py`, `router.py`, `health.py` |
| `services/harper.py` | Phase pipeline (`run_phase`), contracts, KIT stages |
| `services/local_agent/` | Execution packages for local agents, one module per phase (`local_agent_package.py` is a compatibility facade) |
| `phases/` | Phase definitions as data: `phase.yaml`, `text.yaml`, cloud prompts |
| `services/cloud_prompt/`, `services/phase_context.py` | Cloud phase messages composed for the gateway; typed `PhaseContext` |
| `services/context_sources.py`, `services/extend_cascade.py` | Project context sources and release folders; `/idea --extend` cascade rules |
| `services/kit_repair.py`, `services/gate_integrity.py`, `services/finalize_verify.py` | Auto-eval repair, acceptance lock and amendments, `/finalize` verification |
| `services/methodologies/` | Methodology profiles (BMAD resolver, quality contracts) |
| `eval_runner.py` | Deterministic execution of LTC profiles, regression of promoted REQs |
| `eval_environment.py` | Eval environment provisioning (variables, test databases, services) |
| `eval_sandbox_app.py`, `eval_tools_app.py`, `eval_tools_catalog.yaml` | Eval sandbox and eval tools services (own containers, same image) |
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
| `CLIKE_EVAL_SANDBOX_URL`, `CLIKE_EVAL_TOOLS_URL` | Eval sandbox and eval tools services (unset: in-process eval, no tool installs) |

## API

See [../docs/api-reference.md](../docs/api-reference.md) and [../docs/mcp.md](../docs/mcp.md).
