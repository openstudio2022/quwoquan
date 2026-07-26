# provider_conformance: {"adapterId":"infra.livekit_sfu","capabilityId":"rtc.room.transport","testLayer":"local_contract","typedPort":"MediaTransportPort","contractRef":"quwoquan_service/services/rtc-service/contracts/rtc/call_session/operations.yaml","assertionIds":["provider.success","provider.validation","provider.auth","provider.network_dns","provider.timeout","provider.throttle","provider.retry","provider.idempotency","provider.callback_ordering","provider.redaction","provider.observability","provider.rtc_transport"],"command":["python3","quwoquan_ops/tests/local_contract/service_ops/rtc-service/ci/livekit_sfu_provider_conformance.py"],"target":"livekit-sfu-local-contract","networkBoundary":"offline_harness"}
# spec_ref: specs/feature-tree/runtime/runtime-external-integration/provider-adapter-conformance-suite/spec.md#gwt-001
# spec_ref: specs/feature-tree/chat-conversation/realtime-call/media-infrastructure/spec.md#gwt-004
"""Execute the LiveKit SFU adapter's offline protocol contracts."""
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
TARGET = "livekit-sfu-local-contract"
COMMAND = (
    "go",
    "-C",
    "quwoquan_service",
    "test",
    "./services/rtc-service/tests/local_contract/rtc/call_session",
    "-count=1",
)


if __name__ == "__main__":
    raise SystemExit(run_native_harness(command=COMMAND, target=TARGET))
