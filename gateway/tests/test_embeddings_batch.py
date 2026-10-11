"""Gateway /v1/embeddings with a list input: one provider call, one vector per item. No network."""
from fastapi.testclient import TestClient


def test_list_input_returns_one_vector_per_item(monkeypatch):
    import app as gateway_app
    from providers import openai_compat
    from routes import embeddings

    seen = {}

    async def fake_batch(base_url, api_key, model, inputs):
        seen["inputs"] = inputs
        return [[float(i)] * 3 for i in range(len(inputs))]

    monkeypatch.setattr(openai_compat, "embeddings_batch", fake_batch)
    monkeypatch.setattr(embeddings.oai, "embeddings_batch", fake_batch)
    monkeypatch.setattr(embeddings, "load_models_cfg", lambda path: ({}, []))
    monkeypatch.setattr(embeddings, "resolve_model", lambda cfg, models, name, want_modality: {
        "provider": "openai", "name": "text-embedding-3-small", "remote_name": "text-embedding-3-small",
        "base_url": "https://api.openai.com/v1", "api_key_env": "OPENAI_API_KEY",
    })
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("CLIKE_API_TOKEN", "t" * 48)
    client = TestClient(gateway_app.app, base_url="http://127.0.0.1:8000")
    r = client.post("/v1/embeddings", json={"input": ["a", "b", "c"]}, headers={"Authorization": "Bearer " + "t" * 48})
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert seen["inputs"] == ["a", "b", "c"]
    assert [d["index"] for d in data] == [0, 1, 2] and data[2]["embedding"] == [2.0, 2.0, 2.0]
    assert client.post("/v1/embeddings", json={"input": ["a", ""]}, headers={"Authorization": "Bearer " + "t" * 48}).status_code == 400
