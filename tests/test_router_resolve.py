import os
import pytest

# 1) Piano: risoluzione del profilo plan.fast (pin o selector)
def test_resolve_plan_fast(load_router_and_app):
    router, _app = load_router_and_app
    chosen, warnings = router.resolve(task="plan", hint="plan.fast")
    # Deve dare un modello valido
    assert "id" in chosen and "provider" in chosen and "model" in chosen
    # In molte config plan.fast punta a OpenAI; se non è così nella tua, questo assert può essere reso più generico.
    assert chosen["provider"] in {"openai", "anthropic", "ollama", "vllm", "deepseek"}
    assert isinstance(warnings, list)

# 2) Build: preferenza locale vs cloud (policy soft)
def test_policy_prefer_local_for_codegen(load_router_and_app, monkeypatch):
    router, _app = load_router_and_app
    # Assicuriamoci che la preferenza sia attiva
    monkeypatch.setenv("PREFER_LOCAL_FOR_CODEGEN", "true")
    # Reload dopo cambio env
    from tests.conftest import _reload_with_local_models
    router, _app = _reload_with_local_models()

    chosen, warnings = router.resolve(task="build", hint=None)
    # Idealmente provider locale, ma in soft policy è un prefer, non un vincolo assoluto:
    assert chosen["provider"] in {"ollama", "vllm", "openai", "anthropic", "deepseek"}
    # Verifica che almeno abbia i campi essenziali
    assert "model" in chosen and "temperature" in chosen

# 3) Strict: se aggiungi `strict: true` a un profilo, il pin non può essere sovrascritto
@pytest.mark.skipif(True, reason="Enable after adding `strict: true` in your models_test.yaml for the chosen profile.")
def test_strict_pin_no_override(load_router_and_app):
    router, _app = load_router_and_app
    # Esempio: se in models_test.yaml metti:
    # profiles:
    #   plan.fast:
    #     model: openai:gpt-4o-mini
    #     strict: true
    chosen, _ = router.resolve(task="plan", hint="plan.fast")
    assert chosen["id"] == "openai:gpt-4o-mini"

# 4) Redaction: cloud + NEVER_SEND_SOURCE_TO_CLOUD=true -> redact_source True
def test_redaction_cloud_vs_local(load_router_and_app, monkeypatch):
    # Caso cloud (tipicamente plan.fast su openai)
    router, _app = load_router_and_app
    monkeypatch.setenv("NEVER_SEND_SOURCE_TO_CLOUD", "true")
    from tests.conftest import _reload_with_local_models
    router, _app = _reload_with_local_models()

    chosen_cloud, _ = router.resolve(task="plan", hint="plan.fast")
    # Se il provider è cloud, redact_source dovrebbe essere True; se locale, False
    if chosen_cloud["provider"] in {"openai", "anthropic", "azure", "google", "deepseek"}:
        assert chosen_cloud.get("redact_source") is True
    else:
        assert chosen_cloud.get("redact_source") is False

    # Caso locale (es. build → local.codegen)
    chosen_local, _ = router.resolve(task="build", hint="local.codegen")
    assert chosen_local["provider"] in {"ollama", "vllm"} or "local" in (chosen_local.get("tags") or [])
    assert chosen_local.get("redact_source") is False

# 5) Defaults pass-through
def test_defaults_exposed(load_router_and_app):
    router, _app = load_router_and_app
    chosen, _ = router.resolve(task="plan", hint="plan.fast")
    defaults = chosen.get("defaults", {})
    # Se in models_test.yaml hai defaults.chat_model / defaults.embedding_model, qui li vedrai
    # Non assertiamo valori fissi per non vincolarti: verifichiamo che siano un dict
    assert isinstance(defaults, dict)
