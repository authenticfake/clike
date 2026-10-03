# Clike Gateway (FastAPI)

OpenAI-like endpoints backed by multiple providers (Ollama, vLLM/OpenAI-compatible).

## Endpoints
- `GET  /health`
- `GET  /v1/models`
- `POST /v1/chat/completions`
- `POST /v1/embeddings`

## Run
```bash
uv sync --frozen                      # Python 3.12, locked in uv.lock
export MODELS_CONFIG=$(pwd)/../configs/models.yaml
uv run uvicorn main:app --host 127.0.0.1 --port 8000 --reload
uv run pytest -q                      # independent from orchestrator code
```

## models.yaml (example)
See chat for a full example. Use container service names in Docker (e.g., http://ollama:11434).
