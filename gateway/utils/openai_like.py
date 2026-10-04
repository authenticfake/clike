
def format_embeddings_response(model_name: str, vector):
    return {
        "object": "list",
        "data": [{"object": "embedding", "embedding": vector, "index": 0}],
        "model": model_name,
    }
