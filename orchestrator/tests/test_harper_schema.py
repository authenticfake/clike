import unittest

try:
    from schemas.harper import HarperPhaseRequest
except ModuleNotFoundError as exc:
    HarperPhaseRequest = None
    IMPORT_ERROR = exc
else:
    IMPORT_ERROR = None


@unittest.skipIf(HarperPhaseRequest is None, f"schema dependencies unavailable: {IMPORT_ERROR}")
class HarperSchemaTests(unittest.TestCase):
    def test_kit_phases_and_repair_survive_schema_validation(self):
        request = HarperPhaseRequest(
            cmd="kit",
            phase="kit",
            kit={
                "targets": ["REQ-001"],
                "phases": ["kit", "integrity_eval"],
                "repair": True,
            },
        )

        self.assertEqual(request.kit.targets, ["REQ-001"])
        self.assertEqual(request.kit.phases, ["kit", "integrity_eval"])
        self.assertIs(request.kit.repair, True)


if __name__ == "__main__":
    unittest.main()
