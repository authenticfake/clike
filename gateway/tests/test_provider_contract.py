"""Provider contract suite (WP7): exact HTTP requests and the unified result, old and new models.

Every request goes through providers.http, where an httpx.MockTransport replaces the network,
so these tests see what OpenAI / Anthropic would actually receive, and check the result shape
the orchestrator and the extension rely on.
"""

import asyncio
import json
import os
import unittest
from pathlib import Path
from unittest.mock import patch

import httpx
from starlette.testclient import TestClient

from providers import anthropic as anth
from providers import http as phttp
from providers import openai_compat as oai

REPO_ROOT = Path(__file__).resolve().parents[2]
UNIFIED_KEYS = {"ok", "text", "files", "usage", "finish_reason", "raw", "errors"}
LONG_SYSTEM = "You are the Harper SPEC writer. " * 300  # > cache threshold
FILE_BLOCK = "BEGIN_FILE docs/harper/SPEC.md\n# SPEC\nhello\nEND_FILE\n"

OPENAI_RESPONSES_OK = {"output": [{"type": "message", "content": [{"type": "output_text", "text": FILE_BLOCK}]}],
                       "usage": {"input_tokens": 10, "output_tokens": 5}, "status": "completed"}
OPENAI_CHAT_OK = {"choices": [{"message": {"role": "assistant", "content": FILE_BLOCK}, "finish_reason": "stop"}],
                  "usage": {"prompt_tokens": 10, "completion_tokens": 5}}
ANTHROPIC_OK = {"content": [{"type": "text", "text": FILE_BLOCK}], "stop_reason": "end_turn",
                "usage": {"input_tokens": 10, "output_tokens": 5}}


class Recorder:
    """MockTransport handler: records requests, replies from a queue (last reply repeats)."""

    def __init__(self, *replies):
        self.replies = list(replies)
        self.requests = []

    def __call__(self, request: httpx.Request):
        self.requests.append(request)
        reply = self.replies.pop(0) if len(self.replies) > 1 else self.replies[0]
        if isinstance(reply, Exception):
            raise reply
        status, body, headers = reply if len(reply) == 3 else (*reply, {})
        return httpx.Response(status, json=body, headers=headers)

    def body(self, index=-1):
        return json.loads(self.requests[index].content)


def run(coro):
    return asyncio.run(coro)


class ProviderContractBase(unittest.TestCase):
    def use(self, recorder):
        patcher = patch.object(phttp, "TRANSPORT", httpx.MockTransport(recorder))
        patcher.start()
        self.addCleanup(patcher.stop)
        backoff = patch.object(phttp, "BACKOFF_BASE_S", 0)
        backoff.start()
        self.addCleanup(backoff.stop)
        return recorder

    def assert_unified(self, result, ok=True):
        self.assertTrue(UNIFIED_KEYS <= set(result), result.keys())
        self.assertIs(result["ok"], ok, result.get("errors"))

    def assert_spec_delivered(self, result):
        """The generated SPEC reaches the caller: as text (OpenAI) or extracted into files (Anthropic)."""
        paths = [f.get("path") for f in result.get("files") or []]
        self.assertTrue("BEGIN_FILE docs/harper/SPEC.md" in result["text"] or "docs/harper/SPEC.md" in paths, result)


