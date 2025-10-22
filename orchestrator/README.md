# Clike Orchestrator (Structured, Multilanguage)

## Structure
```
clike_orchestrator/
│── app.py
│── main.py
│── routes/
│   ├── agent.py
│   ├── rag.py
│   ├── git.py
│   └── health.py
│── services/
│   ├── utils.py
│   ├── rationale.py
│   ├── docstrings.py
│   └── tests.py
│── __init__.py
```

## Endpoints
- `POST /agent/code` — intents: `docstring`, `refactor`, `tests`, `fix_errors`, `new_file`
- `POST /v1/rag/reindex`
- `POST /v1/rag/search`
- `POST /git/branch`
- `POST /git/commit`
- `POST /git/pr`
- `GET  /health`

## Environment
- `GATEWAY_URL` (default `http://gateway:8000`)
- `QDRANT_HOST` (default `qdrant`), `QDRANT_PORT` (default `6333`)

## Run (dev)
```
uvicorn clike_orchestrator.app:app --host 0.0.0.0 --port 8080 --reload
```
or
```
python -m clike_orchestrator.main
```

## Notes
- The orchestrator returns both `diff` and `new_content` to match the VS Code extension expectations.
- Docstrings/JSDoc are inserted contextually by language; tests scaffolding is language-aware.
- RAG and Git endpoints are optional; they degrade gracefully when underlying tools are not available.
