import httpx

async def chat(base_url: str, api_key: str | None, model: str, messages: list, temperature: float, max_tokens: int) -> str:
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    payload = {"model": model, "messages": messages, "temperature": temperature, "max_tokens": max_tokens}
    async with httpx.AsyncClient(timeout=120) as client:
        r = await client.post(f"{base_url.rstrip('/')}/chat/completions", json=payload, headers=headers)
        r.raise_for_status()
        data = r.json()
        return (data.get("choices", [{}])[0].get("message", {}) or {}).get("content", "")

async def embeddings(base_url: str, api_key: str | None, model: str, input_text: str):
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    payload = {"model": model, "input": input_text}
    async with httpx.AsyncClient(timeout=120) as client:
        r = await client.post(f"{base_url.rstrip('/')}/embeddings", json=payload, headers=headers)
        r.raise_for_status()
        data = r.json()
        return (data.get("data") or [{}])[0].get("embedding")