class OpenAIContractTests(ProviderContractBase):
    def messages(self):
        return [{"role": "system", "content": "sys"}, {"role": "user", "content": "first"},
                {"role": "assistant", "content": "answer"}, {"role": "user", "content": "second"}]

    def test_responses_models_keep_roles_and_effort(self):
        for model in ["gpt-5", "gpt-5-mini", "gpt-5.4-mini", "gpt-5.5", "gpt-5.1-codex-mini", "gpt-6.1-sol", "gpt-6-luna"]:
            with self.subTest(model):
                rec = self.use(Recorder((200, OPENAI_RESPONSES_OK)))
                out = run(oai.chat("https://api.openai.com/v1", "sk-x", model, self.messages(), max_tokens=1234))
                self.assert_unified(out)
                self.assertIn("BEGIN_FILE docs/harper/SPEC.md", out["text"])
                req = rec.requests[-1]
                self.assertEqual(str(req.url), "https://api.openai.com/v1/responses")
                self.assertEqual(req.headers["authorization"], "Bearer sk-x")
                body = rec.body()
                self.assertEqual(body["instructions"], "sys")
                self.assertEqual(body["input"], [{"role": "user", "content": "first"},
                                                 {"role": "assistant", "content": "answer"},
                                                 {"role": "user", "content": "second"}])
                self.assertEqual(body["max_output_tokens"], 1234)
                self.assertEqual(body["reasoning"], {"effort": "medium"})

    def test_new_generations_never_receive_sampling_parameters(self):
        # gpt-6.x is recognized by generation number, not by a hand-maintained list
        self.assertTrue(oai._is_reasoning_model_name("gpt-6.1-sol"))
        self.assertTrue(oai._is_reasoning_model_name("gpt-7"))
        self.assertFalse(oai._is_reasoning_model_name("gpt-4o"))
        payload = oai._normalize_and_validate("responses", {"model": "gpt-6.1-sol", "input": [], "temperature": 0.2, "top_p": 0.9})
        self.assertNotIn("temperature", payload)
        self.assertNotIn("top_p", payload)

    def test_reasoning_effort_from_the_request(self):
        rec = self.use(Recorder((200, OPENAI_RESPONSES_OK)))
        run(oai.chat("https://api.openai.com/v1", "sk-x", "gpt-5.5", self.messages(), reasoning={"effort": "high"}))
        self.assertEqual(rec.body()["reasoning"], {"effort": "high"})

    def test_older_chat_models_use_chat_completions_unchanged(self):
        for model in ["gpt-4o", "gpt-4o-mini", "gpt-4.1"]:
            with self.subTest(model):
                rec = self.use(Recorder((200, OPENAI_CHAT_OK)))
                out = run(oai.chat("https://api.openai.com/v1", "sk-x", model, self.messages(), temperature=0.0, max_tokens=500))
                self.assert_unified(out)
                self.assertIn("BEGIN_FILE", out["text"])
                self.assertEqual(str(rec.requests[-1].url), "https://api.openai.com/v1/chat/completions")
                body = rec.body()
                self.assertEqual([m["role"] for m in body["messages"]], ["system", "user", "assistant", "user"])
                # pre-existing behaviour kept: the chat path does not forward sampling params
                self.assertNotIn("temperature", body)
                self.assertEqual(body["max_completion_tokens"], 500)

    def test_base_url_is_honoured(self):
        rec = self.use(Recorder((200, OPENAI_CHAT_OK)))
        run(oai.chat("http://ollama:11434/v1", "ollama", "llama4", self.messages()))
        self.assertEqual(str(rec.requests[-1].url), "http://ollama:11434/v1/chat/completions")

    def test_rate_limit_is_retried_then_succeeds(self):
        rec = self.use(Recorder((429, {"error": {"message": "slow down"}}), (200, OPENAI_CHAT_OK)))
        out = run(oai.chat("https://api.openai.com/v1", "sk-x", "gpt-4o", self.messages()))
        self.assert_unified(out)
        self.assertEqual(len(rec.requests), 2)

    def test_client_errors_are_not_retried_and_reported(self):
        rec = self.use(Recorder((400, {"error": {"message": "bad param", "code": "invalid", "param": "x"}})))
        out = run(oai.chat("https://api.openai.com/v1", "sk-x", "gpt-4o", self.messages()))
        self.assert_unified(out, ok=False)
        self.assertEqual(len(rec.requests), 1)
        self.assertEqual(out["raw"]["status_code"], 400)
        self.assertIn("bad param", out["errors"][0])

    def test_connection_errors_are_retried(self):
        rec = self.use(Recorder(httpx.ConnectError("down"), (200, OPENAI_CHAT_OK)))
        self.assert_unified(run(oai.chat("https://api.openai.com/v1", "sk-x", "gpt-4o", self.messages())))
        self.assertEqual(len(rec.requests), 2)

    def test_read_timeouts_are_not_retried(self):
        rec = self.use(Recorder(httpx.ReadTimeout("slow")))
        out = run(oai.chat("https://api.openai.com/v1", "sk-x", "gpt-4o", self.messages()))
        self.assert_unified(out, ok=False)
        self.assertEqual(len(rec.requests), 1)


