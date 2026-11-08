"""Cloud KIT sized on the model: the model's own output budget, a deeper reasoning effort, and a
timeout that follows them (no more 48k for every model, no default 4096 cap shrinking timeouts)."""

import os
from unittest.mock import patch

from providers.anthropic import _build_messages_payload
from routes.harper import _resolve_ctx_caps, kit_effort, kit_output_tokens


def test_kit_output_follows_the_declared_model_cap_within_the_ceiling():
    with patch.dict(os.environ, {"CLIKE_KIT_MAX_OUTPUT_TOKENS": ""}):
        assert kit_output_tokens({"max_output_tokens": 128000}) == 64000
        assert kit_output_tokens({}) == 48000                     # undeclared: as before
        assert kit_output_tokens({"max_output_tokens": 32000}) == 32000  # a smaller model is not overrun
    with patch.dict(os.environ, {"CLIKE_KIT_MAX_OUTPUT_TOKENS": "128000"}):
        assert kit_output_tokens({"max_output_tokens": 128000}) == 128000


def test_kit_effort_defaults_high_and_is_validated():
    with patch.dict(os.environ, {"CLIKE_KIT_EFFORT": ""}):
        assert kit_effort() == "high"
    with patch.dict(os.environ, {"CLIKE_KIT_EFFORT": "xhigh"}):
        assert kit_effort() == "xhigh"
    with patch.dict(os.environ, {"CLIKE_KIT_EFFORT": "turbo"}):
        assert kit_effort() == "high"


def test_an_undeclared_output_cap_no_longer_caps_at_4096():
    ctx, cap = _resolve_ctx_caps({"context_window": 1000000})
    assert ctx == 1000000 and cap >= 128000


def test_anthropic_effort_reaches_the_models_that_take_it():
    msgs = [{"role": "system", "content": "s"}, {"role": "user", "content": "u"}]
    gen = {"max_tokens": 64000, "temperature": 0.1, "output_config": {"effort": "high"}}
    opus = _build_messages_payload("claude-opus-5-5", msgs, dict(gen))
    assert opus["output_config"] == {"effort": "high"} and "temperature" not in opus and opus["max_tokens"] == 64000
    sonnet46 = _build_messages_payload("claude-sonnet-4-6", msgs, dict(gen))
    assert sonnet46["output_config"] == {"effort": "high"}
    haiku45 = _build_messages_payload("claude-haiku-4-5", msgs, dict(gen))
    assert "output_config" not in haiku45  # rejects effort
