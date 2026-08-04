# provider_conformance: {"adapterId":"ext.push.protocol_substitute","capabilityId":"integration.push.delivery","testLayer":"local_contract","typedPort":"PushDeliveryPort","contractRef":"quwoquan_service/services/integration-service/contracts/external_integration/external_interaction/operations.yaml","assertionIds":["provider.success","provider.validation","provider.auth","provider.network_dns","provider.timeout","provider.throttle","provider.retry","provider.idempotency","provider.callback_ordering","provider.redaction","provider.observability","provider.push_delivery"],"command":["python3","quwoquan_ops/tests/local_contract/service_ops/integration-service/ci/push_protocol_substitute_provider_conformance.py"],"target":"push-protocol-substitute-local-contract","networkBoundary":"offline_harness"}
# spec_ref: specs/feature-tree/runtime/runtime-external-integration/provider-adapter-conformance-suite/spec.md#gwt-001
"""Execute the external protocol-substitute PushDeliveryPort contract suite."""
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
TARGET = "push-protocol-substitute-local-contract"
COMMAND = (
    "go",
    "-C",
    "quwoquan_service",
    "test",
    "./services/integration-service/tests/local_contract/external_integration/push_delivery",
    "-count=1",
)


if __name__ == "__main__":
    raise SystemExit(run_native_harness(command=COMMAND, target=TARGET))