class AnthropicContractTests(ProviderContractBase):
    OLD = ["claude-haiku-4-5-20251001", "claude-haiku-4-5", "claude-sonnet-4-6", "claude-opus-4-6", "claude-opus-4-5-20251101"]
    NEW = ["claude-opus-5-5", "claude-sonnet-5-5", "claude-opus-4-7", "claude-opus-4-8", "claude-sonnet-5"]

    def call(self, model, **kw):
        messages = [{"role": "system", "content": kw.pop("system", LONG_SYSTEM)}, {"role": "user", "content": "go"}]
        return run(anth.chat("https://api.anthropic.com/v1", "sk-ant-x", model, messages, **kw))

    def test_request_shape_and_headers(self):
        rec = self.use(Recorder((200, ANTHROPIC_OK)))
        out = self.call("claude-sonnet-4-6", max_tokens=48000)
        self.assert_unified(out)
        self.assert_spec_delivered(out)
        req = rec.requests[-1]
        self.assertEqual(str(req.url), "https://api.anthropic.com/v1/messages")
        self.assertEqual(req.headers["anthropic-version"], "2023-06-01")
        self.assertEqual(req.headers["x-api-key"], "sk-ant-x")
        body = rec.body()
        self.assertEqual(body["max_tokens"], 48000)
        self.assertEqual(body["messages"], [{"role": "user", "content": "go"}])

    def test_old_models_keep_sampling_and_forced_tools(self):
        tools = [{"type": "function", "function": {"name": "emit", "parameters": {"type": "object", "properties": {}}}}]
        for model in self.OLD:
            with self.subTest(model):
                rec = self.use(Recorder((200, ANTHROPIC_OK)))
                self.assert_unified(self.call(model, temperature=0.2, top_p=0.9, tools=tools, tool_choice="required"))
                body = rec.body()
                self.assertEqual((body.get("temperature"), body.get("top_p")), (0.2, 0.9))
                self.assertEqual(body["tool_choice"].get("type"), "any")
                self.assertEqual(body["model"], model)

    def test_new_models_omit_sampling(self):
        for model in self.NEW:
            with self.subTest(model):
                rec = self.use(Recorder((200, ANTHROPIC_OK)))
                self.assert_unified(self.call(model, temperature=0.2, top_p=0.9))
                body = rec.body()
                self.assertNotIn("temperature", body)
                self.assertNotIn("top_p", body)
                self.assertEqual(body["model"], model)

    def test_forced_tool_choice_becomes_auto_only_where_rejected(self):
        tools = [{"type": "function", "function": {"name": "emit", "parameters": {"type": "object", "properties": {}}}}]
        expected = {"claude-opus-5-5": "auto", "claude-sonnet-5-5": "auto", "claude-opus-4-8": "any", "claude-sonnet-4-6": "any"}
        for model, kind in expected.items():
            with self.subTest(model):
                rec = self.use(Recorder((200, ANTHROPIC_OK)))
                self.call(model, tools=tools, tool_choice="required")
                self.assertEqual(rec.body()["tool_choice"]["type"], kind)

    def test_long_system_prompt_is_cacheable_short_one_is_plain(self):
        rec = self.use(Recorder((200, ANTHROPIC_OK)))
        self.call("claude-haiku-4-5")
        self.assertEqual(rec.body()["system"], [{"type": "text", "text": LONG_SYSTEM.strip(), "cache_control": {"type": "ephemeral"}}])
        self.call("claude-haiku-4-5", system="short")
        self.assertEqual(rec.body()["system"], "short")

    def test_aliases_still_resolve_without_network(self):
        rec = self.use(Recorder((200, ANTHROPIC_OK)))
        self.call("sonnet-4.5")
        self.assertEqual(rec.body()["model"], "claude-sonnet-4-5-20250929")
        self.assertEqual(len(rec.requests), 1, "no model-listing call any more")

    def test_overloaded_is_retried_and_errors_carry_status(self):
        rec = self.use(Recorder((529, {"error": {"type": "overloaded_error", "message": "busy"}}), (200, ANTHROPIC_OK)))
        self.assert_unified(self.call("claude-sonnet-4-6"))
        self.assertEqual(len(rec.requests), 2)
        self.use(Recorder((400, {"error": {"type": "invalid_request_error", "message": "temperature not supported"}})))
        out = self.call("claude-sonnet-4-6")
        self.assert_unified(out, ok=False)
        self.assertEqual(out["raw"]["status_code"], 400)
        self.assertIn("temperature not supported", out["errors"][0])


