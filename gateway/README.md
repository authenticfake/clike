# Clike Gateway (FastAPI)

OpenAI-like endpoints backed by multiple providers (Ollama, vLLM/OpenAI-compatible).

## Endpoints
- `GET  /health`
- `GET  /v1/models`
- `POST /v1/chat/completions`
- `POST /v1/embeddings`

## Run
```bash
pip install -r requirements.txt
export MODELS_CONFIG=/workspace/configs/models.yaml
uvicorn gateway.app:app --host 0.0.0.0 --port 8000 --reload
# or compatibility entry:
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

## models.yaml (example)
See chat for a full example. Use container service names in Docker (e.g., http://ollama:11434).
