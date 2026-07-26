# provider_conformance: {"adapterId":"ext.auth.carrier_one_tap_protocol_fixture","capabilityId":"identity.carrier.one_tap","testLayer":"user_acceptance","typedPort":"CarrierOneTapPort","contractRef":"quwoquan_service/services/user-service/contracts/account/user_account/operations.yaml","assertionIds":["provider.auth","provider.callback_ordering","provider.idempotency","provider.network_dns","provider.observability","provider.redaction","provider.retry","provider.success","provider.throttle","provider.timeout","provider.validation","provider.carrier_one_tap"],"command":["python3","quwoquan_ops/tests/acceptance/user_acceptance/service_ops/user-service/ci/ext_auth_carrier_one_tap_protocol_fixture_provider_conformance.py"],"target":"ext-auth-carrier_one_tap_protocol_fixture-user-acceptance","networkBoundary":"user_journey"}
# spec_ref: specs/feature-tree/runtime/runtime-external-integration/provider-adapter-conformance-suite/spec.md#gwt-002
"""Execute the ext.auth.carrier_one_tap_protocol_fixture production-Remote auth journey."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[7]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quwoquan_ops.ci.provider_conformance.native_case_result import run_native_harness

RESULT_PATH_ENV = "QWQ_PROVIDER_CONFORMANCE_RESULT_PATH"
TARGET = 'ext-auth-carrier_one_tap_protocol_fixture-user-acceptance'
COMMAND = ('python3', 'quwoquan_ops/ci/provider_conformance/run_provider_patrol_uat.py', '--target', 'test/user_acceptance/patrol/user/carrier_one_tap_provider__user_acceptance_test.dart', '--platform', 'android', '--unauthenticated')

if __name__ == "__main__":
    raise SystemExit(run_native_harness(command=COMMAND, target=TARGET))
