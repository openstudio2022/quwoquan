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
                transport="json",
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
                transport="json",
            )
        )
        self.assertFalse(
            MODULE._has_response_decoder(
                source,
                "decodeAssistantEntryResponse",
            )
        )

    def test_sse_operation_requires_a_typed_stream_method(self) -> None:
        source = """
Stream<assistantContracts.AssistantStreamEventWire>
assistantAssistantRunStreamAssistantRunEvents(
  assistantContracts.AssistantRunEventStreamQuery request,
) {
  return executor.stream<assistantContracts.AssistantStreamEventWire>(
    responseDecoder: assistantContracts.decodeAssistantStreamEventWire,
  );
}
"""

        self.assertTrue(
            MODULE._has_typed_method(
                source,
                response_type="AssistantStreamEventWire",
                method_name="assistantAssistantRunStreamAssistantRunEvents",
                transport="sse",
            )
        )
        self.assertFalse(
            MODULE._has_typed_method(
                source,
                response_type="AssistantStreamEventWire",
                method_name="assistantAssistantRunStreamAssistantRunEvents",
                transport="json",
            )
        )

    def test_sse_operation_rejects_a_future_method(self) -> None:
        source = """
Future<assistantContracts.AssistantStreamEventWire>
assistantAssistantRunStreamAssistantRunEvents(
  assistantContracts.AssistantRunEventStreamQuery request,
) async => throw UnimplementedError();
"""

        self.assertFalse(
            MODULE._has_typed_method(
                source,
                response_type="AssistantStreamEventWire",
                method_name="assistantAssistantRunStreamAssistantRunEvents",
                transport="sse",
            )
        )

    def test_upgrade_operation_requires_descriptor_and_canonical_encoder(self) -> None:
        source = """
abstract final class AppCloudOperationUpgradeDescriptors {
  static final CloudOperationUpgradeDescriptor<realtimeContracts.WebSocketUpgradeRequest>
      realtimeConnectionWebSocketUpgrade =
      CloudOperationUpgradeDescriptor<realtimeContracts.WebSocketUpgradeRequest>(
        operation: appCloudOperationContracts[AppCloudOperationIds.realtimeConnectionWebSocketUpgrade]!,
        requestEncoder: realtimeContracts.encodeRealtimeConnectionWebSocketUpgradeGeneratedRequest,
      );
}
"""

        self.assertTrue(
            MODULE._has_typed_upgrade_descriptor(
                source,
                request_type="WebSocketUpgradeRequest",
                method_name="realtimeConnectionWebSocketUpgrade",
                request_encoder=(
                    "encodeRealtimeConnectionWebSocketUpgradeGeneratedRequest"
                ),
            )
        )

    def test_upgrade_descriptor_rejects_wrong_encoder_or_dummy_future(self) -> None:
        descriptor = """
static final CloudOperationUpgradeDescriptor<
  realtimeContracts.WebSocketUpgradeRequest
> realtimeConnectionWebSocketUpgrade = CloudOperationUpgradeDescriptor<
  realtimeContracts.WebSocketUpgradeRequest
>(
  operation: appCloudOperationContracts[
    AppCloudOperationIds.realtimeConnectionWebSocketUpgrade
  ]!,
  requestEncoder: realtimeContracts.encodeWrongRequest,
);
"""
        dummy = """
Future<void> realtimeConnectionWebSocketUpgrade(
  realtimeContracts.WebSocketUpgradeRequest request,
) async {}
"""

        self.assertFalse(
            MODULE._has_typed_upgrade_descriptor(
                descriptor,
                request_type="WebSocketUpgradeRequest",
                method_name="realtimeConnectionWebSocketUpgrade",
                request_encoder=(
                    "encodeRealtimeConnectionWebSocketUpgradeGeneratedRequest"
                ),
            )
        )
        self.assertTrue(
            MODULE._has_typed_method(
                dummy,
                response_type="void",
                method_name="realtimeConnectionWebSocketUpgrade",
                transport="json",
            )
        )


if __name__ == "__main__":
    unittest.main()