class ChatRouteContractTests(ProviderContractBase):
    """/v1/chat/completions as the orchestrator calls it."""

    @classmethod
    def setUpClass(cls):
        cls._env = patch.dict(os.environ, {"CLIKE_API_TOKEN": "c" * 48, "MODELS_CONFIG": str(REPO_ROOT / "configs/models.yaml")})
        cls._env.start()
        from app import app
        from routes import chat

        cls.chat = chat
        cls.client = TestClient(app, base_url="http://127.0.0.1:8000", raise_server_exceptions=False)
        cls.auth = {"Authorization": "Bearer " + "c" * 48}

    @classmethod
    def tearDownClass(cls):
        cls._env.stop()

    def post(self, model, **extra):
        return self.client.post("/v1/chat/completions", headers=self.auth,
                                json={"model": model, "messages": [{"role": "user", "content": "hi"}], **extra})

    def test_success_keeps_the_unified_shape_and_temperature_zero(self):
        self.use(Recorder((200, OPENAI_CHAT_OK)))
        with patch.object(self.chat, "OPENAI_API_KEY", "sk-x"):
            r = self.post("gpt-4o", temperature=0)
        self.assertEqual(r.status_code, 200, r.text)
        self.assertTrue(UNIFIED_KEYS <= set(r.json()))
        rec = self.use(Recorder((200, ANTHROPIC_OK)))  # a provider that forwards temperature
        with patch.object(self.chat, "ANTHROPIC_API_KEY", "sk-ant-x"):
            self.assertEqual(self.post("anthropic:claude-haiku-4-5", temperature=0).status_code, 200)
        self.assertEqual(rec.body()["temperature"], 0, "temperature 0 must not become 0.4")

    def test_provider_failure_is_an_http_error_not_an_empty_200(self):
        self.use(Recorder((400, {"error": {"message": "model not found", "code": "model_not_found"}})))
        with patch.object(self.chat, "OPENAI_API_KEY", "sk-x"):
            r = self.post("gpt-4o")
        self.assertEqual(r.status_code, 502)
        self.assertIn("model not found", json.dumps(r.json()))
        self.use(Recorder((429, {"error": {"message": "rate"}})))
        with patch.object(self.chat, "OPENAI_API_KEY", "sk-x"), patch.object(phttp, "MAX_ATTEMPTS", 1):
            self.assertEqual(self.post("gpt-4o").status_code, 429)

    def test_anthropic_new_and_old_models_through_the_route(self):
        for model in ["anthropic:claude-haiku-4-5", "anthropic:claude-sonnet-5-5"]:
            with self.subTest(model):
                rec = self.use(Recorder((200, ANTHROPIC_OK)))
                with patch.object(self.chat, "ANTHROPIC_API_KEY", "sk-ant-x"):
                    r = self.post(model, temperature=0.3)
                self.assertEqual(r.status_code, 200, r.text)
                self.assert_spec_delivered(r.json())
                self.assertEqual("temperature" in rec.body(), model.endswith("haiku-4-5"))

    def test_missing_provider_key_is_503_provider_not_configured_never_401(self):
        # 401 is reserved for the service token: the extension would tell the user to fix it.
        for model, attr in [("gpt-4o", "OPENAI_API_KEY"), ("anthropic:claude-haiku-4-5", "ANTHROPIC_API_KEY")]:
            with self.subTest(model), patch.object(self.chat, attr, ""):
                r = self.post(model)
            self.assertEqual(r.status_code, 503, r.text)
            self.assertEqual(r.json()["detail"]["code"], "provider_not_configured")

    def test_ollama_goes_through_the_openai_compatible_api(self):
        rec = self.use(Recorder((200, OPENAI_CHAT_OK)))
        r = self.post("ollama:llama4")
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(str(rec.requests[-1].url), "http://ollama:11434/v1/chat/completions")


if __name__ == "__main__":
    unittest.main()
