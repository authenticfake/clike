"""One FILE_REQUIREMENTS for cloud and local agents (B15): same obligations whatever the runner."""

import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.local_agent.kit import _unified_file_requirements  # noqa: E402

SHARED = {
    "version": "1.0.0", "req_id": "REQ-001",
    "namespace_materialization": {"ecosystem": "python", "import_namespace": "pingboard.status"},
    "required_outputs": [
        {"role": "primary_implementation", "required": True, "path_hint": "runs/kit/REQ-001/src/pingboard/status/implementation.py"},
        {"role": "module_launcher", "required": True, "path_hint": "runs/kit/REQ-001/src/<execution-area-composition-root>"},
    ],
}
AGENT = {
    "schema_version": "clike.file_requirements.v2", "req_id": "REQ-001",
    "required_outputs": [{"role": "external_library_obligation", "required": True, "named_obligations": ["python"]}],
    "runtime_manifest_policy": {"required": True}, "solution_launcher_policy": {"policy": "one per area"},
}


class UnifiedFileRequirementsTests(unittest.TestCase):
    def test_obligations_come_from_the_orchestrator_document(self):
        doc = _unified_file_requirements({"core_blobs": {"FILE_REQUIREMENTS.json": json.dumps(SHARED)}}, AGENT)
        self.assertEqual(doc["required_outputs"], SHARED["required_outputs"])  # same as cloud prompt, contract and gate
        self.assertEqual(doc["namespace_materialization"], SHARED["namespace_materialization"])
        self.assertEqual(doc["runtime_manifest_policy"], {"required": True})  # agent guidance kept
        self.assertNotIn("schema_version", doc)

    def test_without_the_orchestrator_document_the_agent_document_is_used(self):
        self.assertIs(_unified_file_requirements({"core_blobs": {}}, AGENT), AGENT)


if __name__ == "__main__":
    unittest.main()
