# provider_conformance: {"adapterId":"ext.obs.elasticsearch","capabilityId":"runtime.log.sink","testLayer":"user_acceptance","typedPort":"RuntimeLogSinkPort","contractRef":"quwoquan_service/services/product-ops-service/contracts/product_ops/event_record/operations.yaml","assertionIds":["provider.auth","provider.callback_ordering","provider.idempotency","provider.network_dns","provider.observability","provider.redaction","provider.retry","provider.success","provider.throttle","provider.timeout","provider.validation","provider.observability_log_sink"],"command":["python3","quwoquan_ops/tests/acceptance/user_acceptance/service_ops/prod_sim_first_party_blackbox.py"],"target":"prod-sim-first-party-runtime-log","networkBoundary":"user_journey","prodSimFirstParty":{"service":"product-ops-service"}}
# spec_ref: specs/feature-tree/runtime/runtime-external-integration/provider-adapter-conformance-suite/spec.md#gwt-003
"""prod-sim first-party blackbox for runtime.log.sink."""
from __future__ import annotations

# Writes QWQ_PROVIDER_CONFORMANCE_RESULT_PATH and QWQ_PROVIDER_CONFORMANCE_PROD_SIM_RESULT_PATH.
