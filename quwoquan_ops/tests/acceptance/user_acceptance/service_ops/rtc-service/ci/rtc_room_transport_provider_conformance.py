# provider_conformance: {"adapterId":"infra.livekit_sfu","capabilityId":"rtc.room.transport","testLayer":"user_acceptance","typedPort":"MediaTransportPort","contractRef":"quwoquan_service/services/rtc-service/contracts/rtc/call_session/operations.yaml","assertionIds":["provider.success","provider.validation","provider.auth","provider.network_dns","provider.timeout","provider.throttle","provider.retry","provider.idempotency","provider.callback_ordering","provider.redaction","provider.observability","provider.rtc_transport","provider.adapter_health","provider.adapter_switch","provider.adapter_rollback"],"command":["python3","quwoquan_ops/tests/acceptance/user_acceptance/service_ops/rtc-service/ci/rtc_room_transport_provider_conformance.py"],"target":"b10-remote-rtc.room.transport","networkBoundary":"user_journey"}
# spec_ref: specs/feature-tree/chat-conversation/realtime-call/media-infrastructure/spec.md#gwt-004
# spec_ref: specs/feature-tree/chat-conversation/realtime-call/one-to-one-call/spec.md#gwt-003
"""Run the real-device Prod Remote UAT for LiveKit transport."""
from __future__ import annotations

import os
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[7]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quwoquan_ops.ci.provider_conformance import b10_prod_remote_uat


RESULT_PATH_ENV = "QWQ_PROVIDER_CONFORMANCE_RESULT_PATH"


def main() -> int:
    if not os.environ.get(RESULT_PATH_ENV):
        return 1
    return b10_prod_remote_uat.run("rtc.room.transport", "infra.livekit_sfu")


if __name__ == "__main__":
    raise SystemExit(main())
