# provider_conformance: {"adapterId":"ext.push.protocol_substitute","capabilityId":"integration.push.delivery","testLayer":"user_acceptance","typedPort":"PushDeliveryPort","contractRef":"quwoquan_service/services/integration-service/contracts/external_integration/external_interaction/operations.yaml","assertionIds":["provider.auth","provider.callback_ordering","provider.idempotency","provider.network_dns","provider.observability","provider.redaction","provider.retry","provider.success","provider.throttle","provider.timeout","provider.validation","provider.push_delivery"],"command":["python3","quwoquan_ops/tests/acceptance/user_acceptance/service_ops/integration-service/ci/ext_push_protocol_substitute_provider_conformance.py"],"target":"ext-push-protocol-substitute-user-acceptance","networkBoundary":"user_journey"}
# spec_ref: specs/feature-tree/runtime/runtime-external-integration/provider-adapter-conformance-suite/spec.md#gwt-002
"""Execute the ext.push.protocol_substitute two-device Remote user journey."""
from __future__ import annotations

import sys
from pathlib import Path

sys.dont_write_bytecode = True

ROOT = Path(__file__).resolve().parents[7]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quwoquan_ops.ci.provider_conformance.native_case_result import run_native_harness

RESULT_PATH_ENV = "QWQ_PROVIDER_CONFORMANCE_RESULT_PATH"
TARGET = "ext-push-protocol-substitute-user-acceptance"
COMMAND = ("python3", "quwoquan_ops/ci/provider_conformance/run_fixture_patrol_uat.py")

if __name__ == "__main__":
    raise SystemExit(run_native_harness(command=COMMAND, target=TARGET))
