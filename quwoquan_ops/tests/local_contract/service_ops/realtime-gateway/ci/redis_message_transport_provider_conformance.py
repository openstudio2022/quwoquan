# provider_conformance: {"adapterId":"infra.redis.message_transport","capabilityId":"runtime.message.transport","testLayer":"local_contract","typedPort":"MessageTransportPort","contractRef":"quwoquan_service/services/chat-service/contracts/chat/conversation/operations.yaml","assertionIds":["provider.success","provider.validation","provider.auth","provider.network_dns","provider.timeout","provider.throttle","provider.retry","provider.idempotency","provider.callback_ordering","provider.redaction","provider.observability","provider.redis_message_transport"],"command":["python3","quwoquan_ops/tests/local_contract/service_ops/realtime-gateway/ci/redis_message_transport_provider_conformance.py"],"target":"redis-message-transport-local-contract","networkBoundary":"offline_harness"}
# spec_ref: specs/feature-tree/runtime/runtime-external-integration/provider-adapter-conformance-suite/spec.md#gwt-001
# spec_ref: specs/feature-tree/gateway-orchestrator-foundation/realtime-gateway/realtime-channel-delivery/spec.md#gwt-002
"""Execute the production Redis message-transport offline contracts."""
from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[6]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quwoquan_ops.ci.provider_conformance.native_case_result import (
    run_native_harness,
)


RESULT_PATH_ENV = "QWQ_PROVIDER_CONFORMANCE_RESULT_PATH"
TARGET = "redis-message-transport-local-contract"
COMMAND = (
    "go",
    "-C",
    "quwoquan_service",
    "test",
    "./runtime/messaging",
    "-count=1",
)


if __name__ == "__main__":
    raise SystemExit(run_native_harness(command=COMMAND, target=TARGET))
