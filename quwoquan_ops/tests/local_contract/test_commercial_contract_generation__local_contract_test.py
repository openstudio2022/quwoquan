# spec_ref: specs/feature-tree/runtime/system-architecture-and-engineering-guide/app-cloud-business-object-commercial-closure/spec.md#gwt-002
from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
MODULE_PATH = ROOT / "quwoquan_ops/gate/verify_commercial_contract_generation.py"
SPEC = importlib.util.spec_from_file_location(
    "verify_commercial_contract_generation",
    MODULE_PATH,
)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class CommercialContractGenerationLocalContractTest(unittest.TestCase):
    def test_domain_qualified_type_and_decoder_are_canonical_typed_wiring(self) -> None:
        source = """
Future<assistantContracts.AssistantEntryResponse>
assistantAssistantEntryViewGetAssistantEntry(
  assistantContracts.AssistantEntryQuery request,
) {
  return executor.send<assistantContracts.AssistantEntryResponse>(
    responseDecoder: assistantContracts.decodeAssistantEntryResponse,
  );
}
"""

        self.assertTrue(
            MODULE._has_typed_method(
                source,
                response_type="AssistantEntryResponse",
                method_name="assistantAssistantEntryViewGetAssistantEntry",
            )
        )
        self.assertTrue(
            MODULE._has_response_decoder(
                source,
                "decodeAssistantEntryResponse",
            )
        )

    def test_wrong_type_or_decoder_is_rejected(self) -> None:
        source = """
Future<assistantContracts.OtherResponse> operation() {
  return executor.send<assistantContracts.OtherResponse>(
    responseDecoder: assistantContracts.decodeOtherResponse,
  );
}
"""

        self.assertFalse(
            MODULE._has_typed_method(
                source,
                response_type="AssistantEntryResponse",
                method_name="operation",
            )
        )
        self.assertFalse(
            MODULE._has_response_decoder(
                source,
                "decodeAssistantEntryResponse",
            )
        )


if __name__ == "__main__":
    unittest.main()
