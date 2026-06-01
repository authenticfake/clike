from pathlib import Path
import re
import unittest


SOURCE = Path(__file__).resolve().parents[1].joinpath("routes", "routes_eval.py").read_text(
    encoding="utf-8"
)


def _function_source(name):
    pattern = rf"def {name}\(.*?(?=\n\n@|\n\ndef |\Z)"
    match = re.search(pattern, SOURCE, flags=re.S)
    if not match:
        raise AssertionError(f"Function {name} not found")
    return match.group(0)


class EvalCanonicalBmadTests(unittest.TestCase):
    def test_eval_run_uses_eval_runner_run_profile_as_canonical_path(self):
        source = _function_source("eval_run")

        self.assertIn("runner = EvalRunner(prj)", source)
        self.assertIn("rep = runner.run_profile(", source)
        self.assertIn("return _eval_payload(rep, args.req_id)", source)

    def test_gate_check_uses_eval_runner_and_not_methodology_context(self):
        source = _function_source("gate_check")

        self.assertIn("runner = EvalRunner(prj)", source)
        self.assertIn("rep = runner.run_profile(", source)
        self.assertNotIn("methodology", source.lower())
        self.assertNotIn("bmad", source.lower())

    def test_gate_check_request_remains_methodology_free(self):
        match = re.search(r"class GateCheckRequest\(BaseModel\):.*?(?=\n\nclass |\n\n_|\Z)", SOURCE, flags=re.S)
        self.assertIsNotNone(match)
        source = match.group(0)

        self.assertIn("profile: Optional[str]", source)
        self.assertIn("req_id: Optional[str]", source)
        self.assertNotIn("methodology", source.lower())
        self.assertNotIn("agent", source.lower())
        self.assertNotIn("methodology_context", source.lower())

    def test_eval_payload_promotable_is_derived_from_eval_report_only(self):
        source = _function_source("_eval_payload")

        self.assertIn('quality_passed = rep.status == "PASS"', source)
        self.assertIn("promotable = quality_passed", source)
        self.assertNotIn("methodology", source.lower())
        self.assertNotIn("bmad", source.lower())


if __name__ == "__main__":
    unittest.main()
