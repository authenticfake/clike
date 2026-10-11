
def format_embeddings_response(model_name: str, vector):
    return {
        "object": "list",
        "data": [{"object": "embedding", "embedding": vector, "index": 0}],
        "model": model_name,
    }


def format_embeddings_list_response(model_name: str, vectors):
    return {
        "object": "list",
        "data": [{"object": "embedding", "embedding": v, "index": i} for i, v in enumerate(vectors)],
        "model": model_name,
    }
