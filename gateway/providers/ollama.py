# app/providers/ollama.py
import httpx
from typing import List, Dict, Any, Optional
import logging

log = logging.getLogger("gateway.chat.ollama")

def _flatten_messages(messages: List[Dict[str, str]]) -> str:
    """
    Converte i messaggi OpenAI-like in un unico prompt “chatml-like”.
    Mantiene la tua funzionalità esistente.
    """
    out: List[str] = []
    for m in messages:
        role = m.get("role", "")
        content = m.get("content", "")
        if role == "system":
            out.append(f"<|system|>\n{content}\n")
        elif role == "user":
            out.append(f"<|user|>\n{content}\n")
        elif role == "assistant":
            out.append(f"<|assistant|>\n{content}\n")
        else:
            out.append(content)
    out.append("<|assistant|>\n")
    return "\n".join(out)

# alias backward compatibility se nel tuo codice si chiamava così
_flatter_message = _flatten_messages

async def _post_json(url: str, json: Dict[str, Any], timeout: float = 240.0) -> Dict[str, Any]:
    async with httpx.AsyncClient(timeout=timeout) as client:
        r = await client.post(url, json=json)
        r.raise_for_status()
        return r.json()

async def chat(base_url: str, remote_model: str, messages: List[Dict[str, str]],
               temperature: float = 0.2, max_tokens: Optional[int] = None,  timeout: Optional[float] = 240.0) -> str:
    """
    Chat con Ollama:
    - prova prima /api/chat (stream=false)
    - se fallisce, prova /api/generate come fallback
    """
    # normalizza base_url senza /v1
    base = base_url.rstrip("/")
    # 1) preferisci /api/chat
    chat_url = f"{base}/api/chat"
    gen_url = f"{base}/api/generate"

    prompt = _flatten_messages(messages)

    # tentativo 1: /api/chat
    try:
        log.info("[chat] ollama /api/chat model=%s base=%s", remote_model, base)
        data = await _post_json(
            chat_url,
            {
                "model": remote_model,
                "messages": messages,     # alcuni server supportano direttamente messages
                "stream": False,
                "options": {
                    "temperature": temperature
                }
            },     
            timeout
        )
        # formati possibili:
        # - {"message":{"role":"assistant","content":"..."}, ...}
        # - oppure {"response":"..."}
        msg = (data.get("message") or {}).get("content")
        if not msg:
            msg = data.get("response")
        if not msg:
            raise RuntimeError("ollama /api/chat: empty response")
        return msg
    except httpx.HTTPStatusError as e:
        # fallback a /api/generate
        log.error("ollama /api/chat error: %s", e)
    except Exception as e:
        log.error("ollama /api/chat unexpected: %s", e)

    # tentativo 2: /api/generate con prompt “flattened”
    log.info("[chat] ollama /api/generate (fallback) model=%s base=%s", remote_model, base)
    data = await _post_json(
        gen_url,
        {
            "model": remote_model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": temperature
            }
        }
    )
    msg = data.get("response")
    if not msg:
        raise RuntimeError("ollama /api/generate: empty response")
    return msg
