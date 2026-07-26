# provider_conformance: {"adapterId":"ext.sms.local_capture","capabilityId":"identity.sms.otp","testLayer":"api_integration","typedPort":"SmsDeliveryPort","contractRef":"quwoquan_service/services/integration-service/contracts/external_integration/external_interaction/operations.yaml","assertionIds":["provider.auth","provider.callback_ordering","provider.idempotency","provider.network_dns","provider.observability","provider.redaction","provider.retry","provider.success","provider.throttle","provider.timeout","provider.validation","provider.sms_delivery"],"command":["python3","quwoquan_ops/tests/acceptance/api_integration/service_ops/integration-service/ci/ext_sms_local_capture_provider_conformance.py"],"target":"ext-sms-local_capture-api-integration","networkBoundary":"remote_protocol"}
# spec_ref: specs/feature-tree/runtime/runtime-external-integration/provider-adapter-conformance-suite/spec.md#gwt-001
"""Execute the ext.sms.local_capture native protocol-integration suite."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[7]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quwoquan_ops.ci.provider_conformance.native_case_result import run_native_harness

RESULT_PATH_ENV = "QWQ_PROVIDER_CONFORMANCE_RESULT_PATH"
TARGET = 'ext-sms-local_capture-api-integration'
COMMAND = ('go', '-C', 'quwoquan_service', 'test', './services/integration-service/tests/api_integration/external_integration/external_interaction', '-count=1')

if __name__ == "__main__":
    raise SystemExit(run_native_harness(command=COMMAND, target=TARGET))
