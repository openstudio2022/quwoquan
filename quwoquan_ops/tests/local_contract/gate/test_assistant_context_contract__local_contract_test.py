from __future__ import annotations

import copy
import importlib.util
import tempfile
import unittest
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[4]
VERIFIER = (
    ROOT
    / "quwoquan_service/scripts/assistant-service/assistant/assistant_run"
    / "verify_assistant_context_contract.py"
)
FIELDS = (
    ROOT
    / "quwoquan_service/services/assistant-service/contracts/assistant/assistant_run/fields.yaml"
)
OPERATIONS = (
    ROOT
    / "quwoquan_service/services/assistant-service/contracts/assistant/assistant_run/operations.yaml"
)


def _load_verifier():
    spec = importlib.util.spec_from_file_location("assistant_context_contract", VERIFIER)
    if spec is None or spec.loader is None:
        raise RuntimeError("无法加载助手上下文契约门禁")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class AssistantContextContractLocalContractTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.verifier = _load_verifier()
        cls.fields = yaml.safe_load(FIELDS.read_text(encoding="utf-8"))
        cls.operations = yaml.safe_load(OPERATIONS.read_text(encoding="utf-8"))

    def _verify(self, fields: dict) -> int:
        with tempfile.TemporaryDirectory() as temporary_directory:
            temporary_root = Path(temporary_directory)
            fields_path = temporary_root / "fields.yaml"
            operations_path = temporary_root / "operations.yaml"
            fields_path.write_text(
                yaml.safe_dump(fields, allow_unicode=True, sort_keys=False),
                encoding="utf-8",
            )
            operations_path.write_text(
                yaml.safe_dump(self.operations, allow_unicode=True, sort_keys=False),
                encoding="utf-8",
            )
            original_fields = self.verifier.FIELDS_PATH
            original_operations = self.verifier.OPERATIONS_PATH
            self.verifier.FIELDS_PATH = fields_path
            self.verifier.OPERATIONS_PATH = operations_path
            try:
                return self.verifier.main()
            finally:
                self.verifier.FIELDS_PATH = original_fields
                self.verifier.OPERATIONS_PATH = original_operations

    def test_tracked_contract_is_minimal_page_grounding_only(self) -> None:
        snapshot = self.fields["types"]["AssistantContextSnapshot"]
        snapshot_fields = {field["name"] for field in snapshot["fields"]}
        consent = self.fields["types"]["AssistantConsentMatrix"]
        consent_fields = {field["name"] for field in consent["fields"]}

        self.assertIn("intersectionEvidenceRefs", snapshot_fields)
        self.assertNotIn("conversationGrounding", snapshot_fields)
        self.assertEqual(consent_fields, {"canReadCurrentPage"})
        self.assertEqual(self._verify(copy.deepcopy(self.fields)), 0)

    def test_missing_current_page_consent_is_a_contract_failure(self) -> None:
        candidate = copy.deepcopy(self.fields)
        candidate["types"]["AssistantConsentMatrix"]["fields"] = []

        self.assertEqual(self._verify(candidate), 1)


if __name__ == "__main__":
    unittest.main()
