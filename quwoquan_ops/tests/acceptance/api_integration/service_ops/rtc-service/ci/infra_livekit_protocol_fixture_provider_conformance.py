# provider_conformance: {"adapterId":"infra.livekit_protocol_fixture","capabilityId":"rtc.room.transport","testLayer":"api_integration","typedPort":"MediaTransportPort","contractRef":"quwoquan_service/services/rtc-service/contracts/rtc/call_session/operations.yaml","assertionIds":["provider.auth","provider.callback_ordering","provider.idempotency","provider.network_dns","provider.observability","provider.redaction","provider.retry","provider.success","provider.throttle","provider.timeout","provider.validation","provider.rtc_transport"],"command":["python3","quwoquan_ops/tests/acceptance/api_integration/service_ops/rtc-service/ci/infra_livekit_protocol_fixture_provider_conformance.py"],"target":"infra-livekit_protocol_fixture-api-integration","networkBoundary":"remote_protocol"}
# spec_ref: specs/feature-tree/runtime/runtime-external-integration/provider-adapter-conformance-suite/spec.md#gwt-001
"""Execute the infra.livekit_protocol_fixture native protocol-integration suite."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[7]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quwoquan_ops.ci.provider_conformance.native_case_result import run_native_harness

RESULT_PATH_ENV = "QWQ_PROVIDER_CONFORMANCE_RESULT_PATH"
TARGET = 'infra-livekit_protocol_fixture-api-integration'
COMMAND = ('go', '-C', 'quwoquan_service', 'test', './services/rtc-service/tests/api_integration/rtc/call_session', '-count=1')

if __name__ == "__main__":
    raise SystemExit(run_native_harness(command=COMMAND, target=TARGET))
