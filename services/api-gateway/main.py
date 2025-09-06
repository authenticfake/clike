from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="Clike API Gateway (MVP)")

app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

@app.get("/health")
def health():
    return {"ok": True, "service": "gateway"}

@app.get("/v1/models")
def list_models():
    return {"data": [{"id": "deepseek"}, {"id": "ollama"}, {"id": "claude"}, {"id": "gpt"}]}
