import pytest

pydantic = pytest.importorskip("pydantic")
pytest.importorskip("pydantic_settings")

ValidationError = pydantic.ValidationError
from config import Settings


def test_settings_ignore_unrelated_environment_variables(monkeypatch):
    monkeypatch.setenv("RAG_BASE_URL", "http://localhost:8080/v1/rag")
    monkeypatch.setenv("RAG_TOP_K", "8")
    monkeypatch.setenv("OPENAI_API_KEY", "dummy-openai-key")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "dummy-anthropic-key")
    monkeypatch.setenv("GATEWAY_DUMP_DIR", "/tmp/clike-gateway-dump")
    monkeypatch.setenv("CLIKE_MCP_SERVER_ENABLED", "false")

    settings = Settings()

    assert str(settings.GATEWAY_URL).startswith("http://localhost:8000")
    assert settings.REQUEST_TIMEOUT_S == 240


def test_settings_still_load_declared_environment_variables(monkeypatch):
    monkeypatch.setenv("GATEWAY_URL", "http://orchestrator-test-gateway:9000")
    monkeypatch.setenv("REQUEST_TIMEOUT_S", "17")

    settings = Settings()

    assert str(settings.GATEWAY_URL).startswith("http://orchestrator-test-gateway:9000")
    assert settings.REQUEST_TIMEOUT_S == 17


def test_settings_still_reject_invalid_declared_values():
    with pytest.raises(ValidationError):
        Settings(REQUEST_TIMEOUT_S="not-an-int")
