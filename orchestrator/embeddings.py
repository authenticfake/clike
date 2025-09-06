import os, httpx

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://ollama:11434")

async def embed_text(text: str, model: str = "nomic-embed-text") -> list[float]:
    payload = {"model": model, "prompt": text}
    async with httpx.AsyncClient(timeout=60) as client:
        # 1) prova la rotta ufficiale
        r = await client.post(f"{OLLAMA_URL}/api/embeddings", json=payload)
        if r.status_code == 200:
            return r.json().get("embedding", [])
        # 2) messaggio chiaro se la rotta non esiste
        if r.status_code == 404:
            raise RuntimeError(
                "Ollama embeddings endpoint (/api/embeddings) not found. "
                "Update the ollama image (docker compose pull ollama) and retry."
            )
        r.raise_for_status()
        return r.json().get("embedding", [])
