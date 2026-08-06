# provider_conformance: {"adapterId":"infra.redis.message_transport_fixture","capabilityId":"runtime.message.transport","testLayer":"user_acceptance","typedPort":"MessageTransportPort","contractRef":"quwoquan_service/services/chat-service/contracts/chat/conversation/operations.yaml","assertionIds":["provider.auth","provider.callback_ordering","provider.idempotency","provider.network_dns","provider.observability","provider.redaction","provider.retry","provider.success","provider.throttle","provider.timeout","provider.validation","provider.redis_message_transport"],"command":["python3","quwoquan_ops/tests/acceptance/user_acceptance/service_ops/realtime-gateway/ci/infra_redis_message_transport_fixture_provider_conformance.py"],"target":"infra-redis-message_transport_fixture-user-acceptance","networkBoundary":"user_journey"}
# spec_ref: specs/feature-tree/runtime/runtime-external-integration/provider-adapter-conformance-suite/spec.md#gwt-002
"""Execute the infra.redis.message_transport_fixture two-device Remote user journey."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[7]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quwoquan_ops.ci.provider_conformance.native_case_result import run_native_harness

RESULT_PATH_ENV = "QWQ_PROVIDER_CONFORMANCE_RESULT_PATH"
TARGET = 'infra-redis-message_transport_fixture-user-acceptance'
COMMAND = ('python3', 'quwoquan_ops/ci/provider_conformance/run_fixture_patrol_uat.py')

if __name__ == "__main__":
    raise SystemExit(run_native_harness(command=COMMAND, target=TARGET))
