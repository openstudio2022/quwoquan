# provider_conformance: {"adapterId":"infra.redis.message_transport","capabilityId":"runtime.message.transport","testLayer":"user_acceptance","typedPort":"MessageTransportPort","contractRef":"quwoquan_service/services/chat-service/contracts/chat/conversation/operations.yaml","assertionIds":["provider.success","provider.validation","provider.auth","provider.network_dns","provider.timeout","provider.throttle","provider.retry","provider.idempotency","provider.callback_ordering","provider.redaction","provider.observability","provider.redis_message_transport","provider.adapter_health","provider.adapter_switch","provider.adapter_rollback"],"command":["python3","quwoquan_ops/tests/acceptance/user_acceptance/service_ops/realtime-gateway/ci/message_transport_provider_conformance.py"],"target":"provider-remote-runtime.message.transport","networkBoundary":"user_journey"}
# spec_ref: specs/feature-tree/chat-conversation/realtime-call/one-to-one-call/spec.md#gwt-003
# spec_ref: specs/feature-tree/runtime/runtime-external-integration/provider-adapter-conformance-suite/spec.md#gwt-002
"""Run the real-device Prod Remote UAT for durable realtime transport."""
from __future__ import annotations

import os
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[7]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quwoquan_ops.ci.provider_conformance import run_prod_remote_uat


RESULT_PATH_ENV = "QWQ_PROVIDER_CONFORMANCE_RESULT_PATH"


def main() -> int:
    if not os.environ.get(RESULT_PATH_ENV):
        return 1
    return run_prod_remote_uat.run(
        "runtime.message.transport",
        "infra.redis.message_transport",
    )


if __name__ == "__main__":
    raise SystemExit(main())
