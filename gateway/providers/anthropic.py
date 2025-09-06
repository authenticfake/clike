import httpx

ANTHROPIC_VERSION = "2023-06-01" #too old...

def _merge_messages(messages: list) -> str:
    parts = []
    for m in messages:
        role = m.get("role", "user")
        content = m.get("content", "")
        if isinstance(content, list):
            content = "".join([c.get("text", "") if isinstance(c, dict) else str(c) for c in content])
        parts.append(f"{role.upper()}: {content}")
    return "\n\n".join(parts)

async def chat(base_url: str, api_key: str, model: str, messages: list, temperature: float, max_tokens: int) -> str:
    headers = {
        "Content-Type": "application/json",
        "x-api-key": api_key,
        "anthropic-version": ANTHROPIC_VERSION,
    }
    user_prompt = _merge_messages(messages)
    payload = {
        "model": model,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "messages": [{"role": "user", "content": user_prompt}],
    }
    async with httpx.AsyncClient(timeout=120) as client:
        r = await client.post(f"{base_url.rstrip('/')}/messages", headers=headers, json=payload)
        r.raise_for_status()
        data = r.json()
        content = ""
        for block in data.get("content", []):
            if block.get("type") == "text":
                content += block.get("text", "")
        return content
