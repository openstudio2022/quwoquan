# provider_conformance: {"adapterId":"ext.auth.carrier_one_tap","capabilityId":"identity.carrier.one_tap","testLayer":"api_integration","typedPort":"CarrierOneTapPort","contractRef":"quwoquan_service/services/user-service/contracts/account/user_account/operations.yaml","assertionIds":["provider.auth","provider.callback_ordering","provider.idempotency","provider.network_dns","provider.observability","provider.redaction","provider.retry","provider.success","provider.throttle","provider.timeout","provider.validation","provider.carrier_one_tap"],"command":["python3","quwoquan_ops/tests/acceptance/api_integration/service_ops/user-service/ci/ext_auth_carrier_one_tap_provider_conformance.py"],"target":"ext-auth-carrier_one_tap-api-integration","networkBoundary":"remote_protocol"}
# spec_ref: specs/feature-tree/runtime/runtime-external-integration/provider-adapter-conformance-suite/spec.md#gwt-001
"""Execute the ext.auth.carrier_one_tap native protocol-integration suite."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[7]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quwoquan_ops.ci.provider_conformance.native_case_result import run_native_harness

RESULT_PATH_ENV = "QWQ_PROVIDER_CONFORMANCE_RESULT_PATH"
TARGET = 'ext-auth-carrier_one_tap-api-integration'
COMMAND = ('go', '-C', 'quwoquan_service', 'test', './services/user-service/tests/api_integration/account/user_account', '-count=1')

if __name__ == "__main__":
    raise SystemExit(run_native_harness(command=COMMAND, target=TARGET))
