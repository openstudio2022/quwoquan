# provider_conformance: {"adapterId":"ext.auth.federated_identity_protocol_fixture","capabilityId":"identity.social.login","testLayer":"local_contract","typedPort":"FederatedIdentityPort","contractRef":"quwoquan_service/services/user-service/contracts/account/user_account/operations.yaml","assertionIds":["provider.auth","provider.callback_ordering","provider.idempotency","provider.network_dns","provider.observability","provider.redaction","provider.retry","provider.success","provider.throttle","provider.timeout","provider.validation","provider.social_identity"],"command":["python3","quwoquan_ops/tests/local_contract/service_ops/user-service/ci/ext_auth_federated_identity_protocol_fixture_provider_conformance.py"],"target":"ext-auth-federated_identity_protocol_fixture-local-contract","networkBoundary":"offline_harness"}
# spec_ref: specs/feature-tree/runtime/runtime-external-integration/provider-adapter-conformance-suite/spec.md#gwt-001
"""Execute the ext.auth.federated_identity_protocol_fixture offline native conformance suite."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[6]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quwoquan_ops.ci.provider_conformance.native_case_result import run_native_harness

RESULT_PATH_ENV = "QWQ_PROVIDER_CONFORMANCE_RESULT_PATH"
TARGET = 'ext-auth-federated_identity_protocol_fixture-local-contract'
COMMAND = ('python3', 'quwoquan_ops/ci/provider_conformance/run_generic_protocol_substitute_conformance.py')

if __name__ == "__main__":
    raise SystemExit(run_native_harness(command=COMMAND, target=TARGET))
