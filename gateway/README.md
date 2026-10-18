# Clike Gateway (FastAPI)

OpenAI-like endpoints backed by multiple providers (OpenAI, Anthropic, Ollama and other
OpenAI-compatible endpoints), Harper model calls on the messages composed by the orchestrator, and
telemetry. Every endpoint except `/health` requires `Authorization: Bearer <CLIKE_API_TOKEN>`.

## Endpoints
- `GET  /health`
- `GET  /v1/models`, `GET /v1/models/validate`, `GET /v1/providers`
- `POST /v1/chat/completions`
- `POST /v1/embeddings`
- `POST /v1/harper/run`, `POST /v1/harper/telemetry`
- `/v1/metrics/*` (telemetry API and UI)

## Run
```bash
uv sync --frozen                      # Python 3.12, locked in uv.lock
export MODELS_CONFIG=$(pwd)/../configs/models.yaml CLIKE_API_TOKEN=…
uv run uvicorn main:app --host 127.0.0.1 --port 8000 --reload
uv run pytest -q                      # independent from orchestrator code
```

## models.yaml (example)
See chat for a full example. Use container service names in Docker (e.g., http://ollama:11434).
