# provider_conformance: {"adapterId":"ext.auth.carrier_one_tap_protocol_fixture","capabilityId":"identity.carrier.one_tap","testLayer":"user_acceptance","typedPort":"CarrierOneTapPort","contractRef":"quwoquan_service/services/user-service/contracts/account/user_account/operations.yaml","assertionIds":["provider.auth","provider.callback_ordering","provider.idempotency","provider.network_dns","provider.observability","provider.redaction","provider.retry","provider.success","provider.throttle","provider.timeout","provider.validation","provider.carrier_one_tap"],"command":["python3","quwoquan_ops/tests/acceptance/user_acceptance/service_ops/prod_sim_first_party_blackbox.py"],"target":"prod-sim-first-party-carrier-one-tap","networkBoundary":"user_journey","prodSimFirstParty":{"service":"user-service"}}
# spec_ref: specs/feature-tree/runtime/runtime-external-integration/provider-adapter-conformance-suite/spec.md#gwt-003
"""prod-sim first-party blackbox for identity.carrier.one_tap."""
from __future__ import annotations

# Writes QWQ_PROVIDER_CONFORMANCE_RESULT_PATH and QWQ_PROVIDER_CONFORMANCE_PROD_SIM_RESULT_PATH.
