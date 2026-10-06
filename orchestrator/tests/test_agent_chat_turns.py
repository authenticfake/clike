"""Native agent chat (H1): a resumed agent session gets only the context and the new user turn."""

import sys
import unittest
from pathlib import Path

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


if __name__ == "__main__":
    unittest.main()
