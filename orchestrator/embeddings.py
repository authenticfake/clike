from typing import List, Optional
import httpx

from config import settings

OLLAMA_URL = getattr(settings, "OLLAMA_URL", "http://ollama:11434")
REQUEST_TIMEOUT_S = float(getattr(settings, "REQUEST_TIMEOUT_S", 60))
DEFAULT_EMBED_MODEL = getattr(settings, "EMBED_MODEL", "nomic-embed-text")

async def embed_text(text: str, model: Optional[str] = None) -> List[float]:
    """
    Calcola l'embedding di una singola stringa (compatibile con Ollama /api/embeddings).
    """
    m = model or DEFAULT_EMBED_MODEL
    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT_S) as client:
        r = await client.post(f"{OLLAMA_URL}/api/embeddings", json={"model": m, "prompt": text})
        r.raise_for_status()
        data = r.json()
        vec = data.get("embedding") or (data.get("data", [{}])[0].get("embedding"))
        if not isinstance(vec, list):
            raise RuntimeError(f"invalid embedding response for model={m}")
        return vec

async def embed_texts(texts: List[str], model: Optional[str] = None) -> List[List[float]]:
    """
    Calcola gli embedding per una lista di testi (loop singoli per massima compatibilità).
    """
    if not texts:
        return []
    out: List[List[float]] = []
    for t in texts:
        out.append(await embed_text(t, model=model))
    return out


