"""Phase → system prompt mapping (WP7.7): every phase has its own prompt, failures are explicit."""

import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import HTTPException

from routes import harper

PROMPTS = Path(__file__).resolve().parents[1] / "prompts" / "harper"


def _compose(phase):
    return harper._compose_system_messages(phase, "# idea", {}, None, None, "run-1", None, None)


class PhasePromptTests(unittest.TestCase):
    def test_eval_and_gate_use_their_own_prompts(self):
        for phase in ("eval", "gate"):
            path = PROMPTS / f"{phase}_system.md"
            env = {"PROMPT_EVAL_SYSTEM_PATH": str(PROMPTS / "eval_system.md"),
                   "PROMPT_GATE_SYSTEM_PATH": str(PROMPTS / "gate_system.md")}
            with patch.multiple(harper, **{k: v for k, v in env.items()}):
                system = _compose(phase)[0]["content"]
            self.assertIn(path.read_text(encoding="utf-8").strip()[:200], system, phase)

    def test_unknown_phase_is_rejected(self):
        with self.assertRaises(HTTPException) as ctx:
            _compose("deploy")
        self.assertEqual(ctx.exception.status_code, 400)

    def test_missing_prompt_is_an_error_not_a_placeholder(self):
        with patch.object(harper, "PROMPT_SPEC_SYSTEM_PATH", "/nonexistent/spec_system.md"):
            with self.assertRaises(HTTPException) as ctx:
                _compose("spec")
        self.assertEqual(ctx.exception.status_code, 503)


if __name__ == "__main__":
    unittest.main()
