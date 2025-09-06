def format_chat_response(model_name: str, content: str):
    return {
        "id": "chatcmpl-1",
        "object": "chat.completion",
        "choices": [
            {"index": 0, "message": {"role": "assistant", "content": content}}
        ],
        "model": model_name,
    }

def format_embeddings_response(model_name: str, vector):
    return {
        "object": "list",
        "data": [{"object": "embedding", "embedding": vector, "index": 0}],
        "model": model_name,
    }
