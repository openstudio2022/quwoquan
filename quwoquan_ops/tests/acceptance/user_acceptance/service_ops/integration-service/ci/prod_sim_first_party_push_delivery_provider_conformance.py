# provider_conformance: {"adapterId":"ext.push.protocol_substitute","capabilityId":"integration.push.delivery","testLayer":"user_acceptance","typedPort":"PushDeliveryPort","contractRef":"quwoquan_service/services/integration-service/contracts/external_integration/external_interaction/operations.yaml","assertionIds":["provider.auth","provider.callback_ordering","provider.idempotency","provider.network_dns","provider.observability","provider.redaction","provider.retry","provider.success","provider.throttle","provider.timeout","provider.validation","provider.push_delivery"],"command":["python3","quwoquan_ops/tests/acceptance/user_acceptance/service_ops/prod_sim_first_party_blackbox.py"],"target":"prod-sim-first-party-push-delivery","networkBoundary":"user_journey","prodSimFirstParty":{"service":"user-service"}}
# spec_ref: specs/feature-tree/runtime/runtime-external-integration/provider-adapter-conformance-suite/spec.md#gwt-003
"""prod-sim first-party blackbox for integration.push.delivery."""
from __future__ import annotations

# Writes QWQ_PROVIDER_CONFORMANCE_RESULT_PATH and QWQ_PROVIDER_CONFORMANCE_PROD_SIM_RESULT_PATH.
