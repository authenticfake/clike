"""Native agent chat (H1): a resumed agent session gets only the context and the new user turn."""

import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from routes.v1 import _agent_turn_messages  # noqa: E402

MSGS = [
    {"role": "system", "content": "instructions"},
    {"role": "user", "content": "first"},
    {"role": "assistant", "content": "answer"},
    {"role": "system", "content": "RAG context"},
    {"role": "user", "content": "second"},
]


class AgentTurnTests(unittest.TestCase):
    def test_new_session_gets_the_whole_conversation(self):
        self.assertEqual(_agent_turn_messages(MSGS, {}), MSGS)

    def test_resumed_session_gets_context_and_the_new_turn(self):
        self.assertEqual(
            [m["content"] for m in _agent_turn_messages(MSGS, {"agentSessionResume": True})],
            ["instructions", "RAG context", "second"],
        )


class LocalChatPackageTests(unittest.TestCase):
    """Free text with an agent: Q&A stays read-only, Harper may write under the generated root."""

    TOKEN = "f" * 48

    @classmethod
    def setUpClass(cls):
        cls._env = patch.dict(os.environ, {"CLIKE_API_TOKEN": cls.TOKEN})
        cls._env.start()
        from starlette.testclient import TestClient

        from app import app

        cls.client = TestClient(app, base_url="http://127.0.0.1:8080", raise_server_exceptions=False)

    @classmethod
    def tearDownClass(cls):
        cls._env.stop()

    def _chat(self, mode):
        body = {"mode": mode, "model": "auto", "project_id": "p", "executionPreference": "local_agent_only",
                "localAgentExecutor": "codex", "messages": [{"role": "user", "content": "create factorial.py"}]}
        r = self.client.post("/v1/chat", json=body, headers={"Authorization": f"Bearer {self.TOKEN}"})
        self.assertEqual(r.status_code, 200, r.text)
        return r.json()

    def test_free_is_read_only(self):
        pkg = self._chat("free")
        self.assertEqual(pkg["mode"], "free")
        self.assertNotIn("output_root", pkg)

    def test_harper_writes_only_under_the_generated_root(self):
        pkg = self._chat("harper")
        self.assertEqual(pkg["mode"], "harper")
        self.assertRegex(pkg["output_root"], r"^generated/[0-9a-f]{8}$")
        self.assertIn(f"under the directory '{pkg['output_root']}/'", pkg["prompt"])
        self.assertIn("create factorial.py", pkg["prompt"])


if __name__ == "__main__":
    unittest.main()
