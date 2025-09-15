from fastapi.testclient import TestClient

def test_routing_resolve_endpoint(load_router_and_app):
    _router, app = load_router_and_app
    client = TestClient(app)
    r = client.get("/routing/resolve", params={"task": "plan", "hint": "plan.fast"})
    assert r.status_code == 200
    data = r.json()
    assert data["task"] == "plan"
    assert data["hint"] == "plan.fast"
    assert "chosen" in data and "warnings" in data
    assert "id" in data["chosen"]

def test_models_and_defaults_endpoints(load_router_and_app):
    _router, app = load_router_and_app
    client = TestClient(app)

    r = client.get("/models")
    assert r.status_code == 200
    models = r.json()["models"]
    assert isinstance(models, list)
    assert len(models) > 0

    r = client.get("/models/defaults")
    assert r.status_code == 200
    defaults = r.json()["defaults"]
    assert isinstance(defaults, dict)
