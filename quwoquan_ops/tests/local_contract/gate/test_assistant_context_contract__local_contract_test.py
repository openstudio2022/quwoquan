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
SHARED_TYPES = (
    ROOT
    / "quwoquan_service/services/assistant-service/contracts/_shared/types.yaml"
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
        cls.shared_types = yaml.safe_load(SHARED_TYPES.read_text(encoding="utf-8"))

    def _verify(self, fields: dict, *, shared_types: dict | None = None) -> int:
        with tempfile.TemporaryDirectory() as temporary_directory:
            temporary_root = Path(temporary_directory)
            fields_path = temporary_root / "fields.yaml"
            shared_types_path = temporary_root / "shared-types.yaml"
            fields_path.write_text(
                yaml.safe_dump(fields, allow_unicode=True, sort_keys=False),
                encoding="utf-8",
            )
            shared_types_path.write_text(
                yaml.safe_dump(
                    shared_types or self.shared_types,
                    allow_unicode=True,
                    sort_keys=False,
                ),
                encoding="utf-8",
            )
            original_fields = self.verifier.FIELDS_PATH
            original_shared_types = self.verifier.SHARED_TYPES_PATH
            self.verifier.FIELDS_PATH = fields_path
            self.verifier.SHARED_TYPES_PATH = shared_types_path
            try:
                return self.verifier.main()
            finally:
                self.verifier.FIELDS_PATH = original_fields
                self.verifier.SHARED_TYPES_PATH = original_shared_types

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

    def test_missing_shared_citation_destination_is_a_contract_failure(self) -> None:
        shared_types = copy.deepcopy(self.shared_types)
        del shared_types["types"]["CitationDestination"]

        self.assertEqual(
            self._verify(copy.deepcopy(self.fields), shared_types=shared_types),
            1,
        )


if __name__ == "__main__":
    unittest.main()
